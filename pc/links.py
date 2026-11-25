"""
links.py — how the laptop talks to the blasters.

BleLink : real TinyScreen+ blasters over Bluetooth LE (bleak), in a background thread.
SimLink : fake blasters for testing without hardware (keyboard or auto "bots").

Both push events into a queue.Queue as tuples:
    ("status", player_index, text, t)     connection status changes
    ("msg",    player_index, packet, t)   a packet from a blaster (e.g. "T231120")
t is time.perf_counter() when it arrived.
"""
from __future__ import annotations

import asyncio
import heapq
import queue
import random
from typing import Optional
import threading
import time

from game_logic import (BEATS_PER_ROUND, COUNT_IN_BEATS, DRAW_TIMEOUT_MS, HIT_WINDOW_MS, LEVEL_INTRO_MS,
                        MAX_BULLETS, MAX_MANA, SPELLS, START_MANA, CAST_COOLDOWN_MS, CHARGE_MS, counter_of, judge_hit,
                        TUTORIAL_ORDER, TUTORIAL_REPEATS)

# Nordic UART Service, as set up by firmware/BeatDrawBlaster/UART.ino
UART_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"    # laptop -> blaster
NOTIFY_CHAR = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"   # blaster -> laptop


# ======================================================================
#  Real Bluetooth
# ======================================================================
class BleLink:
    """Keeps a connection to each named blaster, reconnecting automatically.

    Runs bleak in its own thread with its own asyncio loop. This avoids the
    Windows "STA/COM" clash between pygame (SDL) and bleak's WinRT backend.
    """

    def __init__(self, names: list[str], events: queue.Queue):
        self.names = names
        self.events = events
        self.clients = [None] * len(names)
        self.addresses = [None] * len(names)   # remembered after the first connect = fast reconnect
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._thread_main, daemon=True)
        self._running = True

    # ---- public API (called from the game thread) --------------------
    def start(self):
        self.thread.start()

    def is_connected(self, i: int) -> bool:
        c = self.clients[i]
        return c is not None and c.is_connected

    def send(self, i: int, text: str):
        asyncio.run_coroutine_threadsafe(self._write(i, text), self.loop)

    def send_many(self, texts: dict):
        """Send to several blasters at the same moment (used for R, W, G)."""
        asyncio.run_coroutine_threadsafe(self._write_many(texts), self.loop)

    def tick(self, now: float):
        pass

    def stop(self):
        self._running = False
        fut = asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop)
        try:
            fut.result(timeout=5)
        except Exception:
            pass

    # ---- background thread -------------------------------------------
    def _thread_main(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._manager())
        except Exception as e:  # keep the game alive even if BLE dies
            self._status(0, f"BLE crashed: {e}")

    def _status(self, i: int, text: str):
        self.events.put(("status", i, text, time.perf_counter()))

    async def _manager(self):
        from bleak import BleakScanner  # imported here so --sim works without bleak

        while self._running:
            missing = [i for i in range(len(self.names)) if not self.is_connected(i)]
            for i in list(missing):          # known wand: connect straight to its address (no 4 s scan)
                if self.addresses[i] and await self._connect(i, self.addresses[i], timeout=5.0):
                    missing.remove(i)
            if missing:
                for i in missing:
                    self._status(i, "scanning...")
                try:
                    found = await BleakScanner.discover(timeout=4.0, return_adv=True)
                except Exception as e:
                    for i in missing:
                        self._status(i, f"scan failed: {e}")
                    await asyncio.sleep(3)
                    continue
                for _addr, (dev, adv) in found.items():
                    name = adv.local_name or dev.name
                    for i in missing:
                        if name == self.names[i] and not self.is_connected(i):
                            await self._connect(i, dev)
            await asyncio.sleep(1.0)

    async def _connect(self, i: int, dev, timeout: float = 10.0) -> bool:
        from bleak import BleakClient

        self._status(i, "connecting...")
        try:
            client = BleakClient(dev, disconnected_callback=lambda _c, i=i: self._status(i, "disconnected"))
            await client.connect(timeout=timeout)
            await client.start_notify(NOTIFY_CHAR, lambda _h, data, i=i: self._on_notify(i, data))
            self.clients[i] = client
            self.addresses[i] = client.address
            self._status(i, "connected")
            return True
        except Exception as e:
            self._status(i, f"connect failed: {e}")
            return False

    def _on_notify(self, i: int, data: bytearray):
        t = time.perf_counter()
        msg = bytes(data).split(b"\x00")[0].decode(errors="ignore").strip()
        if msg:
            self.events.put(("msg", i, msg, t))

    async def _write_many(self, texts: dict):
        await asyncio.gather(*(self._write(i, t) for i, t in texts.items()))

    async def _write(self, i: int, text: str):
        c = self.clients[i]
        if c is None or not c.is_connected:
            return
        try:
            # The blaster's characteristic is write-WITHOUT-response (see UART.ino)
            await c.write_gatt_char(WRITE_CHAR, text.encode()[:20], response=False)
        except Exception as e:      # one lost packet is not a disconnect: just report it
            self.events.put(("warn", i, f"send failed: {e}", time.perf_counter()))

    async def _shutdown(self):
        for c in self.clients:
            if c is not None and c.is_connected:
                try:
                    await c.disconnect()
                except Exception:
                    pass


