"""
announcer.py — the fighting-game style announcer ("ROUND ONE... FIGHT!").

The voice lines are made ONCE on your Windows laptop with the speech voice that is built into
Windows (no internet, no extra installs), then given an "arena announcer" effect: deeper, punchier,
with a stadium echo. They are saved in pc/sounds/announcer/ and loaded like any other sound.

    python announcer.py              # make any missing lines (the arena also does this on first start)
    python announcer.py --force      # make them all again
    python announcer.py --voice "Microsoft Zira Desktop"   # pick another installed Windows voice
    python announcer.py --list       # show the installed voices

Want a real announcer? Record a teammate and save it as pc/sounds/announcer/<name>.wav
(e.g. ann_fight.wav). Files you put there are never overwritten unless you use --force.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds", "announcer")
SR_OUT = 44100

# file name -> what the announcer says
LINES = {
    "ann_1": "One!", "ann_2": "Two!", "ann_3": "Three!", "ann_4": "Four!",
    "ann_fight": "Fight!", "ann_go": "Go!",
    "ann_holster": "Holster!", "ann_draw": "Draw!", "ann_foul": "Foul!", "ann_tie": "Tie!",
    "ann_round1": "Round one!", "ann_round2": "Round two!", "ann_round3": "Round three!",
    "ann_round4": "Round four!", "ann_round5": "Round five!", "ann_round6": "Round six!",
    "ann_final": "Final round!", "ann_sudden": "Sudden death!",
    "ann_level1": "Level one. Cowboy showdown!", "ann_level2": "Level two. Spellcaster!",
    "ann_level3": "Level three. Combo clash!",
    "ann_p1wins": "Player one wins!", "ann_p2wins": "Player two wins!",
    "ann_ko": "K. O.!", "ann_time": "Time!", "ann_perfect": "Perfect!",
    "ann_warmup": "Warm up! Try every spell!", "ann_cowboy_school": "Cowboy school! Learn the moves!",
    "ann_freeze": "Freeze!", "ann_paused": "Pause!", "ann_resume": "Resume!",
    "ann_p1champ": "Player one... is the champion!", "ann_p2champ": "Player two... is the champion!",
}

# short count/cue words are spoken a bit faster so they fit between the beats (Level 1 count-in = 0.5 s)
FAST = {"ann_1", "ann_2", "ann_3", "ann_4", "ann_go", "ann_draw", "ann_fight", "ann_foul", "ann_tie",
        "ann_holster", "ann_ko", "ann_time"}

PS_SCRIPT = r"""
param([string]$ListFile, [string]$OutDir, [string]$Voice)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($Voice) { $s.SelectVoice($Voice) }
else {
  $male = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Gender -eq 'Male' } | Select-Object -First 1
  if ($male) { $s.SelectVoice($male.VoiceInfo.Name) }
}
$s.Volume = 100
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($line in Get-Content -Encoding UTF8 $ListFile) {
  $parts = $line -split '\|', 3
  $s.Rate = [int]$parts[1]
  $s.SetOutputToWaveFile((Join-Path $OutDir ($parts[0] + '.raw.wav')), $fmt)
  $s.Speak($parts[2])
}
$s.SetOutputToNull()
$s.Dispose()
"""


def list_voices():
    ps = ("Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer)"
          ".GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name + '  (' + $_.VoiceInfo.Gender + ')' }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60)
    return out.stdout.strip()


def missing(force=False):
    os.makedirs(FOLDER, exist_ok=True)
    return [n for n in LINES if force or not any(os.path.exists(os.path.join(FOLDER, f"{n}.{e}"))
                                                 for e in ("wav", "ogg"))]


def make_announcer(force=False, voice=None, log=print) -> int:
    """Record the missing lines with the Windows voice and process them. Returns how many were made."""
    todo = missing(force)
    if not todo:
        return 0
    if sys.platform != "win32":
        log("Announcer: needs Windows to record the voice lines (or put your own WAVs in pc/sounds/announcer/).")
        return 0
    log(f"Announcer: recording {len(todo)} voice lines with the Windows voice (first run only, ~20 s)...")
    with tempfile.TemporaryDirectory() as tmp:
        lst = os.path.join(tmp, "lines.txt")
        with open(lst, "w", encoding="utf-8") as f:
            f.write("\n".join(f"{n}|{1 if n in FAST else -1}|{LINES[n]}" for n in todo))
        ps1 = os.path.join(tmp, "speak.ps1")
        with open(ps1, "w", encoding="utf-8") as f:
            f.write(PS_SCRIPT)
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1, "-ListFile", lst, "-OutDir", tmp]
        if voice:
            cmd += ["-Voice", voice]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as e:
            log(f"Announcer: Windows speech failed ({e}) - the game runs without a voice.")
            return 0
        made = 0
        for n in todo:
            raw = os.path.join(tmp, f"{n}.raw.wav")
            if os.path.exists(raw):
                x, sr = read_wav(raw)
                write_wav(os.path.join(FOLDER, f"{n}.wav"), announcerize(x, sr))
                made += 1
    log(f"Announcer: {made} lines saved in {FOLDER}")
    return made


# ----------------------------------------------------------------------------------------------
# the "arena announcer" effect
# ----------------------------------------------------------------------------------------------
def read_wav(path):
    with wave.open(path) as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        data = w.readframes(w.getnframes())
    x = np.frombuffer(data, np.int16 if sw == 2 else np.uint8).astype(np.float32)
    if sw == 1:
        x = (x - 128) * 256
    x = x.reshape(-1, ch).mean(axis=1) / 32768
    return x, sr


def write_wav(path, x):
    y = (np.clip(x, -1, 1) * 32000).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR_OUT)
        w.writeframes(y.tobytes())


def trim(x, thresh=0.02, pad=0.01, sr=SR_OUT):
    idx = np.where(np.abs(x) > thresh)[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(pad * sr))
    b = min(len(x), idx[-1] + int(0.05 * sr))
    return x[a:b]


def announcerize(x, sr, deeper=1.18, drive=2.5):
    """Deeper (slowed resample), punchy (soft clipping), big (stadium echo), loud (normalised)."""
    x = x / max(1e-6, np.abs(x).max())
    # resample to 44.1 kHz AND lower the pitch in one go
    n_out = int(len(x) * SR_OUT / sr * deeper)
    t = np.linspace(0, len(x) - 1, n_out)
    x = np.interp(t, np.arange(len(x)), x)
    x = trim(x)
    # a little bass boost + presence: mix in a smoothed copy
    low = np.convolve(x, np.ones(12) / 12, mode="same")
    x = x + 0.6 * low
    x = np.tanh(drive * x) / np.tanh(drive)                  # shout-y saturation
    x = np.concatenate([np.zeros(int(0.005 * SR_OUT)), x, np.zeros(int(0.45 * SR_OUT))])
    y = x.copy()
    for d_ms, g in ((70, 0.32), (140, 0.2), (230, 0.12), (330, 0.06)):   # stadium echo
        d = int(d_ms / 1000 * SR_OUT)
        y[d:] += g * x[:-d]
    y *= np.minimum(1, np.linspace(40, 0, len(y)))           # fade out the last 25 ms
    return 0.95 * y / max(1e-6, np.abs(y).max())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Make the announcer voice lines")
    ap.add_argument("--force", action="store_true", help="make all lines again (overwrites!)")
    ap.add_argument("--voice", default=None, help="installed Windows voice name")
    ap.add_argument("--list", action="store_true", help="list installed Windows voices")
    a = ap.parse_args()
    if a.list:
        print(list_voices())
    else:
        n = make_announcer(a.force, a.voice)
        print("Nothing to do - all lines exist (use --force to remake)." if n == 0 and not missing() else "")
