"""
game_logic.py — pure game rules for Beat-Draw Showdown (no Bluetooth, no graphics).

A full MATCH has 3 levels:
    Level 1  Cowboy       rhythm + quick-draw, best of 3 draws      (winner: +1 HP in Level 2)
    Level 2  Spellcaster  real-time spell duel with HP and mana     (HP left sets Level 3 start)
    Level 3  Combo Clash  memorise a 3-spell combo, cast it back    (winner = match winner)

Keep these constants in sync with firmware/BeatDrawBlaster/config.h.
Everything here is unit-tested in tests/test_game_logic.py.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Optional

BEATS_PER_ROUND = 16          # v5.7: 16-beat rounds (was 8)
COUNT_IN_BEATS = 4
MAX_BULLETS = 6
HIT_WINDOW_MS = 150
PERFECT_MS = 60               # |timing error| up to this = PERFECT, up to HIT_WINDOW_MS = GOOD (v5.7)
BULLET_BONUS_MS = 25          # each loaded bullet shaves 25 ms off your draw time
BATT_LOW_PCT = 20             # battery at or below this = red warning (also in config.h)

# Why a wand last (re)started - 4th field of its V packet (firmware readResetCause(), v5)
RESET_CAUSES = {"P": "power on", "B": "BROWN-OUT (battery low or loose wire)", "W": "WATCHDOG (wand froze)",
                "R": "reset button", "S": "software reset"}


def parse_version(info: str) -> dict:
    """'5.0,BDS-1,0,W' -> {'version': '5.0', 'name': 'BDS-1', 'buzzer': '0', 'reset': 'W'}"""
    parts = (info.split(",") + ["", "", "", ""])[:4]
    return {"version": parts[0], "name": parts[1], "buzzer": parts[2], "reset": parts[3] or None}
MIN_HUMAN_REACTION_MS = 100   # faster than this = you guessed -> counts as a foul
DRAW_TIMEOUT_MS = 3000

# 16-beat air-drum patterns of ARROWS (v5.7, was 8): flick the wand tip U = up, D = down, L = left, R = right;
# - = rest. Every pattern has 8 notes (one every 2 beats on average); each correct note loads a bullet, up to
# MAX_BULLETS = 6, so you can miss 2 and still be fully loaded. Beat 1 is never a rest, never more than 3 notes
# or 3 rests in a row.
# The patterns get harder each round (random_pattern):
#   round 1   only UP and DOWN
#   round 2   UP and DOWN + one or two LEFT / RIGHT
#   round 3+  all four directions mixed (each one at least once)
DIRECTIONS = "UDLR"
# Cowboy tutorial (before Level 1, no timer): learn the 4 arrows -> a slow practice beat -> holster practice
# (freeze for CTUT_STILL_S with a live stillness meter) -> one practice draw. None of it counts.
CTUT_BPM = 70                 # v5.7 (was 80): practice is slower than NORMAL (90)
CTUT_PATTERN = "U-D-L-R-"
CTUT_STILL_S = 3.0
STILL_FOUL = 10               # s<n> from the wand: 10 = moving as much as FOUL_THRESHOLD_G
FLICK_TIP = "Flick just the TIP, quick - like cracking a whip"
DIRECTION_NAMES = {"U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT"}
NOTES_PER_ROUND = 8


def pattern_ok(p: str, round_no: int) -> bool:
    notes = [c for c in p if c != "-"]
    if len(p) != BEATS_PER_ROUND or len(notes) != NOTES_PER_ROUND or p[0] == "-":
        return False
    if re.search(r"[UDLR]{4}", p) or "----" in p:       # keep it groovy: no long runs of notes or rests
        return False
    side = sum(c in "LR" for c in notes)
    if round_no <= 1:
        return side == 0 and set(notes) == set("UD")
    if round_no == 2:
        return 1 <= side <= 2 and "U" in notes and "D" in notes
    return set(notes) == set(DIRECTIONS)


def random_pattern(rng: random.Random | None = None, round_no: int = 3) -> str:
    """e.g. round 1 'U-DU--D-UD--U-D-', round 3+ 'UL-D--RU-D-L--R-' (16 beats, 8 notes)."""
    rng = rng or random
    while True:
        rests = rng.sample(range(1, BEATS_PER_ROUND), BEATS_PER_ROUND - NOTES_PER_ROUND)
        pool = "UD" if round_no <= 1 else ("UDUDLR" if round_no == 2 else DIRECTIONS)
        p = "".join("-" if k in rests else rng.choice(pool) for k in range(BEATS_PER_ROUND))
        if pattern_ok(p, round_no):
            return p


def drum_packet(bpm: int, pattern: str) -> str:
    """Laptop -> wand: start the air-drum. v5.7 format R<3-digit bpm><pattern>, e.g. 'R090U-DU--D-UD--U-D-'
    (exactly 20 bytes for a 16-beat round - the old 'R120,' comma format no longer fits)."""
    return f"R{int(bpm):03d}{pattern}"


def hit_rating(ok: bool, err_ms: int) -> str:
    """PERFECT / GOOD / MISS for the popup over the hit line."""
    if not ok:
        return "MISS"
    return "PERFECT" if abs(err_ms) <= PERFECT_MS else "GOOD"


def judge_hit(rel_ms: float, gesture: str, pattern: str, beat_ms: float,
              used: list[bool]) -> tuple[int, bool, int]:
    """Mirror of judgeHit() in the firmware.

    rel_ms: time of the hit relative to beat 0 (after the count-in).
    Returns (beat_index, ok, error_ms). beat_index is -1 if outside the 8 beats.
    """
    half = beat_ms / 2
    if rel_ms < -half:
        return -1, False, 0
    k = int((rel_ms + half) // beat_ms)
    if k < 0 or k >= len(pattern):
        return -1, False, 0
    err = int(round(rel_ms - k * beat_ms))
    ok = abs(err) <= HIT_WINDOW_MS and pattern[k] == gesture and not used[k]
    if ok:
        used[k] = True
    return k, ok, err


@dataclass
class PlayerRound:
    """Everything the referee learns about one player during one round."""
    bullets: int = 0
    hits: dict = field(default_factory=dict)   # beat index -> True (hit) / False (miss)
    fouled: bool = False
    draw_us: Optional[int] = None              # raw time measured on the blaster
    no_draw: bool = False
    latency_ms: float = 0.0                    # one-way BLE latency estimate

    def corrected_draw_ms(self, mean_latency_ms: float) -> Optional[float]:
        """Reaction time measured from when the *laptop* played "DRAW!".

        The blaster starts its stopwatch when the G packet arrives, which is
        latency_ms after the laptop sent it. The laptop plays the sound
        mean_latency_ms after sending. So:
            reaction = blaster_time + (my_latency - mean_latency)
        """
        if self.draw_us is None:
            return None
        return self.draw_us / 1000.0 + (self.latency_ms - mean_latency_ms)


@dataclass
class RoundResult:
    winner: Optional[int]          # 0, 1 or None (tie)
    reason: str
    effective_ms: list            # [p1, p2] — None if no valid draw
    corrected_ms: list
    fouls: list                   # [bool, bool]


def parse_message(msg: str) -> dict:
    """Parse a packet sent by a blaster. Unknown packets return {'type': '?'}."""
    msg = msg.strip().strip("\x00")
    if not msg:
        return {"type": "?"}
    c = msg[0]
    try:
        if c == "Q":
            return {"type": "pong"}
        if c == "H" and len(msg) >= 5:          # H<k><g><ok><err>   e.g. H3U1+12, H14L0-140 (k = 0-15)
            m = re.match(r"H(\d{1,2})([UDLRH])([01])([+-]?\d+)$", msg)
            if m:
                return {"type": "hit", "beat": int(m.group(1)), "gesture": m.group(2),
                        "ok": m.group(3) == "1", "err": int(m.group(4))}
        if c == "B":
            return {"type": "bullets", "n": int(msg[1:])}
        if c == "F":
            return {"type": "foul"}
        if c == "T":
            return {"type": "draw", "us": int(msg[1:])}
        if c == "N":
            return {"type": "no_draw"}
        if c == "V":
            return {"type": "version", "info": msg[1:]}
        # ---- Level 2 / 3 packets ----
        if c == "%":                              # %<0-100>         battery level
            return {"type": "battery", "pct": max(0, min(100, int(msg[1:])))}
        if c == "d" and len(msg) >= 2:            # d<U/D/L/R>       cowboy tutorial: a free arrow flick
            return {"type": "flick", "dir": msg[1]}
        if c == "s" and len(msg) >= 2:            # s<0-20>          cowboy tutorial: how much you moved (10 = foul line)
            return {"type": "still", "n": int(msg[1:])}
        if c == "f" and len(msg) >= 2:            # f<closest>       FIZZLE: closest spell (s = move too short)
            return {"type": "fizzle", "closest": msg[1]}
        if c == "A":                              # A<mana>          mana after a finished charge pose
            return {"type": "mana", "n": int(msg[1:])}
        if c == "C" and len(msg) >= 2 and msg[1] in SPELLS:   # C<spell><mana>  e.g. CL2
            return {"type": "cast", "spell": msg[1], "mana": int(msg[2:] or 0)}
        if c == "X" and len(msg) >= 3 and msg[1] in SPELLS:   # X<spell><us>  combo spell (us since GO)
            return {"type": "answer", "spell": msg[1], "us": int(msg[2:])}
    except ValueError:
        pass
    return {"type": "?", "raw": msg}


def decide(p: list[PlayerRound]) -> RoundResult:
    """Decide the winner of a 2-player round."""
    mean_lat = (p[0].latency_ms + p[1].latency_ms) / 2
    corrected = [pl.corrected_draw_ms(mean_lat) for pl in p]

    fouls = [pl.fouled for pl in p]
    # Anti-cheat: a "reaction" faster than humanly possible means they guessed.
    for i in range(2):
        if corrected[i] is not None and corrected[i] < MIN_HUMAN_REACTION_MS:
            fouls[i] = True

    effective = [None, None]
    for i in range(2):
        if not fouls[i] and corrected[i] is not None:
            effective[i] = corrected[i] - min(p[i].bullets, MAX_BULLETS) * BULLET_BONUS_MS

    if fouls[0] and fouls[1]:
        return RoundResult(None, "Both guns jammed!", effective, corrected, fouls)
    if fouls[0] or fouls[1]:
        w = 1 if fouls[0] else 0
        return RoundResult(w, f"P{2 - w} jumped the gun - FOUL!", effective, corrected, fouls)
    if effective[0] is None and effective[1] is None:
        return RoundResult(None, "Nobody drew!", effective, corrected, fouls)
    if effective[0] is None or effective[1] is None:
        w = 0 if effective[0] is not None else 1
        return RoundResult(w, f"P{2 - w} never drew!", effective, corrected, fouls)
    if abs(effective[0] - effective[1]) < 0.5:
        return RoundResult(None, "Dead heat!", effective, corrected, fouls)
    w = 0 if effective[0] < effective[1] else 1
    margin = abs(effective[0] - effective[1])
    return RoundResult(w, f"P{w + 1} wins by {margin:.0f} ms", effective, corrected, fouls)


def result_packet(result: RoundResult, i: int) -> str:
    """The E<outcome><ms> packet the referee sends to player i."""
    eff = result.effective_ms[i]
    ms = f"{eff:.0f}" if eff is not None else "0"
    if result.fouls[i]:
        return "EF0"
    if result.winner is None:
        return f"EX{ms}"
    return f"EW{ms}" if result.winner == i else f"EL{ms}"


# ======================================================================
#  MATCH (3 levels)
# ======================================================================
L1_WINS_NEEDED = 2            # Level 1 is best of 3 draws (ties are replayed)
L1_MAX_ROUNDS = 5             # safety cap so the demo queue keeps moving
LEVEL_INTRO_MS = 5000         # "LEVEL 2 - SPELLCASTER" intro screen (also in config.h)


def level1_bonus(wins: list[int]) -> Optional[int]:
    """Who won Level 1 (gets +1 HP in Level 2). None = nobody (equal wins)."""
    if wins[0] == wins[1]:
        return None
    return 0 if wins[0] > wins[1] else 1


def level1_done(wins: list[int], rounds_played: int) -> bool:
    return max(wins) >= L1_WINS_NEEDED or rounds_played >= L1_MAX_ROUNDS


# ======================================================================
#  LEVEL 2 — Spellcaster (real-time duel)
# ======================================================================
# Spells: L = Lightning (zig-zag), W = Water (circle), F = Fire (forward thrust)
SPELLS = "LWF"
SPELL_NAMES = {"L": "LIGHTNING", "W": "WATER", "F": "FIRE"}
# what to do better after a FIZZLE (same words as fizzleHint() in the firmware)
FIZZLE_HINTS = {"L": "zig-zag faster!", "W": "rounder circle!", "F": "thrust harder!", "s": "bigger move!"}
TUTORIAL_ORDER = "LWF"         # Level 2 spell tutorial: learn Lightning, then Water, then Fire
TUTORIAL_REPEATS = 2           # land each spell this many times to move on (no timer)
SPELL_TIPS = {"L": "Swing left-right-left FAST - 3 sharp turns",
              "W": "Draw a big round circle in the air",
              "F": "Punch the wand straight at your rival - hard!"}


class Tutorial:
    """One player's progress through the Level 2 spell tutorial (each player goes at their own pace).

    cast(spell) -> ("good", spell, count) | ("next", new_spell) | ("done", None) | ("wrong", expected) | ("over", None)
    """

    def __init__(self, order: str = TUTORIAL_ORDER, repeats: int = TUTORIAL_REPEATS):
        self.order, self.repeats = order, repeats
        self.step = 0                 # index into order (len(order) = finished)
        self.count = 0                # landed so far on this step

    @property
    def spell(self) -> Optional[str]:
        return self.order[self.step] if self.step < len(self.order) else None

    @property
    def done(self) -> bool:
        return self.step >= len(self.order)

    def cast(self, spell: str):
        if self.done:
            return ("over", None)
        if spell != self.spell:
            return ("wrong", self.spell)
        self.count += 1
        if self.count < self.repeats:
            return ("good", spell, self.count)
        self.step += 1
        self.count = 0
        return ("done", None) if self.done else ("next", self.spell)
SPELL_MOVES = {"L": "ZIG-ZAG", "W": "CIRCLE", "F": "THRUST"}
BEATS = {"L": "W", "W": "F", "F": "L"}     # key beats value: Lightning > Water > Fire > Lightning

L2_START_HP = 5
L2_BONUS_HP = 1               # Level 1 winner starts with 5 + 1
L2_DURATION_S = 60
SPELL_TRAVEL_S = 2.0          # time a spell takes to cross the arena (= your window to counter it)
SPELL_DAMAGE = 1
MAX_MANA = 3                  # also in config.h
START_MANA = 1                # also in config.h
CAST_COOLDOWN_MS = 1500       # judged on the wand (config.h); listed here for the docs/UI
CHARGE_MS = 800               # charge pose (wand at the sky) time per +1 mana - judged on the wand (config.h)


def counter_of(spell: str) -> str:
    """The spell that beats `spell`."""
    for k, v in BEATS.items():
        if v == spell:
            return k
    raise ValueError(spell)


@dataclass
class Projectile:
    owner: int                # 0 or 1
    spell: str
    t_launch: float
    alive: bool = True

    def progress(self, now: float) -> float:
        """0.0 at the caster, 1.0 when it reaches the opponent."""
        return max(0.0, min(1.0, (now - self.t_launch) / SPELL_TRAVEL_S))


class SpellDuel:
    """Pure rules for Level 2. The referee feeds it casts and the clock.

    Spells COLLIDE IN MID-AIR: when a P1 spell and a P2 spell meet on the lane
      * one beats the other  -> the loser is destroyed (BLOCK), the winner keeps flying
      * same element         -> both are destroyed (CLASH)
    It doesn't matter who cast first - Water always puts out Fire.
    A spell that reaches the opponent takes SPELL_DAMAGE HP.

    Events (from update):
      ("hit",   target, spell)
      ("block", winner_owner, destroyed_spell, where)   where = 0.0 at P1 .. 1.0 at P2
      ("clash", None, spell, where)
    """

    def __init__(self, hp=(L2_START_HP, L2_START_HP), t_start: float = 0.0,
                 duration_s: float = L2_DURATION_S):
        self.hp = list(hp)
        self.start_hp = list(hp)
        self.t_start = t_start
        self.t_end = t_start + duration_s
        self.flying: list[Projectile] = []
        self.stats = {"casts": [0, 0], "blocks": [0, 0], "hits": [0, 0]}

    def resume(self, paused_at: float, new_start: float, min_left_s: float = 15.0):
        """After a wand dropped out: keep HP and stats, clear the spells in the air, and give back
        the time that was left when the match paused (at least min_left_s)."""
        left = min(self.t_end - self.t_start, max(min_left_s, self.t_end - paused_at))   # never more than the full duel
        self.flying = []
        self.t_start = new_start
        self.t_end = new_start + left

    def time_left(self, now: float) -> float:
        return max(0.0, self.t_end - now)

    def cast(self, i: int, spell: str, now: float) -> list[tuple]:
        """Player i cast `spell`. Returns [("launch", i, spell)] (or [] if not allowed)."""
        if spell not in SPELLS or self.done(now):
            return []
        self.stats["casts"][i] += 1
        self.flying.append(Projectile(i, spell, now))
        return [("launch", i, spell)]

    @staticmethod
    def meet_time(a: Projectile, b: Projectile) -> float:
        """When two spells flying in opposite directions meet (they cover the lane together)."""
        return (a.t_launch + b.t_launch + SPELL_TRAVEL_S) / 2

    def _next_event(self, now: float):
        """The earliest collision or hit that has happened by `now`."""
        best = None
        alive = [p for p in self.flying if p.alive]
        for a in alive:
            if a.owner != 0:
                continue
            for b in alive:
                if b.owner != 1:
                    continue
                t = self.meet_time(a, b)
                # they only meet if both are still in the air at that moment
                if t <= now and t <= a.t_launch + SPELL_TRAVEL_S and t <= b.t_launch + SPELL_TRAVEL_S \
                        and t >= max(a.t_launch, b.t_launch):
                    if best is None or t < best[0]:
                        best = (t, "meet", a, b)
        for p in alive:
            t = p.t_launch + SPELL_TRAVEL_S
            if t <= now and (best is None or t < best[0]):
                best = (t, "hit", p, None)
        return best

    def update(self, now: float) -> list[tuple]:
        """Move spells, resolve mid-air collisions and hits in the order they happen."""
        events = []
        while True:
            ev = self._next_event(now)
            if ev is None:
                break
            t, kind, a, b = ev
            if kind == "hit":
                a.alive = False
                target = 1 - a.owner
                self.hp[target] = max(0, self.hp[target] - SPELL_DAMAGE)
                self.stats["hits"][a.owner] += 1
                events.append(("hit", target, a.spell))
                continue
            where = a.progress(t)                     # a = P1's spell: distance from P1
            if a.spell == b.spell:
                a.alive = b.alive = False
                events.append(("clash", None, a.spell, where))
            elif BEATS[a.spell] == b.spell:
                b.alive = False
                self.stats["blocks"][0] += 1
                events.append(("block", 0, b.spell, where))
            else:                                     # BEATS[b.spell] == a.spell
                a.alive = False
                self.stats["blocks"][1] += 1
                events.append(("block", 1, a.spell, where))
        self.flying = [p for p in self.flying if p.alive]
        return events

    def done(self, now: float) -> bool:
        return min(self.hp) <= 0 or now >= self.t_end

    def winner(self) -> Optional[int]:
        if self.hp[0] == self.hp[1]:
            return None
        return 0 if self.hp[0] > self.hp[1] else 1


def hp_packet(duel: SpellDuel, i: int, event: str = "-") -> str:
    """U<my hp>,<opponent hp>,<event>  event: H = I got hit, D = I dealt damage, B = I blocked, - = none."""
    return f"U{duel.hp[i]},{duel.hp[1 - i]},{event}"


# ======================================================================
#  LEVEL 3 — Combo Clash (beam + memory combos, no shaking)
# ======================================================================
# Each round: the arena flashes a combo of spells one by one, waits 2 s (combo hidden),
# then says GO. Both players cast the combo from memory. The most accurate combo pushes the beam
# toward the other player. Equal accuracy -> whoever finished first.
# pos is the clash point from P1's point of view: 0 = P1 loses, 100 = P1 wins.
BEAM_START = 50
BEAM_HP_SHIFT = 5             # each HP of difference after Level 2 moves the start 5 toward the weaker player
BEAM_MAX_SHIFT = 15
COMBO_LEN = 3                 # spells per round. Round 1 = 3 DIFFERENT spells; from round 2 a spell repeats (WFW)
COMBO_FINAL_LEN = 5           # the final round (and sudden death) = 5 spells in a row - the decider
COMBO_FLASH_S = [0.9, 0.8, 0.7, 0.6, 0.5]   # how long each spell flashes, per round (gets faster; last value repeats)
COMBO_FINAL_FLASH_S = 0.6     # 5-spell rounds flash a little slower
COMBO_WAIT_S = 2.0            # combo hidden, then GO
COMBO_INPUT_S = 7.0           # time to cast a 3-spell combo after GO...
COMBO_INPUT_PER_SPELL_S = 1.8  # ...plus this for each extra spell (5 spells = 10.6 s)
COMBO_GRACE_S = 0.3           # after one player finishes, wait this long for the other's last packet
COMBO_WIN_PUSH = 10           # pushing for winning the round...
COMBO_POINT_PUSH = 10         # ...plus this per extra correct spell over the rival (3 vs 0 = 40)
L3_MAX_ROUNDS = 6             # then whoever is ahead wins
SUDDEN_DEATH_MAX = 3          # still exactly level -> up to 3 extra rounds
MIN_SPELL_MS = 150            # a spell "cast" faster than this after GO = it started before GO


def beam_start_pos(hp: list[int]) -> float:
    shift = BEAM_HP_SHIFT * (hp[0] - hp[1])
    return BEAM_START + max(-BEAM_MAX_SHIFT, min(BEAM_MAX_SHIFT, shift))


def my_beam_pos(pos: float, i: int) -> int:
    """Position from player i's point of view (100 = I win). Sent as b<pos>."""
    return int(round(pos if i == 0 else 100 - pos))


