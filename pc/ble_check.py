"""
ble_check.py — quick Bluetooth test for one wand (run this BEFORE the arena).

    python ble_check.py              # list nearby Bluetooth devices, BDS-* first
    python ble_check.py BDS-1        # connect to BDS-1, ask its version, ping it 10x

If BDS-1 does not show up: is the wand switched on, is the BLE shield stacked
properly, and is it NOT connected to a phone app at the same time?
"""
import asyncio
import statistics
import sys
import time

from bleak import BleakClient, BleakScanner

from links import NOTIFY_CHAR, WRITE_CHAR


async def scan():
    print("Scanning for 5 seconds...")
    found = await BleakScanner.discover(timeout=5.0, return_adv=True)
    rows = []
    for addr, (dev, adv) in found.items():
        name = adv.local_name or dev.name or "?"
        rows.append((not name.startswith("BDS"), name, addr, adv.rssi))
    for _, name, addr, rssi in sorted(rows):
        star = "<-- wand" if name.startswith("BDS") else ""
        print(f"  {name:20s} {addr:20s} signal {rssi:4d} dBm  {star}")


async def check(name):
    dev = await BleakScanner.find_device_by_name(name, timeout=8.0)
    if dev is None:
        print(f"Could not find {name}. Run without arguments to see what is nearby.")
        return
    replies = asyncio.Queue()

    def on_notify(_h, data):
        replies.put_nowait((time.perf_counter(), bytes(data).split(b"\x00")[0].decode(errors="ignore")))

    async with BleakClient(dev) as client:
        print(f"Connected to {name} ({dev.address})")
        await client.start_notify(NOTIFY_CHAR, on_notify)
        await client.write_gatt_char(WRITE_CHAR, b"V", response=False)
        try:
            _, v = await asyncio.wait_for(replies.get(), 2)
            print(f"Firmware says: {v}   (version, name, buzzer on/off, why it last restarted: P power, W watchdog, B brown-out)")
        except asyncio.TimeoutError:
            print("No reply to V - is the Beat-Draw firmware uploaded?")
            return
        rtts = []
        for _ in range(10):
            t0 = time.perf_counter()
            await client.write_gatt_char(WRITE_CHAR, b"P", response=False)
            try:
                t1, msg = await asyncio.wait_for(replies.get(), 1)
                if msg == "Q":
                    rtts.append((t1 - t0) * 1000)
            except asyncio.TimeoutError:
                print("  ping lost")
            await asyncio.sleep(0.1)
        if rtts:
            print(f"Ping round-trip: median {statistics.median(rtts):.1f} ms, "
                  f"min {min(rtts):.1f}, max {max(rtts):.1f}  (one-way is about half)")
        print("All good!" if len(rtts) >= 8 else "Connection is flaky - move closer / check battery.")


if __name__ == "__main__":
    asyncio.run(check(sys.argv[1]) if len(sys.argv) > 1 else scan())
