"""Tests for the maths in bench.py (no Bluetooth needed).

Run:  python tests/test_bench.py      (or)   python -m pytest tests
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bench import drain_per_hour, summarize_gestures, summarize_latency  # noqa: E402


def test_latency_summary():
    r = summarize_latency([30.0, 40.0, 50.0, 60.0, 200.0], sent=10)
    assert r["median_ms"] == 50 and r["one_way_ms"] == 25 and r["max_ms"] == 200
    assert r["lost_pct"] == 50 and r["p95_ms"] == 200
    assert summarize_latency([], 5)["lost_pct"] == 100


def test_gesture_summary():
    trials = [("L", "L"), ("L", "W"), ("W", "W"), ("W", "?"), ("F", "F"), ("F", "-")]
    r = summarize_gestures(trials)
    assert r["n"] == 6 and r["right"] == 3 and r["pct"] == 50
    assert r["per"]["L"] == {"n": 2, "right": 1, "got": {"L": 1, "W": 1}}
    assert r["per"]["F"]["got"] == {"F": 1, "-": 1}


def test_battery_drain():
    assert drain_per_hour([(0, 90), (60, 90)]) is None                  # too short
    samples = [(t, 90 - t // 360) for t in range(0, 3600, 10)]          # 10 % per hour
    assert abs(drain_per_hour(samples) - 10) < 0.2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