# ======================================================================
#  Simulated blasters (no hardware needed)
# ======================================================================


class SimDevice:
    """A Python copy of the firmware state machine. Used for testing the
    referee and for practising the game flow on a laptop keyboard."""

    def __init__(self, idx: int, emit, bot: bool, rng: random.Random, form: Optional[bool] = None):
        self.idx = idx
        self.emit = emit              # emit(packet_text, at_time)
        self.bot = bot
        self.rng = rng
        self.form = form              # filming (--winner): True = this bot plays sharp, False = sloppy, None = normal
        self.state = "lobby"
        self.pattern = "--------"
        self.beat_ms = 500.0
        self.t0 = 0.0
        self.used = [False] * BEATS_PER_ROUND
        self.bullets = 0
        self.cue = 0.0
        self.standoff_start = 0.0
        self.bot_actions = []         # (time, action)
        # level 2
        self.mana = START_MANA
        self.last_cast = -99.0
        self.last_charge = -99.0
        self.level_start = 0.0
        self.bot_next_think = 0.0
        # level 3
        self.combo = ""
        self.go_t = 0.0
        self.casts = 0
        self.l3_round = 0
        self.battery = rng.randint(55, 100)  # fake battery that slowly drains
        self.last_batt = -99.0
        self.reset_cause = "P"
        self.warmup = False
        self.tut_still = False            # cowboy tutorial holster practice: stream s<n>, never foul
        self.last_still = 0.0
        self.moved_until = -1.0

    # commands from the referee -----------------------------------------
    def on_command(self, text: str, now: float):
        c = text[:1]
        if c == "P":
            self.emit("Q", now)
        elif c == "V":
            self.emit(f"V5.1,SIM-{self.idx + 1},0,{self.reset_cause}", now)
            self.emit(f"%{self.battery}", now)
            self.last_batt = now
        elif c == "L":
            self.state = "lobby"
            self.tut_still = False
            self.bot_actions = []
        elif c == "O" and text[1:2] == "1":                    # cowboy tutorial: free arrow flicks
            self.state = "tut_arrows"
            self.bot_actions = []
            if self.bot:                                       # bots learn U, D, L, R (twice each)
                t = now + self.rng.uniform(1.5, 2.5)
                for g in "UDLR":
                    for _ in range(2):
                        if self.rng.random() < 0.12:           # a wrong flick sometimes
                            self._plan(t, "d" + self.rng.choice([x for x in "UDLR" if x != g]))
                            t += self.rng.uniform(0.8, 1.4)
                        self._plan(t, "d" + g)
                        t += self.rng.uniform(0.8, 1.5)
        elif c == "O" and text[1:2] == "3":                    # cowboy tutorial: holster practice
            self.state = "standoff"
            self.standoff_start = now
            self.tut_still = True
            self.last_still = now + 0.3                        # 300 ms to learn the pose first
            self.bot_actions = []
        elif c == "w":                                         # Level 2 warm-up: free spells
            self.state = "spell"
            self.warmup = True
            self.level_start = now
            self.bot_actions = []
            if self.bot:                                       # bots do the spell tutorial: L, W, F twice each
                t = now + self.rng.uniform(1.5, 2.5)
                for sp in TUTORIAL_ORDER:
                    for _ in range(TUTORIAL_REPEATS):
                        if self.rng.random() < 0.2:                # a fizzle first sometimes
                            self._plan(t, "?" + sp)
                            t += self.rng.uniform(1.0, 1.6)
                        elif self.rng.random() < 0.1:              # or the wrong spell
                            self._plan(t, self.rng.choice([x for x in SPELLS if x != sp]))
                            t += self.rng.uniform(1.0, 1.6)
                        self._plan(t, sp)
                        t += self.rng.uniform(1.0, 1.8)
        elif c == "R":                                         # v5.7: R<3-digit bpm><pattern> (old R120,... too)
            if "," in text:
                bpm, pat = int(text[1:text.index(",")]), text[text.index(",") + 1:]
            else:
                bpm, pat = int(text[1:4]), text[4:]
            self.pattern = pat[:BEATS_PER_ROUND]
            self.beat_ms = 60000.0 / bpm
            self.t0 = now + COUNT_IN_BEATS * self.beat_ms / 1000
            self.used = [False] * len(self.pattern)
            self.bullets = 0
            self.state = "drum"
            if self.bot:
                self._plan_bot_drums()
        elif c == "W":
            self.tut_still = False
            self.state = "standoff"
            self.standoff_start = now
            if self.bot and self.form is None and self.rng.random() < 0.08:   # bots sometimes flinch
                self._plan(now + self.rng.uniform(0.5, 1.4), "X")
        elif c == "G":
            if self.state == "standoff":
                self.tut_still = False
                self.state = "draw"
                self.cue = now
                if self.bot:
                    lo, hi = {True: (0.17, 0.22), False: (0.36, 0.48)}.get(self.form, (0.18, 0.42))
                    self._plan(now + self.rng.uniform(lo, hi), "X")
        elif c == "E":
            self.state = "result"
        elif c == "M" and text[1:2] == "2":                    # M2,<bpm>,<hp>,<opp>
            self.warmup = False
            parts = text[3:].split(",")
            self.beat_ms = 60000.0 / int(parts[0])
            self.level_start = now + LEVEL_INTRO_MS / 1000
            self.t0 = self.level_start
            self.mana = START_MANA
            self.last_cast = -99.0
            self.last_charge = -99.0
            self.bot_actions = []
            self.bot_next_think = self.level_start + 0.5
            self.state = "spell"
        elif c == "M" and text[1:2] == "3":                    # M3,<mypos>
            self.l3_round = 0
            self.level_start = now + LEVEL_INTRO_MS / 1000
            self.bot_actions = []
            self.state = "beam"
        elif c == "I" and self.bot and self.state == "spell":  # incoming enemy spell
            p_try, p_right = {True: (0.95, 1.0), False: (0.35, 0.5)}.get(self.form, (0.7, 0.85))
            if self.mana > 0 and self.rng.random() < p_try:
                spell = counter_of(text[1]) if self.rng.random() < p_right else self.rng.choice(SPELLS)
                self._plan(now + self.rng.uniform(0.35, 0.9), spell)
        elif c == "Z":                                         # Z<combo><flash x 0.1 s>: watch the combo (3-5)
            self.combo = "".join(ch for ch in text[1:] if ch in SPELLS)
            self.l3_round += 1
            self.state = "show"
            self.bot_actions = []
        elif c == "K":                                         # GO: cast the combo
            self.state = "combo"
            self.go_t = now
            self.casts = 0
            if self.bot:                                       # bots remember each spell 80 % of the time
                t = now + self.rng.uniform(0.6, 1.0)
                memory, gap = 0.8, (0.6, 1.2)
                if self.form is not None:
                    # filming (--winner): both remember everything, so every round pushes 10 and the match
                    # lasts to the 5-spell FINAL round; the faster one wins the round - the loser takes
                    # rounds 2 and 4, the chosen winner the rest (and the match)
                    memory = 1.0
                    wins = self.form != (self.l3_round in (2, 4))
                    gap = (0.45, 0.6) if wins else (0.85, 1.05)
                for k in range(len(self.combo)):
                    spell = self.combo[k] if self.rng.random() < memory else self.rng.choice(SPELLS)
                    self._plan(t, spell)
                    t += self.rng.uniform(*gap)
        elif c == "J":                                         # round over
            if self.state in ("show", "combo"):
                self.state = "beam"
                self.bot_actions = []
        elif c == "Y":
            self.state = "result"
            self.bot_actions = []

    # player input -----------------------------------------------------
    def on_key(self, action: str, now: float):
        """action: 'dU'/'dD'/'dL'/'dR' drum arrow, 'X' draw flick / charge pose, 'L'/'W'/'F' spells."""
        if action[:1] == "d" and len(action) == 2:
            if self.state not in ("drum", "tut_arrows"):
                return
            action = action[1]
            if self.state == "tut_arrows":
                self.emit(f"d{action}", now)
                return
            rel_ms = (now - self.t0) * 1000
            k0 = int((rel_ms + self.beat_ms / 2) // self.beat_ms)
            if 0 <= k0 < len(self.pattern) and self.used[k0] and abs(rel_ms - k0 * self.beat_ms) <= HIT_WINDOW_MS + 100:
                return                                        # rebound of a loaded beat: ignored (as firmware)
            k, ok, err = judge_hit(rel_ms, action, self.pattern, self.beat_ms, self.used)
            if k >= 0:
                if ok and self.bullets < MAX_BULLETS:
                    self.bullets += 1
                self.emit(f"H{k}{action}{1 if ok else 0}{err:+d}", now)
        elif action[:1] == "?" and self.state in ("spell", "combo"):
            self.emit(f"f{action[1:2] or 's'}", now)              # FIZZLE + the closest spell
        elif self.state == "spell" and self.warmup and action in SPELLS:
            self.emit(f"C{action}0", now)                      # warm-up: free spells
        elif self.state == "spell" and now >= self.level_start:
            if action == "X":                                 # = one finished charge pose (+1 mana)
                if (now - self.last_charge) * 1000 >= CHARGE_MS:
                    self.last_charge = now
                    if self.mana < MAX_MANA:
                        self.mana += 1
                    self.emit(f"A{self.mana}", now)
            elif action in SPELLS:
                if self.mana > 0 and (now - self.last_cast) * 1000 >= CAST_COOLDOWN_MS:
                    self.mana -= 1
                    self.last_cast = now
                    self.emit(f"C{action}{self.mana}", now)
        elif self.state == "combo" and action in SPELLS and self.casts < len(self.combo):
            self.casts += 1
            self.emit(f"X{action}{int((now - self.go_t) * 1e6)}", now)
        elif action == "X":
            if self.state == "standoff" and self.tut_still:
                self.moved_until = now + 0.25                  # tutorial: shows on the stillness meter instead
            elif self.state == "standoff":
                self.state = "result"
                self.emit("F", now)
            elif self.state == "draw":
                self.state = "result"
                self.emit(f"T{int((now - self.cue) * 1e6)}", now)

    def tick(self, now: float):
        if self.last_batt > 0 and now - self.last_batt >= 10.0:      # like BATT_SEND_MS in config.h
            self.last_batt = now
            self.battery = max(0, self.battery - 1)
            self.emit(f"%{self.battery}", now)
        if self.state == "standoff" and self.tut_still and now - self.last_still >= 0.1:
            self.last_still = now                              # stillness stream, like the firmware (every 100 ms)
            if now < self.moved_until:
                n = 15
            elif self.bot:
                n = 13 if self.rng.random() < 0.02 else self.rng.choice((0, 1, 1, 2, 3))
            else:
                n = 1
            self.emit(f"s{n}", now)
        while self.bot_actions and self.bot_actions[0][0] <= now:
            _, a = self.bot_actions.pop(0)
            self.on_key(a, now)
        if self.state == "drum":
            end = self.t0 + (len(self.pattern) * self.beat_ms + HIT_WINDOW_MS) / 1000
            if now > end:
                self.state = "holster"
                self.emit(f"B{self.bullets}", now)
        elif self.state == "draw" and now - self.cue > DRAW_TIMEOUT_MS / 1000:
            self.state = "result"
            self.emit("N", now)
        elif self.state == "spell" and self.bot and not self.warmup and now >= self.bot_next_think:
            self._bot_spell_think(now)

    def _bot_spell_think(self, now):
        """Bot: hold the charge pose until it has mana, then attack."""
        if self.mana < 2 or self.rng.random() < 0.3:
            self._plan(now + CHARGE_MS / 1000, "X")           # one charge takes CHARGE_MS
            self.bot_next_think = now + CHARGE_MS / 1000 + 0.05
        else:
            if self.rng.random() < 0.6:
                self._plan(now + self.rng.uniform(0.05, 0.3), self.rng.choice(SPELLS))
            self.bot_next_think = now + 0.5

    def _plan(self, t, action):
        self.bot_actions.append((t, action))
        self.bot_actions.sort()

    def _plan_bot_drums(self):
        acts = []
        for k, g in enumerate(self.pattern):
            if g == "-":
                continue
            miss, wrong, sd = {True: (0.0, 0.0, 30), False: (0.15, 0.15, 75)}.get(self.form, (0.1, 0.1, 60))
            if self.rng.random() < miss:                       # missed note
                continue
            jitter = self.rng.gauss(0, sd) / 1000
            if self.rng.random() < wrong:                      # wrong arrow
                g = self.rng.choice([x for x in "UDLR" if x != g])
            acts.append((self.t0 + k * self.beat_ms / 1000 + jitter, "d" + g))
        self.bot_actions = sorted(acts)


class SimLink:
    """Drop-in replacement for BleLink. Adds fake Bluetooth latency.

    clock: function returning the current time (time.perf_counter, or a fake
    clock for the fast automated tests)."""

    KEYMAP = {  # keyboard controls for human sim players
        # P1: W A S D = arrows, F = draw / charge, Z X C = Lightning / Water / Fire
        "w": (0, "dU"), "a": (0, "dL"), "s": (0, "dD"), "d": (0, "dR"), "f": (0, "X"),
        "z": (0, "L"), "x": (0, "W"), "c": (0, "F"),
        # P2: I J K L = arrows, H = draw / charge, , . / = Lightning / Water / Fire
        "i": (1, "dU"), "j": (1, "dL"), "k": (1, "dD"), "l": (1, "dR"), "h": (1, "X"),
        ",": (1, "L"), ".": (1, "W"), "/": (1, "F"),
    }

    def __init__(self, events: queue.Queue, bots=(False, False), latency_ms=(18, 26), seed=None,
                 clock=time.perf_counter, winner: Optional[int] = None):
        self.events = events
        self.clock = clock
        self.rng = random.Random(seed)
        self.latency = [l / 1000 for l in latency_ms]
        self._pending = []   # heap of (time, seq, kind, idx, payload)
        self._seq = 0
        forms = [None, None] if not winner else [winner == 1, winner == 2]   # --winner: who the bots let win
        self.devices = [SimDevice(i, self._make_emit(i), bots[i], self.rng, forms[i]) for i in range(2)]
        self.up = [True, True]
        self._last_down = [0.0, 0.0]

    def _make_emit(self, i):
        def emit(text, at):
            self._push(at + self._lat(i), "up", i, text)
        return emit

    def _lat(self, i):
        return max(0.004, self.latency[i] + self.rng.uniform(-0.006, 0.006))

    def _push(self, t, kind, i, payload):
        heapq.heappush(self._pending, (t, self._seq, kind, i, payload))
        self._seq += 1

    def start(self):
        for i in range(2):
            self.events.put(("status", i, "connected (sim)", self.clock()))

    def is_connected(self, i):
        return self.up[i]

    def drop(self, i: int, seconds: float = 4.0, cause: str = "W"):
        """Pretend wand i froze / lost Bluetooth for `seconds`, then rebooted (watchdog) and reconnected."""
        if not self.up[i]:
            return
        now = self.clock()
        self.up[i] = False
        self.events.put(("status", i, "disconnected", now))
        self._push(now + seconds, "back", i, cause)

    def send(self, i, text):
        if self.up[i]:                                     # Bluetooth keeps packets in order: so does the sim
            t = max(self.clock() + self._lat(i), self._last_down[i] + 1e-4)
            self._last_down[i] = t
            self._push(t, "down", i, text)

    def send_many(self, texts):
        for i, t in texts.items():
            self.send(i, t)

    def key(self, keyname: str):
        if keyname in self.KEYMAP:
            i, action = self.KEYMAP[keyname]
            self.devices[i].on_key(action, self.clock())

    def tick(self, now: float):
        while self._pending and self._pending[0][0] <= now:
            t, _, kind, i, payload = heapq.heappop(self._pending)
            if kind == "back":                                 # the wand rebooted and is back
                d = self.devices[i]
                d.state, d.bot_actions, d.reset_cause, d.warmup = "lobby", [], payload, False
                self.up[i] = True
                self.events.put(("status", i, "connected (sim)", t))
            elif kind == "down":
                self.devices[i].on_command(payload, t)
            elif self.up[i]:
                self.events.put(("msg", i, payload, t))
        for d in self.devices:
            d.tick(now)

    def stop(self):
        pass
