"""
menu.py — the arena's main menu (what you see before and between matches).

    PLAY FULL MATCH     all 3 levels
    PRACTICE A LEVEL    Level 1 / 2 / 3 on its own
    HOW TO PLAY         4 illustrated pages (LEFT / RIGHT to flip)
    PLAYERS & WANDS     names, connection, battery, Bluetooth delay, firmware, drop-outs
    HALL OF FAME        fastest draws + champions of all time (hall_of_fame.json)
    SETTINGS            volumes, announcer, spell tutorial, difficulty (settings.json)
    QUIT

Keyboard: UP / DOWN move, ENTER (or SPACE) select, LEFT / RIGHT change a setting or flip a page,
ESC / BACKSPACE back. Mouse: point = highlight, left-click = select, right-click = back, wheel = move;
click the < > arrows to change a setting or flip a page. The menu is keyboard / mouse only (v5.6: wand control removed).
"""
from __future__ import annotations

from game_logic import BATT_LOW_PCT, RESET_CAUSES, SPELL_NAMES, SPELL_TIPS

INK = (240, 232, 220)
GOLD = (245, 190, 60)
GREEN = (80, 200, 120)
RED = (230, 70, 60)
DIM = (170, 160, 150)
P_COLORS = [(235, 110, 70), (70, 190, 230)]
SPELL_COLORS = {"L": (250, 220, 60), "W": (70, 150, 250), "F": (250, 110, 40)}
MOVES = {"L": "ZIG-ZAG", "W": "CIRCLE", "F": "THRUST"}

MAIN = [("PLAY FULL MATCH", "play", "All 3 levels: Cowboy, Spellcaster, Combo Clash  (about 3 minutes)"),
        ("PRACTICE A LEVEL", "practice", "Play one level on its own - the best way to learn"),
        ("HOW TO PLAY", "howto", "The rules and the wand moves, with pictures"),
        ("PLAYERS & WANDS", "players", "Names, battery, Bluetooth and firmware of both wands"),
        ("HALL OF FAME", "fame", "Fastest draws and champions of all time"),
        ("SETTINGS", "settings", "Volume, announcer, spell tutorial, difficulty"),
        ("QUIT", "quit", "Close the arena")]
PRACTICE = [("LEVEL 1 - COWBOY", 1, "Air-drum to load bullets, then the quick-draw"),
            ("LEVEL 2 - SPELLCASTER", 2, "Spell tutorial, then a 60 s spell duel"),
            ("LEVEL 3 - COMBO CLASH", 3, "Remember 3 spells and cast them back"),
            ("BACK", None, "")]
SETTINGS = [("MUSIC VOLUME", "music"), ("EFFECTS VOLUME", "effects"), ("ANNOUNCER VOLUME", "announcer"),
            ("COWBOY TUTORIAL", "cowboy_tutorial"), ("SPELL TUTORIAL", "tutorial"), ("DIFFICULTY", "difficulty"),
            ("BACK", None)]
DIFF_HELP = {"EASY": "Level 1 beat at 75 BPM", "NORMAL": "Level 1 beat at 90 BPM", "HARD": "Level 1 beat at 110 BPM"}
HOWTO_PAGES = 4
# where things are on the 1280 x 720 screen (used for drawing AND for mouse clicks)
LIST_RECTS = {"main": (430, 108, 420, 384), "practice": (390, 150, 500, 280)}
SET_X, SET_Y, SET_W = 330, 120, 620
HOWTO_ARROWS = {-1: (86, 300, 44, 80), 1: (1150, 300, 44, 80)}
BACK_BUTTONS = {"howto": (1060, 548, 120, 36), "fame": (1020, 526, 120, 36)}


def inside(rect, pos):
    x, y, w, h = rect
    return x <= pos[0] < x + w and y <= pos[1] < y + h


