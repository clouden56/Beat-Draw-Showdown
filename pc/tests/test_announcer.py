"""Tests for the arena announcer ("ROUND ONE... FIGHT!").

Run:  python tests/test_announcer.py      (or)   python -m pytest tests
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402

import announcer  # noqa: E402
import arena_referee  # noqa: E402


class _Recorder:
    """Stands in for SoundBank: remembers every announcer line that was played."""
    def __init__(self):
        self.lines = []
        self.voice_on = True

    def play(self, name, *_a, **_k):
        if name.startswith("ann_"):
            self.lines.append(name)

    def loop(self, *_a, **_k):
        pass

    set_volume = stop = stop_loops = stop_voice = loop


def _run(argv):
    rec = _Recorder()
    real = arena_referee._Muted
    arena_referee._Muted = lambda: rec            # run_fast() builds its sound bank from _Muted
    try:
        ref = arena_referee.main(argv)
    finally:
        arena_referee._Muted = real
    pending = [name for _, name, _ in ref.schedule if name.startswith("ann_")]   # e.g. the winner line
    return ref, rec.lines + pending


def test_every_line_used_has_a_recording():
    _, lines = _run(["--sim", "--bots", "--auto", "--fast", "--matches", "1", "--seed", "7"])
    assert lines and set(lines) <= set(announcer.LINES)


def test_full_match_calls():
    _, lines = _run(["--sim", "--bots", "--auto", "--fast", "--matches", "1", "--seed", "7"])
    assert lines[0] == "ann_cowboy_school"                            # the cowboy tutorial comes first
    i1 = lines.index("ann_level1")
    assert lines[i1:i1 + 6] == ["ann_level1", "ann_round1", "ann_4", "ann_3", "ann_2", "ann_1"]
    assert "ann_holster" in lines and "ann_draw" in lines
    i2 = lines.index("ann_level2")
    assert lines[i2 + 1:i2 + 6] == ["ann_warmup", "ann_3", "ann_2", "ann_1", "ann_fight"]   # warm-up, then the duel
    i3 = lines.index("ann_level3")
    assert lines[i3 + 1:i3 + 5] == ["ann_3", "ann_2", "ann_1", "ann_round1"]
    assert lines[i3 + 5:i3 + 8] == ["ann_2", "ann_1", "ann_go"]       # combo countdown
    assert lines[-1] in ("ann_p1champ", "ann_p2champ", "ann_tie")
    assert lines[-2] in ("ann_ko", "ann_time")


def test_level3_final_round_is_called():
    _, lines = _run(["--sim", "--bots", "--auto", "--fast", "--level", "3", "--matches", "1", "--seed", "11"])
    assert "ann_round5" in lines and "ann_final" in lines
    assert lines[-2] in ("ann_ko", "ann_time") and lines[-1] in ("ann_p1wins", "ann_p2wins", "ann_tie")


def test_announcerize_makes_a_loud_44k_line():
    sr = 22050
    t = np.arange(int(0.6 * sr)) / sr
    voice = 0.3 * np.sin(2 * np.pi * 180 * t) * np.hanning(len(t))
    voice = np.concatenate([np.zeros(sr // 5), voice, np.zeros(sr // 5)])    # silence to trim
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "x.raw.wav")
        import wave
        with wave.open(raw, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((voice * 32000).astype(np.int16).tobytes())
        x, got_sr = announcer.read_wav(raw)
        assert got_sr == sr
        y = announcer.announcerize(x, sr)
        out = os.path.join(tmp, "ann_x.wav")
        announcer.write_wav(out, y)
        z, zsr = announcer.read_wav(out)
    assert zsr == 44100
    assert 0.9 < np.abs(z).max() <= 1.0                         # normalised loud
    assert 0.6 * 1.18 < len(z) / zsr < 0.6 * 1.18 + 0.7          # deeper (longer) + echo tail, silence trimmed


def test_no_windows_no_crash():
    if sys.platform == "win32":
        return
    msgs = []
    assert announcer.make_announcer(log=msgs.append) == 0
    assert not msgs or "Windows" in msgs[0]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