def combo_len(round_no: int) -> int:
    """3 spells, or 5 in the final round and sudden death."""
    return COMBO_FINAL_LEN if round_no >= L3_MAX_ROUNDS else COMBO_LEN


def combo_ok(combo: str, mixed: bool) -> bool:
    """Never the same spell 3 times in a row. 3-spell rounds: round 1 all different, later rounds MUST
    repeat a spell (that's what makes them harder to remember)."""
    if any(combo[k] == combo[k - 1] == combo[k - 2] for k in range(2, len(combo))):
        return False
    if len(combo) == 3:
        return (len(set(combo)) < 3) if mixed else (len(set(combo)) == 3)
    return len(set(combo)) >= 2


def random_combo(rng: random.Random | None = None, length: int = COMBO_LEN, mixed: bool = False) -> str:
    """mixed=False: 3 DIFFERENT spells, e.g. 'FLW'. mixed=True: repeats allowed, e.g. 'WFW' or 'FWWLF'."""
    rng = rng or random
    while True:
        if not mixed and length == 3:
            letters = list(SPELLS)
            rng.shuffle(letters)
            combo = "".join(letters)
        else:
            combo = "".join(rng.choice(SPELLS) for _ in range(length))
        if combo_ok(combo, mixed):
            return combo


def flash_s(round_no: int) -> float:
    """Flash time per spell for round 1, 2, 3, ... (5-spell rounds: COMBO_FINAL_FLASH_S)."""
    if combo_len(round_no) > COMBO_LEN:
        return COMBO_FINAL_FLASH_S
    return COMBO_FLASH_S[min(round_no - 1, len(COMBO_FLASH_S) - 1)]


