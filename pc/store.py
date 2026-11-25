"""
store.py — things the arena remembers between runs (saved as small JSON files next to this file).

    settings.json      volumes, announcer, tutorial on/off, difficulty
    hall_of_fame.json  fastest draws + champions, across every session

Both files are optional: delete them to go back to the defaults / an empty hall of fame.
"""
from __future__ import annotations

import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DIFFICULTY_BPM = {"EASY": 75, "NORMAL": 90, "HARD": 110}      # v5.7: slower (was 100/120/140)      # Level 1 air-drum speed


class Settings:
    DEFAULTS = {"music": 8, "effects": 10, "announcer": 10, "cowboy_tutorial": True, "tutorial": True,
                "difficulty": "NORMAL"}

    def __init__(self, path=None, save=True):
        self.path = path or os.path.join(HERE, "settings.json")
        self.save_enabled = save
        self.values = dict(self.DEFAULTS)
        try:                                   # (automated tests use save=False: defaults, no files)
            with open(self.path) as f:
                loaded = json.load(f) if save else {}
            for k, v in loaded.items():
                if k in self.DEFAULTS and type(v) is type(self.DEFAULTS[k]):
                    self.values[k] = v
        except (OSError, ValueError):
            pass
        if self.values["difficulty"] not in DIFFICULTY_BPM:
            self.values["difficulty"] = "NORMAL"

    def __getitem__(self, k):
        return self.values[k]

    def __setitem__(self, k, v):
        self.values[k] = v
        self.save()

    @property
    def bpm(self):
        return DIFFICULTY_BPM[self.values["difficulty"]]

    def change(self, key, step):
        """LEFT / RIGHT on the settings page: volumes 0-10, on/off toggles, difficulty cycles."""
        v = self.values[key]
        if isinstance(v, bool):
            v = not v
        elif isinstance(v, int):
            v = max(0, min(10, v + step))
        else:
            order = list(DIFFICULTY_BPM)
            v = order[(order.index(v) + step) % len(order)]
        self[key] = v

    def save(self):
        if not self.save_enabled:
            return
        try:
            with open(self.path, "w") as f:
                json.dump(self.values, f, indent=2)
        except OSError:
            pass


class HallOfFame:
    KEEP = 10

    def __init__(self, path=None, save=True):
        self.path = path or os.path.join(HERE, "hall_of_fame.json")
        self.save_enabled = save
        self.data = {"draws": [], "champions": []}
        try:
            with open(self.path) as f:
                loaded = json.load(f) if save else {}
            self.data["draws"] = list(loaded.get("draws", []))[: self.KEEP]
            self.data["champions"] = list(loaded.get("champions", []))
        except (OSError, ValueError):
            pass

    @staticmethod
    def _today():
        return dt.date.today().isoformat()

    def add_draw(self, name, ms):
        """A valid Level 1 draw time (bullets already taken off). Keeps the 10 fastest."""
        self.data["draws"].append({"name": name, "ms": round(float(ms), 1), "date": self._today()})
        self.data["draws"].sort(key=lambda d: d["ms"])
        del self.data["draws"][self.KEEP:]
        self.save()

    def add_champion(self, name, rival):
        self.data["champions"].append({"name": name, "rival": rival, "date": self._today()})
        self.save()

    def fastest(self, n=8):
        return self.data["draws"][:n]

    def most_titles(self, n=8):
        """[(name, titles)] most championships first (names are matched without caring about CAPS)."""
        count, shown = {}, {}
        for c in self.data["champions"]:
            key = c["name"].strip().lower()
            count[key] = count.get(key, 0) + 1
            shown.setdefault(key, c["name"])
        return sorted(((shown[k], v) for k, v in count.items()), key=lambda kv: (-kv[1], kv[0]))[:n]

    def recent(self, n=5):
        return list(reversed(self.data["champions"][-n:]))

    def save(self):
        if not self.save_enabled:
            return
        try:
            with open(self.path, "w") as f:
                json.dump(self.data, f, indent=2)
        except OSError:
            pass
