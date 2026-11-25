"""Tests for v5: pause + resume when a wand drops out, Level 2 warm-up, FIZZLE hints,
player names, end-of-match stats.

Run:  python tests/test_v5.py      (or)   python -m pytest tests
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import arena_referee  # noqa: E402
from game_logic import (FIZZLE_HINTS, SpellDuel, parse_message, parse_version)  # noqa: E402

FAST = ["--sim", "--bots", "--auto", "--fast", "--seed", "7"]


def _run(extra, on_tick=None):
    args = arena_referee.parse_args(FAST + extra)
    return arena_referee.run_fast(args, on_tick=on_tick)


def _drop_in(state, player=0, seconds=4.0, nth=1):
    """on_tick hook: drop `player` the nth time the referee is in `state` (once)."""
    seen = {"n": 0, "done": False, "prev": None, "paused_from": None, "resumed": False}

    def tick(ref, link, now):
        if ref.state == state and seen["prev"] != state:
            seen["n"] += 1
        if not seen["done"] and ref.state == state and seen["n"] == nth and now - ref.state_t > 0.3:
            link.drop(player, seconds)
            seen["done"] = True
        if ref.state == "PAUSED" and seen["paused_from"] is None:
            seen["paused_from"] = ref.paused_state
        if seen["paused_from"] and seen["prev"] == "PAUSED" and ref.state != "PAUSED":
            seen["resumed"] = True
        seen["prev"] = ref.state
    return tick, seen


# ---------------- packets ----------------
def test_new_packets():
    assert parse_message("fF") == {"type": "fizzle", "closest": "F"}
    assert parse_message("fs")["closest"] == "s" and FIZZLE_HINTS["s"] == "bigger move!"
    v = parse_version("5.0,BDS-1,0,W")
    assert v == {"version": "5.0", "name": "BDS-1", "buzzer": "0", "reset": "W"}
    assert parse_version("4.1,BDS-2,1")["reset"] is None               # old firmware still parses
    assert len("V5.0,BDS-6,1,W") <= 20


def test_duel_resume_keeps_hp_and_time_left():
    d = SpellDuel(hp=(4, 3), t_start=0, duration_s=60)
    d.cast(0, "F", 1.0)
    d.resume(paused_at=40.0, new_start=100.0)                         # 20 s were left
    assert d.flying == [] and d.hp == [4, 3] and abs(d.time_left(100.0) - 20) < 1e-9
    d2 = SpellDuel(t_start=0, duration_s=60)
    d2.resume(paused_at=58.0, new_start=100.0)                        # at least 15 s after a pause
    assert abs(d2.time_left(100.0) - 15) < 1e-9


# ---------------- pause + resume in every part of the match ----------------
def test_drop_in_level1_replays_the_round():
    tick, seen = _drop_in("DRUM")
    ref = _run(["--matches", "1"], tick)
    assert seen["paused_from"] == "DRUM" and seen["resumed"]
    assert ref.state == "MATCH_END" and ref.matches_played == 1
    assert ref.drops == [1, 0]


def test_drop_in_level2_duel_keeps_hp():
    hp_at_pause = {}

    def tick(ref, link, now):
        base(ref, link, now)
        if ref.state == "PAUSED" and "hp" not in hp_at_pause:
            hp_at_pause["hp"] = list(ref.duel.hp)
        if seen["resumed"] and "after" not in hp_at_pause and ref.state == "INTRO":
            hp_at_pause["after"] = list(ref.duel.hp)
    base, seen = _drop_in("SPELL", player=1)
    ref = _run(["--matches", "1"], tick)
    assert seen["paused_from"] == "SPELL" and seen["resumed"]
    assert hp_at_pause["after"] == hp_at_pause["hp"]
    assert ref.state == "MATCH_END"


def test_drop_in_level3_replays_the_round():
    rounds = {}

    def tick(ref, link, now):
        base(ref, link, now)
        if ref.state == "PAUSED" and "at" not in rounds:
            rounds["at"] = ref.round_no
        if seen["resumed"] and ref.state == "SHOW" and "next" not in rounds:
            rounds["next"] = ref.round_no
    base, seen = _drop_in("INPUT", player=0, nth=2)
    ref = _run(["--level", "3", "--matches", "1"], tick)
    assert seen["paused_from"] == "INPUT" and seen["resumed"]
    assert rounds["next"] == rounds["at"]                              # the cut-off round is played again
    assert ref.levels_played == 1


def test_drop_during_warmup_and_long_outage():
    tick, seen = _drop_in("WARMUP", seconds=20.0)
    ref = _run(["--level", "2", "--matches", "1"], tick)
    assert seen["paused_from"] == "WARMUP" and seen["resumed"] and ref.levels_played == 1


# ---------------- warm-up ----------------
def test_spell_tutorial_each_at_own_pace_no_timer():
    info = {"wrong": 0}

    def tick(ref, link, now):
        if ref.state == "WARMUP":
            info.setdefault("t0", now)
            info["steps"] = [t.step for t in ref.tut]
            info["wrong"] += any(m.startswith("That was") and now - t < 0.003 for t, m in ref.flash)
        elif "t0" in info and "len" not in info:
            info["len"] = now - info["t0"]
    _run(["--level", "2", "--matches", "1"], tick)
    assert info["steps"] == [3, 3]                     # both learned all 3 spells before the duel
    assert info["len"] > 6                             # 6 casts each: nobody was cut off by a timer


def test_tutorial_rules():
    from game_logic import Tutorial
    t = Tutorial()
    assert t.spell == "L"
    assert t.cast("F") == ("wrong", "L") and t.count == 0
    assert t.cast("L") == ("good", "L", 1) and t.cast("L") == ("next", "W")
    assert [t.cast(x)[0] for x in "WWFF"] == ["good", "next", "good", "done"] and t.done


def test_no_warmup_flag():
    states = set()
    _run(["--level", "2", "--matches", "1", "--no-warmup"], lambda r, l, n: states.add(r.state))
    assert "WARMUP" not in states and "SPELL" in states


# ---------------- names + stats ----------------
def test_typing_names_and_stats():
    ref = _run(["--matches", "1", "--players", "Fadil", "Aisyah"])
    assert ref.pname(0) == "Fadil"
    assert any(n in ref.level_msg for n in ("FADIL", "AISYAH", "NO CHAMPION"))
    st = ref.stats
    assert st["notes"] > 0 and sum(st["draws_won"]) >= 2 and st["combo_rounds"] >= 1
    assert all(n == "Fadil" or n == "Aisyah" for _, _, n in ref.leaderboard)
    # name entry in the lobby: 1, type, ENTER
    ref.state = "LOBBY"
    ref.on_key("1", 0)
    assert ref.editing == 0
    ref.on_key("space", 0)                          # keys don't start the match while typing
    assert ref.state == "LOBBY"
    ref.on_text("Zul!!")                            # "!" is not allowed
    ref.on_key("backspace", 0)
    ref.on_key("return", 0)
    assert ref.player_names[0] == "Zu"           # typing starts from an empty name and ref.editing is None
    ref.on_key("2", 0)
    ref.on_text("x" * 30)
    ref.on_key("return", 0)
    assert len(ref.player_names[1]) == arena_referee.NAME_MAX


def test_demo_flag():
    a = arena_referee.parse_args(["--demo", "--fast"])
    assert a.sim and a.bots and a.auto and a.players == ["RED BOT", "BLUE BOT"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
