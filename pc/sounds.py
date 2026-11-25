"""
sounds.py — all game sounds, generated with numpy so no audio files are needed.

Want better sounds (e.g. your teammate shouting "DRAW!" for the YouTube video)?
Drop a WAV file into pc/sounds/ named after the sound, e.g. pc/sounds/draw.wav.
It replaces the generated one automatically.

Names: click, kick, snare, hihat, wrong, heartbeat, draw, gunshot, jam, win
       (Level 2/3) chant, zap, water, fire, block, hurt, freeze, level
       (Level 3 hype) battle, battle_fast (music loops), hum (beam loop), cheer, surge, drumroll
       (music) arcane (Level 2 mystic loop, generated)
       FILE ONLY (no generated version): western (Level 1 music), crowd (Level 3 crowd loop)

Files may be .wav or .ogg (e.g. pc/sounds/western.ogg). The shipped western.ogg, cheer.ogg and
crowd.ogg come from Pixabay (see docs/CODE_ATTRIBUTION.md).

Loops (battle, battle_fast, hum) are played with SoundBank.loop(); a WAV override for a loop
should loop cleanly (same start and end). For a real crowd, drop a free-to-use crowd recording in
pc/sounds/cheer.wav and credit it in docs/CODE_ATTRIBUTION.md.
"""
from __future__ import annotations

import os

import numpy as np

SR = 44100


def _env(n, decay_s):
    t = np.arange(n) / SR
    return np.exp(-t / decay_s)


def _noise(n, rng):
    return rng.uniform(-1, 1, n)


