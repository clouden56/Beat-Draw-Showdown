"""Unit tests for the game rules.  Run:  python -m pytest tests   (or)   python tests/test_game_logic.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re  # noqa: E402

from game_logic import (PlayerRound, drum_packet, hit_rating, pattern_ok, random_pattern, decide, judge_hit, parse_message,  # noqa: E402
                        result_packet)


def test_arrow_patterns_grow_each_round():
    import random
    rng = random.Random(3)
    for _ in range(100):
        p1, p2, p3 = (random_pattern(rng, r) for r in (1, 2, 5))
        for p in (p1, p2, p3):
            assert len(p) == 16 and sum(c != "-" for c in p) == 8 and p[0] != "-" and set(p) <= set("UDLR-")
            assert not re.search(r"[UDLR]{4}", p) and "----" not in p    # no long runs of notes / rests
        assert set(p1) - {"-"} == {"U", "D"}                         # round 1: only up and down
        assert 1 <= sum(c in "LR" for c in p2) <= 2                     # round 2: one or two sideways
        assert set(p3) - {"-"} == set("UDLR")                         # round 3+: all four
    assert not pattern_ok("UDLR-UDL", 1) and not pattern_ok("-UDUDUD-", 1)            # old 8-beat length
    assert pattern_ok("U-DU--D-UD--U-D-", 1) and not pattern_ok("UDUD----UD--U-D-", 1)   # 4 in a row / 4 rests


def test_judge_hit_on_beat():
    used = [False] * 8
    assert judge_hit(1020, "R", "DDR-DDR-", 500, used) == (2, True, 20)
    assert used[2]


def test_judge_hit_wrong_drum_and_rest_and_double():
    used = [False] * 8
    assert judge_hit(0, "R", "DDR-DDR-", 500, used)[1] is False      # wrong arrow
    assert judge_hit(1500, "D", "DDR-DDR-", 500, used)[1] is False   # rest beat
    assert judge_hit(10, "D", "DDR-DDR-", 500, used)[1] is True
    assert judge_hit(40, "D", "DDR-DDR-", 500, used)[1] is False     # already used


def test_judge_hit_late_and_outside():
    used = [False] * 8
    k, ok, err = judge_hit(200, "D", "DDR-DDR-", 500, used)            # 200 ms late
    assert (k, ok, err) == (0, False, 200)
    assert judge_hit(-400, "D", "DDR-DDR-", 500, used)[0] == -1        # during count-in
    assert judge_hit(4100, "D", "DDR-DDR-", 500, used)[0] == -1        # after beat 8


def test_parse_messages():
    assert parse_message("H3U1+12") == {"type": "hit", "beat": 3, "gesture": "U", "ok": True, "err": 12}
    assert parse_message("H0H0-140")["err"] == -140
    assert parse_message("H14L0-140") == {"type": "hit", "beat": 14, "gesture": "L", "ok": False, "err": -140}


def test_drum_packet_and_ratings():
    p = drum_packet(90, "U-DU--D-UD--U-D-")
    assert p == "R090U-DU--D-UD--U-D-" and len(p) == 20                 # BLE limit: 20 bytes
    assert len(drum_packet(110, "U" * 16)) == 20
    assert hit_rating(True, 40) == "PERFECT" and hit_rating(True, -60) == "PERFECT"
    assert hit_rating(True, 61) == "GOOD" and hit_rating(False, 5) == "MISS"
    used = [False] * 16
    assert judge_hit(15 * 667 + 30, "D", "U-DU--D-UD--U-DD", 667, used) == (15, True, 30)   # beat 16
    assert parse_message("B6") == {"type": "bullets", "n": 6}
    assert parse_message("T231120\x00") == {"type": "draw", "us": 231120}
    assert parse_message("F")["type"] == "foul"
    assert parse_message("Q")["type"] == "pong"
    assert parse_message("garbage")["type"] == "?"


def _p(bullets=0, us=None, foul=False, lat=20.0):
    return PlayerRound(bullets=bullets, draw_us=us, fouled=foul, latency_ms=lat)


def test_bullets_can_beat_raw_speed():
    # P1 draws 30 ms slower but has 6 bullets vs 0 -> 150 ms bonus -> P1 wins
    r = decide([_p(6, 260_000), _p(0, 230_000)])
    assert r.winner == 0
    assert round(r.effective_ms[0]) == 110 and round(r.effective_ms[1]) == 230


def test_latency_correction():
    # Same blaster time, but P2's packet arrived 20 ms later -> P2 really reacted faster
    r = decide([_p(0, 250_000, lat=10), _p(0, 250_000, lat=30)])
    assert r.corrected_ms == [240.0, 260.0] or r.corrected_ms == [240, 260]
    assert r.winner == 0


def test_fouls_and_no_draws():
    assert decide([_p(6, None, foul=True), _p(0, 300_000)]).winner == 1
    assert decide([_p(0, None, foul=True), _p(0, None, foul=True)]).winner is None
    assert decide([_p(0, None), _p(0, None)]).winner is None
    assert decide([_p(0, None), _p(0, 400_000)]).winner == 1
    # faster than humanly possible -> counted as a foul
    r = decide([_p(0, 60_000), _p(0, 300_000)])
    assert r.fouls[0] and r.winner == 1


def test_result_packets():
    r = decide([_p(2, 250_000), _p(0, 300_000)])
    assert result_packet(r, 0) == "EW200" and result_packet(r, 1) == "EL300"
    r = decide([_p(0, None, foul=True), _p(0, 300_000)])
    assert result_packet(r, 0) == "EF0"
    for pk in ("EW200", "EL300", "EF0"):
        assert len(pk) <= 20


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