class Menu:
    def __init__(self, ref):
        self.ref = ref
        self.page = "main"
        self.sel = {"main": 0, "practice": 0, "players": 0, "settings": 0, "fame": 0}
        self.howto = 0
        self.msg = (0.0, "", INK)
        self.hover = None                         # (kind, value) under the mouse

    # ------------------------------------------------------------------ input
    def items(self):
        if self.page == "main":
            return MAIN
        if self.page == "practice":
            return PRACTICE
        if self.page == "settings":
            return SETTINGS
        if self.page == "players":
            r = self.ref
            return [(f"P1 NAME:  {r.player_names[0] or '(type one)'}", 0),
                    (f"P2 NAME:  {r.player_names[1] or '(type one)'}", 1),
                    ("RE-MEASURE BLUETOOTH", "c"), ("BACK", None)]
        return [("BACK", None)]

    # ------------------------------------------------------------------ mouse
    def item_rect(self, k):
        """Clickable row k of the current page."""
        if self.page in LIST_RECTS:
            x, y, w, _ = LIST_RECTS[self.page]
            return (x + 20, y + 70 + k * 44 - 19, w - 40, 38)
        if self.page == "settings":
            return (SET_X + 20, SET_Y + 76 + k * 48 - 20, SET_W - 40, 40)
        if self.page == "players":
            return (380, 420 + k * 38 - 17, 520, 34)
        return BACK_BUTTONS.get(self.page, BACK_BUTTONS["fame"])

    def setting_arrow(self, k, step):
        iy, vx = SET_Y + 76 + k * 48, SET_X + SET_W - 190
        return (vx - 38, iy - 18, 32, 36) if step < 0 else (vx + 160, iy - 18, 32, 36)

    def hit_rects(self):
        """[(rect, kind, value)] - everything the mouse can click on this page (arrows before rows)."""
        hits = []
        if self.page == "howto":
            hits += [(HOWTO_ARROWS[st], "page", st) for st in (-1, 1)]
            hits.append((BACK_BUTTONS["howto"], "back", None))
            return hits
        if self.page == "fame":
            return [(BACK_BUTTONS["fame"], "back", None)]
        if self.page == "settings":
            for k, (_, key) in enumerate(SETTINGS):
                if key is not None:
                    hits += [(self.setting_arrow(k, st), "arrow", (k, st)) for st in (-1, 1)]
        hits += [(self.item_rect(k), "item", k) for k in range(len(self.items()))]
        return hits

    def hit(self, pos):
        return next(((kind, val) for rect, kind, val in self.hit_rects() if inside(rect, pos)), None)

    def on_mouse(self, kind, pos, now, amount=0):
        """kind: 'move', 'click' (left button), 'back' (right button), 'wheel' (amount = +1 up / -1 down)."""
        if kind == "wheel":
            if self.page == "howto":
                self.on_key("left" if amount > 0 else "right", now)
            else:
                self.on_key("up" if amount > 0 else "down", now)
            return
        if kind == "back":
            self.on_key("back", now)
            return
        h = self.hit(pos)
        self.hover = h
        if h is None:
            return
        what, val = h
        if what in ("item", "arrow"):
            k = val if what == "item" else val[0]
            if kind == "move" and self.sel.get(self.page) != k:
                self.sel[self.page] = k
                self.ref.sounds.play("click", 0.25)
            elif kind == "click":
                self.sel[self.page] = k
                if what == "arrow":
                    self.change_setting(val[1])
                else:
                    self.select(now)
        elif kind == "click" and what == "page":
            self.on_key("right" if val > 0 else "left", now)
        elif kind == "click" and what == "back":
            self.on_key("back", now)

    def draw_button(self, screen, rect, label):
        """A clickable pixel button (gold when the mouse is on it)."""
        art = self.ref.art
        x, y, w, h = rect
        on = inside(rect, self._mouse_pos())
        art.plate(screen, rect, alpha=230 if on else 170, border=GOLD if on else (250, 230, 190))
        art.text(screen, label, (x + w // 2, y + h // 2), GOLD if on else INK, 14, 2)

    def _mouse_pos(self):
        return getattr(self.ref, "mouse_pos", (-1, -1))

    def say(self, now, text, col=INK):
        self.msg = (now, text, col)

    def on_key(self, key, now) -> bool:
        """Returns True when the menu used the key."""
        if key in ("up", "down"):
            if self.page == "howto":
                return True
            n = len(self.items())
            self.sel[self.page] = (self.sel[self.page] + (1 if key == "down" else -1)) % n
            self.ref.sounds.play("click", 0.5)
            return True
        if key in ("left", "right"):
            step = 1 if key == "right" else -1
            if self.page == "howto":
                self.howto = (self.howto + step) % HOWTO_PAGES
                self.ref.sounds.play("click", 0.5)
            elif self.page == "settings":
                self.change_setting(step)
            return True
        if key in ("return", "enter", "keypad enter", "space"):
            self.select(now)
            return True
        if key in ("escape", "backspace", "back"):
            if self.page != "main":
                self.page = "main"
                self.ref.sounds.play("click", 0.5)
            elif key == "escape":
                self.ref.want_quit = True
            return True
        return False

    def change_setting(self, step):
        key = SETTINGS[self.sel["settings"]][1]
        if key is None:
            return
        self.ref.settings.change(key, step)
        self.ref.apply_settings()
        self.ref.sounds.play("click", 0.6)

    def select(self, now):
        r = self.ref
        r.sounds.play("chant", 0.4)
        if self.page == "main":
            what = MAIN[self.sel["main"]][1]
            if what == "play":
                self.start(0, now)
            elif what == "quit":
                r.want_quit = True
            else:
                self.page = what
                if what == "howto":
                    self.howto = 0
        elif self.page == "practice":
            lvl = PRACTICE[self.sel["practice"]][1]
            if lvl is None:
                self.page = "main"
            else:
                self.start(lvl, now)
        elif self.page == "settings":
            if SETTINGS[self.sel["settings"]][1] is None:
                self.page = "main"
            else:
                self.change_setting(1)
        elif self.page == "players":
            what = self.items()[self.sel["players"]][1]
            if what in (0, 1):
                r.on_key(str(what + 1), now)             # same as pressing 1 / 2
            elif what == "c":
                for i in range(2):
                    if r.connected[i]:
                        r.start_calibration(i)
                self.say(now, "Measuring Bluetooth delay...", GOLD)
            else:
                self.page = "main"
        else:                                            # howto / fame: ENTER = back
            self.page = "main"

    def start(self, level, now):
        r = self.ref
        if not r.ready():
            missing = [f"P{i + 1}" for i in range(2) if not r.connected[i]]
            text = (" and ".join(missing) + " wand not connected" if missing else "Measuring Bluetooth - one moment")
            self.say(now, text + " - see PLAYERS & WANDS", RED)
            r.sounds.play("wrong", 0.5)
            return
        r.only_level = level
        r.start_match(now)
        self.page = "main"

    # ------------------------------------------------------------------ drawing
    def draw(self, screen, now):
        art = self.ref.art
        if self.page == "main":
            self.draw_list(screen, MAIN, "MAIN MENU", now, (430, 108, 420, 384))
        elif self.page == "practice":
            self.draw_list(screen, PRACTICE, "PRACTICE A LEVEL", now, (390, 150, 500, 280))
        elif self.page == "settings":
            self.draw_settings(screen, now)
        elif self.page == "players":
            self.draw_players(screen, now)
        elif self.page == "fame":
            self.draw_fame(screen, now)
        elif self.page == "howto":
            self.draw_howto(screen, now)
        self.draw_status(screen)
        t, text, col = self.msg
        if text and now - t < 2.5:
            art.text(screen, text, (640, 600), col, 14, 2)

    def draw_status(self, screen):
        """One line under the title: is each wand ready?"""
        r, art = self.ref, self.ref.art
        for i in range(2):
            cx = 320 if i == 0 else 960
            name = f"P{i + 1}  {r.player_names[i] or r.names[i]}"
            if not r.connected[i]:
                state, col = "searching...", RED
            elif r.latency[i] is None:
                state, col = "measuring...", GOLD
            else:
                state, col = "READY", GREEN
            pct = r.battery[i]
            batt = f"   {pct}%" if pct is not None else ""
            art.text(screen, f"{name}  -  {state}{batt}", (cx, 80), P_COLORS[i], 14, 2)
            if pct is not None and pct <= BATT_LOW_PCT and self.page == "main":
                art.text(screen, "battery low - charge me!", (cx, 104), RED, 18, 1, shadow=False)

    def draw_list(self, screen, items, title, now, rect):
        import pygame
        art = self.ref.art
        x, y, w, h = rect
        art.plate(screen, rect, alpha=190)
        art.text(screen, title, (x + w // 2, y + 26), GOLD, 14, 2)
        sel = self.sel[self.page]
        for k, item in enumerate(items):
            iy = y + 70 + k * 44
            if k == sel:
                rx, ry, rw, rh = self.item_rect(k)
                bar = pygame.Surface((rw, rh), pygame.SRCALPHA)
                bar.fill((245, 190, 60, 60))
                screen.blit(bar, (rx, ry))
                bob = 4 if int(now * 3) % 2 else 0
                art.text(screen, ">", (x + 36 + bob, iy), GOLD, 16, 2)
                art.text(screen, "<", (x + w - 36 - bob, iy), GOLD, 16, 2)
            art.text(screen, item[0], (x + w // 2, iy), GOLD if k == sel else INK, 14, 2)
        desc = items[sel][2] if len(items[sel]) > 2 else ""
        if desc:
            art.text(screen, desc, (640, y + h + 22), (250, 240, 210), 14, 2)

    def draw_settings(self, screen, now):
        import pygame
        art, st = self.ref.art, self.ref.settings
        x, y, w = SET_X, SET_Y, SET_W
        art.plate(screen, (x, y, w, 420), alpha=190)
        art.text(screen, "SETTINGS", (640, y + 26), GOLD, 14, 2)
        sel = self.sel["settings"]
        for k, (label, key) in enumerate(SETTINGS):
            iy = y + 76 + k * 48
            on = k == sel
            if on:
                bar = pygame.Surface((w - 40, 40), pygame.SRCALPHA)
                bar.fill((245, 190, 60, 60))
                screen.blit(bar, (x + 20, iy - 20))
            col = GOLD if on else INK
            if key is None:
                art.text(screen, label, (640, iy), col, 14, 2)
                continue
            art.text(screen, label, (x + 40 + art.text_width(label, 14, 2) // 2, iy), col, 14, 2)
            v = st[key]
            vx = x + w - 190
            if isinstance(v, bool):
                art.text(screen, "ON" if v else "OFF", (vx + 60, iy), GREEN if v else RED, 14, 2)
            elif isinstance(v, int):
                for b in range(10):                       # 10-block volume bar
                    pygame.draw.rect(screen, GOLD if b < v else (70, 55, 50), (vx + b * 13, iy - 10, 10, 20))
                art.text(screen, str(v), (vx + 150, iy), col, 14, 2)
            else:
                art.text(screen, v, (vx + 60, iy), col, 14, 2)
            for step in (-1, 1):                          # < > : click to change (gold on the selected row)
                ax, ay, aw, ah = self.setting_arrow(k, step)
                art.text(screen, "<" if step < 0 else ">", (ax + aw // 2, ay + ah // 2),
                         GOLD if on else (120, 105, 95), 14, 2)
        key = SETTINGS[sel][1]
        help_text = {"music": "Background music (Wild West, mystic, arcade battle)",
                     "effects": "Drums, gunshots, spells, crowd cheers",
                     "announcer": "The fighting-game voice (0 = off)",
                     "cowboy_tutorial": "Learn the arrows, holster and draw before Level 1",
                     "tutorial": "Learn each spell before the Level 2 duel",
                     "difficulty": DIFF_HELP[st["difficulty"]]}.get(key, "")
        if help_text:
            art.text(screen, help_text, (640, y + 445), (250, 240, 210), 14, 2)

    def draw_players(self, screen, now):
        import pygame
        r, art = self.ref, self.ref.art
        art.plate(screen, (120, 120, 1040, 460), alpha=200)
        art.text(screen, "PLAYERS & WANDS", (640, 146), GOLD, 14, 2)
        for i in range(2):
            cx = 380 if i == 0 else 900
            art.text(screen, f"P{i + 1}  {r.player_names[i] or '(no name)'}", (cx, 186), P_COLORS[i], 16, 2)
            fw = r.fw[i]
            pct = r.battery[i]
            lat = r.latency[i]
            rows = [("Wand", r.names[i]),
                    ("Connection", "connected" if r.connected[i] else "searching..."),
                    ("Battery", f"{pct}%" if pct is not None else "-"),
                    ("Bluetooth delay", f"{lat:.0f} ms" if lat is not None else
                     ("measuring..." if r.connected[i] else "-")),
                    ("Firmware", fw["version"] if fw else "-"),
                    ("Last restart", RESET_CAUSES.get(fw["reset"], "-").split(" (")[0].lower() if fw and fw["reset"]
                     else "-"),
                    ("Drop-outs today", str(r.drops[i]))]
            for n, (label, val) in enumerate(rows):
                y = 220 + n * 24
                art.text(screen, label, (cx - 210 + art.text_width(label, 18, 1) // 2, y), DIM, 18, 1, shadow=False)
                col = INK
                if label == "Battery" and pct is not None:
                    col = RED if pct <= BATT_LOW_PCT else GREEN
                if label == "Connection":
                    col = GREEN if r.connected[i] else RED
                if label == "Last restart" and fw and fw["reset"] in ("W", "B"):
                    col = RED
                art.text(screen, val, (cx + 120, y), col, 18, 1, shadow=False)
        sel = self.sel["players"]
        for k, item in enumerate(self.items()):
            iy = 420 + k * 38
            if k == sel:
                bar = pygame.Surface((520, 34), pygame.SRCALPHA)
                bar.fill((245, 190, 60, 60))
                screen.blit(bar, (380, iy - 17))
            art.text(screen, item[0], (640, iy), GOLD if k == sel else INK, 14, 2)

    def draw_fame(self, screen, now):
        r, art = self.ref, self.ref.art
        hof = r.hof
        art.plate(screen, (120, 120, 1040, 460), alpha=200)
        art.text(screen, "HALL OF FAME", (640, 148), GOLD, 16, 3)
        art.text(screen, "FASTEST DRAWS", (380, 200), GOLD, 14, 2)
        draws = hof.fastest(8)
        if not draws:
            art.text(screen, "no draws yet - be the first!", (380, 250), DIM, 14, 2)
        for n, d in enumerate(draws):
            y = 236 + n * 30
            col = GOLD if n == 0 else INK
            art.text(screen, f"{n + 1}.", (190, y), col, 14, 2)
            art.text(screen, d["name"], (215 + art.text_width(d["name"], 14, 2) // 2, y), col, 14, 2)
            art.text(screen, f"{d['ms']:.0f} ms", (520, y), col, 14, 2)
        art.text(screen, "MOST TITLES", (900, 200), GOLD, 14, 2)
        titles = hof.most_titles(5)
        if not titles:
            art.text(screen, "no champions yet", (900, 250), DIM, 14, 2)
        for n, (name, cnt) in enumerate(titles):
            y = 236 + n * 30
            art.text(screen, f"{n + 1}. {name}   x{cnt}", (900, y), GOLD if n == 0 else INK, 14, 2)
        recent = hof.recent(3)
        if recent:
            art.text(screen, "LATEST CHAMPIONS", (900, 412), GOLD, 18, 1)
            for n, c in enumerate(recent):
                art.text(screen, f"{c['name']} beat {c['rival']}  ({c['date']})", (900, 438 + n * 22), INK,
                         18, 1, shadow=False)
        self.draw_button(screen, BACK_BUTTONS[self.page], "BACK")

    # ---- how to play ------------------------------------------------------------------------
    def draw_howto(self, screen, now):
        art = self.ref.art
        art.plate(screen, (80, 100, 1120, 500), alpha=210)
        page = self.howto
        titles = ["THE MATCH - 3 LEVELS", "LEVEL 1 - COWBOY", "LEVEL 2 - SPELLCASTER", "LEVEL 3 - COMBO CLASH"]
        art.text(screen, titles[page], (640, 132), GOLD, 16, 3)
        getattr(self, f"_howto{page}")(screen, now)
        for k in range(HOWTO_PAGES):                     # page dots
            col = GOLD if k == page else (90, 80, 80)
            art.text(screen, "o" if k != page else "O", (610 + k * 20, 560), col, 16, 2)
        art.text(screen, "LEFT / RIGHT, the arrows or the mouse wheel = flip page", (640, 586), DIM, 18, 1, shadow=False)
        for step, rect in HOWTO_ARROWS.items():          # big clickable page arrows at the sides
            x, y, w, h = rect
            on = inside(rect, self._mouse_pos())
            art.text(screen, "<" if step < 0 else ">", (x + w // 2, y + h // 2), GOLD if on else INK, 16, 5)
        self.draw_button(screen, BACK_BUTTONS[self.page], "BACK")

    def _lines(self, screen, lines, x, y, gap=30, size=14, scale=2):
        art = self.ref.art
        for n, (text, col) in enumerate(lines):
            art.text(screen, text, (x + art.text_width(text, size, scale) // 2, y + n * gap), col, size, scale)

    def _howto0(self, screen, now):
        art = self.ref.art
        cols = [("1", "COWBOY", ["Flick the arrows", "on the beat", "= load bullets", "then QUICK-DRAW!"]),
                ("2", "SPELLCASTER", ["Cast spells:", "zig-zag / circle", "/ thrust", "Take their HP!"]),
                ("3", "COMBO CLASH", ["Remember the combo,", "cast it back.", "Final round: 5!", "Push the beam!"])]
        for k, (num, name, lines) in enumerate(cols):
            cx = 300 + k * 340
            art.slot(screen, (cx - 140, 180, 280, 250), GOLD)
            art.text(screen, num, (cx, 220), GOLD, 16, 4)
            art.text(screen, name, (cx, 270), INK, 14, 2)
            for n, line in enumerate(lines):
                art.text(screen, line, (cx, 310 + n * 26), DIM, 18, 1, shadow=False)
            if k < 2:
                art.text(screen, ">", (cx + 170, 300), GOLD, 16, 3)
        art.text(screen, "Win Level 1 = +1 HP in Level 2.   More HP after Level 2 = the beam starts nearer your rival.",
                 (640, 470), INK, 18, 1, shadow=False)
        art.text(screen, "Push the beam all the way = CHAMPION!", (640, 505), GOLD, 14, 2)

    def _howto1(self, screen, now):
        import pygame
        art = self.ref.art
        rows = [(175, "1  AIR DRUM - flick the wand TIP the way", GOLD), (203, "   the falling arrow points, as it hits the line:", INK),
                (372, "   every right arrow on time = 1 bullet (max 6) - PERFECT / GOOD / MISS", DIM),
                (410, "2  HOLSTER - wand down at your side,", GOLD), (438, "   then FREEZE. Moving = FOUL!", INK),
                (476, "3  DRAW! - flick the wand up fastest", GOLD), (504, "   each bullet takes 25 ms off your time", DIM)]
        for y, text, col in rows:
            art.text(screen, text, (130 + art.text_width(text, 14, 2) // 2, y), col, 14, 2)
        for k, d in enumerate("UDLR"):                       # the 4 arrows, the live one bounces
            x = 190 + k * 130
            bob = -6 if int(now * 2) % 4 == k else 0
            pygame.draw.rect(screen, (40, 25, 20), (x - 34, 262 - 34, 68, 68))
            art.arrow(screen, d, (x, 262 + bob), 7)
            art.text(screen, {"U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT"}[d], (x, 312), INK, 18, 1, shadow=False)
        art.text(screen, "Round 1: up + down only.   Round 2: + left / right.   Round 3: all 4!", (385, 340), GOLD,
                 18, 1, shadow=False)
        # little live demo of the replay bars
        t = (now % 3.0) / 1.4
        for i, ms in enumerate((210, 260)):
            y = 260 + i * 60
            w = int(min(t * 320, ms) / 320 * 260)
            pygame.draw.rect(screen, (40, 25, 20), (840, y, 260, 34))
            pygame.draw.rect(screen, P_COLORS[i], (840, y, w, 34))
            if w >= ms / 320 * 260 - 1:
                art.text(screen, f"P{i + 1} {ms} ms", (970, y + 17), INK, 14, 2)
        art.text(screen, "lowest time wins the draw", (970, 400), DIM, 18, 1, shadow=False)

    def _howto2(self, screen, now):
        art = self.ref.art
        for k, sp in enumerate("LWF"):
            cx = 300 + k * 340
            art.slot(screen, (cx - 150, 170, 300, 230), SPELL_COLORS[sp])
            art.icon(screen, sp, (cx - 95, 215), 5)
            art.text(screen, SPELL_NAMES[sp], (cx + 40, 205), SPELL_COLORS[sp], 14, 2)
            art.text(screen, MOVES[sp], (cx + 40, 232), INK, 14, 2)
            art.move_demo(screen, sp, (cx, 322), now + k * 0.4, size=(260, 170))
            art.text(screen, SPELL_TIPS[sp], (cx, 418), DIM, 18, 1, shadow=False)
        art.text(screen, "LIGHTNING beats WATER  >  WATER beats FIRE  >  FIRE beats LIGHTNING", (640, 462), GOLD, 14, 2)
        art.text(screen, "Point the wand at the SKY and hold still = +1 mana (max 3). Each spell costs 1 mana.",
                 (640, 497), INK, 18, 1, shadow=False)
        art.text(screen, "Spells meet in mid-air: the stronger one destroys the other and keeps flying.",
                 (640, 522), INK, 18, 1, shadow=False)

    def _howto3(self, screen, now):
        art = self.ref.art
        combo = "WFW"                                    # spells can repeat from round 2
        k_lit = int(now / 0.8) % 4
        for k, sp in enumerate(combo):
            cx = 520 + k * 120
            lit = k == k_lit
            art.slot(screen, (cx - 50, 180, 100, 100), SPELL_COLORS[sp] if lit else (250, 230, 190))
            if lit:
                art.icon(screen, sp, (cx, 230), 9)
            else:
                art.text(screen, "?", (cx, 230), (200, 190, 220), 16, 4)
        self._lines(screen, [("1  WATCH - the spells flash one by one. Remember the order - they can repeat!", INK),
                             ("2  WAIT - 2 seconds, the combo is hidden", INK),
                             ("3  GO! - cast the same spells, in the same order, with your wand", INK),
                             ("Most right (in the right place) wins the round. Equal = fastest wins.", DIM),
                             ("FINAL ROUND: 5 spells in a row - the big decider!", RED),
                             ("The winner pushes the beam. Push it into your rival = CHAMPION!", GOLD)],
                    170, 330, 34)
