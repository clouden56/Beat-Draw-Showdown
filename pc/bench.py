"""
bench.py — measure the wands for your test log / report (one wand at a time, arena closed).

    python bench.py latency  BDS-1            # 200 pings -> Bluetooth delay (median, 95 %, worst, lost)
    python bench.py gestures BDS-1 --n 10 --who Fadil
                                              # you cast 10 x each spell when told -> accuracy + mix-ups
    python bench.py battery  BDS-1            # logs the battery % until you press Ctrl+C -> % per hour

Every run saves a CSV in pc/bench_results/ and prints a Markdown table row you can paste
straight into docs/TEST_LOG.md. Needs firmware 5.0 (the gesture test uses the Level 2 warm-up mode).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import os
import random
import statistics
import time

from game_logic import FIZZLE_HINTS, SPELL_NAMES, SPELLS

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench_results")
MOVES = {"L": "ZIG-ZAG", "W": "CIRCLE", "F": "THRUST"}


# ----------------------------------------------------------------------------------------------
# pure maths (tested in tests/test_bench.py)
# ----------------------------------------------------------------------------------------------
def summarize_latency(rtts_ms: list[float], sent: int) -> dict:
    """Round-trip times -> the numbers for the report (one-way = round-trip / 2)."""
    if not rtts_ms:
        return {"sent": sent, "lost_pct": 100.0}
    s = sorted(rtts_ms)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return {"sent": sent, "lost_pct": 100.0 * (sent - len(s)) / sent,
            "median_ms": statistics.median(s), "mean_ms": statistics.mean(s), "p95_ms": p95,
            "max_ms": s[-1], "one_way_ms": statistics.median(s) / 2}


def summarize_gestures(trials: list[tuple[str, str]]) -> dict:
    """trials = [(asked, got)] with got in L/W/F, '?' (fizzle) or '-' (nothing) -> accuracy + confusion."""
    per = {}
    for sp in SPELLS:
        mine = [g for a, g in trials if a == sp]
        if mine:
            per[sp] = {"n": len(mine), "right": sum(g == sp for g in mine),
                       "got": {k: mine.count(k) for k in list(SPELLS) + ["?", "-"] if mine.count(k)}}
    total = len(trials)
    right = sum(a == g for a, g in trials)
    return {"n": total, "right": right, "pct": 100.0 * right / total if total else 0.0, "per": per}


def drain_per_hour(samples: list[tuple[float, int]]) -> float | None:
    """samples = [(seconds, battery %)] -> % used per hour (least-squares slope), None if too short."""
    if len(samples) < 3 or samples[-1][0] - samples[0][0] < 300:
        return None
    ts = [t for t, _ in samples]
    ps = [p for _, p in samples]
    mt, mp = statistics.mean(ts), statistics.mean(ps)
    den = sum((t - mt) ** 2 for t in ts)
    slope = sum((t - mt) * (p - mp) for t, p in zip(ts, ps)) / den if den else 0.0
    return -slope * 3600


# ----------------------------------------------------------------------------------------------
# Bluetooth
# ----------------------------------------------------------------------------------------------
class Wand:
    def __init__(self, name):
        self.name = name
        self.client = None
        self.q: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        from bleak import BleakClient, BleakScanner
        from links import NOTIFY_CHAR
        dev = await BleakScanner.find_device_by_name(self.name, timeout=8.0)
        if dev is None:
            raise SystemExit(f"Could not find {self.name} - is it on and not connected to the arena?")
        self.client = BleakClient(dev)
        await self.client.connect()
        await self.client.start_notify(
            NOTIFY_CHAR, lambda _h, d: self.q.put_nowait((time.perf_counter(),
                                                          bytes(d).split(b"\x00")[0].decode(errors="ignore"))))
        print(f"Connected to {self.name}")
        return self

    async def __aexit__(self, *_):
        try:
            await self.send("L")
            await self.client.disconnect()
        except Exception:
            pass

    async def send(self, text):
        from links import WRITE_CHAR
        await self.client.write_gatt_char(WRITE_CHAR, text.encode(), response=False)

    async def get(self, timeout):
        try:
            return await asyncio.wait_for(self.q.get(), timeout)
        except asyncio.TimeoutError:
            return None, None


def _save(kind, name, header, rows):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{kind}_{name}_{dt.datetime.now():%Y%m%d_%H%M}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"Saved {path}")


async def latency(name, n):
    async with Wand(name) as w:
        rtts, rows = [], []
        for k in range(n):
            while not w.q.empty():                      # ignore battery packets etc.
                w.q.get_nowait()
            t0 = time.perf_counter()
            await w.send("P")
            rtt = None
            while True:
                t1, msg = await w.get(1.0)
                if msg is None:
                    break
                if msg == "Q":
                    rtt = (t1 - t0) * 1000
                    break
            if rtt is not None:
                rtts.append(rtt)
            rows.append([k, "" if rtt is None else f"{rtt:.2f}"])
            if k % 20 == 19:
                print(f"  {k + 1}/{n}")
            await asyncio.sleep(0.05)
    r = summarize_latency(rtts, n)
    _save("latency", name, ["ping", "round_trip_ms"], rows)
    if "median_ms" not in r:
        print("No pongs at all - is the Beat-Draw firmware on the wand?")
        return
    print(f"\nRound trip: median {r['median_ms']:.1f} ms, 95% under {r['p95_ms']:.1f} ms, worst {r['max_ms']:.1f} ms,"
          f" lost {r['lost_pct']:.1f}%  ->  one-way about {r['one_way_ms']:.1f} ms")
    print("\nPaste into docs/TEST_LOG.md:")
    print(f"| {dt.date.today()} | {name} | latency | {n} pings | median RTT {r['median_ms']:.1f} ms, "
          f"95% {r['p95_ms']:.1f} ms, max {r['max_ms']:.1f} ms, lost {r['lost_pct']:.1f}% | |")


async def gestures(name, n, who, wait_s=6.0):
    order = [sp for sp in SPELLS for _ in range(n)]
    random.shuffle(order)
    trials, rows = [], []
    async with Wand(name) as w:
        await w.send("w")                               # warm-up mode: free spells, reported with C / f
        print(f"\n{who}: cast each spell when it appears. {len(order)} tries. Get ready...")
        await asyncio.sleep(3)
        for k, sp in enumerate(order):
            while not w.q.empty():
                w.q.get_nowait()
            print(f"\n[{k + 1}/{len(order)}]  Cast {SPELL_NAMES[sp]}  ({MOVES[sp]})")
            t0 = time.perf_counter()
            got, ms = "-", None
            while time.perf_counter() - t0 < wait_s:
                t1, msg = await w.get(wait_s - (time.perf_counter() - t0))
                if msg is None:
                    break
                if msg[:1] == "C" and len(msg) >= 2:
                    got, ms = msg[1], (t1 - t0) * 1000
                    break
                if msg[:1] == "f":
                    got, ms = "?", (t1 - t0) * 1000
                    print(f"   FIZZLE - {FIZZLE_HINTS.get(msg[1:2], '')}")
                    break
            print("   RIGHT" if got == sp else f"   wrong: got {SPELL_NAMES.get(got, 'fizzle' if got == '?' else 'nothing')}")
            trials.append((sp, got))
            rows.append([k, who, sp, got, "" if ms is None else f"{ms:.0f}"])
            await asyncio.sleep(1.2)
    r = summarize_gestures(trials)
    _save("gestures", name, ["try", "player", "asked", "got", "ms_to_result"], rows)
    print(f"\n{who}: {r['right']}/{r['n']} right ({r['pct']:.0f}%)")
    for sp, d in r["per"].items():
        mix = ", ".join(f"{k}x{v}" for k, v in d["got"].items() if k != sp)
        print(f"  {SPELL_NAMES[sp]:9s} {d['right']}/{d['n']}" + (f"   mix-ups: {mix}" if mix else ""))
    per = "  ".join(f"{sp} {d['right']}/{d['n']}" for sp, d in r["per"].items())
    print("\nPaste into docs/TEST_LOG.md:")
    print(f"| {dt.date.today()} | {name} | gestures ({who}) | {r['n']} casts | {r['pct']:.0f}% right ({per}) | |")


async def battery(name):
    samples, rows = [], []
    async with Wand(name) as w:
        await w.send("V")
        t_start = time.perf_counter()
        print("Logging battery % (the wand sends it every 10 s). Leave it running; Ctrl+C to stop.")
        try:
            while True:
                t, msg = await w.get(30)
                if msg and msg[:1] == "%":
                    pct = int(msg[1:])
                    el = t - t_start
                    samples.append((el, pct))
                    rows.append([dt.datetime.now().isoformat(timespec="seconds"), f"{el:.0f}", pct])
                    rate = drain_per_hour(samples)
                    extra = f"   ~{rate:.1f} %/h -> about {pct / rate:.1f} h left" if rate and rate > 0 else ""
                    print(f"  {el / 60:6.1f} min  {pct:3d}%{extra}")
                    if pct <= 3:
                        print("Battery almost empty - stopping.")
                        break
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
    if rows:
        _save("battery", name, ["time", "seconds", "battery_pct"], rows)
    rate = drain_per_hour(samples)
    if rate:
        print(f"\nPaste into docs/TEST_LOG.md:\n| {dt.date.today()} | {name} | battery | "
              f"{samples[-1][0] / 60:.0f} min, {samples[0][1]}% -> {samples[-1][1]}% | {rate:.1f} %/hour "
              f"(~{100 / rate:.1f} h full charge) | |")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Measure a wand for the test log")
    ap.add_argument("test", choices=["latency", "gestures", "battery"])
    ap.add_argument("wand", help="Bluetooth name, e.g. BDS-1")
    ap.add_argument("--n", type=int, default=None, help="pings (default 200) or tries per spell (default 10)")
    ap.add_argument("--who", default="player", help="(gestures) who is casting")
    a = ap.parse_args(argv)
    try:
        if a.test == "latency":
            asyncio.run(latency(a.wand, a.n or 200))
        elif a.test == "gestures":
            asyncio.run(gestures(a.wand, a.n or 10, a.who))
        else:
            asyncio.run(battery(a.wand))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