def synth(name: str) -> np.ndarray:
    """Return a mono float array in [-1, 1]."""
    rng = np.random.default_rng(sum(map(ord, name)))
    if name == "click":
        n = int(0.04 * SR); t = np.arange(n) / SR
        return 0.6 * np.sin(2 * np.pi * 1500 * t) * _env(n, 0.008)
    if name == "kick":
        n = int(0.18 * SR); t = np.arange(n) / SR
        f = 50 + 90 * np.exp(-t / 0.03)
        return 0.9 * np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.06)
    if name == "snare":
        n = int(0.2 * SR); t = np.arange(n) / SR
        return 0.7 * _noise(n, rng) * _env(n, 0.05) + 0.3 * np.sin(2 * np.pi * 190 * t) * _env(n, 0.03)
    if name == "hihat":
        n = int(0.07 * SR)
        x = np.diff(_noise(n + 1, rng))          # crude high-pass
        return 0.45 * x * _env(n, 0.015)
    if name == "wrong":
        n = int(0.15 * SR); t = np.arange(n) / SR
        return 0.35 * np.sign(np.sin(2 * np.pi * 95 * t)) * _env(n, 0.06)
    if name == "heartbeat":
        k = synth("kick") * 0.7
        gap = np.zeros(int(0.12 * SR))
        return np.concatenate([k, gap, k * 0.6])
    if name == "draw":
        n = int(0.5 * SR); t = np.arange(n) / SR
        f = 1100 + 900 * t / 0.5
        tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
        crack = _noise(n, rng) * _env(n, 0.01)
        return 0.6 * tone * np.minimum(1, (0.5 - t) * 10) + 0.5 * crack
    if name == "gunshot":
        n = int(0.6 * SR); t = np.arange(n) / SR
        boom = np.sin(2 * np.pi * 60 * t) * _env(n, 0.12)
        return np.clip(1.2 * _noise(n, rng) * _env(n, 0.08) + 0.8 * boom, -1, 1)
    if name == "jam":
        n = int(0.05 * SR); t = np.arange(n) / SR
        c = 0.6 * np.sin(2 * np.pi * 2400 * t) * _env(n, 0.006)
        return np.concatenate([c, np.zeros(int(0.07 * SR)), c, np.zeros(int(0.05 * SR)), synth("wrong")])
    if name == "win":
        notes = [523, 659, 784, 1047]
        parts = []
        for f in notes:
            n = int(0.12 * SR); t = np.arange(n) / SR
            parts.append(0.4 * np.sin(2 * np.pi * f * t) * _env(n, 0.08))
        return np.concatenate(parts)
    # ---- Level 2 / 3 ----
    if name == "chant":                          # mana charged: soft rising chime
        n = int(0.18 * SR); t = np.arange(n) / SR
        f = 660 + 440 * t / 0.18
        return 0.35 * np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.08)
    if name == "zap":                            # lightning: buzzy crackle
        n = int(0.35 * SR); t = np.arange(n) / SR
        buzz = np.sign(np.sin(2 * np.pi * (120 + 60 * np.sin(2 * np.pi * 30 * t)) * t))
        return 0.5 * (0.6 * buzz + 0.6 * _noise(n, rng) * (rng.random(n) < 0.3)) * _env(n, 0.12)
    if name == "water":                          # water: bubbly wobble
        n = int(0.45 * SR); t = np.arange(n) / SR
        f = 300 + 250 * np.sin(2 * np.pi * 9 * t)
        return 0.5 * np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.2)
    if name == "fire":                           # fire: whoosh (filtered noise swell)
        n = int(0.5 * SR); t = np.arange(n) / SR
        x = np.convolve(_noise(n, rng), np.ones(25) / 25, mode="same")
        return np.clip(4.0 * x * np.sin(np.pi * t / 0.5), -1, 1) * 0.8
    if name == "block":                          # shield clang
        n = int(0.4 * SR); t = np.arange(n) / SR
        return 0.45 * (np.sin(2 * np.pi * 880 * t) + 0.6 * np.sin(2 * np.pi * 1320 * t)) * _env(n, 0.09)
    if name == "hurt":                           # you got hit: low thud + crunch
        n = int(0.3 * SR); t = np.arange(n) / SR
        return np.clip(0.9 * np.sin(2 * np.pi * 80 * t) * _env(n, 0.08) + 0.5 * _noise(n, rng) * _env(n, 0.03), -1, 1)
    if name == "freeze":                         # beam freezes: descending glassy sweep
        n = int(0.6 * SR); t = np.arange(n) / SR
        f = 2400 - 1800 * t / 0.6
        return 0.45 * np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.3)
    if name == "level":                          # new level fanfare
        parts = []
        for f in (392, 523, 659, 784, 1047):
            n = int(0.14 * SR); t = np.arange(n) / SR
            parts.append(0.4 * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * _env(n, 0.1))
        return np.concatenate(parts)
    # ---- Level 3 hype ----
    if name in ("battle", "battle_fast"):
        return _battle_loop(fast=(name == "battle_fast"))
    if name == "hum":                            # beam energy: low drone + crackle, loops every 2 s
        n = 2 * SR; t = np.arange(n) / SR
        drone = 0.35 * np.sin(2 * np.pi * 55 * t) + 0.25 * np.sign(np.sin(2 * np.pi * 110 * t)) * 0.4
        drone *= 0.75 + 0.25 * np.sin(2 * np.pi * 2 * t)            # 2 pulses per loop -> seamless
        crackle = _noise(n, rng) * (rng.random(n) < 0.004) * 0.9
        crackle = np.convolve(crackle, np.exp(-np.arange(200) / 40), mode="same")
        return np.clip(0.6 * drone + 0.35 * crackle, -1, 1)
    if name == "cheer":                          # crowd roar: noisy swell + whoops + claps
        n = int(2.6 * SR); t = np.arange(n) / SR
        swell = np.minimum(1, t / 0.35) * np.exp(-np.maximum(0, t - 0.9) / 0.8)
        roar = _noise(n, rng)
        roar = np.convolve(roar, np.ones(6) / 6, mode="same") - np.convolve(roar, np.ones(60) / 60, mode="same")
        out = 1.6 * roar * swell
        for _ in range(14):                      # "whoo!" voices
            t0 = rng.uniform(0.05, 0.9); d = rng.uniform(0.35, 0.8); f0 = rng.uniform(260, 520)
            i0, i1 = int(t0 * SR), min(n, int((t0 + d) * SR))
            tt = np.arange(i1 - i0) / SR
            f = f0 * (1 + 0.5 * tt / d) + 8 * np.sin(2 * np.pi * 6 * tt)
            v = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * np.sin(4 * np.pi * np.cumsum(f) / SR)
            out[i0:i1] += 0.09 * v * np.sin(np.pi * tt / d)
        for _ in range(40):                      # claps
            i0 = int(rng.uniform(0.3, 2.2) * SR); m = int(0.025 * SR)
            if i0 + m < n:
                out[i0:i0 + m] += 0.25 * _noise(m, rng) * _env(m, 0.006)
        return np.clip(0.8 * out, -1, 1)
    if name == "surge":                          # power-up whoosh when someone takes over
        n = int(0.9 * SR); t = np.arange(n) / SR
        f = 150 + 1400 * (t / 0.9) ** 2
        tone = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * 0.3
        whoosh = np.convolve(_noise(n, rng), np.ones(12) / 12, mode="same") * 2.5
        return np.clip((tone + whoosh) * np.sin(np.pi * t / 0.9) ** 0.5 * 0.7, -1, 1)
    if name == "drumroll":                       # sudden death: accelerating snare roll + crash
        parts, gap = [], 0.12
        while gap > 0.025:
            m = int(gap * SR)
            hit = np.zeros(m)
            k = min(m, int(0.05 * SR))
            hit[:k] = 0.5 * _noise(k, rng) * _env(k, 0.02)
            parts.append(hit)
            gap *= 0.9
        n = int(1.2 * SR)
        crash = 0.8 * np.convolve(_noise(n, rng), [1, -1], mode="same") * _env(n, 0.35)
        crash += 0.6 * np.sin(2 * np.pi * 55 * np.arange(n) / SR) * _env(n, 0.2)
        return np.clip(np.concatenate(parts + [crash]), -1, 1)
    if name == "arcane":
        return _arcane_loop()
    raise ValueError(name)


