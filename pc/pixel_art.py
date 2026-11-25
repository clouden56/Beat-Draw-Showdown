"""
pixel_art.py — retro pixel-art look for the arena (all drawn in code, no image files).

The scene is painted on a tiny 160 x 90 canvas and scaled up 8x with hard edges, so every
"pixel" is an 8 x 8 block on the 1280 x 720 screen. Text and the HUD are drawn on top at full size.

    Level 1  desert at sunset, two cowboys, tumbleweed
    Level 2  night sky, moon, castle, two wizards, pixel spells
    Level 3  same night, wand beams meeting in the middle

Sprites are little text grids: each letter is a colour from a palette, "." is see-through.
Change a letter to recolour, or redraw a row to change a pose.
"""
from __future__ import annotations

import math
import random

LW, LH = 160, 90          # low-res canvas
S = 8                     # scale: 160 x 8 = 1280
GROUND_Y = 82             # feet line on the canvas

P_MAIN = [(235, 110, 70), (70, 170, 230)]       # P1 orange, P2 blue (same as the arena colours)
P_DARK = [(170, 70, 45), (40, 100, 160)]
SPELL_RGB = {"L": (250, 220, 60), "W": (70, 150, 250), "F": (250, 110, 40)}

# ----------------------------------------------------------------------------------------------
# sprite grids (facing RIGHT; the right-hand player is flipped)
# ----------------------------------------------------------------------------------------------
COWBOY = {
    "idle": [
        "......HHHH......",
        ".....HHHHHH.....",
        ".....HhhhhH.....",
        "..HHHHHHHHHHHH..",
        "......SSSS......",
        "......SSES......",
        "......SSSS......",
        "......BBBS......",
        ".......BB.......",
        ".....CCCCCC.....",
        "....CCVCCVCC....",
        "....CCVCCVCC....",
        "....CCVCCVCC....",
        "....CCVCCVCC....",
        "....SbbbbbbS....",
        ".....PPPPPPGg...",
        ".....PPPPPPG....",
        ".....PPP.PPP....",
        ".....PPP.PPP....",
        ".....PPP.PPP....",
        ".....PPP.PPP....",
        ".....KKK.KKK....",
        ".....KKKK.KKKK..",
    ],
    "aim": [
        "......HHHH......",
        ".....HHHHHH.....",
        ".....HhhhhH.....",
        "..HHHHHHHHHHHH..",
        "......SSSS......",
        "......SSES......",
        "......SSSS......",
        "......BBBS......",
        ".......BB.......",
        ".....CCCCCCCCSgg",
        "....CCVCCVCC.GGG",
        "....CCVCCVC...G.",
        "....CCVCCVC.....",
        "....CCVCCVC.....",
        "....SbbbbbbO....",
        ".....PPPPPPO....",
        ".....PPPPPP.....",
        ".....PPP.PPP....",
        ".....PPP.PPP....",
        ".....PPP.PPP....",
        ".....PPP.PPP....",
        ".....KKK.KKK....",
        ".....KKKK.KKKK..",
    ],
}

