"""
arena_referee.py — the laptop "Arena" for Beat-Draw Showdown (ICT1011).

The laptop is the referee: it connects to two TinyScreen+ wands over
Bluetooth, plays the music and cues, shows a big split screen for the class,
and decides the winner.

A MATCH (about 3 minutes) has 3 levels:
    Level 1  COWBOY       air-drum to load bullets, holster, quick-draw. Best of 3 draws.
    Level 2  SPELLCASTER  60 s real-time spell duel. Level 1 winner starts with +1 HP.
    Level 3  COMBO CLASH  3 spells flash, 2 s wait, cast the combo back from memory. The most accurate
                          combo pushes the beam. HP left after Level 2 sets the start. Winner = champion.

Run (Windows, from the pc folder):
    python arena_referee.py                       # full match, real wands BDS-1 vs BDS-2
    python arena_referee.py --level 2             # practise only Level 2 (or 1 or 3)
    python arena_referee.py --names BDS-3 BDS-4   # use spare wands
    python arena_referee.py --sim                 # no hardware: keyboard players
    python arena_referee.py --sim --bot2          # you (keyboard) vs a bot
    python arena_referee.py --sim --bots --auto   # watch two bots play
    python arena_referee.py --sim --bots --auto --fast --matches 3   # 3 matches in a few seconds (test)

Keys:
    SPACE start / next      N skip to next level      L back to lobby
    C re-measure latency    F11 fullscreen            ESC quit
    Sim players:
        P1  A snare/charge  S hi-hat/charge  D draw/charge   Q lightning  W water  E fire
        P2  J snare/charge  K hi-hat/charge  L draw/charge   U lightning  I water  O fire
        (in Level 2 one press of A/S/D = one finished charge pose, at most one per 0.8 s)
    (in --sim mode use BACKSPACE for the lobby, because L is P2's draw key)
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import datetime as dt
import os
import queue
import random
import statistics
import sys
import time

from game_logic import (BATT_LOW_PCT, BEATS_PER_ROUND, BULLET_BONUS_MS, drum_packet, hit_rating, PERFECT_MS, COMBO_GRACE_S, COMBO_INPUT_S, COMBO_LEN,
                        COMBO_WAIT_S, COUNT_IN_BEATS, DRAW_TIMEOUT_MS, HIT_WINDOW_MS, L1_MAX_ROUNDS, L1_WINS_NEEDED,
                        L2_BONUS_HP, L2_START_HP, L3_MAX_ROUNDS, LEVEL_INTRO_MS, MAX_BULLETS, MAX_MANA, SPELL_NAMES,
                        START_MANA, SUDDEN_DEATH_MAX, BeamClash, ComboEntry, PlayerRound, SpellDuel, beam_start_pos,
                        combo_correct, decide, flash_s, hp_packet, level1_bonus, level1_done, level_packet,
                        my_beam_pos, parse_message, parse_version, random_combo, random_pattern, result_packet,
                        DIRECTION_NAMES, CTUT_BPM, CTUT_PATTERN, CTUT_STILL_S, FLICK_TIP, STILL_FOUL,
                        combo_input_s, combo_len,
                        FIZZLE_HINTS, RESET_CAUSES, SPELL_TIPS, Tutorial)
from menu import MOVES, Menu
from store import HallOfFame, Settings

W, H = 1280, 720
BG = (20, 17, 15)
INK = (240, 232, 220)
MUTED = (140, 130, 120)
GOLD = (245, 190, 60)
GREEN = (80, 200, 120)
RED = (230, 70, 60)
P_COLORS = [(235, 110, 70), (70, 190, 230)]
SPELL_COLORS = {"L": (250, 220, 60), "W": (70, 150, 250), "F": (250, 110, 40)}
P_MAIN_RGB = [(255, 140, 80), (90, 190, 255)]   # beam colours
BEATS_INV = {"W": "L", "F": "W", "L": "F"}   # spell -> the spell that beats it
LEVEL_TITLES = {1: "LEVEL 1 - COWBOY", 2: "LEVEL 2 - SPELLCASTER", 3: "LEVEL 3 - COMBO CLASH"}
LEVEL_RULES = {
    1: ["AIR DRUM: flick the wand tip the way the ARROW points as it hits the line = 1 bullet",
        "HOLSTER: freeze! Moving before DRAW = FOUL",
        "DRAW!: flick fastest - each bullet shaves 25 ms off your time"],
    2: ["Point your wand at the SKY and hold still = charge mana (max 3)",
        "Release + ZIG-ZAG = Lightning   CIRCLE = Water   THRUST = Fire",
        "Lightning > Water > Fire > Lightning  -  spells collide mid-air: the stronger one wins!"],
    3: ["WATCH: the spells flash one by one - remember the order! (they can repeat)",
        "Wait 2 s... then GO: cast the same combo with your wand.  FINAL ROUND = 5 spells!",
        "Most right spells (or fastest if equal) pushes the beam - reach your rival to win"],
}

PINGS_NEEDED = 10
HOLSTER_S = 1.5
STANDOFF_MIN_S, STANDOFF_MAX_S = 1.5, 4.5
MATCH_INTRO_S = 4.0         # "Level one... Round one!" before the first Level 1 round
ANN_VOL = 1.0                # announcer volume
RESULT_S = 4.0               # pause between Level 1 rounds in a match (the draw replay plays here)
REPLAY_S = 1.4               # Level 1 result: the two reaction-time bars race for this long
RESUME_DELAY_S = 1.5         # both wands back + latency measured -> wait this long, then carry on
NAME_MAX = 10                # longest player name typed in the lobby
# clickable buttons outside the menu (mouse)
END_BUTTONS = {"again": (440, 600, 190, 44), "menu": (650, 600, 190, 44)}   # after a match / practice level
SKIP_BUTTON = (560, 600, 160, 44)                                           # spell tutorial
LEVEL_RESULT_S = 4.0
ROUND_PAUSE_S = 1.5          # Level 3: "ROUND n" before the combo flashes
SCORE_S = 2.5                # Level 3: show who pushed before the next round
# Level 3 hype audio
MUSIC_VOL, MUSIC_DUCKED = 0.55, 0.2   # battle music volume normally / while the combo flashes
CROWD_VOL, CROWD_HYPE_VOL = 0.22, 0.5  # recorded crowd loop under the music / when someone is overpowering
HYPE_ZONE = 30               # beam within 20 of an end (|pos - 50| >= 30) = danger zone: crowd + surge
HYPE_S = 1.6                 # how long a hype line stays on screen


class Referee:
    def __init__(self, args, link, events, sounds, clock=time.perf_counter):
        self.args = args
        self.link = link
        self.events = events
        self.sounds = sounds
        self.clock = clock
        self.names = args.names
        self.rng = random.Random(args.seed)
        self.state = "LOBBY"
        self.state_t = clock()
        self.status = ["waiting", "waiting"]
        self.connected = [False, False]
        self.latency = [None, None]          # one-way ms
        self.battery = [None, None]          # % reported by each wand (None = not heard yet)
        self.batt_warned = [False, False]
        self.rtts = [[], []]
        self.ping_sent = [None, None]
        self.next_ping = [0.0, 0.0]
        self.flash = [(0.0, ""), (0.0, "")]  # (time, text) quick feedback per player
        self.rating = [(0.0, "", None), (0.0, "", None)]   # (time, PERFECT/GOOD/MISS, beat) popup on the highway
        self.combo = [0, 0]
        self.passed = [set(), set()]          # notes that went by without a hit (MISS shown once)
        self.schedule = []                   # (time, sound, volume)
        self.bpm = args.bpm or 90
        self.beat_s = 60 / self.bpm
        self.rounds_played = 0               # Level 1 rounds (all time)
        self.levels_played = 0               # finished levels 2/3 in --level mode
        self.matches_played = 0
        self.leaderboard = []                # (effective_ms, player_index, name)
        self.player_names = list(getattr(args, "players", None) or [None, None])   # typed in the lobby (1 / 2)
        self.editing = None                  # player index whose name is being typed, or None
        self.edit_buf = ""
        self.fw = [None, None]               # parse_version() of each wand
        self.drops = [0, 0]                  # disconnects this session (per player)
        self.drop_t = [None, None]           # when each wand dropped out (for the log)
        self.paused_state = None             # state we were in when a wand dropped out
        self.pause_t0 = 0.0
        self.resume_at = None
        self.disconnects_path = None
        self.log = []
        here = os.path.dirname(os.path.abspath(__file__))
        self.scores_path = os.path.join(here, "scores.csv")
        self.matches_path = os.path.join(here, "matches.csv")
        self.disconnects_path = os.path.join(here, "disconnects.csv")
        self.only_level = args.level         # 0 = full match
        self.art = None                      # pixel_art.Art, made on the first draw
        self.bg = None                       # background music playing now: "western" / "arcane" / None
        self.bg_vol = None
        self.save = not getattr(args, "fast", False)   # automated test runs don't touch the CSVs / JSON
        self.settings = Settings(save=self.save)
        self.hof = HallOfFame(save=self.save)
        self.menu = Menu(self)
        self.want_quit = False                         # QUIT in the menu / ESC on the main menu
        self.mouse_pos = (-1, -1)
        self.apply_settings()
        self.reset_match()

    def reset_match(self):
        self.level = self.only_level or 1
        # level 1
        self.players = [PlayerRound(), PlayerRound()]
        self.live_bullets = [0, 0]
        self.got_b = [False, False]
        self.got_t = [False, False]
        self.pattern = "--------"
        self.t_beat0 = 0.0
        self.drum_end = 0.0
        self.standoff_until = 0.0
        self.draw_shown_at = 0.0
        self.draw_deadline = 0.0
        self.result = None
        self.l1_wins = [0, 0]
        self.l1_rounds = 0
        self.l1_bonus = None
        # level 2
        self.duel = None
        self.bursts = []                     # (time, where 0..1, colour) mid-air collisions
        self.cast_t = [-9.0, -9.0]           # last time each wizard cast / got hurt / gained mana (poses)
        self.hurt_t = [-9.0, -9.0]
        self.charge_t = [-9.0, -9.0]
        self.shot_t = [-9.0, -9.0]           # Level 1: when each cowboy fired
        self.mana = [START_MANA, START_MANA]
        self.next_kick = 0.0
        self.l2_winner = None
        # level 3
        self.beam = None
        self.beam_draw = 50.0                # where the beam is drawn (slides toward beam.pos)
        self.round_no = 0
        self.combo = ""
        self.entries = [ComboEntry(), ComboEntry()]
        self.round_result = None
        self.show_t0 = 0.0
        self.show_fl = 0.8
        self.done_t = None
        self.match_winner = None
        self.l3_music = None                 # "battle" or "battle_fast" while Level 3 plays
        self.beam_zone = 0                   # +1 P1 overpowering, -1 P2 overpowering, 0 middle
        self.hype = (0.0, "", INK)           # (time, text, colour) big hype line on the beam screen
        self.level_t0 = 0.0
        self.level_msg = ""
        # spell tutorial (before the Level 2 duel) - each player at their own pace, no timer
        self.tut = [Tutorial(), Tutorial()]
        self.tut_t = [0.0, 0.0]              # when each player's current step started (animation clock)
        self.warm_done_t = None
        self.l2_hp = [L2_START_HP, L2_START_HP]
        # cowboy tutorial (before Level 1) - arrows at your own pace, then practice beat, holster, draw
        self.ctut_phase = None               # "arrows" "beat" "beat_done" "holster" "draw" "results"
        self.ctut_t = 0.0                    # when the phase started
        self.ctut = [Tutorial("UDLR"), Tutorial("UDLR")]
        self.ctut_step_t = [0.0, 0.0]
        self.ctut_done_t = None
        self.still_t = [0.0, 0.0]            # seconds frozen so far
        self.still_last = [None, None]
        self.still_n = [0, 0]                # latest movement level from the wand (10 = foul line)
        self.still_done = [False, False]
        self.ctut_cue = None                 # when the practice DRAW cue is sent
        self.ctut_cue_sent = False
        self.ctut_draw = [None, None]        # practice draw: ms, "slow" or None
        self.ctut_early = [False, False]
        self.ctut_beat_score = [0, 0]
        # end-of-match stats
        self.stats = {"notes": 0, "beat_hits": [0, 0], "perfect": [0, 0], "best_combo": [0, 0], "bullets": [0, 0], "best_draw": [None, None], "draws_won": [0, 0],
                      "fouls": [0, 0], "fizzles": [0, 0], "combo_right": [0, 0], "combo_rounds": 0,
                      "combo_spells": 0}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def set_state(self, s, now):
        self.state = s
        self.state_t = now

    def ann(self, name, at=None):
        """Announcer line (sounds/announcer/<name>.wav): now, or at time `at` via the schedule."""
        if at is None:
            self.sounds.play(name, ANN_VOL)
        else:
            bisect.insort(self.schedule, (at, name, ANN_VOL))

    def mean_latency_ms(self):
        lats = [l if l is not None else 0.0 for l in self.latency]
        return sum(lats) / 2

    def corrected_ms(self, i, us):
        """Same latency correction as Level 1 (see game_logic.PlayerRound)."""
        lat = self.latency[i] or 0.0
        return us / 1000 + (lat - self.mean_latency_ms())

    def ready(self):
        return all(self.connected) and all(l is not None for l in self.latency)

    def apply_settings(self):
        """Volumes + difficulty from the SETTINGS menu (a --bpm on the command line wins)."""
        st = self.settings
        if hasattr(self.sounds, "set_gains"):
            self.sounds.set_gains(st["music"] / 10, st["effects"] / 10, st["announcer"] / 10)
        self.bpm = self.args.bpm or st.bpm
        self.beat_s = 60 / self.bpm

    def pname(self, i):
        """What to call player i on screen: the typed name, or P1 / P2."""
        return self.player_names[i] or f"P{i + 1}"

    def say(self, text):
        self.log.append(text)
        if self.args.headless:
            print(text, flush=True)

    def both(self, fn):
        """Send fn(i) to each wand at the same moment."""
        self.link.send_many({0: fn(0), 1: fn(1)})

    # ------------------------------------------------------------------
    # incoming events
    # ------------------------------------------------------------------
    def handle_event(self, ev, now):
        kind, i, payload, t = ev
        if kind == "status":
            self.status[i] = payload
            was = self.connected[i]
            self.connected[i] = payload.startswith("connected")
            if self.connected[i] and not was:
                self.start_calibration(i)
                self.link.send(i, "V")
            if self.connected[i] and not was and self.drop_t[i] is not None:
                self.log_drop(i, "reconnect", now - self.drop_t[i])
                self.drop_t[i] = None
            if was and not self.connected[i]:
                self.latency[i] = None
                self.battery_at_drop = self.battery[i]
                self.drops[i] += 1
                self.drop_t[i] = now
                self.log_drop(i, "disconnect")
                self.battery[i] = None
                if self.state not in ("LOBBY", "MATCH_END"):
                    self.pause(now, i)
            return
        if kind == "warn":
            self.say(f"P{i + 1}: {payload}")
            return
        self.handle_msg(i, payload, t, now)

    def handle_msg(self, i, msg, t, now):
        m = parse_message(msg)
        p = self.players[i]
        typ = m["type"]
        if typ == "pong":
            if self.ping_sent[i] is not None:
                self.rtts[i].append((t - self.ping_sent[i]) * 1000)
                self.ping_sent[i] = None
                if len(self.rtts[i]) >= PINGS_NEEDED:
                    self.latency[i] = statistics.median(self.rtts[i]) / 2
                    self.say(f"P{i + 1} latency ~{self.latency[i]:.1f} ms one-way")
        elif typ == "battery":
            self.battery[i] = m["pct"]
            if m["pct"] <= BATT_LOW_PCT and not self.batt_warned[i]:
                self.batt_warned[i] = True
                self.say(f"P{i + 1} battery LOW ({m['pct']}%) - charge it after this match")
            elif m["pct"] > BATT_LOW_PCT + 10:
                self.batt_warned[i] = False
        elif typ == "version":
            info = parse_version(m["info"])
            self.fw[i] = info
            self.status[i] = f"connected  fw {info['version']}"
            if info["reset"] in ("W", "B"):                 # the wand restarted itself: tell the team why
                self.say(f"P{i + 1} wand restarted: {RESET_CAUSES[info['reset']]}")
                self.log_drop(i, "restart " + RESET_CAUSES[info["reset"]])
        elif typ == "fizzle":
            hint = FIZZLE_HINTS.get(m["closest"], "bigger move!")
            near = SPELL_NAMES.get(m["closest"])
            self.flash[i] = (now, f"FIZZLE - {'almost ' + near + ': ' if near else ''}{hint}")
            if self.state in ("SPELL", "INPUT"):
                self.stats["fizzles"][i] += 1
        elif typ == "cast" and self.state == "WARMUP":
            self.on_tutorial_cast(i, m["spell"], now)
        elif typ == "flick" and self.state == "CTUT" and self.ctut_phase == "arrows":
            self.on_ctut_flick(i, m["dir"], now)
        elif typ == "still" and self.state == "CTUT":
            self.on_ctut_still(i, m["n"], now)
        elif typ in ("draw", "no_draw") and self.state == "CTUT" and self.ctut_phase == "draw" and self.ctut_cue_sent:
            if typ == "draw":
                self.ctut_draw[i] = self.corrected_ms(i, m["us"])
                self.players[i].draw_us = m["us"]
                self.shot_t[i] = now
                self.sounds.play("gunshot", 0.8)
            else:
                self.ctut_draw[i] = "slow"
        # ---- Level 1 ----
        elif typ == "hit" and (self.state == "DRUM" or (self.state == "CTUT" and self.ctut_phase == "beat")):
            if m["ok"] or not p.hits.get(m["beat"]):       # a loaded (green) beat never turns red again
                p.hits[m["beat"]] = m["ok"]
            rating = hit_rating(m["ok"], m["err"])
            self.rating[i] = (now, rating, m["beat"])
            if m["ok"]:
                self.live_bullets[i] = min(MAX_BULLETS, self.live_bullets[i] + 1)
                self.sounds.play("snare" if m["gesture"] in "UD" else "hihat")
                self.flash[i] = (now, f"HIT {m['err']:+d} ms")
                self.combo[i] += 1
                if self.state == "DRUM":
                    self.stats["perfect"][i] += rating == "PERFECT"
                    self.stats["best_combo"][i] = max(self.stats["best_combo"][i], self.combo[i])
            else:
                self.sounds.play("wrong", 0.5)
                self.flash[i] = (now, "MISS")
                self.combo[i] = 0
        elif typ == "bullets":
            p.bullets = m["n"]
            self.live_bullets[i] = m["n"]
            self.got_b[i] = True
        elif typ == "foul" and self.state in ("HOLSTER", "STANDOFF", "DRAW"):
            p.fouled = True
            self.got_t[i] = True
            self.sounds.play("jam")
            self.flash[i] = (now, "JAMMED!")
        elif typ == "draw" and self.state == "DRAW":
            p.draw_us = m["us"]
            self.got_t[i] = True
            self.shot_t[i] = now
            self.sounds.play("gunshot", 0.8)
        elif typ == "no_draw" and self.state == "DRAW":
            p.no_draw = True
            self.got_t[i] = True
        # ---- Level 2 ----
        elif typ == "mana" and self.state == "SPELL":
            self.mana[i] = m["n"]
            self.charge_t[i] = now
            self.sounds.play("chant", 0.6)
            self.flash[i] = (now, f"MANA {m['n']}")
        elif typ == "cast" and self.state == "SPELL":
            self.mana[i] = m["mana"]
            self.on_cast(i, m["spell"], t, now)
        # ---- Level 3 ----
        elif typ == "answer" and self.state == "INPUT":
            self.on_combo_cast(i, m["spell"], m["us"], now)

    # ------------------------------------------------------------------
    # latency calibration (ping / pong)
    # ------------------------------------------------------------------
    def start_calibration(self, i):
        self.rtts[i] = []
        self.ping_sent[i] = None
        self.latency[i] = None
        self.next_ping[i] = self.clock() + 0.5

    def update_calibration(self, now):
        for i in range(2):
            if not self.connected[i] or self.latency[i] is not None:
                continue
            if self.ping_sent[i] is not None and now - self.ping_sent[i] > 0.5:
                self.ping_sent[i] = None              # lost ping, try again
            if self.ping_sent[i] is None and now >= self.next_ping[i]:
                self.link.send(i, "P")
                self.ping_sent[i] = now
                self.next_ping[i] = now + 0.12

    # ------------------------------------------------------------------
    # match flow
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # dropped wands: pause, wait for it to come back, carry on
    # ------------------------------------------------------------------
    def log_drop(self, i, event, offline_s=None):
        """One line per disconnect / reconnect / self-restart in pc/disconnects.csv (+ the console)."""
        batt = getattr(self, "battery_at_drop", None) if event == "disconnect" else self.battery[i]
        self.say(f"[drop log] P{i + 1} {event}" + (f" after {offline_s:.1f} s" if offline_s is not None else "")
                 + (f"  battery {batt}%" if batt is not None else ""))
        if not self.save:
            return
        new = not os.path.exists(self.disconnects_path)
        try:
            with open(self.disconnects_path, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["time", "player", "event", "level", "state", "battery_pct", "offline_s"])
                w.writerow([dt.datetime.now().isoformat(timespec="seconds"), f"P{i + 1}", event, self.level,
                            self.paused_state or self.state, "" if batt is None else batt,
                            "" if offline_s is None else f"{offline_s:.1f}"])
        except OSError as e:
            self.say(f"(could not write disconnects.csv: {e})")

    def pause(self, now, i):
        if self.state == "PAUSED":
            return
        self.paused_state = self.state
        self.pause_t0 = now
        self.resume_at = None
        self.schedule.clear()
        self.sounds.stop_voice()
        self.stop_all_music(300)
        self.sounds.play("freeze")
        self.ann("ann_paused")
        self.link.send_many({0: "L", 1: "L"})        # the wand that is still there waits in its lobby
        self.say(f"P{i + 1} dropped out during {self.paused_state} (level {self.level}) - PAUSED")
        self.set_state("PAUSED", now)

    def update_paused(self, now):
        self.update_calibration(now)                   # measure the latency of the wand that came back
        if not self.ready():
            self.resume_at = None
        elif self.resume_at is None:
            self.resume_at = now + RESUME_DELAY_S
        elif now >= self.resume_at:
            self.resume(now)

    def resume(self, now):
        """Both wands are back. Replay whatever was interrupted (a round that was cut off doesn't count)."""
        ps, lvl = self.paused_state, self.level
        self.paused_state = None
        self.say(f"Both wands back after {now - self.pause_t0:.1f} s - resuming")
        self.ann("ann_resume")
        if lvl == 1:
            if ps == "CTUT":
                self.after_cowboy_tutorial(now)          # a drop-out ends the tutorial: on to the match
            elif ps == "RESULT":
                if self.only_level == 1:
                    self.set_state("RESULT", now)
                elif not level1_done(self.l1_wins, self.l1_rounds):
                    self.start_round(now)
                else:
                    self.start_level2(now)
            else:
                self.start_round(now)                  # the interrupted round is played again
        elif lvl == 2:
            if ps == "LEVEL_RESULT":
                self.set_state("LEVEL_RESULT", now)
            elif ps == "WARMUP":                       # carry on with the spell tutorial (progress kept)
                self.link.send_many({0: "w", 1: "w"})
                self.warm_done_t = None
                self.set_state("WARMUP", now)
            elif ps in ("SPELL", "INTRO") and self.duel is not None:
                self.begin_duel(now, resume=True)      # same HP, the time that was left
            else:
                self.begin_duel(now)                   # dropped in the warm-up: straight to the duel
        else:
            if ps == "LEVEL_RESULT":
                self.set_state("LEVEL_RESULT", now)
                return
            if ps in ("SHOW", "WAIT", "INPUT"):
                self.round_no -= 1                     # this round is replayed with a new combo
            if ps == "SCORE":
                self.after_score(now)                  # the round counted: maybe the match is over
                if self.state != "ROUND":
                    return
            self.start_level3(now, resume=self.beam is not None)

    def go_lobby(self, now):
        self.link.send_many({0: "L", 1: "L"})
        self.schedule.clear()
        self.sounds.stop_voice()
        self.stop_all_music()
        self.reset_match()
        self.paused_state = None
        self.set_state("LOBBY", now)

    def start_match(self, now):
        if not self.ready():
            self.say("Not ready: both wands must be connected and calibrated")
            return
        self.stop_all_music()
        self.reset_match()
        if self.only_level == 2:
            self.start_level2(now)
        elif self.only_level == 3:
            self.start_level3(now)
        elif self.settings["cowboy_tutorial"] and not getattr(self.args, "no_cowboy_tutorial", False):
            self.start_cowboy_tutorial(now)
        else:
            self.after_cowboy_tutorial(now)

    def start_match_intro(self, now):
        self.say("=== NEW MATCH ===")
        self.level = 1                           # short intro: "Level one. Cowboy showdown! ... Round one!"
        self.level_msg = ""
        self.level_t0 = now + MATCH_INTRO_S
        self.ann("ann_level1")
        self.ann("ann_round1", self.level_t0 - 1.4)
        self.set_state("INTRO", now)

    # ------------------------------------------------------------------
    # COWBOY TUTORIAL (before Level 1, no timer)
    #   arrows  : each player flicks U, D, L, R twice at their own pace (wand mode O1 -> d<dir>)
    #   beat    : one slow practice beat (70 BPM, U-D-L-R-), doesn't count
    #   holster : freeze for 3 s - live stillness meter from the wand (O3 -> s<0-20>), at your own pace
    #   draw    : one practice quick-draw for both, then the real match starts
    # ------------------------------------------------------------------
    def start_cowboy_tutorial(self, now):
        self.level = 1
        self.say("=== COWBOY TUTORIAL ===")
        self.link.send_many({0: "O1", 1: "O1"})
        self.ctut = [Tutorial("UDLR"), Tutorial("UDLR")]
        self.ctut_step_t = [now, now]
        self.ctut_done_t = None
        self.ann("ann_cowboy_school")
        self.ctut_phase, self.ctut_t = "arrows", now
        self.set_state("CTUT", now)

    def after_cowboy_tutorial(self, now):
        """Tutorial finished or skipped: the real thing."""
        self.schedule.clear()
        self.ctut_phase = None
        self.beat_s = 60 / self.bpm
        self.players = [PlayerRound(), PlayerRound()]
        self.live_bullets = [0, 0]
        if self.only_level == 1:
            self.start_round(now)
        else:
            self.link.send_many({0: "L", 1: "L"})            # wands wait in their lobby during the intro
            self.start_match_intro(now)

    def ctut_go(self, phase, now):
        self.ctut_phase, self.ctut_t = phase, now
        if phase == "beat":                                  # slow practice beat, using the normal drum mode
            self.beat_s = 60 / CTUT_BPM
            self.pattern = CTUT_PATTERN
            self.players = [PlayerRound(latency_ms=self.latency[i] or 0) for i in range(2)]
            self.live_bullets = [0, 0]
            self.start_drum(CTUT_BPM, CTUT_PATTERN, now)
        elif phase == "beat_done":
            notes = sum(c != "-" for c in CTUT_PATTERN)
            for i in range(2):
                self.ctut_beat_score[i] = sum(1 for ok in self.players[i].hits.values() if ok)
                n = self.ctut_beat_score[i]
                self.flash[i] = (now, f"{n}/{notes} arrows" + ("  - PERFECT!" if n == notes else ("  - nice!" if n else "")))
            self.beat_s = 60 / self.bpm
        elif phase == "holster":
            self.link.send_many({0: "O3", 1: "O3"})
            self.still_t, self.still_last = [0.0, 0.0], [None, None]
            self.still_n, self.still_done = [0, 0], [False, False]
            self.ann("ann_holster")
        elif phase == "draw":
            self.link.send_many({0: "O3", 1: "O3"})         # learn the pose again, then wait for DRAW
            self.ctut_cue = now + 1.5 + self.rng.uniform(1.5, 3.0)
            self.ctut_cue_sent = False
            self.ctut_draw = [None, None]
            self.ctut_early = [False, False]
            self.players = [PlayerRound(latency_ms=self.latency[i] or 0) for i in range(2)]
            self.ann("ann_freeze")
        elif phase == "results":
            self.sounds.play("win", 0.5)

    def on_ctut_flick(self, i, g, now):
        tut = self.ctut[i]
        ev = tut.cast(g)
        self.shot_t[i] = now
        if ev[0] == "wrong":
            self.sounds.play("wrong", 0.4)
            self.flash[i] = (now, f"That was {DIRECTION_NAMES[g]} - flick {DIRECTION_NAMES[ev[1]]}")
            return
        if ev[0] == "over":
            return
        self.sounds.play("snare" if g in "UD" else "hihat")
        if ev[0] == "good":
            self.flash[i] = (now, f"GOOD! {tut.repeats - ev[2]} more {DIRECTION_NAMES[g]}")
        elif ev[0] == "next":
            self.sounds.play("chant", 0.5)
            self.ctut_step_t[i] = now
            self.flash[i] = (now, f"{DIRECTION_NAMES[g]} done!  Next: {DIRECTION_NAMES[ev[1]]}")
        else:
            self.sounds.play("cheer", 0.4)
            self.flash[i] = (now, "ALL 4 ARROWS!")

    def on_ctut_still(self, i, n, now):
        self.still_n[i] = n
        if self.ctut_phase == "holster" and not self.still_done[i]:
            last = self.still_last[i]
            self.still_last[i] = now
            dt = min(0.2, now - last) if last is not None else 0.0
            if n < STILL_FOUL:
                self.still_t[i] += dt
                if self.still_t[i] >= CTUT_STILL_S:
                    self.still_done[i] = True
                    self.sounds.play("chant", 0.5)
                    self.flash[i] = (now, "FROZEN! Perfect holster")
            else:
                if self.still_t[i] > 0.3:
                    self.sounds.play("wrong", 0.3)
                self.still_t[i] = 0.0
                self.flash[i] = (now, "MOVED! Freeze again...")
        elif self.ctut_phase == "draw" and not self.ctut_cue_sent and n >= STILL_FOUL and now - self.ctut_t > 0.6:
            self.ctut_early[i] = True

    def update_ctut(self, now):
        ph, el = self.ctut_phase, now - self.ctut_t
        if ph == "arrows":
            if all(t.done for t in self.ctut) and self.ctut_done_t is None:
                self.ctut_done_t = now
            if self.ctut_done_t is not None and now - self.ctut_done_t > 1.5:
                self.ctut_go("beat", now)
        elif ph == "beat":
            self.update_passed_notes(now)
            if now > self.drum_end + 0.4:
                self.ctut_go("beat_done", now)
        elif ph == "beat_done" and el > 2.5:
            self.ctut_go("holster", now)
        elif ph == "holster" and all(self.still_done) and el > 0.5:
            if self.ctut_done_t is None or self.ctut_done_t < self.ctut_t:
                self.ctut_done_t = now
            if now - self.ctut_done_t > 1.2:
                self.ctut_go("draw", now)
        elif ph == "draw":
            if not self.ctut_cue_sent and now >= self.ctut_cue:
                self.ctut_cue_sent = True
                self.link.send_many({0: "G", 1: "G"})
                self.draw_shown_at = now + self.mean_latency_ms() / 1000
                self.schedule = [(self.draw_shown_at, "draw", 1.0)]
                self.ann("ann_draw", self.draw_shown_at)
            done = all(d is not None for d in self.ctut_draw)
            if self.ctut_cue_sent and (done or now > self.ctut_cue + DRAW_TIMEOUT_MS / 1000 + 0.6):
                self.ctut_draw = [d if d is not None else "slow" for d in self.ctut_draw]
                self.ctut_go("results", now)
        elif ph == "results" and el > 3.5:
            self.after_cowboy_tutorial(now)

    def skip_level(self, now):
        """N key: jump to the next level (e.g. if a sensor misbehaves during the demo)."""
        if self.state in ("LOBBY", "MATCH_END") or self.only_level:
            return
        self.schedule.clear()
        self.stop_all_music()
        if self.level == 1:
            self.start_level2(now)
        elif self.level == 2:
            self.start_level3(now)
        else:
            self.finish_level3(self.beam.leader() if self.beam else None, now)

    # ------------------------------------------------------------------
    # LEVEL 1 - Cowboy
    # ------------------------------------------------------------------
    def start_round(self, now):
        if not self.ready():
            self.say("Not ready: both wands must be connected and calibrated")
            return
        self.level = 1
        self.players = [PlayerRound(latency_ms=self.latency[i]) for i in range(2)]
        self.live_bullets = [0, 0]
        self.got_b = [False, False]
        self.got_t = [False, False]
        self.result = None
        self.pattern = random_pattern(self.rng, self.l1_rounds + 1)     # arrows: harder each round
        self.start_drum(self.bpm, self.pattern, now)
        self.say(f"L1 round {self.l1_rounds + 1}: pattern {self.pattern} @ {self.bpm} BPM")
        self.set_state("DRUM", now)

    def start_drum(self, bpm, pattern, now):
        """Send the pattern, then play the count-in + play-along groove (one generated sound, v5.7).
        Wands start their count-in when the R packet ARRIVES, so our audio starts after the average
        Bluetooth delay to stay in sync with them."""
        self.link.send_many({0: drum_packet(bpm, pattern), 1: drum_packet(bpm, pattern)})
        self.beat_s = 60 / bpm
        self.combo = [0, 0]
        self.passed = [set(), set()]
        self.rating = [(0.0, "", None), (0.0, "", None)]
        t_audio0 = now + self.mean_latency_ms() / 1000
        self.t_beat0 = t_audio0 + COUNT_IN_BEATS * self.beat_s
        name = f"groove_{bpm}_{len(pattern)}"
        if getattr(self.sounds, "enabled", False) and name not in self.sounds.sounds:
            from sounds import groove
            self.sounds.add(name, groove(bpm, len(pattern), COUNT_IN_BEATS))
        self.schedule = [(t_audio0, name, 0.8)]
        self.schedule += [(t_audio0 + c * self.beat_s, f"ann_{COUNT_IN_BEATS - c}", ANN_VOL)   # "4, 3, 2, 1"
                          for c in range(COUNT_IN_BEATS)]
        self.schedule.sort()
        self.drum_end = self.t_beat0 + len(pattern) * self.beat_s + HIT_WINDOW_MS / 1000

    def finish(self, now):
        self.schedule.clear()
        r = decide(self.players)
        self.result = r
        self.link.send_many({0: result_packet(r, 0), 1: result_packet(r, 1)})
        t = now
        if any(r.fouls):
            self.ann("ann_foul")
            t += 0.9
        self.ann("ann_tie" if r.winner is None else f"ann_p{r.winner + 1}wins", t)
        if r.winner is not None:
            self.sounds.play("win", 0.7)
            self.l1_wins[r.winner] += 1
            for i in range(2):
                if r.effective_ms[i] is not None:
                    self.leaderboard.append((r.effective_ms[i], i, self.pname(i)))
                    self.hof.add_draw(self.pname(i), r.effective_ms[i])
            self.leaderboard.sort()
            self.leaderboard = self.leaderboard[:5]
        st = self.stats
        st["notes"] += sum(1 for g in self.pattern if g != "-")
        for i in range(2):
            st["beat_hits"][i] += sum(1 for ok in self.players[i].hits.values() if ok)
            st["bullets"][i] += self.players[i].bullets
            st["fouls"][i] += bool(r.fouls[i])
            e = r.effective_ms[i]
            if e is not None and (st["best_draw"][i] is None or e < st["best_draw"][i]):
                st["best_draw"][i] = e
        if r.winner is not None:
            st["draws_won"][r.winner] += 1
        self.rounds_played += 1
        self.l1_rounds += 1
        self.say(f"  -> {r.reason} | corrected={_fmt(r.corrected_ms)} "
                 f"bullets={[p.bullets for p in self.players]} effective={_fmt(r.effective_ms)} "
                 f"| L1 score {self.l1_wins[0]}-{self.l1_wins[1]}")
        self.save_score(r)
        if not self.only_level and not level1_done(self.l1_wins, self.l1_rounds):
            n = self.l1_rounds + 1
            final = n >= L1_MAX_ROUNDS or min(self.l1_wins) == L1_WINS_NEEDED - 1
            self.ann("ann_final" if final else f"ann_round{min(n, 6)}", now + RESULT_S - 1.3)
        self.set_state("RESULT", now)

    # ------------------------------------------------------------------
    # LEVEL 2 - Spellcaster
    # ------------------------------------------------------------------
    def start_level2(self, now):
        self.level = 2
        self.schedule.clear()
        self.duel = None
        self.l1_bonus = level1_bonus(self.l1_wins) if not self.only_level else None
        hp = [L2_START_HP, L2_START_HP]
        if self.l1_bonus is not None:
            hp[self.l1_bonus] += L2_BONUS_HP
        self.l2_hp = hp
        bonus = f"{self.pname(self.l1_bonus)} won Level 1: +{L2_BONUS_HP} HP" if self.l1_bonus is not None else ""
        self.level_msg = bonus
        self.say(f"=== LEVEL 2 === HP {hp}  {bonus}")
        self.sounds.play("level")
        self.ann("ann_level2")
        if getattr(self.args, "no_warmup", False):
            self.begin_duel(now)
            return
        if not self.settings["tutorial"]:
            self.begin_duel(now)
            return
        # spell tutorial: free casts; each player learns Lightning, Water, Fire at their own pace (no timer)
        self.link.send_many({0: "w", 1: "w"})
        self.tut = [Tutorial(), Tutorial()]
        self.tut_t = [now, now]
        self.warm_done_t = None
        self.ann("ann_warmup", now + 2.2)
        self.set_state("WARMUP", now)

    def on_tutorial_cast(self, i, spell, now):
        ev = self.tut[i].cast(spell)
        self.cast_t[i] = now
        kind = ev[0]
        if kind == "wrong":
            self.sounds.play("wrong", 0.5)
            self.flash[i] = (now, f"That was {SPELL_NAMES[spell]} - try a {MOVES[ev[1]]}")
            return
        if kind == "over":
            return
        self.sounds.play(_spell_sound(spell), 0.7)
        if kind == "good":
            self.flash[i] = (now, f"GOOD! {self.tut[i].repeats - ev[2]} more {MOVES[spell]}")
        elif kind == "next":
            self.sounds.play("chant", 0.6)
            self.tut_t[i] = now
            self.flash[i] = (now, f"{SPELL_NAMES[spell]} LEARNED!  Next: {SPELL_NAMES[ev[1]]}")
        else:
            self.sounds.play("cheer", 0.5)
            self.flash[i] = (now, "ALL 3 SPELLS LEARNED!")

    def update_warmup(self, now):
        if all(t.done for t in self.tut) and self.warm_done_t is None:
            self.warm_done_t = now                     # both players finished: the duel starts
        if self.warm_done_t is not None and now - self.warm_done_t > 1.5:
            self.begin_duel(now)

    def begin_duel(self, now, resume=False):
        """Send M2 (5 s intro on the wands, then the duel). resume=True keeps HP and the time left."""
        self.level = 2
        self.schedule.clear()
        hp = self.duel.hp if (resume and self.duel) else self.l2_hp
        self.both(lambda i: f"M2,{self.bpm},{hp[i]},{hp[1 - i]}")
        # wands begin LEVEL_INTRO_MS after the packet arrives
        self.level_t0 = now + self.mean_latency_ms() / 1000 + LEVEL_INTRO_MS / 1000
        if resume and self.duel:
            self.duel.resume(self.pause_t0, self.level_t0)
            self.level_msg = f"RESUMING - {self.duel.time_left(self.level_t0):.0f} s left"
        else:
            self.duel = SpellDuel(hp, t_start=self.level_t0)
        self.mana = [START_MANA, START_MANA]
        self.next_kick = self.level_t0
        for k in (3, 2, 1):
            self.ann(f"ann_{k}", self.level_t0 - k)
        self.ann("ann_fight", self.level_t0)
        self.set_state("INTRO", now)

    def on_cast(self, i, spell, t, now):
        for ev in self.duel.cast(i, spell, t):
            if ev[0] == "launch":
                self.cast_t[i] = now
                self.sounds.play(_spell_sound(spell))
                self.flash[i] = (now, f"{SPELL_NAMES[spell]}!")
                self.link.send(1 - i, f"I{spell}")          # warn the target: "INCOMING FIRE"

    def update_level2(self, now):
        for ev in self.duel.update(now):
            kind = ev[0]
            if kind == "hit":
                _, target, spell = ev
                self.hurt_t[target] = now
                self.sounds.play("hurt")
                self.flash[target] = (now, f"OUCH! {SPELL_NAMES[spell]}")
                self.link.send_many({target: hp_packet(self.duel, target, "H"),
                                     1 - target: hp_packet(self.duel, 1 - target, "D")})
            elif kind == "block":                            # winner's spell destroyed the other mid-air
                _, w, lost_spell, where = ev
                self.sounds.play("block")
                self.flash[w] = (now, f"BLOCKED {SPELL_NAMES[lost_spell]}!")
                self.link.send(w, hp_packet(self.duel, w, "B"))
                self.bursts.append((now, where, SPELL_COLORS[BEATS_INV[lost_spell]]))
            elif kind == "clash":
                _, _, spell, where = ev
                self.sounds.play("block")
                self.flash[0] = self.flash[1] = (now, "CLASH!")
                self.bursts.append((now, where, SPELL_COLORS[spell]))
        if self.duel.done(now):
            self.finish_level2(now)

    def finish_level2(self, now):
        w = self.duel.winner()
        self.l2_winner = w
        self.both(lambda i: level_packet(None if w is None else w == i, 2))
        self.sounds.play("win", 0.7)
        hp = self.duel.hp
        self.ann("ann_ko" if min(hp) <= 0 else "ann_time")
        self.ann("ann_tie" if w is None else f"ann_p{w + 1}wins", now + 1.3)
        self.level_msg = (f"{self.pname(w)} wins Level 2  ({hp[0]} HP vs {hp[1]} HP)" if w is not None
                          else f"Level 2 draw  ({hp[0]} HP each)")
        self.say(f"  -> {self.level_msg} | casts {self.duel.stats['casts']} blocks {self.duel.stats['blocks']}")
        self.levels_played += self.only_level == 2
        self.set_state("LEVEL_RESULT", now)

    # ------------------------------------------------------------------
    # LEVEL 3 - Combo Clash
    # ------------------------------------------------------------------
    # ROUND (short pause) -> SHOW (3 spells flash one by one) -> WAIT (2 s, combo hidden)
    # -> INPUT (cast it back) -> SCORE (beam moves) -> next ROUND ... until the beam hits an end.
    def start_level3(self, now, resume=False):
        self.level = 3
        self.schedule.clear()
        if not (resume and self.beam):
            hp = self.duel.hp if (self.duel and not self.only_level) else [L2_START_HP, L2_START_HP]
            self.beam = BeamClash(beam_start_pos(hp))
            self.beam_draw = self.beam.pos
            self.round_no = 0
            self.combo = ""
            lead = self.beam.leader()
            self.level_msg = (f"{self.pname(lead)} starts ahead (HP {hp[0]} vs {hp[1]})" if lead is not None
                              else "Even start")
        else:
            self.level_msg = f"RESUMING - round {self.round_no + 1}"
        self.both(lambda i: f"M3,{my_beam_pos(round(self.beam.pos), i)}")
        self.level_t0 = now + self.mean_latency_ms() / 1000 + LEVEL_INTRO_MS / 1000
        self.entries = [ComboEntry(), ComboEntry()]
        self.round_result = None
        self.say(f"=== LEVEL 3 === pos {self.beam.pos:.0f}  ({self.level_msg})")
        self.sounds.play("level")
        self.ann("ann_level3")
        for k in (3, 2, 1):
            self.ann(f"ann_{k}", self.level_t0 - k)
        self.set_state("INTRO", now)

    def sudden_death(self):
        return self.round_no >= L3_MAX_ROUNDS

    def start_show(self, now):
        self.round_no += 1
        last = self.combo
        n = combo_len(self.round_no)                    # 3 spells, 5 in the final round / sudden death
        mixed = self.round_no > 1                       # round 1 = all different, then spells repeat
        self.combo = random_combo(self.rng, n, mixed)
        while self.combo == last:                       # never the same combo twice in a row
            self.combo = random_combo(self.rng, n, mixed)
        self.flash = [(0.0, ""), (0.0, "")]
        fl = flash_s(self.round_no)
        self.both(lambda i: f"Z{self.combo}{int(round(fl * 10))}")
        self.show_t0 = now + self.mean_latency_ms() / 1000
        self.show_fl = fl
        self.schedule = sorted((self.show_t0 + k * fl, _spell_sound(c), 0.9) for k, c in enumerate(self.combo))
        self.duck(True)
        self.say(f"  round {self.round_no}: combo {self.combo} ({fl:.1f} s per spell)")
        self.set_state("SHOW", now)

    def start_input(self, now):
        self.link.send_many({0: "K", 1: "K"})
        self.entries = [ComboEntry(len(self.combo)), ComboEntry(len(self.combo))]
        self.done_t = None
        self.sounds.play("surge", 0.7)
        self.ann("ann_go")
        self.duck(False)
        self.set_state("INPUT", now)

    def end_input(self, now):
        self.link.send_many({0: "J", 1: "J"})
        w, push, correct = self.beam.resolve_combo(self.combo, self.entries)
        self.round_result = (w, push, correct)
        self.stats["combo_rounds"] += 1
        self.stats["combo_spells"] += len(self.combo)
        for i in range(2):
            self.stats["combo_right"][i] += correct[i]
        self.both(lambda i: f"b{my_beam_pos(self.beam.pos, i)}")
        for i in range(2):
            n = len(self.combo)
            self.flash[i] = (now, "PERFECT!" if correct[i] == n else f"{correct[i]}/{n} right")
        if w is None:
            self.sounds.play("wrong", 0.6)
            self.hype = (now, "NO PUSH - TIE!", INK)
        else:
            self.sounds.play("block")
            self.sounds.play("cheer", 0.8)
            self.hype = (now, f"{self.pname(w)} PUSHES +{push}!", P_COLORS[w])
            if correct[w] == len(self.combo):
                self.ann("ann_perfect")
        self.say(f"    -> P1 {self.entries[0].spells or '-'} ({correct[0]})  P2 {self.entries[1].spells or '-'} "
                 f"({correct[1]})  winner {None if w is None else 'P%d' % (w + 1)}  pos {self.beam.pos:.0f}")
        self.set_state("SCORE", now)

    def after_score(self, now):
        w = self.beam.winner()
        if w is not None:
            self.finish_level3(w, now)
            return
        if self.round_no >= L3_MAX_ROUNDS:
            lead = self.beam.leader()
            if lead is not None:
                self.finish_level3(lead, now)
                return
            if self.round_no >= L3_MAX_ROUNDS + SUDDEN_DEATH_MAX:
                self.finish_level3(None, now)
                return
            self.sounds.play("drumroll")
            self.hype = (now, "SUDDEN DEATH!", RED)
        self.enter_round(now)

    def enter_round(self, now):
        """'ROUND n' pause before the combo flashes - the announcer calls the round."""
        n = self.round_no + 1
        self.ann("ann_sudden" if n > L3_MAX_ROUNDS else ("ann_final" if n == L3_MAX_ROUNDS else f"ann_round{n}"))
        self.set_state("ROUND", now)

    def update_level3(self, now):
        s = self.state
        self.beam_draw += (self.beam.pos - self.beam_draw) * 0.08     # beam slides to its new spot
        self.update_l3_audio(now)
        if s == "ROUND":
            if now - self.state_t > ROUND_PAUSE_S:
                self.start_show(now)
        elif s == "SHOW":
            if now >= self.show_t0 + len(self.combo) * self.show_fl:
                self.schedule = [(now + k, "click", 0.4) for k in range(int(COMBO_WAIT_S))]
                for k in range(int(COMBO_WAIT_S)):                    # "two... one..." then "GO!"
                    self.ann(f"ann_{int(COMBO_WAIT_S) - k}", now + k)
                self.set_state("WAIT", now)
        elif s == "WAIT":
            if now - self.state_t >= COMBO_WAIT_S:
                self.start_input(now)
        elif s == "INPUT":
            both_done = all(e.done for e in self.entries)
            if both_done and self.done_t is None:
                self.done_t = now
            timeout = combo_input_s(len(self.combo)) + self.mean_latency_ms() / 1000
            if (self.done_t is not None and now - self.done_t > COMBO_GRACE_S) or now - self.state_t > timeout:
                self.end_input(now)
        elif s == "SCORE":
            if now - self.state_t > SCORE_S:
                self.after_score(now)

    def on_combo_cast(self, i, spell, us, now):
        e = self.entries[i]
        if e.add(spell, self.corrected_ms(i, us)):
            self.sounds.play(_spell_sound(spell), 0.8)
            self.cast_t[i] = now

    # ---- Level 3 hype: music, beam hum, crowd -----------------------------
    def stop_all_music(self, fade_ms=400):
        self.sounds.stop_loops(fade_ms)
        self.bg = None
        self.l3_music = None

    def start_l3_audio(self, now):
        self.l3_music = "battle"
        self.sounds.loop("battle", MUSIC_VOL)
        self.sounds.loop("hum", 0.12)
        self.sounds.loop("crowd", CROWD_VOL)
        self.sounds.play("cheer", 0.7)
        self.hype = (now, "CLASH!", GOLD)

    def duck(self, on):
        """Quieter music while the combo flashes so the spell sounds stand out."""
        if self.l3_music:
            self.sounds.set_volume(self.l3_music, MUSIC_DUCKED if on else MUSIC_VOL)
            self.sounds.set_volume("hum", 0.04 if on else 0.12)
            self.sounds.set_volume("crowd", 0.08 if on else CROWD_VOL)

    def update_l3_audio(self, now):
        b = self.beam
        off = abs(b.pos - 50)
        # music: fast loop when someone is close to winning or in the last rounds
        want = self.l3_music
        if off >= HYPE_ZONE or self.round_no >= L3_MAX_ROUNDS - 1:
            want = "battle_fast"
        elif off < HYPE_ZONE - 10:
            want = "battle"
        if want != self.l3_music and self.l3_music is not None:
            self.sounds.stop(self.l3_music, 300)
            self.sounds.loop(want, MUSIC_VOL if self.state not in ("SHOW", "WAIT") else MUSIC_DUCKED, 300)
            self.l3_music = want
        if self.state in ("INPUT", "SCORE", "ROUND"):    # crowd bed gets louder when someone is close to winning
            self.sounds.set_volume("crowd", CROWD_HYPE_VOL if off >= HYPE_ZONE else CROWD_VOL)
        # crowd: someone enters the danger zone, or fights their way out of it
        zone = 1 if b.pos >= 50 + HYPE_ZONE else (-1 if b.pos <= 50 - HYPE_ZONE else 0)
        if zone == 0 and self.beam_zone != 0 and off > HYPE_ZONE - 8:
            zone = self.beam_zone                          # hysteresis: must get well clear to "fight back"
        if zone != self.beam_zone and now - self.hype[0] > 1.0:
            if zone != 0:
                lead = 0 if zone == 1 else 1
                self.sounds.play("surge")
                self.sounds.play("cheer", 0.9)
                self.hype = (now, f"{self.pname(lead)} IS OVERPOWERING!", P_COLORS[lead])
            else:
                back = 1 if self.beam_zone == 1 else 0      # the player who was being overpowered
                self.sounds.play("cheer", 0.6)
                self.hype = (now, f"{self.pname(back)} FIGHTS BACK!", P_COLORS[back])
            self.beam_zone = zone

    def finish_level3(self, w, now):
        self.match_winner = w
        self.both(lambda i: level_packet(None if w is None else w == i, 3))
        self.stop_all_music(1500)
        self.sounds.play("surge")
        self.sounds.play("cheer", 1.0)
        self.sounds.play("win", 0.9)
        self.ann("ann_ko" if self.beam.winner() is not None else "ann_time")
        if w is None:
            self.ann("ann_tie", now + 1.3)
        else:
            self.ann(f"ann_p{w + 1}wins" if self.only_level == 3 else f"ann_p{w + 1}champ", now + 1.3)
        if self.only_level == 3:
            self.level_msg = f"{self.pname(w)} wins the Combo Clash!" if w is not None else "Combo Clash draw!"
            self.levels_played += 1
            self.say(f"  -> {self.level_msg}")
            self.set_state("LEVEL_RESULT", now)
            return
        self.level_msg = f"{self.pname(w).upper()} IS THE CHAMPION!" if w is not None else "NO CHAMPION - REMATCH!"
        if w is not None:
            self.hof.add_champion(self.pname(w), self.pname(1 - w))
        self.matches_played += 1
        self.say(f"=== MATCH OVER === {self.level_msg}  pos {self.beam.pos:.0f} "
                 f"rounds won {self.beam.rounds_won} perfect {self.beam.perfect}")
        self.save_match()
        self.set_state("MATCH_END", now)

    # ------------------------------------------------------------------
    # main update
    # ------------------------------------------------------------------
    # ---- background music (Level 1 Wild West, Level 2 mystic) -------------
    BG_VOLUME = {"LOBBY": 0.45, "DRUM": 0.0, "HOLSTER": 0.35, "STANDOFF": 0.06, "DRAW": 0.06, "RESULT": 0.45,
                 "INTRO": 0.3, "WARMUP": 0.35, "CTUT": 0.2, "SPELL": 0.4, "LEVEL_RESULT": 0.3}

    def update_music(self):
        s = self.state
        want = None
        if s == "LOBBY" or (self.level == 1 and s in ("INTRO", "CTUT", "DRUM", "HOLSTER", "STANDOFF", "DRAW", "RESULT")):
            want = "western"                     # silent during the air-drum (the groove plays), quiet in the standoff
        elif self.level == 2 and s in ("WARMUP", "INTRO", "SPELL", "LEVEL_RESULT"):
            want = "arcane"
        vol = self.BG_VOLUME.get(s, 0.4)
        if s == "CTUT" and self.ctut_phase == "beat":
            vol = 0.0                            # the practice groove is playing
        if want != self.bg:
            if self.bg:
                self.sounds.stop(self.bg, 900)
            if want:
                self.sounds.loop(want, vol, 900)
            self.bg, self.bg_vol = want, vol
        elif want and vol != self.bg_vol:
            self.bg_vol = vol
            self.sounds.set_volume(want, self.bg_vol)

    def update(self, now):
        self.update_music()
        s = self.state
        a = self.args
        if s == "LOBBY":
            self.update_calibration(now)
            if a.auto and self.ready() and now - self.state_t > 1.0:
                self.start_match(now)
        elif s == "DRUM":
            self.update_passed_notes(now)
            if (all(self.got_b) and now > self.drum_end) or now > self.drum_end + 1.5:
                for i in range(2):
                    if not self.got_b[i]:          # packet lost: trust the live count
                        self.players[i].bullets = self.live_bullets[i]
                self.ann("ann_holster")
                self.set_state("HOLSTER", now)
        elif s == "HOLSTER":
            if now - self.state_t > HOLSTER_S:
                self.link.send_many({0: "W", 1: "W"})
                self.standoff_until = now + self.rng.uniform(STANDOFF_MIN_S, STANDOFF_MAX_S)
                self.schedule = [(now + 0.3 + k * 0.9, "heartbeat", 0.7)
                                 for k in range(int((self.standoff_until - now) / 0.9) + 1)
                                 if now + 0.3 + k * 0.9 < self.standoff_until - 0.2]
                self.set_state("STANDOFF", now)
        elif s == "STANDOFF":
            if any(p.fouled for p in self.players):
                self.finish(now)
            elif now >= self.standoff_until:
                self.link.send_many({0: "G", 1: "G"})
                self.draw_shown_at = now + self.mean_latency_ms() / 1000
                self.schedule = [(self.draw_shown_at, "draw", 1.0)]
                self.ann("ann_draw", self.draw_shown_at)
                self.draw_deadline = now + DRAW_TIMEOUT_MS / 1000 + 0.5
                self.set_state("DRAW", now)
        elif s == "DRAW":
            if all(self.got_t) or now > self.draw_deadline:
                self.finish(now)
        elif s == "RESULT":
            if self.only_level == 1:                 # practice mode: one round at a time
                if a.auto and now - self.state_t > 3.0:
                    if a.rounds and self.rounds_played >= a.rounds:
                        return
                    self.start_round(now)
            elif now - self.state_t > RESULT_S:
                if level1_done(self.l1_wins, self.l1_rounds):
                    self.start_level2(now)
                else:
                    self.start_round(now)
        elif s == "INTRO":
            if now >= self.level_t0:
                if self.level == 1:
                    self.start_round(now)
                    if self.state == "INTRO":            # a wand dropped out during the intro
                        self.go_lobby(now)
                elif self.level == 2:
                    self.set_state("SPELL", now)
                else:
                    self.start_l3_audio(now)
                    self.enter_round(now)
        elif s == "WARMUP":
            self.update_warmup(now)
        elif s == "CTUT":
            self.update_ctut(now)
        elif s == "PAUSED":
            self.update_paused(now)
        elif s == "SPELL":
            self.update_level2(now)
        elif s in ("ROUND", "SHOW", "WAIT", "INPUT", "SCORE"):
            self.update_level3(now)
        elif s == "LEVEL_RESULT":
            if self.only_level:
                if a.auto and now - self.state_t > LEVEL_RESULT_S and not self.quit_now():
                    self.start_match(now)
            elif now - self.state_t > LEVEL_RESULT_S:
                self.start_level3(now)
        elif s == "MATCH_END":
            if a.auto and now - self.state_t > 6.0 and not self.quit_now():
                self.start_match(now)

    def quit_now(self):
        """True when the --rounds / --matches limit has been reached."""
        a = self.args
        if self.only_level == 1:
            return bool(a.rounds) and self.rounds_played >= a.rounds
        if self.only_level:
            return bool(a.matches) and self.levels_played >= a.matches
        return bool(a.matches) and self.matches_played >= a.matches

    # ------------------------------------------------------------------
    # saving results (evidence for the report)
    # ------------------------------------------------------------------
    def save_score(self, r):
        if not self.save:
            return
        new = not os.path.exists(self.scores_path)
        try:
            with open(self.scores_path, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["time", "pattern", "bpm", "p1_bullets", "p1_ms", "p1_effective", "p1_foul",
                                "p2_bullets", "p2_ms", "p2_effective", "p2_foul", "winner", "reason",
                                "p1_name", "p2_name"])
                row = [dt.datetime.now().isoformat(timespec="seconds"), self.pattern, self.bpm]
                for i in range(2):
                    row += [self.players[i].bullets, _r(r.corrected_ms[i]), _r(r.effective_ms[i]), r.fouls[i]]
                row += ["tie" if r.winner is None else f"P{r.winner + 1}", r.reason, self.pname(0), self.pname(1)]
                w.writerow(row)
        except OSError as e:
            self.say(f"(could not write scores.csv: {e})")

    def save_match(self):
        if not self.save:
            return
        new = not os.path.exists(self.matches_path)
        try:
            with open(self.matches_path, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["time", "l1_p1_wins", "l1_p2_wins", "l2_p1_hp_start", "l2_p2_hp_start",
                                "l2_p1_hp_end", "l2_p2_hp_end", "l2_p1_casts", "l2_p2_casts", "l2_p1_blocks",
                                "l2_p2_blocks", "l3_start_pos", "l3_end_pos", "l3_rounds", "l3_p1_rounds_won",
                                "l3_p2_rounds_won", "l3_p1_perfect", "l3_p2_perfect", "champion", "p1_name", "p2_name"])
                d, b = self.duel, self.beam
                w.writerow([dt.datetime.now().isoformat(timespec="seconds"), *self.l1_wins,
                            *d.start_hp, *d.hp, *d.stats["casts"], *d.stats["blocks"],
                            round(b.start_pos), round(b.pos), self.round_no, *b.rounds_won, *b.perfect,
                            "none" if self.match_winner is None else f"P{self.match_winner + 1}",
                            self.pname(0), self.pname(1)])
        except (OSError, AttributeError) as e:
            self.say(f"(could not write matches.csv: {e})")

    def play_scheduled(self, now):
        while self.schedule and self.schedule[0][0] <= now:
            _, name, vol = self.schedule.pop(0)
            self.sounds.play(name, vol)

    # ------------------------------------------------------------------
    # keyboard
    # ------------------------------------------------------------------
    def end_screen(self):
        """True on the screens that show PLAY AGAIN / MAIN MENU buttons."""
        s = self.state
        return s == "MATCH_END" or (self.only_level and s == "LEVEL_RESULT") or (self.only_level == 1 and s == "RESULT")

    def on_mouse(self, kind, pos, now, amount=0):
        """Mouse: kind = 'move', 'click' (left), 'back' (right), 'wheel' (amount +1 up / -1 down)."""
        from menu import inside
        if kind != "wheel":
            self.mouse_pos = pos
        if self.editing is not None:
            return
        if self.state == "LOBBY":
            self.menu.on_mouse(kind, pos, now, amount)
        elif kind == "click" and self.end_screen():
            if inside(END_BUTTONS["again"], pos):
                self.on_key("space", now)
            elif inside(END_BUTTONS["menu"], pos):
                self.go_lobby(now)
        elif kind == "click" and self.state == "WARMUP" and inside(SKIP_BUTTON, pos):
            self.begin_duel(now)
        elif kind == "click" and self.state == "CTUT" and inside(SKIP_BUTTON, pos):
            self.after_cowboy_tutorial(now)

    def on_text(self, text):
        """Typed characters (pygame TEXTINPUT) while a player name is being edited."""
        if self.editing is None:
            return
        for ch in text:
            if (ch.isalnum() or ch in " -_.") and len(self.edit_buf) < NAME_MAX:
                self.edit_buf += ch

    def on_key(self, key_name, now):
        if self.editing is not None:                       # typing a name: keys don't control the game
            if key_name in ("return", "enter", "keypad enter"):
                name = self.edit_buf.strip()
                self.player_names[self.editing] = name or None
                self.say(f"P{self.editing + 1} is now {self.pname(self.editing)}")
                self.editing = None
            elif key_name == "escape":
                self.editing = None
            elif key_name == "backspace":
                self.edit_buf = self.edit_buf[:-1]
            return
        if key_name in ("1", "2") and self.state in ("LOBBY", "MATCH_END"):
            self.editing = int(key_name) - 1                # 1 / 2 = type that player's name
            self.edit_buf = ""                              # new player: start with an empty name
            return
        if self.args.sim and key_name in ("f1", "f2"):      # sim: pretend a wand froze and restarted
            self.link.drop(0 if key_name == "f1" else 1, 4.0)
            return
        if self.state == "LOBBY" and self.menu.on_key(key_name, now):
            return
        if key_name == "space" and self.state == "WARMUP":   # operator: skip the spell tutorial
            self.begin_duel(now)
            return
        if key_name == "space" and self.state == "CTUT":     # operator: skip the cowboy tutorial
            self.after_cowboy_tutorial(now)
            return
        if key_name == "escape" and self.state in ("MATCH_END", "LEVEL_RESULT", "RESULT"):
            self.go_lobby(now)
            return
        if key_name == "space":
            if self.state in ("LOBBY", "MATCH_END"):
                self.start_match(now)
            elif self.state == "RESULT" and self.only_level == 1:
                self.start_round(now)
            elif self.state == "LEVEL_RESULT" and self.only_level:
                self.start_match(now)
        elif key_name == "l" and not self.args.sim:
            self.go_lobby(now)
        elif key_name == "backspace":
            self.go_lobby(now)
        elif key_name == "n":
            self.skip_level(now)
        elif key_name == "v":
            on = not getattr(self.sounds, "voice_on", True)
            self.sounds.voice_on = on
            if not on:
                self.sounds.stop_voice()
            self.say(f"Announcer {'ON' if on else 'OFF'}")
        elif key_name == "c" and self.state == "LOBBY":
            for i in range(2):
                if self.connected[i]:
                    self.start_calibration(i)
        if self.args.sim:
            self.link.key(key_name)

    # ------------------------------------------------------------------
    # drawing (pixel-art scene from pixel_art.py + HUD on top)
    # ------------------------------------------------------------------
    def draw(self, screen, fonts, now):
        import pygame
        from pixel_art import Art
        if self.art is None:
            self.art = Art(pygame)
        art = self.art
        sw, sh = screen.get_size()
        half = sw // 2
        s = self.state
        desert = s == "LOBBY" or self.level == 1
        canvas = art.canvas("desert" if desert else "night")

        if s in ("INTRO", "WARMUP", "PAUSED"):
            self.scene_intro(canvas, now)
        elif s == "LOBBY":
            self.scene_cowboys(canvas, now)
        elif desert:
            self.scene_cowboys(canvas, now)
        elif s in ("SPELL",) or (s == "LEVEL_RESULT" and self.level == 2):
            self.scene_spell(canvas, now)
        else:
            self.scene_beam(canvas, now)
        art.present(screen, canvas)

        # ---- HUD ----
        art.text(screen, "BEAT-DRAW SHOWDOWN", (half, 32), GOLD, 16, 3)
        if s != "LOBBY":
            sub = LEVEL_TITLES[self.level]
            if self.level == 1 and not self.only_level:
                sub += f"   P1 {self.l1_wins[0]} - {self.l1_wins[1]} P2"
            art.text(screen, sub, (half, 66), INK, 14, 2)
        if s == "LOBBY":
            self.menu.draw(screen, now)
        elif s == "INTRO":
            self.hud_intro(screen, now)
        elif s == "WARMUP":
            self.hud_warmup(screen, now)
        elif s == "CTUT":
            self.hud_ctut(screen, now)
        elif s == "PAUSED":
            self.hud_paused(screen, now)
        elif desert:
            self.hud_cowboys(screen, now)
        elif s in ("SPELL",) or (s == "LEVEL_RESULT" and self.level == 2):
            self.hud_spell(screen, now)
        else:
            self.hud_beam(screen, now)

        big, col = self.center_text(now)
        if big and s != "INTRO":
            huge = s in ("DRAW", "MATCH_END")
            art.text(screen, big, (half, 118 if not huge else 125), col, 16, 5 if huge else 3)

        if s == "MATCH_END" and not self.only_level and now - self.state_t > 2.0:
            self.hud_stats(screen)
        if self.end_screen():
            self.menu.draw_button(screen, END_BUTTONS["again"], "PLAY AGAIN")
            self.menu.draw_button(screen, END_BUTTONS["menu"], "MAIN MENU")
        elif s in ("WARMUP", "CTUT"):
            self.menu.draw_button(screen, SKIP_BUTTON, "SKIP")
        if self.editing is not None:
            self.hud_name_entry(screen, now)
        hint = "N next level   V announcer   BACKSPACE main menu   F11 fullscreen"
        if s == "LOBBY":
            hint = "Mouse or UP / DOWN + ENTER   right-click / ESC back"
        elif s in ("MATCH_END", "LEVEL_RESULT") or (s == "RESULT" and self.only_level == 1):
            hint = "SPACE play again      BACKSPACE / ESC main menu      1 / 2 player names"
        elif s == "WARMUP":
            hint = "Spell tutorial - no timer.   SPACE = skip to the duel   BACKSPACE main menu"
        elif s == "CTUT":
            hint = "Cowboy tutorial - no timer.   SPACE = skip to the match   BACKSPACE main menu"
        elif self.args.sim:
            hint = ("P1: W A S D arrows  F draw/charge  Z X C spells   |   P2: I J K L arrows  H draw/charge  , . / spells"
                    "   |   F1/F2 drop a wand  BACKSPACE menu")
        if getattr(self.args, "demo", False):
            return                                          # clean screen for filming
        strip = pygame.Surface((sw, 26), pygame.SRCALPHA)
        strip.fill((10, 6, 10, 170))
        screen.blit(strip, (0, sh - 26))
        art.text(screen, hint, (half, sh - 13), (220, 210, 200), 18, 1, shadow=False)

    def hud_name(self, screen, i, cx, now):
        """Player name + battery level (every screen)."""
        r = self.art.text(screen, f"P{i + 1}  {self.player_names[i] or self.names[i]}", (cx, 165), P_COLORS[i], 14, 2)
        pct = self.battery[i]
        if pct is not None:
            low = pct <= BATT_LOW_PCT
            if not low or int(now * 2) % 2:                 # low battery blinks
                self.art.battery(screen, r.right + 16, 165, pct, low)

    def center_text(self, now):
        s = self.state
        if s == "LOBBY":
            return "", INK                                  # the menu draws itself
        if s == "DRUM":
            rel = now - self.t_beat0
            if rel < 0:
                return str(int(-rel // self.beat_s) + 1), INK
            return ("AIR DRUM!" if rel < len(self.pattern) * self.beat_s else "..."), GOLD
        if s == "HOLSTER":
            return "HOLSTER!", GOLD
        if s == "STANDOFF":
            return "steady...", RED
        if s == "DRAW":
            return ("DRAW!", GREEN) if now >= self.draw_shown_at else ("steady...", RED)
        if s == "RESULT" and self.result:
            r = self.result
            if r.winner is None:
                return r.reason, INK
            return f"{self.pname(r.winner).upper()} WINS THE DRAW", P_COLORS[r.winner]
        if s == "SPELL":
            return f"{self.duel.time_left(now):.0f}", INK
        if s == "ROUND":
            sd = self.round_no >= L3_MAX_ROUNDS
            if sd:
                return f"SUDDEN DEATH {self.round_no + 1 - L3_MAX_ROUNDS}  -  5 SPELLS!", RED
            if self.round_no + 1 == L3_MAX_ROUNDS:
                return "FINAL ROUND  -  5 SPELLS!", RED
            return f"ROUND {self.round_no + 1} / {L3_MAX_ROUNDS}", GOLD
        if s == "SHOW":
            return ("WATCH ALL 5!" if len(self.combo) > 3 else "WATCH THE COMBO!"), GOLD
        if s == "WAIT":
            return f"{max(1, int(COMBO_WAIT_S - (now - self.state_t)) + 1)}...", INK
        if s == "INPUT":
            return "GO!  CAST THE COMBO", GREEN
        if s == "SCORE":
            w = self.round_result[0] if self.round_result else None
            return (f"{self.pname(w).upper()} WINS THE ROUND" if w is not None else "TIE ROUND"), (P_COLORS[w] if w is not None else INK)
        if s in ("LEVEL_RESULT", "MATCH_END"):
            w = self.match_winner if (self.level == 3) else self.l2_winner
            return self.level_msg, (P_COLORS[w] if w is not None else INK)
        return "", INK

    # ---- positions on the 160 x 90 canvas ----
    COWBOY_X = (32, 112)
    WIZARD_X_L2 = (18, 126)
    WIZARD_X_L3 = (4, 140)

    def scene_cowboys(self, canvas, now):
        art, s = self.art, self.state
        if s in ("LOBBY", "HOLSTER", "STANDOFF"):
            art.tumbleweed(canvas, now)
        r = self.result if s == "RESULT" else None
        cur_beat = int((now - self.t_beat0) // self.beat_s) if s == "DRUM" else -1
        for i in range(2):
            p = self.players[i]
            pose = "idle"
            if (s == "DRAW" or (s == "CTUT" and self.ctut_phase in ("draw", "results"))) and p.draw_us is not None:
                pose = "flash" if now - self.shot_t[i] < 0.25 else "aim"
            elif r is not None:
                if r.fouls[i]:
                    pose = "idle"
                elif r.winner is None:
                    pose = "aim" if r.corrected_ms[i] is not None else "idle"
                else:
                    pose = "aim" if r.winner == i else "down"
            bob = 1 if (s == "DRUM" and now - self.flash[i][0] < 0.12) else 0
            art.cowboy(canvas, i, pose, self.COWBOY_X[i], now, bob)
            if s != "LOBBY":
                art.bullets(canvas, self.COWBOY_X[i] + 8, 50, self.live_bullets[i])
            if r is not None and r.fouls[i]:                     # smoke puff from a jammed gun
                rng = random.Random(int(now * 8) + i)
                for _ in range(6):
                    canvas.set_at((self.COWBOY_X[i] + 8 + rng.randint(-5, 5), 56 + rng.randint(-4, 2)),
                                  (200, 200, 200))
        _ = cur_beat

    def hud_cowboys(self, screen, now):
        import pygame
        art, s = self.art, self.state
        drumming = s == "DRUM" or (s == "CTUT" and self.ctut_phase in ("beat", "beat_done"))
        cur_beat = int((now - self.t_beat0) // self.beat_s) if drumming else -1
        for i in range(2):
            cx = 320 if i == 0 else 960
            p = self.players[i]
            col = P_COLORS[i]
            self.hud_name(screen, i, cx, now)
            lat = self.latency[i]
            stat = self.status[i] + (f"   ~{lat:.0f} ms" if lat is not None else
                                     ("   measuring..." if self.connected[i] else ""))
            art.text(screen, stat, (cx, 192), (90, 60, 50), 18, 1, shadow=False)
            if s == "LOBBY":
                if self.drops[i]:
                    art.text(screen, f"dropped {self.drops[i]}x this session (see disconnects.csv)",
                             (cx, 212), RED, 18, 1, shadow=False)
                continue
            if drumming:
                self.hud_highway(screen, i, cx, now)
            t_flash, msg = self.flash[i]
            if now - t_flash < 0.6 and msg and not drumming:
                art.text(screen, msg, (cx, 300), GREEN if msg.startswith("HIT") else RED, 14, 2)
            if s == "RESULT" and self.result:
                r = self.result
                if r.fouls[i]:
                    line = "FOUL - gun jammed"
                elif r.corrected_ms[i] is None:
                    line = "no draw"
                else:
                    line = (f"{r.corrected_ms[i]:.0f} ms - {p.bullets} x {BULLET_BONUS_MS}"
                            f" = {r.effective_ms[i]:.0f} ms")
                art.plate(screen, (cx - 240, 318, 480, 44))
                art.text(screen, line, (cx, 340), INK if r.winner == i else (200, 190, 180), 14, 2)
        if s == "RESULT" and self.result:
            self.hud_replay(screen, now)
        if s == "DRUM" or (s == "CTUT" and self.ctut_phase == "beat"):
            self.hud_big_arrow(screen, now)

    # ---- Level 1 note highway (v5.7): 4 lanes, arrows fall onto a hit line exactly on their beat ----
    LANES = "LDUR"                      # left to right, like Dance Dance Revolution
    HW_TOP, HW_HIT, HW_PX_BEAT = 200, 382, 70   # top of the highway, the hit line (y), pixels per beat
    RATING_COL = {"PERFECT": (255, 214, 70), "GOOD": (110, 220, 130), "MISS": (230, 80, 60)}

    def hud_highway(self, screen, i, cx, now):
        import pygame
        art, p = self.art, self.players[i]
        col_w, gap = 52, 6
        w = 4 * col_w + 3 * gap
        x0 = cx - w // 2
        top, hit_y, ppb = self.HW_TOP, self.HW_HIT, self.HW_PX_BEAT
        bs = self.beat_s
        # dark glass panel + lanes
        ph = hit_y - top + 16
        panel = pygame.Surface((w + 20, ph), pygame.SRCALPHA)
        panel.fill((20, 11, 9, 205))
        for c in range(4):
            pygame.draw.rect(panel, (58, 34, 26, 150), (10 + c * (col_w + gap), 0, col_w, ph))
        screen.blit(panel, (x0 - 10, top))
        # beat lines scroll down with the music (brighter on each bar), so you can SEE the tempo
        for k in range(-COUNT_IN_BEATS, len(self.pattern) + 1):
            y = hit_y - (self.t_beat0 + k * bs - now) / bs * ppb
            if top <= y <= hit_y + 14:
                bar = k % 4 == 0
                pygame.draw.line(screen, (150, 110, 80) if bar else (90, 62, 48), (x0, int(y)), (x0 + w, int(y)),
                                 3 if bar else 1)
        # the hit line + 4 receptors (they light up when you hit that lane)
        lit_t, lit_r, lit_k = self.rating[i]
        lit_g = self.pattern[lit_k] if lit_k is not None and 0 <= lit_k < len(self.pattern) else None
        pygame.draw.rect(screen, (255, 240, 200), (x0 - 6, hit_y - 2, w + 12, 4))
        for c, g in enumerate(self.LANES):
            lx = x0 + c * (col_w + gap) + col_w // 2
            glow = g == lit_g and now - lit_t < 0.15 and lit_r != "MISS"
            if glow:
                pygame.draw.rect(screen, self.RATING_COL[lit_r], (lx - 26, hit_y - 26, 52, 52))
            art.arrow(screen, g, (lx, hit_y), 5, (255, 250, 235) if glow else (95, 70, 58), outline=not glow)
        # falling notes
        for k, g in enumerate(self.pattern):
            if g == "-":
                continue
            t_k = self.t_beat0 + k * bs
            y = hit_y - (t_k - now) / bs * ppb
            if y < top + 14 or y > hit_y + 12:
                continue
            res = p.hits.get(k)
            if res is True:
                continue                                      # hit: it vanished into the receptor
            lx = x0 + self.LANES.index(g) * (col_w + gap) + col_w // 2
            missed = res is False or k in self.passed[i]
            art.arrow(screen, g, (lx, int(y)), 5, (110, 90, 85) if missed else None)
        # rating popup (rises and fades) + combo
        t_r, r, _ = self.rating[i]
        if r and now - t_r < 0.6:
            a = now - t_r
            art.text(screen, r, (cx, hit_y - 50 - int(a * 40)), self.RATING_COL[r], 16, 3)
        if self.combo[i] >= 2:
            art.text(screen, f"COMBO {self.combo[i]}", (cx, top + 18), GOLD, 14, 2)
        _ = PERFECT_MS

    def update_passed_notes(self, now):
        """A note that went past the hit window without a hit = MISS (popup + combo reset)."""
        late = (HIT_WINDOW_MS + 120) / 1000 + self.mean_latency_ms() / 1000
        for i in range(2):
            p = self.players[i]
            for k, g in enumerate(self.pattern):
                if g == "-" or k in p.hits or k in self.passed[i]:
                    continue
                if now > self.t_beat0 + k * self.beat_s + late:
                    self.passed[i].add(k)
                    self.rating[i] = (now, "MISS", k)
                    self.combo[i] = 0

    def hud_big_arrow(self, screen, now):
        """One BIG arrow between the two lanes: the move for this beat (or the first move during the count-in)."""
        import pygame
        art = self.art
        rel = now - self.t_beat0
        k = int((rel + self.beat_s / 2) // self.beat_s)       # the beat we are closest to
        if rel < -self.beat_s / 2:
            k = 0
        if not 0 <= k < len(self.pattern):
            return
        g = self.pattern[k]
        art.plate(screen, (566, 178, 148, 148), alpha=200)
        if g == "-":
            art.text(screen, "rest", (640, 252), (200, 190, 180), 14, 2)
        else:
            pulse = 1 if (rel >= -self.beat_s / 2 and abs(rel - k * self.beat_s) < 0.08) else 0   # throb on the beat
            art.arrow(screen, g, (640, 240), 11 + pulse)
            art.text(screen, DIRECTION_NAMES[g], (640, 306), INK, 14, 2)
        nxt = next((c for c in self.pattern[k + 1:] if c != "-"), None) if rel >= -self.beat_s / 2 else None
        if nxt:
            art.text(screen, "next", (606, 346), (60, 40, 30), 14, 2, shadow=False)
            art.arrow(screen, nxt, (650, 346), 4)
        elif rel < -self.beat_s / 2:
            art.text(screen, "first move", (640, 346), (60, 40, 30), 14, 2, shadow=False)
        _ = pygame

    def hud_replay(self, screen, now):
        """Draw replay: two bars race - each stops at that player's time (bullets already taken off)."""
        import pygame
        art, r = self.art, self.result
        x0, y0, bw = 455, 392, 370
        art.plate(screen, (x0 - 25, y0 - 22, bw + 50, 150))
        art.text(screen, "DRAW REPLAY", (x0 + bw // 2, y0 - 2), GOLD, 14, 2)
        times = [v for v in list(r.corrected_ms) + list(r.effective_ms) if v is not None]
        scale = max([400.0] + times) * 1.08                    # ms that fill the whole bar
        clock = (now - self.state_t) / REPLAY_S * scale        # the race clock (ms)
        for i in range(2):
            y = y0 + 22 + i * 46
            pygame.draw.rect(screen, (40, 25, 20), (x0, y, bw, 30))
            if r.fouls[i] or r.effective_ms[i] is None:
                art.text(screen, f"{self.pname(i)}: {'FOUL' if r.fouls[i] else 'no draw'}",
                         (x0 + bw // 2, y + 15), RED, 14, 2)
                continue
            eff, raw = max(0.0, r.effective_ms[i]), r.corrected_ms[i]
            ghost = min(clock, raw) / scale * bw               # reaction time (light)
            solid = min(clock, eff) / scale * bw               # minus the bullet bonus (solid)
            pygame.draw.rect(screen, tuple(c // 2 for c in P_COLORS[i]), (x0, y, int(ghost), 30))
            pygame.draw.rect(screen, P_COLORS[i], (x0, y, int(solid), 30))
            label = self.pname(i)
            if clock >= eff:
                label += f"  {r.effective_ms[i]:.0f} ms" + ("  WIN!" if r.winner == i else "")
            art.text(screen, label, (x0 + 8 + art.text_width(label, 14, 2) // 2, y + 15), INK, 14, 2)

    def hud_stats(self, screen):
        """End-of-match numbers (also good evidence for the report)."""
        art, st, d, b = self.art, self.stats, self.duel, self.beam
        x0, y0 = 300, 200
        art.plate(screen, (x0, y0, 680, 324), alpha=200)
        art.text(screen, "MATCH STATS", (640, y0 + 24), GOLD, 14, 2)
        pct = lambda a, n: f"{100 * a / n:.0f}%" if n else "-"          # noqa: E731
        rows = [("Draws won", [str(v) for v in st["draws_won"]]),
                ("Best draw time", [f"{v:.0f} ms" if v is not None else "-" for v in st["best_draw"]]),
                ("Beat accuracy", [pct(v, st["notes"]) for v in st["beat_hits"]]),
                ("Perfect hits / best combo", [f"{st['perfect'][i]} / {st['best_combo'][i]}" for i in range(2)]),
                ("Fouls", [str(v) for v in st["fouls"]])]
        if d is not None:
            rows.append(("Spells cast / landed", [f"{d.stats['casts'][i]} / {d.stats['hits'][i]}" for i in range(2)]))
            rows.append(("Spells blocked", [str(v) for v in d.stats["blocks"]]))
        if b is not None:
            rows.append(("Combo accuracy", [pct(v, st["combo_spells"]) for v in st["combo_right"]]))
            rows.append(("Perfect combos", [str(v) for v in b.perfect]))
        rows.append(("Fizzles", [str(v) for v in st["fizzles"]]))
        for i in range(2):
            art.text(screen, self.pname(i), (720 + 170 * i, y0 + 56), P_COLORS[i], 14, 2)
        for n, (label, vals) in enumerate(rows):
            y = y0 + 84 + 24 * n
            art.text(screen, label, (x0 + 30 + art.text_width(label, 18, 1) // 2, y), INK, 18, 1, shadow=False)
            for i in range(2):
                art.text(screen, vals[i], (720 + 170 * i, y), INK, 18, 1, shadow=False)

    def hud_name_entry(self, screen, now):
        art, i = self.art, self.editing
        cx = 320 if i == 0 else 960
        art.plate(screen, (cx - 250, 200, 500, 100), alpha=220, border=P_COLORS[i])
        cursor = "_" if int(now * 2) % 2 else " "
        art.text(screen, f"P{i + 1} name: {self.edit_buf}{cursor}", (cx, 232), INK, 14, 2)
        art.text(screen, "type, then ENTER = save   ESC = cancel", (cx, 272), (220, 210, 200), 18, 1, shadow=False)

    def hud_warmup(self, screen, now):
        """Spell tutorial: each player's own card - big symbol, animated wand doing the move, progress."""
        import pygame
        art = self.art
        art.text(screen, "LEARN YOUR SPELLS  -  no timer, take your time", (640, 100), GOLD, 14, 2)
        for i in range(2):
            cx = 320 if i == 0 else 960
            tut = self.tut[i]
            art.plate(screen, (cx - 300, 122, 600, 352), alpha=200, border=P_COLORS[i])
            art.text(screen, f"P{i + 1}  {self.player_names[i] or self.names[i]}", (cx, 146), P_COLORS[i], 14, 2)
            for k, sp in enumerate(tut.order):              # the 3 steps: done / now / next
                x = cx + 190 + (k - 1) * 40
                border = GREEN if k < tut.step else (GOLD if k == tut.step else (110, 100, 110))
                art.slot(screen, (x - 17, 129, 34, 34), border)
                art.icon(screen, sp, (x, 146), 2)
            if tut.done:
                art.text(screen, "READY!", (cx, 260), GREEN, 16, 5)
                other = 1 - i
                wait = (f"waiting for {self.pname(other)}..." if not self.tut[other].done
                        else "both ready - here comes the duel!")
                art.text(screen, wait, (cx, 340), INK, 14, 2)
                for k, sp in enumerate(tut.order):
                    art.icon(screen, sp, (cx + (k - 1) * 90, 410), 5)
                continue
            sp = tut.spell
            col = SPELL_COLORS[sp]
            art.slot(screen, (cx - 280, 176, 150, 150), col)    # the element symbol
            art.icon(screen, sp, (cx - 205, 251), 10)
            art.text(screen, SPELL_NAMES[sp], (cx - 205, 346), col, 14, 2)
            box = pygame.Rect(cx - 112, 176, 392, 150)          # the move, animated
            pygame.draw.rect(screen, (24, 18, 30), box)
            art.move_demo(screen, sp, box.center, now - self.tut_t[i], size=(box.w, box.h),
                          facing=1 if i == 0 else -1)
            art.text(screen, f"= {MOVES[sp]}", (cx + 84, 346), INK, 14, 2)
            art.text(screen, SPELL_TIPS[sp], (cx, 378), (230, 225, 210), 18, 1, shadow=False)
            for k in range(tut.repeats):                        # landed 0/2, 1/2 ...
                x = cx - 20 * (tut.repeats - 1) + k * 40
                pygame.draw.rect(screen, (40, 25, 20), (x - 14, 398, 28, 28))
                if k < tut.count:
                    pygame.draw.rect(screen, col, (x - 11, 401, 22, 22))
            art.text(screen, f"cast it {tut.repeats}x", (cx + 100, 412), (200, 190, 180), 18, 1, shadow=False)
            t_flash, msg = self.flash[i]
            if now - t_flash < 1.8 and msg:
                good = msg.startswith(("GOOD", "ALL")) or "LEARNED" in msg
                art.text(screen, msg, (cx, 450), GREEN if good else RED, 14, 2)

    def hud_ctut(self, screen, now):
        """Cowboy tutorial: step tracker + the screen for the current step."""
        art, ph = self.art, self.ctut_phase
        art.text(screen, "COWBOY SCHOOL  -  no timer, take your time", (640, 100), GOLD, 14, 2)
        cur = {"arrows": 0, "beat": 1, "beat_done": 1, "holster": 2, "draw": 3, "results": 3}.get(ph, 0)
        for k, label in enumerate(("1 ARROWS", "2 BEAT", "3 HOLSTER", "4 DRAW")):
            col = GREEN if k < cur else (GOLD if k == cur else (110, 85, 75))
            x = 640 + int((k - 1.5) * 190)
            art.text(screen, label, (x, 128), col, 14, 2)
            if k < 3:
                art.text(screen, ">", (x + 95, 128), (110, 85, 75), 14, 2)
        if ph in ("beat", "beat_done"):
            self.hud_cowboys(screen, now)                      # lanes + big arrow, like the real thing
            art.text(screen, "PRACTICE BEAT  -  slow, and it doesn't count", (640, 390), INK, 14, 2)
            if ph == "beat_done":
                for i in range(2):
                    n = self.ctut_beat_score[i]
                    total = sum(c != "-" for c in CTUT_PATTERN)
                    art.text(screen, f"{n} / {total} arrows", (320 if i == 0 else 960, 310),
                             GREEN if n == total else (GOLD if n else RED), 16, 3)
            return
        for i in range(2):
            cx = 320 if i == 0 else 960
            if ph == "arrows":
                self._ctut_arrow_card(screen, i, cx, now)
            elif ph == "holster":
                self._ctut_holster_card(screen, i, cx, now)
            else:
                self._ctut_draw_card(screen, i, cx, now)
        if ph == "draw":
            if not self.ctut_cue_sent:
                art.text(screen, "steady...", (640, 420), RED, 16, 3)
            else:
                art.text(screen, "DRAW!", (640, 420), GREEN, 16, 5)
        elif ph == "results":
            art.text(screen, "Get ready for the real thing!", (640, 420), GOLD, 16, 3)

    def _ctut_arrow_card(self, screen, i, cx, now):
        import pygame
        art, tut = self.art, self.ctut[i]
        art.plate(screen, (cx - 300, 145, 600, 330), alpha=200, border=P_COLORS[i])
        art.text(screen, f"P{i + 1}  {self.player_names[i] or self.names[i]}", (cx - 120, 166), P_COLORS[i], 14, 2)
        for k, d in enumerate(tut.order):                     # the 4 steps: done / now / next
            x = cx + 160 + int((k - 1.5) * 38)
            border = GREEN if k < tut.step else (GOLD if k == tut.step else (110, 100, 110))
            art.slot(screen, (x - 15, 151, 30, 30), border)
            art.arrow(screen, d, (x, 166), 3, outline=False)
        if tut.done:
            art.text(screen, "READY!", (cx, 270), GREEN, 16, 5)
            other = 1 - i
            art.text(screen, f"waiting for {self.pname(other)}..." if not self.ctut[other].done
                     else "both ready - practice beat next!", (cx, 350), INK, 14, 2)
            return
        d = tut.spell
        art.slot(screen, (cx - 280, 196, 150, 150), art.ARROW_RGB[d])
        art.arrow(screen, d, (cx - 205, 271), 12)
        art.text(screen, DIRECTION_NAMES[d], (cx - 205, 366), art.ARROW_RGB[d], 14, 2)
        box = pygame.Rect(cx - 112, 196, 392, 150)
        pygame.draw.rect(screen, (24, 18, 30), box)
        art.move_demo(screen, "a" + d, box.center, now - self.ctut_step_t[i], size=(box.w, box.h))
        art.text(screen, f"= FLICK {DIRECTION_NAMES[d]}", (cx + 84, 366), INK, 14, 2)
        art.text(screen, FLICK_TIP, (cx, 394), (230, 225, 210), 18, 1, shadow=False)
        for k in range(tut.repeats):
            x = cx - 20 * (tut.repeats - 1) + k * 40
            pygame.draw.rect(screen, (40, 25, 20), (x - 14, 410, 28, 28))
            if k < tut.count:
                pygame.draw.rect(screen, art.ARROW_RGB[d], (x - 11, 413, 22, 22))
        art.text(screen, "flick it 2x", (cx + 100, 424), (200, 190, 180), 18, 1, shadow=False)
        t_flash, msg = self.flash[i]
        if now - t_flash < 1.8 and msg:
            good = msg.startswith(("GOOD", "ALL")) or "done" in msg
            art.text(screen, msg, (cx, 456), GREEN if good else RED, 14, 2)

    def _still_meter(self, screen, i, cx, y):
        """20 blocks: how much the wand moves right now. Past the white line (10) = a FOUL in a real round."""
        import pygame
        art, n = self.art, self.still_n[i]
        for k in range(20):
            x = cx - 200 + k * 20
            on = k < n
            col = (GREEN if k < STILL_FOUL else RED) if on else (55, 40, 35)
            pygame.draw.rect(screen, col, (x, y, 18, 26))
        pygame.draw.rect(screen, (255, 250, 235), (cx - 200 + STILL_FOUL * 20 - 2, y - 6, 3, 38))
        art.text(screen, "FOUL LINE", (cx - 200 + STILL_FOUL * 20, y + 44), (230, 225, 210), 18, 1, shadow=False)

    def _ctut_holster_card(self, screen, i, cx, now):
        import pygame
        art = self.art
        art.plate(screen, (cx - 280, 145, 560, 330), alpha=200, border=P_COLORS[i])
        art.text(screen, f"P{i + 1}  {self.player_names[i] or self.names[i]}", (cx, 168), P_COLORS[i], 14, 2)
        if self.still_done[i]:
            art.text(screen, "FROZEN!", (cx, 270), GREEN, 16, 5)
            other = 1 - i
            art.text(screen, f"waiting for {self.pname(other)}..." if not self.still_done[other]
                     else "both frozen - practice draw next!", (cx, 350), INK, 14, 2)
            return
        art.text(screen, "Wand DOWN at your side... then FREEZE!", (cx, 200), INK, 14, 2)
        art.text(screen, "how much you move:", (cx, 232), (200, 190, 180), 18, 1, shadow=False)
        self._still_meter(screen, i, cx, 248)
        art.text(screen, f"frozen {self.still_t[i]:.1f} / {CTUT_STILL_S:.0f} s", (cx, 336), INK, 14, 2)
        pygame.draw.rect(screen, (40, 25, 20), (cx - 200, 354, 400, 24))
        pygame.draw.rect(screen, GOLD, (cx - 200, 354, int(400 * min(1.0, self.still_t[i] / CTUT_STILL_S)), 24))
        art.text(screen, "In a real round, moving past the line before DRAW = FOUL!", (cx, 404), (200, 190, 180),
                 18, 1, shadow=False)
        t_flash, msg = self.flash[i]
        if now - t_flash < 1.2 and msg.startswith("MOVED"):
            art.text(screen, msg, (cx, 444), RED, 14, 2)

    def _ctut_draw_card(self, screen, i, cx, now):
        art = self.art
        art.plate(screen, (cx - 240, 145, 480, 220), alpha=200, border=P_COLORS[i])
        art.text(screen, f"P{i + 1}  {self.player_names[i] or self.names[i]}", (cx, 168), P_COLORS[i], 14, 2)
        res = self.ctut_draw[i]
        if not self.ctut_cue_sent:
            art.text(screen, "Holster & freeze... wait for DRAW!", (cx, 205), INK, 14, 2)
            self._still_meter(screen, i, cx, 236)
        elif res is None:
            art.text(screen, "DRAW!  flick the wand UP!", (cx, 240), GREEN, 14, 2)
        elif res == "slow":
            art.text(screen, "TOO SLOW", (cx, 240), RED, 16, 3)
        else:
            art.text(screen, f"BANG!  {res:.0f} ms", (cx, 240), GOLD, 16, 3)
        if self.ctut_early[i]:
            art.text(screen, "You moved before DRAW - in a real round that's a FOUL!", (cx, 330), RED, 18, 1,
                     shadow=False)

    def hud_paused(self, screen, now):
        art = self.art
        art.plate(screen, (290, 140, 700, 320), alpha=210, border=RED)
        art.text(screen, "PAUSED", (640, 185), RED, 16, 4)
        y = 245
        for i in range(2):
            if self.connected[i] and self.latency[i] is not None:
                continue
            gone = now - self.drop_t[i] if self.drop_t[i] is not None else 0.0
            what = "measuring Bluetooth..." if self.connected[i] else f"reconnecting... {gone:.0f} s"
            art.text(screen, f"{self.pname(i)} {what}", (640, y), P_COLORS[i], 14, 2)
            y += 34
        if self.resume_at is not None:
            art.text(screen, "Both wands are back - carrying on!", (640, y), GREEN, 14, 2)
        for n, line in enumerate(["The round that was cut off is played again.",
                                  "Wand stuck? Switch it off and on.   BACKSPACE = back to lobby"]):
            art.text(screen, line, (640, 395 + 26 * n), (220, 210, 200), 18, 1, shadow=False)

    def scene_spell(self, canvas, now):
        art, d = self.art, self.duel
        xs = self.WIZARD_X_L2
        done = self.state == "LEVEL_RESULT"
        for i in range(2):
            pose = "idle"
            if done and self.l2_winner is not None:
                pose = "cast" if self.l2_winner == i else "down"
            elif now - self.cast_t[i] < 0.5:
                pose = "cast"
            elif now - self.charge_t[i] < 1.3:
                pose = "charge"
            art.wizard(canvas, i, pose, xs[i], now, hurt=now - self.hurt_t[i] < 0.5)
            cx = 40 if i == 0 else 120
            art.hearts(canvas, cx, 26, d.hp[i], max(d.start_hp))
            art.crystals(canvas, cx, 35, self.mana[i], MAX_MANA)
        tip = [art.wand_tip(0, xs[0]), art.wand_tip(1, xs[1])]
        for pr in d.flying:
            prog = pr.progress(now)
            x0, x1 = tip[pr.owner][0], tip[1 - pr.owner][0]
            y = tip[0][1] + (-2 if pr.owner == 0 else 2)
            art.spell(canvas, pr.spell, x0 + (x1 - x0) * prog, y, flip=pr.owner == 1, now=now)
        self.bursts = [b for b in self.bursts if now - b[0] < 0.6]
        for t0, where, c in self.bursts:
            art.burst(canvas, tip[0][0] + (tip[1][0] - tip[0][0]) * where, tip[0][1], (now - t0) / 0.6, c)

    def hud_spell(self, screen, now):
        art = self.art
        for i in range(2):
            cx = 320 if i == 0 else 960
            self.hud_name(screen, i, cx, now)
            t_flash, msg = self.flash[i]
            if now - t_flash < 0.9 and msg:
                art.text(screen, msg, (cx, 350), INK, 14, 2)
        art.plate(screen, (190, 392, 900, 36), alpha=140)
        art.text(screen, "LIGHTNING > WATER > FIRE > LIGHTNING      zig-zag / circle / thrust      wand UP = mana",
                 (640, 410), (230, 225, 255), 18, 1, shadow=False)

    def scene_beam(self, canvas, now):
        art, b = self.art, self.beam
        if b is None:
            return
        xs = self.WIZARD_X_L3
        end = self.state in ("MATCH_END", "LEVEL_RESULT")
        calm = self.state in ("SHOW", "WAIT")              # beam holds still while you memorise
        w = self.match_winner
        for i in range(2):
            pose = "cast"
            if end and w is not None:
                pose = "cast" if w == i else "down"
            elif self.state == "INPUT" and now - self.cast_t[i] < 0.4:
                pose = "charge"
            art.wizard(canvas, i, pose, xs[i], now)
        if end:
            if w is not None:
                art.confetti(canvas, now)
            return
        tl, tr = art.wand_tip(0, xs[0]), art.wand_tip(1, xs[1])
        y = tl[1] - 2
        cx = tl[0] + (tr[0] - tl[0]) * self.beam_draw / 100
        col = [(200, 230, 255)] * 2 if calm else [P_MAIN_RGB[0], P_MAIN_RGB[1]]
        art.beam(canvas, tl[0], cx, y, col[0], now, calm, seed=1)
        art.beam(canvas, cx, tr[0], y, col[1], now, calm, seed=2)
        art.clash(canvas, cx, y, now, calm)

    def hud_beam(self, screen, now):
        art, b = self.art, self.beam
        if b is None:
            return
        sw = screen.get_size()[0]
        half = sw // 2
        st = self.state
        # the combo: 3 big slots in the middle
        if st in ("SHOW", "WAIT", "INPUT", "SCORE"):
            n = len(self.combo)
            big, step, top = (100, 120, 245) if n <= 3 else (80, 92, 330)   # 5 spells: smaller, under the players' rows
            for k in range(n):
                cx = half + int((k - (n - 1) / 2) * step)
                cy = top + big // 2
                shown = (st == "SHOW" and now >= self.show_t0 + k * self.show_fl) or st == "SCORE"
                lit = st == "SHOW" and self.show_t0 + k * self.show_fl <= now < self.show_t0 + (k + 1) * self.show_fl
                art.slot(screen, (cx - big // 2, top, big, big), SPELL_COLORS[self.combo[k]] if lit else (250, 230, 190))
                if shown:
                    art.icon(screen, self.combo[k], (cx, cy), (10 if lit else 8) if n <= 3 else (8 if lit else 6))
                else:
                    art.text(screen, "?", (cx, cy), (200, 190, 220), 16, 4 if n <= 3 else 3)
        for i in range(2):
            cx = 320 if i == 0 else 960
            self.hud_name(screen, i, cx, now)
            if st == "MATCH_END":
                continue
            art.text(screen, f"rounds won {b.rounds_won[i]}", (cx, 195), INK, 18, 1)
            t_flash, msg = self.flash[i]
            if st == "INPUT" and msg.startswith("FIZZLE") and now - t_flash < 1.5:
                art.text(screen, msg, (cx, 300), RED, 18, 1, shadow=False)
            if st in ("INPUT", "SCORE"):                    # what this player cast so far
                e = self.entries[i]
                n = len(self.combo)
                step = 64 if n <= 3 else 52
                for k in range(n):
                    x = cx + int((k - (n - 1) / 2) * step)
                    border = (250, 230, 190)
                    if st == "SCORE" and k < len(e.spells):
                        border = GREEN if e.spells[k] == self.combo[k] else RED
                    elif st == "SCORE":
                        border = RED
                    sz = 56 if n <= 3 else 46
                    art.slot(screen, (x - sz // 2, 215, sz, sz), border)
                    if k < len(e.spells):
                        art.icon(screen, e.spells[k], (x, 215 + sz // 2), 5 if n <= 3 else 4)
                if st == "SCORE":
                    t_flash, msg = self.flash[i]
                    if msg:
                        art.text(screen, msg, (cx, 300), GREEN if msg == "PERFECT!" else INK, 14, 2)
        t_h, h_text, h_col = self.hype
        if now - t_h < HYPE_S and h_text and st in ("ROUND", "SCORE"):
            art.text(screen, h_text, (half, 400 if len(self.combo) <= 3 else 455), h_col, 16, 3)

    def scene_intro(self, canvas, now):
        art = self.art
        if self.level == 1:
            for i in range(2):
                art.cowboy(canvas, i, "idle", self.COWBOY_X[i], now)
        else:
            xs = self.WIZARD_X_L2 if self.level == 2 else self.WIZARD_X_L3
            for i in range(2):
                art.wizard(canvas, i, "charge" if self.level == 2 else "idle", xs[i], now)

    def hud_intro(self, screen, now):
        art = self.art
        sw = screen.get_size()[0]
        half = sw // 2
        art.plate(screen, (half - 470, 130, 940, 330))
        art.text(screen, LEVEL_TITLES[self.level], (half, 180), GOLD, 16, 4)
        for n, line in enumerate(LEVEL_RULES.get(self.level, [])):
            art.text(screen, line, (half, 250 + 38 * n), INK, 14, 2)
        if self.level_msg:
            art.text(screen, self.level_msg, (half, 380), GREEN, 14, 2)
        left = max(0.0, self.level_t0 - now)
        art.text(screen, str(int(left) + 1), (half, 425), INK, 16, 3)


def _spell_sound(spell):
    return {"L": "zap", "W": "water", "F": "fire"}[spell]


def _fmt(vals):
    return [None if v is None else round(v) for v in vals]


def _r(v):
    return "" if v is None else f"{v:.1f}"


def _text(screen, font, text, center, color):
    surf = font.render(text, True, color)
    screen.blit(surf, surf.get_rect(center=(int(center[0]), int(center[1]))))


# ======================================================================
def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Beat-Draw Showdown arena referee")
    ap.add_argument("--names", nargs=2, default=["BDS-1", "BDS-2"], help="Bluetooth names of the two wands")
    ap.add_argument("--level", type=int, choices=[0, 1, 2, 3], default=0,
                    help="play only this level (0 = full 3-level match)")
    ap.add_argument("--bpm", type=int, default=None, help="Level 1 beat (default: SETTINGS > DIFFICULTY = 90)")
    ap.add_argument("--sim", action="store_true", help="no hardware: simulated wands")
    ap.add_argument("--bots", action="store_true", help="(sim) both players are bots")
    ap.add_argument("--bot2", action="store_true", help="(sim) player 2 is a bot")
    ap.add_argument("--auto", action="store_true", help="start rounds/matches automatically")
    ap.add_argument("--rounds", type=int, default=0, help="(--level 1) quit after N rounds (0 = never)")
    ap.add_argument("--matches", type=int, default=0, help="quit after N matches (or N levels with --level 2/3)")
    ap.add_argument("--headless", action="store_true", help="no window/sound (for automated tests)")
    ap.add_argument("--fast", action="store_true", help="(sim) headless + fake clock: runs a match in seconds")
    ap.add_argument("--mute", action="store_true")
    ap.add_argument("--no-voice", action="store_true", help="no announcer (V toggles it during play)")
    ap.add_argument("--no-warmup", action="store_true", help="skip the Level 2 warm-up")
    ap.add_argument("--no-cowboy-tutorial", action="store_true", help="skip the Level 1 cowboy tutorial")
    ap.add_argument("--players", nargs=2, default=None, metavar=("P1", "P2"), help="player names (or press 1 / 2 in the lobby)")
    ap.add_argument("--demo", action="store_true",
                    help="film mode: two bots play match after match, no key hints on screen (= --sim --bots --auto)")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--winner", type=int, choices=[1, 2], default=None,
                    help="(sim bots, for filming) this player's bot plays sharp and the other sloppy, so they win")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args(argv)
    if args.demo:
        args.sim = args.bots = args.auto = True
        args.players = args.players or ["RED BOT", "BLUE BOT"]
    if args.fast:
        args.headless = True
        args.sim = True
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        args.mute = True
    if args.sim:
        args.names = ["SIM-1", "SIM-2"]
    return args


def finished(ref, now):
    if not ref.quit_now():
        return False
    end_state = "RESULT" if ref.only_level == 1 else ("LEVEL_RESULT" if ref.only_level else "MATCH_END")
    hold = 9.0 if (getattr(ref.args, "demo", False) and not ref.args.fast) else 0.5   # filming: keep the champion
    return ref.state == end_state and now - ref.state_t > hold                    # + match stats on screen


class _Muted:
    def play(self, *_a, **_k):
        pass

    loop = set_volume = stop = stop_loops = stop_voice = play


def run_fast(args, max_virtual_s=3600.0, on_tick=None, sounds=None):
    """Automated test run: fake clock, no pygame at all. on_tick(ref, link, now) runs every step (tests)."""
    from links import SimLink
    clock_t = [1000.0]
    clock = lambda: clock_t[0]          # noqa: E731
    events = queue.Queue()
    link = SimLink(events, bots=(args.bots, args.bots or args.bot2), seed=args.seed, clock=clock, winner=args.winner)
    link.start()
    ref = Referee(args, link, events, sounds or _Muted(), clock=clock)
    while clock_t[0] - 1000.0 < max_virtual_s:
        now = clock_t[0]
        link.tick(now)
        while True:
            try:
                ev = events.get_nowait()
            except queue.Empty:
                break
            ref.handle_event(ev, now)
        ref.update(now)
        ref.play_scheduled(now)
        if on_tick:
            on_tick(ref, link, now)
        if finished(ref, now):
            break
        clock_t[0] += 0.002
    return ref


def main(argv=None):
    args = parse_args(argv)
    if args.fast:
        return run_fast(args)

    import pygame
    from links import BleLink, SimLink
    from sounds import SoundBank

    pygame.mixer.pre_init(44100, -16, 2, 256)       # small buffer = low audio delay
    pygame.init()
    sounds_ok = not args.mute
    if sounds_ok:
        try:
            pygame.mixer.init(44100, -16, 2, 256)
        except pygame.error as e:
            print(f"No audio device ({e}) - running muted")
            sounds_ok = False
    if sounds_ok and not args.no_voice:
        try:                                         # first start on Windows: record the announcer lines
            import announcer
            announcer.make_announcer(log=print)
        except Exception as e:                       # never stop the game over the voice
            print(f"Announcer skipped: {e}")
    sounds = SoundBank(enabled=sounds_ok)
    sounds.voice_on = not args.no_voice

    # The game is always drawn on a 1280 x 720 "canvas" and then scaled to fit the window, so the window can be
    # resized / MAXIMISED (button at the top right) and F11 can go fullscreen on whichever monitor the window is on.
    def open_window(full):
        if full:
            return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)          # desktop resolution, no mode switch
        return pygame.display.set_mode((W, H), pygame.RESIZABLE)
    window = open_window(args.fullscreen)
    screen = pygame.Surface((W, H))                  # what the game draws on
    view = [1.0, 0, 0]                               # scale, x offset, y offset of the canvas inside the window

    def to_game(pos):
        """Window pixel -> game pixel (for the mouse)."""
        sc, ox, oy = view
        return (int((pos[0] - ox) / sc), int((pos[1] - oy) / sc))

    def present():
        ww, wh = window.get_size()
        sc = min(ww / W, wh / H)
        sw_, sh_ = int(W * sc), int(H * sc)
        view[:] = [sc, (ww - sw_) // 2, (wh - sh_) // 2]
        if (sw_, sh_) == (W, H):
            window.blit(screen, (view[1], view[2]))
        else:
            window.fill((0, 0, 0))                   # black bars if the window isn't 16:9
            window.blit(pygame.transform.scale(screen, (sw_, sh_)), (view[1], view[2]))  # hard edges = pixel art
        pygame.display.flip()
    pygame.key.start_text_input()                    # typed player names arrive as TEXTINPUT events
    pygame.display.set_caption("Beat-Draw Showdown - Arena")
    fonts = {
        "title": pygame.font.SysFont("arial", 34, bold=True),
        "huge": pygame.font.SysFont("arial", 110, bold=True),
        "big": pygame.font.SysFont("arial", 56, bold=True),
        "med": pygame.font.SysFont("arial", 28, bold=True),
        "small": pygame.font.SysFont("arial", 20),
    }

    events = queue.Queue()
    if args.sim:
        link = SimLink(events, bots=(args.bots, args.bots or args.bot2), seed=args.seed, winner=args.winner)
    else:
        link = BleLink(args.names, events)
    link.start()
    ref = Referee(args, link, events, sounds)

    clock = pygame.time.Clock()
    last_frame = 0.0
    fullscreen = args.fullscreen
    running = True
    try:
        while running:
            now = time.perf_counter()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.TEXTINPUT:
                    ref.on_text(e.text)
                elif e.type == pygame.MOUSEMOTION:
                    ref.on_mouse("move", to_game(e.pos), now)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):     # 4/5 = old wheel events
                    ref.on_mouse("click" if e.button == 1 else "back", to_game(e.pos), now)
                elif e.type == pygame.MOUSEWHEEL:
                    ref.on_mouse("wheel", ref.mouse_pos, now, e.y)
                elif e.type == pygame.KEYDOWN:
                    name = pygame.key.name(e.key)
                    if name == "f11":
                        fullscreen = not fullscreen
                        window = open_window(fullscreen)
                    else:
                        ref.on_key(name, now)
            link.tick(now)
            while True:
                try:
                    ev = events.get_nowait()
                except queue.Empty:
                    break
                ref.handle_event(ev, now)
            ref.update(now)
            ref.play_scheduled(now)
            if ref.want_quit:
                running = False
            if now - last_frame > 1 / 60:
                last_frame = now
                ref.draw(screen, fonts, now)
                present()
            if finished(ref, now):
                running = False
            clock.tick(500)                            # ~2 ms loop for tight audio timing
    finally:
        link.stop()
        pygame.quit()
    return ref


if __name__ == "__main__":
    main()
    sys.exit(0)