def _arcane_loop() -> np.ndarray:
    """Original mystic loop for Level 2: low drone, slow minor pad, bell arpeggio, echo. Loops seamlessly."""
    bpm = 84
    beat = 60 / bpm
    n = int(round(16 * beat * SR))
    t = np.arange(n) / SR
    out = 0.12 * np.sin(2 * np.pi * 73.42 * t) * (0.8 + 0.2 * np.sin(2 * np.pi * t * 2 / (16 * beat)))   # D2 drone
    chords = [[146.8, 174.6, 220.0], [116.5, 146.8, 174.6], [130.8, 164.8, 196.0], [110.0, 138.6, 164.8]]  # Dm Bb C A
    bar = 4 * beat
    for b, ch in enumerate(chords):
        i0, i1 = int(b * bar * SR), int((b + 1) * bar * SR)
        tt = np.arange(i1 - i0) / SR
        pad = sum(np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt + 0.3) for f in ch)
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.6)
        out[i0:i1] += 0.05 * pad * env
        arp = [ch[0] * 4, ch[1] * 4, ch[2] * 4, ch[1] * 4, ch[0] * 8, ch[2] * 4, ch[1] * 4, ch[2] * 2]
        for k, f in enumerate(arp):                          # bells on 8th notes
            j0 = i0 + int(k * beat / 2 * SR)
            m = min(int(1.2 * SR), n - j0)
            tb = np.arange(m) / SR
            bell = (np.sin(2 * np.pi * f * tb) + 0.4 * np.sin(2 * np.pi * 2.76 * f * tb)) * np.exp(-tb / 0.35)
            out[j0:j0 + m] += 0.07 * bell
    for d, g in ((int(beat * 0.75 * SR), 0.35), (int(beat * 1.5 * SR), 0.2)):   # echo that wraps around
        out = out + g * np.roll(out, d)
    out[:int(0.003 * SR)] *= np.linspace(0, 1, int(0.003 * SR))
    out[-int(0.003 * SR):] *= np.linspace(1, 0, int(0.003 * SR))
    return 0.8 * out / max(1e-9, np.abs(out).max())