WIZARD = {
    "idle": [
        "........H.......",
        ".......HH.......",
        "......HHH.......",
        "......HHHH......",
        ".....HHYHH......",
        ".....HHHHHH.....",
        "...hhhhhhhhhh...",
        "......SSSS......",
        "......SSES......",
        "......WWWS......",
        ".....WWWWW......",
        "....RRWWWRR.....",
        "....RRRWRRRR....",
        "....RRRRRRRSw...",
        "....RRyyyyRR.w..",
        "....RRRRRRR...w.",
        "...RRRRRRRRR..*.",
        "...RRRRRRRRR....",
        "...rRRRRRRRr....",
        "..rRRRRRRRRRr...",
        "..rRRRRRRRRRr...",
        "..rRRRRRRRRRr...",
        "..rrrrrrrrrrr...",
        "....KK...KK.....",
    ],
    "cast": [
        "........H.......",
        ".......HH.......",
        "......HHH.......",
        "......HHHH......",
        ".....HHYHH......",
        ".....HHHHHH.....",
        "...hhhhhhhhhh...",
        "......SSSS......",
        "......SSES......",
        "......WWWS......",
        ".....WWWWW....*.",
        "....RRWWWRRRSw..",
        "....RRRWRRRR....",
        "....RRRRRRRR....",
        "....RRyyyyRR....",
        "....RRRRRRR.....",
        "...RRRRRRRRR....",
        "...RRRRRRRRR....",
        "...rRRRRRRRr....",
        "..rRRRRRRRRRr...",
        "..rRRRRRRRRRr...",
        "..rRRRRRRRRRr...",
        "..rrrrrrrrrrr...",
        "....KK...KK.....",
    ],
    "charge": [
        "........H....*..",
        ".......HH....w..",
        "......HHH....w..",
        "......HHHH...w..",
        ".....HHYHH...S..",
        ".....HHHHHH..R..",
        "...hhhhhhhhhhR..",
        "......SSSS..R...",
        "......SSES.R....",
        "......WWWSR.....",
        ".....WWWWR......",
        "....RRWWWR......",
        "....RRRWRRRR....",
        "....RRRRRRRR....",
        "....RRyyyyRR....",
        "....RRRRRRR.....",
        "...RRRRRRRRR....",
        "...RRRRRRRRR....",
        "...rRRRRRRRr....",
        "..rRRRRRRRRRr...",
        "..rRRRRRRRRRr...",
        "..rRRRRRRRRRr...",
        "..rrrrrrrrrrr...",
        "....KK...KK.....",
    ],
}

CACTUS = [
    "..G..",
    ".GGG.",
    ".GGG.G",
    "GGGGGG",
    "GGGGG.",
    ".GGG..",
    ".GGG..",
    ".GGG..",
    ".GGG..",
]
TUMBLEWEED = [
    "..bbbb..",
    ".b.bb.b.",
    "bb.b..bb",
    "b.bbbb.b",
    "bb..b.bb",
    ".b.bb.b.",
    "..bbbb..",
]
BULLET = [".y", "yY", "YY", "YY", "BB", "BB"]
HEART = [".RR.RR.", "RRRRRRR", "RRRRRRR", ".RRRRR.", "..RRR..", "...R..."]
CRYSTAL = ["..C..", ".CCC.", "CCcCC", "CCcCC", ".CCC.", "..C.."]
FIREBALL = ["..oyo...", ".oYYYo..", "oYWWYYoo", "oYWWYYoo", ".oYYYo..", "..oyo..."]
WATERBALL = ["..bbb...", ".bBBBb..", "bBWWBBb.", "bBWBBBbb", ".bBBBb..", "..bbb..."]
BOLT = ["...YY...", "..YY....", ".YYYYYY.", "....YY..", "...YY...", "..Y....."]