def combo_input_s(length: int) -> float:
    return COMBO_INPUT_S + COMBO_INPUT_PER_SPELL_S * max(0, length - COMBO_LEN)


def combo_correct(target: str, cast: str) -> int:
    """How many spells are right AND in the right place."""
    return sum(1 for k, c in enumerate(cast[:len(target)]) if c == target[k])


@dataclass
class ComboEntry:
    """What one player cast after GO: spells in order + latency-corrected ms since GO for each."""
    length: int = COMBO_LEN
    spells: str = ""
    times_ms: list = field(default_factory=list)

    def add(self, spell: str, ms: float) -> bool:
        if len(self.spells) >= self.length or ms < MIN_SPELL_MS and not self.spells:
            return False
        self.spells += spell
        self.times_ms.append(ms)
        return True

    @property
    def done(self) -> bool:
        return len(self.spells) >= self.length

    @property
    def finish_ms(self) -> Optional[float]:
        return self.times_ms[-1] if self.done else None


class BeamClash:
    def __init__(self, start_pos: float = BEAM_START):
        self.pos = float(start_pos)
        self.start_pos = float(start_pos)
        self.rounds_won = [0, 0]
        self.perfect = [0, 0]                 # rounds with every spell right

    def _move(self, i: int, amount: float):
        self.pos += amount * (1 if i == 0 else -1)
        self.pos = max(0.0, min(100.0, self.pos))

    def resolve_combo(self, target: str, entries: list[ComboEntry]) -> tuple[Optional[int], int, list[int]]:
        """Score a round. Returns (round winner or None, how far the beam moved, [correct per player])."""
        n = len(target)
        correct = [combo_correct(target, e.spells) for e in entries]
        for i in range(2):
            if correct[i] == n:
                self.perfect[i] += 1
        if correct[0] != correct[1]:
            w = 0 if correct[0] > correct[1] else 1
        elif correct[0] == 0:
            return None, 0, correct                    # nobody got anything right
        else:                                          # same accuracy: who finished first?
            f = [e.times_ms[min(len(e.times_ms), n) - 1] if e.times_ms else None for e in entries]
            if f[0] is None or f[1] is None or abs(f[0] - f[1]) < 1:
                return None, 0, correct
            w = 0 if f[0] < f[1] else 1
        push = COMBO_WIN_PUSH + COMBO_POINT_PUSH * (correct[w] - correct[1 - w])
        self._move(w, push)
        self.rounds_won[w] += 1
        return w, push, correct

    def winner(self) -> Optional[int]:
        if self.pos >= 100:
            return 0
        if self.pos <= 0:
            return 1
        return None

    def leader(self) -> Optional[int]:
        if abs(self.pos - 50) < 1e-9:
            return None
        return 0 if self.pos > 50 else 1


def level_packet(outcome_for_me: Optional[bool], level: int) -> str:
    """Y<o><level>: o = W (won the level), L (lost), X (tie)."""
    o = "X" if outcome_for_me is None else ("W" if outcome_for_me else "L")
    return f"Y{o}{level}"