def _battle_loop(fast: bool) -> np.ndarray:
    """Original arcade battle loop (A minor: Am - F - G - E), 4 bars, loops seamlessly.
    battle = 140 BPM; battle_fast = 168 BPM with 16th hats, 4-on-the-floor and a higher arpeggio."""
    rng = np.random.default_rng(7 if fast else 3)
    bpm = 168 if fast else 140
    beat = 60 / bpm
    n = int(round(16 * beat * SR))
    out = np.zeros(n)
    chords = [(110.0, [220.0, 261.6, 329.6]),     # Am
              (87.31, [174.6, 220.0, 261.6]),     # F
              (98.0, [196.0, 246.9, 293.7]),      # G
              (82.41, [164.8, 207.7, 246.9])]     # E (harmonic-minor V = drama)

    def put(i0, x):
        i1 = min(n, i0 + len(x))
        out[i0:i1] += x[:i1 - i0]

    def sq(f, dur, vol, decay):
        m = int(dur * SR); t = np.arange(m) / SR
        w = np.sign(np.sin(2 * np.pi * f * t)) * 0.6 + 0.4 * np.sin(2 * np.pi * f * t)
        return vol * w * _env(m, decay) * np.minimum(1, (dur - t) * 200)

    for bar, (root, tones) in enumerate(chords):
        b0 = bar * 4 * beat
        for e in range(8):                                   # bass: 8ths, octave bounce
            f = root * (2 if e % 2 else 1)
            put(int((b0 + e * beat / 2) * SR), sq(f, beat / 2 * 0.9, 0.22, 0.15))
        steps = 16
        mult = 2 if fast else 1
        for k in range(steps):                               # arpeggio: 16ths
            f = tones[[0, 1, 2, 1][k % 4]] * 2 * mult
            put(int((b0 + k * beat / 4) * SR), sq(f, beat / 4 * 0.8, 0.09, 0.05))
        m = int(4 * beat * SR); t = np.arange(m) / SR       # pad: soft saw-ish chord under the bar
        pad = sum(np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) for f in tones)
        put(int(b0 * SR), 0.035 * pad * np.minimum(1, t / 0.05) * np.minimum(1, (4 * beat - t) / 0.05))
        for q in range(4):                                   # drums
            tq = b0 + q * beat
            if fast or q in (0, 2):
                put(int(tq * SR), 0.7 * synth("kick"))
            if q in (1, 3):
                put(int(tq * SR), 0.45 * synth("snare"))
            if not fast and q == 3:
                put(int((tq + beat / 2) * SR), 0.5 * synth("kick"))
            hats = 4 if fast else 2
            for h in range(hats):
                put(int((tq + h * beat / hats) * SR), (0.25 if h % 2 else 0.15) * synth("hihat"))
    out[:int(0.003 * SR)] *= np.linspace(0, 1, int(0.003 * SR))      # no click at the loop point
    out[-int(0.003 * SR):] *= np.linspace(1, 0, int(0.003 * SR))
    return 0.85 * out / max(1e-9, np.abs(out).max())