class Art:
    def __init__(self, pygame):
        self.pg = pygame
        self.fonts = {}
        self.text_cache = {}
        self.bg = {"desert": self._desert(), "night": self._night()}
        skin, eye = (232, 180, 140), (30, 20, 20)
        self.cowboys = []
        for i in range(2):
            pal = {"H": (60, 45, 35) if i else (190, 110, 50), "h": (30, 20, 15) if i else (120, 60, 25),
                   "S": skin, "E": eye, "B": (40, 30, 25) if i else (110, 60, 30), "C": P_MAIN[i],
                   "V": (70, 45, 30), "P": (60, 55, 80) if i else (70, 60, 50), "b": (50, 30, 20),
                   "K": (55, 35, 20), "G": (80, 80, 90), "g": (170, 170, 180), "O": (35, 25, 25)}
            self.cowboys.append({k: self._sprite(v, pal) for k, v in COWBOY.items()})
        self.wizards = []
        for i in range(2):
            pal = {"H": P_DARK[i], "h": P_DARK[i], "Y": (255, 230, 90), "S": skin, "E": eye,
                   "W": (235, 235, 240) if i else (150, 90, 50), "R": P_MAIN[i], "r": P_DARK[i],
                   "y": (240, 200, 70), "K": (40, 30, 40), "w": (120, 80, 50), "*": (255, 255, 200)}
            self.wizards.append({k: self._sprite(v, pal) for k, v in WIZARD.items()})
        self.cactus = self._sprite(CACTUS, {"G": (80, 130, 70)})
        self.tumble = self._sprite(TUMBLEWEED, {"b": (140, 100, 60)})
        self.bullet_full = self._sprite(BULLET, {"y": (250, 230, 150), "Y": (220, 170, 60), "B": (160, 110, 40)})
        self.bullet_empty = self._sprite(BULLET, {"y": (80, 60, 50), "Y": (80, 60, 50), "B": (80, 60, 50)})
        self.heart = self._sprite(HEART, {"R": (230, 60, 70)})
        self.heart_empty = self._sprite(HEART, {"R": (70, 40, 50)})
        self.crystal = self._sprite(CRYSTAL, {"C": (110, 170, 255), "c": (220, 240, 255)})
        self.crystal_empty = self._sprite(CRYSTAL, {"C": (50, 60, 90), "c": (50, 60, 90)})
        self.spells = {
            "F": self._sprite(FIREBALL, {"o": (200, 60, 30), "y": (240, 140, 40), "Y": (255, 190, 60), "W": (255, 250, 210)}),
            "W": self._sprite(WATERBALL, {"b": (40, 90, 200), "B": (90, 160, 255), "W": (230, 245, 255)}),
            "L": self._sprite(BOLT, {"Y": (255, 235, 90)}),
        }

    # ------------------------------------------------------------------ building blocks
    def _sprite(self, rows, pal):
        pg = self.pg
        w = max(len(r) for r in rows)
        surf = pg.Surface((w, len(rows)), pg.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in pal:
                    surf.set_at((x, y), pal[ch])
        return surf

    def canvas(self, which):
        return self.bg[which].copy()

    def present(self, screen, canvas):
        sw, sh = screen.get_size()
        screen.blit(self.pg.transform.scale(canvas, (sw, sh)), (0, 0))

    def put(self, canvas, sprite, x, y_feet, flip=False):
        """Blit a sprite with its feet on y_feet (canvas pixels)."""
        if flip:
            sprite = self.pg.transform.flip(sprite, True, False)
        canvas.blit(sprite, (int(x), int(y_feet) - sprite.get_height()))

    def lying(self, sprite, flip=False):
        s = self.pg.transform.rotate(sprite, 90 if flip else -90)
        return s

    def rect(self, canvas, color, x, y, w, h):
        self.pg.draw.rect(canvas, color, (int(x), int(y), int(w), int(h)))

    # ------------------------------------------------------------------ backgrounds
    def _desert(self):
        pg = self.pg
        c = pg.Surface((LW, LH))
        bands = [(250, 232, 196), (248, 220, 180), (246, 206, 164), (242, 190, 148), (236, 172, 130)]
        for i, col in enumerate(bands):
            c.fill(col, (0, i * 13, LW, 13))
        c.fill(bands[-1], (0, 65, LW, 5))
        pg.draw.circle(c, (255, 236, 190), (80, 58), 13)           # setting sun between the two cowboys
        pg.draw.circle(c, (255, 248, 220), (80, 58), 10)
        mesa = (214, 150, 115)
        for x0, w, h in ((0, 30, 10), (22, 18, 16), (60, 26, 7), (96, 20, 12), (128, 32, 9)):
            c.fill(mesa, (x0, 66 - h, w, h))
            c.fill((200, 135, 102), (x0 + 2, 66 - h, w - 4, 2))
        c.fill((222, 146, 100), (0, 66, LW, LH - 66))               # ground
        rng = random.Random(4)
        for y in range(68, LH, 3):
            for _ in range(10):
                c.fill((204, 128, 86), (rng.randrange(LW), y, rng.randrange(2, 6), 1))
        c.fill((200, 120, 80), (0, GROUND_Y, LW, 1))
        for x, y in ((6, 70), (148, 72), (64, 68)):
            c.blit(self._sprite(CACTUS, {"G": (95, 140, 80)}), (x, y - 9 + 9 - len(CACTUS)))
        return c

    def _night(self):
        pg = self.pg
        c = pg.Surface((LW, LH))
        bands = [(18, 16, 38), (24, 20, 50), (32, 24, 64), (42, 30, 78), (54, 38, 92)]
        for i, col in enumerate(bands):
            c.fill(col, (0, i * 13, LW, 13))
        c.fill(bands[-1], (0, 65, LW, 5))
        rng = random.Random(9)
        for _ in range(70):
            x, y = rng.randrange(LW), rng.randrange(58)
            c.set_at((x, y), rng.choice([(255, 255, 255), (200, 210, 255), (255, 240, 180)]))
        pg.draw.circle(c, (240, 240, 220), (130, 18), 9)            # moon
        pg.draw.circle(c, (215, 215, 195), (127, 16), 2)
        pg.draw.circle(c, (215, 215, 195), (133, 21), 1)
        dark = (22, 16, 36)
        for x0, w, h in ((0, 14, 20), (12, 10, 28), (21, 16, 14), (58, 8, 24), (64, 22, 12), (84, 8, 26),
                         (118, 18, 16), (134, 10, 30), (143, 17, 18)):
            c.fill(dark, (x0, 66 - h, w, h))
            for k in range(0, w, 3):                                  # battlements
                c.fill(dark, (x0 + k, 66 - h - 2, 2, 2))
        for x, y in ((15, 44), (60, 48), (87, 46), (137, 42), (122, 54)):
            c.fill((250, 210, 110), (x, y, 1, 2))                     # lit windows
        c.fill((52, 46, 70), (0, 66, LW, LH - 66))                    # stone floor
        for y in range(68, LH, 4):
            off = 0 if (y // 4) % 2 else 4
            for x in range(off, LW, 8):
                c.fill((44, 38, 60), (x, y, 1, 4))
            c.fill((44, 38, 60), (0, y, LW, 1))
        return c

    # ------------------------------------------------------------------ text + panels (full resolution)
    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = self.pg.font.Font(None, size)
        return self.fonts[size]

    def text(self, screen, text, center, color, size=16, scale=3, shadow=True):
        """Chunky pixel text: rendered small without smoothing, then scaled up."""
        key = (text, size, scale, tuple(color), shadow)
        surf = self.text_cache.get(key)
        if surf is None:
            pg = self.pg
            base = self.font(size).render(text, False, color)
            w, h = base.get_size()
            surf = pg.Surface((w + 2, h + 3), pg.SRCALPHA)
            surf.fill((0, 0, 0, 0))
            if shadow:                                   # dark pixel outline + drop shadow: readable on any sky
                dark = self.font(size).render(text, False, (25, 14, 12))
                for ox, oy in ((0, 1), (2, 1), (1, 0), (1, 2), (2, 2), (1, 3), (2, 3)):
                    surf.blit(dark, (ox, oy))
            surf.blit(base, (1, 1))
            surf = pg.transform.scale(surf, ((w + 2) * scale, (h + 3) * scale))
            if len(self.text_cache) > 400:
                self.text_cache.clear()
            self.text_cache[key] = surf
        r = surf.get_rect(center=(int(center[0]), int(center[1])))
        screen.blit(surf, r)
        return r

    ARROW = ["...#...",
             "..###..",
             ".#####.",
             "#######",
             "..###..",
             "..###..",
             "..###.."]
    ARROW_RGB = {"U": (90, 210, 110), "D": (80, 150, 250), "L": (250, 200, 60), "R": (240, 90, 80)}

    def arrow(self, screen, d, center, px, color=None, outline=True):
        """Chunky pixel arrow pointing U / D / L / R. px = size of one "pixel" (7 x 7 grid)."""
        pg = self.pg
        col = color or self.ARROW_RGB[d]
        cx, cy = center
        cells = []
        for r, row in enumerate(self.ARROW):
            for c, ch in enumerate(row):
                if ch == "#":
                    x, y = c - 3, r - 3                       # pointing UP, centred on (0, 0)
                    if d == "D":
                        y = -y
                    elif d == "L":
                        x, y = y, x
                    elif d == "R":
                        x, y = -y, x
                    cells.append((x, y))
        if outline:
            for x, y in cells:
                pg.draw.rect(screen, (30, 18, 14), (cx + x * px - px // 2 - 2, cy + y * px - px // 2 - 2, px + 4, px + 4))
        for x, y in cells:
            pg.draw.rect(screen, col, (cx + x * px - px // 2, cy + y * px - px // 2, px, px))

    def text_width(self, text, size=16, scale=3):
        """Width in screen pixels of text() with the same size/scale (to left-align labels)."""
        return (self.font(size).size(text)[0] + 2) * scale

    def plate(self, screen, rect, alpha=170, border=(250, 230, 190)):
        """Retro dialog box: dark see-through panel with a 2-block pixel border."""
        pg = self.pg
        r = pg.Rect(rect)
        panel = pg.Surface((r.w, r.h), pg.SRCALPHA)
        panel.fill((20, 14, 20, alpha))
        screen.blit(panel, (r.x, r.y))
        pg.draw.rect(screen, border, r, 3)
        pg.draw.rect(screen, (40, 28, 30), r.inflate(6, 6), 3)

    def battery(self, screen, x, cy, pct, low=False):
        """Pixel battery icon + percentage, left edge at x, centred on cy."""
        pg = self.pg
        w, h = 36, 18
        y = int(cy - h / 2)
        col = (230, 60, 50) if low else ((240, 200, 60) if pct <= 50 else (90, 200, 110))
        pg.draw.rect(screen, (25, 15, 15), (x - 3, y - 3, w + 12, h + 6))          # dark outline
        pg.draw.rect(screen, (240, 230, 210), (x, y, w, h), 3)
        pg.draw.rect(screen, (240, 230, 210), (x + w, y + 5, 4, h - 10))          # nub
        bars = 0 if pct <= 0 else 1 + min(3, pct // 25)                            # 1-4 blocks
        for k in range(bars):
            pg.draw.rect(screen, col, (x + 5 + k * 7, y + 5, 5, h - 10))
        self.text(screen, f"{pct}%", (x + w + 34, cy), col, 14, 2)

    def slot(self, screen, rect, border):
        """A square pixel frame (combo slots)."""
        pg = self.pg
        r = pg.Rect(rect)
        panel = pg.Surface((r.w, r.h), pg.SRCALPHA)
        panel.fill((20, 14, 30, 190))
        screen.blit(panel, (r.x, r.y))
        pg.draw.rect(screen, border, r, 4)

    def icon(self, screen, kind, center, scale):
        """A spell sprite drawn big at full resolution (combo display)."""
        spr = self.spells[kind]
        big = self.pg.transform.scale(spr, (spr.get_width() * scale, spr.get_height() * scale))
        screen.blit(big, big.get_rect(center=(int(center[0]), int(center[1]))))

    # ------------------------------------------------------------------ "how to move" demo (full resolution)
    @staticmethod
    def move_path(kind, t, facing=1):
        """Where the wand tip is (-1..1, -1..1) at time t for each move, and whether it is "active".
        kind: L / W / F = spells (zig-zag, circle, thrust); Level 1 arrows = "aU", "aD", "aL", "aR"."""
        if kind[:1] == "a":                               # Level 1 arrow: a quick flick of the tip, then back
            u = t % 1.2
            if u < 0.1:
                f = 1 - (1 - u / 0.1) ** 2
            elif u < 0.3:
                f = 1.0
            elif u < 0.65:
                f = 1 - (u - 0.3) / 0.35
            else:
                f = 0.0
            dx, dy = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}[kind[1]]
            return dx * f, dy * f, u < 0.3
        if kind == "L":                                   # zig-zag: a lightning bolt, top to bottom, fast
            per = 1.6
            u = (t % per) / 1.0
            if u >= 1.0:
                return 1.0 * facing, 1.0, False           # short rest at the end
            pts = [(-0.7, -1), (0.7, -0.33), (-0.7, 0.33), (0.7, 1)]   # a tall bolt shape
            k = min(2, int(u * 3))
            f = u * 3 - k
            (x0, y0), (x1, y1) = pts[k], pts[k + 1]
            return (x0 + (x1 - x0) * f) * facing, y0 + (y1 - y0) * f, True
        if kind == "W":                                   # circle: one smooth round loop
            a = (t % 1.5) / 1.5 * 2 * math.pi
            return math.cos(a) * 0.9 * facing, math.sin(a) * 0.9, True
        per = 1.4                                         # thrust: punch forward fast, hold, pull back slowly
        u = t % per
        if u < 0.18:
            x = -1 + 2 * (1 - (1 - u / 0.18) ** 3)
        elif u < 0.45:
            x = 1
        elif u < 1.0:
            x = 1 - 2 * (u - 0.45) / 0.55
        else:
            x = -1
        return x * facing, 0.1, 0.1 <= u < 0.45

    def move_demo(self, screen, kind, center, t, size=(300, 150), facing=1):
        """Animated pixel wand doing the move for spell `kind` (zig-zag / circle / thrust), with a trail."""
        pg = self.pg
        cx, cy = center
        hw, hh = size[0] / 2 - 34, size[1] / 2 - 10
        if kind != "F":                                   # leave room under the path for the hand
            hh -= 18
            cy -= 14
            hw = min(hw, hh * {"L": 1.3, "W": 1.15}.get(kind, 1.0))   # a tall bolt / a round circle / a square
        else:                                             # thrust: shorter push, moved forward so wand + flames fit
            hw = size[0] / 2 - 90
            cx += 36 * facing
        col = SPELL_RGB[kind] if kind in SPELL_RGB else self.ARROW_RGB[kind[1]]
        snap = lambda v: int(v) // 6 * 6                  # noqa: E731  chunky 6-px "pixels"
        guide = tuple(int(v * 0.45) for v in col)         # the whole move as a dim dotted path
        per = {"L": 1.0, "W": 1.5, "F": 0.18}.get(kind, 0.1)
        for k in range(36):
            x, y, _ = self.move_path(kind, per * k / 36, facing)
            pg.draw.rect(screen, guide, (snap(cx + x * hw) - 3, snap(cy + y * hh) - 3, 6, 6))
        if kind[:1] == "a":                               # arrow head at the end of the flick
            x, y, _ = self.move_path(kind, 0.1, facing)
            self.arrow(screen, kind[1], (snap(cx + x * hw * 1.25), snap(cy + y * hh * 1.25)), 4, guide, outline=False)
        if kind == "F":                                   # arrow head: push this way
            ax, ay = snap(cx + hw * facing + 12 * facing), snap(cy + 0.1 * hh)
            for d in range(4):
                pg.draw.rect(screen, guide, (ax - d * 6 * facing - 3, ay - d * 6 - 3, 6, 6))
                pg.draw.rect(screen, guide, (ax - d * 6 * facing - 3, ay + d * 6 - 3, 6, 6))
        for k in range(14, 0, -1):                        # trail: older positions, smaller + darker
            x, y, on = self.move_path(kind, t - k * 0.025, facing)
            if kind == "F" and not on:
                continue
            fade = 1 - k / 15
            c = tuple(int(v * (0.35 + 0.65 * fade)) for v in col)
            r = max(6, int(14 * fade)) // 6 * 6
            pg.draw.rect(screen, c, (snap(cx + x * hw) - r // 2, snap(cy + y * hh) - r // 2, r, r))
        x, y, on = self.move_path(kind, t, facing)
        tx, ty = snap(cx + x * hw), snap(cy + y * hh)
        if kind == "F":                                   # wand lies flat, pointing at the rival
            hx, hy = tx - 64 * facing, ty + 12
        else:                                             # wand held up, hand below the tip
            hx, hy = tx - 20 * facing, ty + 40
        pg.draw.line(screen, (40, 22, 12), (hx, hy), (tx, ty), 14)       # outline
        pg.draw.line(screen, (150, 95, 45), (hx, hy), (tx, ty), 8)       # wooden wand
        pg.draw.rect(screen, (240, 190, 150), (hx - 12, hy - 10, 24, 22))  # hand
        pg.draw.rect(screen, (40, 22, 12), (hx - 12, hy - 10, 24, 22), 3)
        glow = 18 if on else 12
        pg.draw.rect(screen, col, (tx - glow // 2, ty - glow // 2, glow, glow))      # glowing tip
        pg.draw.rect(screen, (255, 255, 230), (tx - 3, ty - 3, 6, 6))
        if kind == "F" and on:                            # little flame burst on the punch
            for dx, dy, r in ((24, 0, 12), (40, -8, 8), (40, 8, 8), (54, 0, 6)):
                pg.draw.rect(screen, col, (tx + dx * facing - r // 2, ty + dy - r // 2, r, r))

    # ------------------------------------------------------------------ scene pieces (canvas pixels)
    def cowboy(self, canvas, i, pose, x, now, bob=0):
        flip = i == 1
        if pose == "down":
            s = self.lying(self.cowboys[i]["idle"], flip)
            self.put(canvas, s, x - 4, GROUND_Y + 1)
            return
        self.put(canvas, self.cowboys[i]["aim" if pose in ("aim", "flash") else "idle"], x, GROUND_Y - bob, flip)
        if pose == "flash":                                   # muzzle flash in front of the gun
            fx = x + 16 if not flip else x - 4
            col = (255, 240, 150) if int(now * 30) % 2 else (255, 160, 60)
            self.rect(canvas, col, fx, GROUND_Y - 23 + 8, 4, 3)
            self.rect(canvas, (255, 255, 230), fx + (1 if not flip else 2), GROUND_Y - 23 + 9, 1, 1)

    def wizard(self, canvas, i, pose, x, now, hurt=False):
        flip = i == 1
        if pose == "down":
            self.put(canvas, self.lying(self.wizards[i]["idle"], flip), x - 4, GROUND_Y + 1)
            return
        spr = self.wizards[i]["cast" if pose == "cast" else ("charge" if pose == "charge" else "idle")]
        # magic circle under the feet
        glow = SPELL_RGB["W"] if pose == "charge" else P_DARK[i]
        self.rect(canvas, glow, x + 1, GROUND_Y, 14, 1)
        self.rect(canvas, glow, x + 3, GROUND_Y + 1, 10, 1)
        self.put(canvas, spr, x, GROUND_Y, flip)
        if hurt and int(now * 20) % 2:
            self.rect(canvas, (255, 60, 60), x + 4, GROUND_Y - 14, 8, 2)
        if pose == "charge":                                   # sparkles round the raised wand
            rng = random.Random(int(now * 12) + i * 99)
            tip_x = x + (13 if not flip else 2)
            for _ in range(5):
                canvas.set_at((tip_x + rng.randint(-4, 4), GROUND_Y - 24 + rng.randint(-4, 3)),
                              rng.choice([(200, 230, 255), (255, 255, 255), (120, 170, 255)]))

    def wand_tip(self, i, x, pose="cast"):
        """Canvas position of the wand tip for spells / beams."""
        return (x + 15, GROUND_Y - 13) if i == 0 else (x + 0, GROUND_Y - 13)

    def tumbleweed(self, canvas, now):
        x = (now * 9) % (LW + 20) - 10
        hop = abs(math.sin(now * 3)) * 2
        self.put(canvas, self.tumble, x, GROUND_Y - 1 - hop)

    def bullets(self, canvas, cx, y, loaded):
        for k in range(6):
            spr = self.bullet_full if k < loaded else self.bullet_empty
            canvas.blit(spr, (int(cx - 9 + k * 3), y))

    def hearts(self, canvas, cx, y, hp, max_hp):
        n = max(max_hp, hp)
        x0 = cx - (n * 8 - 1) // 2
        for k in range(n):
            canvas.blit(self.heart if k < hp else self.heart_empty, (int(x0 + k * 8), y))

    def crystals(self, canvas, cx, y, mana, max_mana):
        x0 = cx - (max_mana * 7 - 1) // 2
        for k in range(max_mana):
            canvas.blit(self.crystal if k < mana else self.crystal_empty, (int(x0 + k * 7), y))

    def spell(self, canvas, kind, x, y, flip=False, now=0.0):
        spr = self.spells[kind]
        if flip:
            spr = self.pg.transform.flip(spr, True, False)
        wob = int(math.sin(now * 25) * 1) if kind == "L" else 0
        canvas.blit(spr, (int(x) - spr.get_width() // 2, int(y) - spr.get_height() // 2 + wob))
        # little trail
        col = SPELL_RGB[kind]
        tx = int(x) + (-6 if not flip else 6)
        self.rect(canvas, col, tx - 1, int(y), 2, 1)
        self.rect(canvas, col, tx + (-3 if not flip else 3), int(y) + 1, 1, 1)

    def burst(self, canvas, x, y, k, col):
        """Expanding pixel ring, k = 0..1."""
        r = 2 + int(k * 9)
        for a in range(0, 360, 30):
            ax = int(x + r * math.cos(math.radians(a)))
            ay = int(y + r * 0.7 * math.sin(math.radians(a)))
            self.rect(canvas, col, ax, ay, 2, 2)
        if k < 0.4:
            self.rect(canvas, (255, 255, 255), x - 2, y - 2, 4, 4)

    def beam(self, canvas, x0, x1, y, col, now, frozen=False, seed=0):
        if x1 < x0:
            x0, x1 = x1, x0
        rng = random.Random(int(now * 25) + seed)
        thick = 2 if frozen else 3
        for x in range(int(x0), int(x1) + 1):
            dy = 0 if frozen else rng.choice((0, 0, 0, 1, -1))
            self.rect(canvas, col, x, y - thick // 2 + dy, 1, thick)
            if not frozen and rng.random() < 0.6:
                canvas.set_at((x, y + dy), (255, 255, 240))
        if frozen:
            self.rect(canvas, (210, 235, 255), int(x0), y, int(x1 - x0), 1)

    def clash(self, canvas, x, y, now, frozen=False):
        rng = random.Random(int(now * 30))
        r = 3 if frozen else 3 + int(abs(math.sin(now * 18)) * 2)
        col = (200, 230, 255) if frozen else (255, 220, 120)
        self.pg.draw.circle(canvas, col, (int(x), int(y)), r)
        self.pg.draw.circle(canvas, (255, 255, 255), (int(x), int(y)), max(1, r - 2))
        if not frozen:
            for _ in range(10):
                a = rng.uniform(0, 2 * math.pi)
                d = rng.uniform(r + 1, r + 9)
                canvas.set_at((int(x + d * math.cos(a)), int(y + d * 0.8 * math.sin(a))),
                              rng.choice([(255, 240, 150), (255, 255, 255), (255, 140, 60)]))

    def confetti(self, canvas, now):
        rng = random.Random(3)
        for k in range(50):
            x = (rng.uniform(0, LW) + math.sin(now * 2 + k) * 4) % LW
            y = (rng.uniform(0, LH) + now * rng.uniform(8, 20)) % 70
            canvas.set_at((int(x), int(y)), rng.choice([(255, 210, 80), (240, 100, 80), (90, 180, 250), (250, 250, 250)]))
