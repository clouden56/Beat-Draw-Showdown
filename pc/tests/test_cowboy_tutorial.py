"""Tests for v5.4: the cowboy tutorial (arrows -> practice beat -> holster -> practice draw).

Run:  python tests/test_cowboy_tutorial.py      (or)   python -m pytest tests
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import arena_referee  # noqa: E402
from game_logic import CTUT_STILL_S, parse_message  # noqa: E402


def _ref():
    args = arena_referee.parse_args(["--sim", "--bots", "--fast", "--seed", "1"])
    return arena_referee.run_fast(args, max_virtual_s=3.0)


def test_packets():
    assert parse_message("dL") == {"type": "flick", "dir": "L"}
    assert parse_message("s13") == {"type": "still", "n": 13}


def test_full_tutorial_with_bots_then_match():
    phases, info = [], {}

    def tick(ref, link, now):
        if ref.state == "CTUT" and (not phases or phases[-1] != ref.ctut_phase):
            phases.append(ref.ctut_phase)
        if ref.state == "CTUT" and ref.ctut_phase == "results":
            info["draw"] = list(ref.ctut_draw)
            info["beat"] = list(ref.ctut_beat_score)
        if ref.state == "DRUM" and "bpm" not in info:
            info["bpm"] = 60 / ref.beat_s
    args = arena_referee.parse_args(["--sim", "--bots", "--auto", "--fast", "--seed", "3", "--matches", "1"])
    ref = arena_referee.run_fast(args, on_tick=tick)
    assert phases == ["arrows", "beat", "beat_done", "holster", "draw", "results"]
    assert all(isinstance(d, float) for d in info["draw"]) and max(info["beat"]) >= 2
    assert info["bpm"] == 90 and ref.state == "MATCH_END"       # the real beat is back to normal speed


def test_arrows_at_own_pace_and_wrong_flick():
    ref = _ref()
    ref.start_cowboy_tutorial(10.0)
    assert ref.state == "CTUT" and ref.ctut_phase == "arrows"
    ref.handle_msg(0, "dL", 10.1, 10.1)                              # wrong: UP comes first
    assert ref.ctut[0].step == 0 and ref.flash[0][1].startswith("That was LEFT")
    for g in "UUDDLLRR":
        ref.handle_msg(0, "d" + g, 10.2, 10.2)
    assert ref.ctut[0].done and not ref.ctut[1].done
    ref.update(20.0)
    assert ref.ctut_phase == "arrows"                                # waits for P2 - no timer
    for g in "UUDDLLRR":
        ref.handle_msg(1, "d" + g, 30.0, 30.0)
    ref.update(30.1)
    ref.update(31.7)
    assert ref.ctut_phase == "beat"


def test_holster_stillness_resets_when_you_move():
    ref = _ref()
    ref.start_cowboy_tutorial(10.0)
    ref.ctut_go("holster", 10.0)
    t = 10.0
    for _ in range(15):                                              # 1.5 s still
        t += 0.1
        ref.handle_msg(0, "s2", t, t)
    assert 1.3 < ref.still_t[0] < 1.6
    ref.handle_msg(0, "s14", t + 0.1, t + 0.1)                       # moved past the foul line
    assert ref.still_t[0] == 0 and ref.flash[0][1].startswith("MOVED")
    t += 0.1
    for _ in range(int(CTUT_STILL_S / 0.1) + 2):
        t += 0.1
        ref.handle_msg(0, "s1", t, t)
    assert ref.still_done[0] and not ref.still_done[1]


def test_skip_and_settings_off():
    ref = _ref()
    ref.start_cowboy_tutorial(10.0)
    ref.on_key("space", 10.5)                                        # operator skip
    assert ref.state == "INTRO" and ref.ctut_phase is None
    ref = _ref()
    ref.settings.change("cowboy_tutorial", 1)                        # off in SETTINGS
    ref.start_match(5.0)
    assert ref.state == "INTRO"
    ref = _ref()
    ref.only_level = 1
    ref.start_match(5.0)
    ref.on_key("space", 6.0)
    assert ref.state == "DRUM"                                       # practice Level 1: straight to round 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