def groove(bpm: float, beats: int, count_in: int = 4) -> np.ndarray:
    """Level 1 play-along beat (v5.7), generated for the exact tempo so it can never drift from the wands.
    Starts at the count-in: sticks + hi-hat for `count_in` beats, then a Wild-West "train" groove for
    `beats` beats (kick on 1 + 3, snare on 2 + 4, 8th hats, boom-chick bass, guitar strum on the off-beats)
    over Am - G - F - E, then one ring-out beat. Played as ONE sound, scheduled at the first count-in beat."""
    rng = np.random.default_rng(int(bpm) * 31 + beats)
    beat = 60.0 / bpm
    total = count_in + beats + 2
    n = int(total * beat * SR)
    out = np.zeros(n)

    def put(t, x, vol=1.0):
        i0 = int(round(t * SR))
        if i0 >= n:
            return
        i1 = min(n, i0 + len(x))
        out[i0:i1] += vol * x[:i1 - i0]

    def pluck(f, dur, decay):                   # twangy guitar-ish tone (saw + a bit of square)
        m = int(dur * SR); t = np.arange(m) / SR
        ph = (f * t) % 1.0
        w = (2 * ph - 1) * 0.7 + 0.3 * np.sign(np.sin(2 * np.pi * f * t))
        return w * _env(m, decay) * np.minimum(1, t / 0.003)

    def bass(f, dur):
        m = int(dur * SR); t = np.arange(m) / SR
        return (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)) * _env(m, 0.18) * np.minimum(1, t / 0.004)

    stick = synth("click") * 0.9
    kick, snare, hat = synth("kick"), synth("snare"), synth("hihat")
    # count-in: a stick on every beat (accent on 1), hats on the 8ths so you feel the speed before it starts
    for c in range(count_in):
        put(c * beat, stick, 1.0 if c == 0 else 0.7)
        put(c * beat, hat, 0.35)
        put((c + 0.5) * beat, hat, 0.25)
    chords = [(110.0, [220.0, 261.6, 329.6]),     # Am
              (98.0, [196.0, 246.9, 293.7]),      # G
              (87.31, [174.6, 220.0, 261.6]),     # F
              (82.41, [164.8, 207.7, 246.9])]     # E (the "Spanish" turnaround - very spaghetti western)
    t0 = count_in * beat
    for k in range(beats):
        t = t0 + k * beat
        q = k % 4
        root, tones = chords[(k // 4) % 4]
        put(t, kick if q in (0, 2) else snare, 0.85 if q in (0, 2) else 0.55)
        if q == 3:
            put(t + beat / 2, kick, 0.45)                             # pickup into the next bar
        put(t, hat, 0.3 if q % 2 else 0.2)
        put(t + beat / 2, hat, 0.32)                                  # off-beat hats drive it along
        put(t, bass(root if q in (0, 1) else root * 1.5, beat * 0.9), 0.32)   # boom ... root, fifth
        strum = sum(pluck(f, beat * 0.45, 0.09) for f in tones)
        put(t + beat / 2, strum, 0.07)                                # "chick" on the off-beat
        if k % 4 == 0:
            put(t, pluck(tones[2] * 2, beat * 0.9, 0.25), 0.08)      # little twang on each new chord
    end = t0 + beats * beat
    put(end, kick, 0.9)                                               # final hit + ring out
    put(end, sum(pluck(f, beat * 1.8, 0.5) for f in chords[0][1]), 0.09)
    put(end, bass(110.0, beat * 1.8), 0.32)
    out[-int(0.05 * SR):] *= np.linspace(1, 0, int(0.05 * SR))
    return 0.85 * out / max(1e-9, np.abs(out).max())


NAMES = ["click", "kick", "snare", "hihat", "wrong", "heartbeat", "draw", "gunshot", "jam", "win",
         "chant", "zap", "water", "fire", "block", "hurt", "freeze", "level",
         "battle", "battle_fast", "hum", "cheer", "surge", "drumroll", "arcane", "western", "crowd"]
LOOPS = ("battle", "battle_fast", "hum", "arcane", "western", "crowd")
FILE_ONLY = ("western", "crowd")    # recordings: no generated fallback (silent if the file is missing)


class SoundBank:
    """Loads every sound into pygame.mixer (or does nothing if muted)."""

    def __init__(self, enabled=True, folder=None):
        self.sounds = {}
        self.looping = set()
        self.enabled = enabled
        self.voice = None                     # mixer channel kept free for the announcer
        self.voice_on = True
        self.gains = {"music": 1.0, "effects": 1.0, "voice": 1.0}   # from the SETTINGS menu (0..1)
        self.wanted = {}                      # volume each sound was asked for (before the gain)
        if not enabled:
            return
        import pygame
        folder = folder or os.path.join(os.path.dirname(__file__), "sounds")
        # announcer lines (sounds/announcer/ann_*.wav) get their own channel, so a new line
        # cuts off the old one instead of talking over it, and they never steal music channels
        pygame.mixer.set_num_channels(24)
        pygame.mixer.set_reserved(1)
        self.voice = pygame.mixer.Channel(0)
        ann = os.path.join(folder, "announcer")
        if os.path.isdir(ann):
            for fn in sorted(os.listdir(ann)):
                stem, ext = os.path.splitext(fn)
                if stem.startswith("ann_") and ext.lower() in (".wav", ".ogg") and stem not in self.sounds:
                    try:
                        self.sounds[stem] = pygame.mixer.Sound(os.path.join(ann, fn))
                    except pygame.error as e:
                        print(f"Could not load announcer line {fn}: {e}")
        for name in NAMES:
            path = next((os.path.join(folder, f"{name}.{ext}") for ext in ("wav", "ogg")
                         if os.path.exists(os.path.join(folder, f"{name}.{ext}"))), None)
            if path:
                try:
                    self.sounds[name] = pygame.mixer.Sound(path)
                    continue
                except pygame.error as e:
                    print(f"Could not load {path}: {e} - using the generated sound")
            if name in FILE_ONLY:
                continue
            mono = np.clip(synth(name), -1, 1)
            stereo = np.repeat((mono * 32000).astype(np.int16)[:, None], 2, axis=1)
            self.sounds[name] = pygame.sndarray.make_sound(np.ascontiguousarray(stereo))

    def add(self, name, mono):
        """Register a sound made at run time (e.g. a groove for this tempo). Does nothing when muted."""
        if not self.enabled or name in self.sounds:
            return
        import pygame
        mono = np.clip(mono, -1, 1)
        stereo = np.repeat((mono * 32000).astype(np.int16)[:, None], 2, axis=1)
        self.sounds[name] = pygame.sndarray.make_sound(np.ascontiguousarray(stereo))

    def gain(self, name):
        if name.startswith("ann_"):
            return self.gains["voice"]
        return self.gains["music"] if (name in LOOPS or name.startswith("groove")) else self.gains["effects"]

    def set_gains(self, music=None, effects=None, voice=None):
        """Master volumes 0..1. Loops that are playing change straight away."""
        for k, v in (("music", music), ("effects", effects), ("voice", voice)):
            if v is not None:
                self.gains[k] = max(0.0, min(1.0, v))
        for name in self.looping:
            self.set_volume(name, self.wanted.get(name, 1.0))

    def play(self, name, volume=1.0):
        s = self.sounds.get(name)
        if s is None:
            return
        s.set_volume(volume * self.gain(name))
        if name.startswith("ann_"):
            if self.voice is not None and self.voice_on:
                self.voice.play(s)                 # replaces whatever the announcer was saying
            return
        s.play()

    def stop_voice(self):
        if self.voice is not None:
            self.voice.stop()

    # ---- looping sounds (Level 3 music and beam hum) ----
    def loop(self, name, volume=1.0, fade_ms=400):
        """Start `name` looping forever (does nothing if it is already looping)."""
        s = self.sounds.get(name)
        if s is None or name in self.looping:
            return
        self.wanted[name] = volume
        s.set_volume(volume * self.gain(name))
        s.play(loops=-1, fade_ms=fade_ms)
        self.looping.add(name)

    def set_volume(self, name, volume):
        s = self.sounds.get(name)
        if s is not None:
            self.wanted[name] = volume
            s.set_volume(max(0.0, min(1.0, volume)) * self.gain(name))

    def stop(self, name, fade_ms=400):
        s = self.sounds.get(name)
        if s is not None and name in self.looping:
            s.fadeout(fade_ms)
        self.looping.discard(name)

    def stop_loops(self, fade_ms=400):
        for name in list(self.looping):
            self.stop(name, fade_ms)
