"""
Lights Out: a puzzle that plays inside an Outlook email. No script, no server.

    python lights_out.py --theme mybrand --out C:/temp/lights/emails
        -> lights-out.html       3 levels, live hint map, floor moons
           lights-out-lite.html  control: the smallest card, to tell a size limit from a feature gap
           img/lights-out-hero.gif
    --theme signature  gives the gold / pink / ink poster look (flat night hero, gold card, pink accents)
    --theme signature-light / signature-dark  the masthead layout: a full-bleed gold masthead carries
                       the title, then the hero (no baked-in text) and a cream or ink page

The game is the Adaptive Card at the top of the email (Outlook desktop, web and mobile):

  click = XOR    Action.ToggleVisibility flips every element it names. That is the rule of Lights Out
                 itself: a window flips, and so do its four neighbours.
  nesting = AND  An element shows only if all its ancestors do. The win banner sits inside one wrapper
                 per window, each visible while its window is dark, so it appears only when all are out.
                 Each floor has its own 5-deep chain, so a moon rises beside every floor you clear.
  hint = XOR     Pressing a window twice undoes it, so "the solution from here" is the start solution
                 with your clicks flipped in. Every click also flips its own dot on the hint map.

The HTML body is the poster every other client sees: an animated solve (frame 1 is the lit tower), the
rules, and how the card works. Self-sent, the card needs no registration (send_outlook.py).
"""
import argparse
import json
import math
import pathlib
import random
import re
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emailkit as ek  # noqa: E402

ROWS, COLS = 5, 5
N = ROWS * COLS
LIT, DARK, MOON, NIGHT, DOOR = "\U0001F7E8", "\u2B1B", "\U0001F319", "\U0001F303", "\U0001F6AA"
LEVELS = [(3, 9), (5, 12), (8, 14)]   # (par, lit windows to aim for)
DEMO = (4, 11)                        # the solve the hero GIF plays; never one of the levels
S = 2                                 # hero GIF scale (retina)
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


# =================================================================== the puzzle, over GF(2)
def neighbourhood(k: int) -> list[int]:
    """The window and its four neighbours, in the order: self, above, below, left, right."""
    r, c = divmod(k, COLS)
    cells = [(r, c), (r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
    return [rr * COLS + cc for rr, cc in cells if 0 <= rr < ROWS and 0 <= cc < COLS]


def press(state: int, k: int) -> int:
    for j in neighbourhood(k):
        state ^= 1 << j
    return state


def apply(presses: int) -> int:
    state = 0
    for k in bits(presses):
        state = press(state, k)
    return state


def bits(v: int) -> list[int]:
    return [k for k in range(N) if v >> k & 1]


def solve(state: int) -> int:
    """Shortest press set that clears `state`: Gauss-Jordan over GF(2), then every null-space shift."""
    pending = [(sum(1 << j for j in neighbourhood(k)), state >> k & 1) for k in range(N)]
    pivots = []  # (column, row, rhs), fully reduced
    for col in range(N):
        hit = next((i for i, (row, _) in enumerate(pending) if row >> col & 1), None)
        if hit is None:
            continue
        prow, prhs = pending.pop(hit)
        pending = [(r ^ prow, b ^ prhs) if r >> col & 1 else (r, b) for r, b in pending]
        pivots = [(c, r ^ prow, b ^ prhs) if r >> col & 1 else (c, r, b) for c, r, b in pivots]
        pivots.append((col, prow, prhs))
    if any(b for _, b in pending):
        raise ValueError("pattern is not solvable")
    free = sorted(set(range(N)) - {c for c, _, _ in pivots})
    best = None
    for combo in range(1 << len(free)):
        x = sum(1 << f for i, f in enumerate(free) if combo >> i & 1)
        for c, r, b in pivots:
            if b ^ ((r & x).bit_count() & 1):
                x |= 1 << c
        if best is None or (x.bit_count(), x) < (best.bit_count(), best):
            best = x
    return best


def mirror(k: int) -> int:
    r, c = divmod(k, COLS)
    return r * COLS + COLS - 1 - c


def symmetric_puzzles(sizes: set[int]) -> dict[int, list[tuple[int, int]]]:
    """Every left-right symmetric press set of a wanted size that is also a shortest solution,
    so the par we print is honest. Symmetric starts look like a designed facade."""
    orbits = sorted({(1 << k) | (1 << mirror(k)) for k in range(N)})
    found = {size: [] for size in sizes}
    for mask in range(1, 1 << len(orbits)):
        presses = sum(o for i, o in enumerate(orbits) if mask >> i & 1)
        size = presses.bit_count()
        if size in found:
            state = apply(presses)
            if solve(state).bit_count() == size:
                found[size].append((presses, state))
    return found


def pick(candidates: list[tuple[int, int]], lit_target: int, avoid: set[int],
         avoid_presses: int = 0) -> tuple[int, int]:
    def score(item):
        presses, state = item
        floors_lit = sum(1 for r in range(ROWS) if state >> (r * COLS) & (2 ** COLS - 1))
        press_floors = len({k // COLS for k in bits(presses)})
        return abs(state.bit_count() - lit_target), -floors_lit, -press_floors, presses
    return min((c for c in candidates if c[1] not in avoid and not c[0] & avoid_presses), key=score)


def ascii_board(state: int, presses: int = 0) -> str:
    return "\n".join("   " + " ".join(("#" if state >> (r * COLS + c) & 1 else ".")
                                       + ("*" if presses >> (r * COLS + c) & 1 else " ") for c in range(COLS))
                     for r in range(ROWS))


# =================================================================== the card
def window_name(k: int) -> str:
    r, c = divmod(k, COLS)
    return f"{ROWS - r}{'ABCDEFGH'[c]}"


def shown(element: dict, visible: bool) -> dict:
    """isVisible defaults to true, so write it only when false: the full card is ~40 KB."""
    if not visible:
        element["isVisible"] = False
    return element


def glyph(id_: str, text: str, visible: bool, size: str = "ExtraLarge", **kw) -> dict:
    return shown({"type": "TextBlock", "id": id_, "text": text, "size": size, "horizontalAlignment": "Center",
                  "spacing": "None", **kw}, visible)


def col(width: str, items: list | None = None, **kw) -> dict:
    """A Column. "type" is optional inside "columns"; Outlook's own samples leave it out."""
    return {"width": width, **({"items": items} if items else {}), **kw}


def click_targets(k: int, hint: bool = True, floors: bool = True) -> list[str]:
    """One click: for the window and each neighbour flip lit (a), dark (b) and its links in the
    tower-wide (w) and floor (f) AND chains; then flip this window's own hint dot (p/q)."""
    ids = []
    for j in neighbourhood(k):
        ids += [f"a{j}", f"b{j}", f"w{j}"] + ([f"f{j}"] if floors else [])
    return ids + ([f"p{k}", f"q{k}"] if hint else [])


def level_targets(levels: list[tuple[int, int]], index: int, hint: bool = True, floors: bool = True) -> list[dict]:
    """A level button sets every element explicitly, so it doubles as Restart."""
    presses, state = levels[index]
    targets = []
    for k in range(N):
        on, dot = bool(state >> k & 1), bool(presses >> k & 1)
        sets = [("a", on), ("b", not on), ("w", not on)] + ([("f", not on)] if floors else []) \
            + ([("p", dot), ("q", not dot)] if hint else [])
        targets += [{"elementId": f"{prefix}{k}", "isVisible": v} for prefix, v in sets]
    targets += [{"elementId": f"lv{i}", "isVisible": i == index} for i in range(len(levels))]
    return targets + ([{"elementId": "hm", "isVisible": False}] if hint else [])


def centered(items: list, spacing: str = "Default") -> dict:
    return {"type": "ColumnSet", "spacing": spacing, "columns": [col("stretch"), col("auto", items), col("stretch")]}


def build_card(levels: list[tuple[int, int]], hint: bool = True, floors: bool = True) -> dict:
    presses0, start = levels[0]
    lit = lambda k: bool(start >> k & 1)  # noqa: E731

    def label(text: str) -> dict:
        return col("30px", [{"type": "TextBlock", "text": text, "size": "Small", "isSubtle": True,
                             "horizontalAlignment": "Right"}], verticalContentAlignment="Center")

    storeys = []
    for r in range(ROWS):
        cells = []
        for c in range(COLS):
            k = r * COLS + c
            cells.append(col("40px", [{
                "type": "Container",
                "selectAction": {"type": "Action.ToggleVisibility", "title": f"Window {window_name(k)}",
                                 "targetElements": click_targets(k, hint, floors)},
                "items": [glyph(f"a{k}", LIT, lit(k)), glyph(f"b{k}", DARK, not lit(k))]}], spacing="Small"))
        moon = col("30px", spacing="Small", verticalContentAlignment="Center")
        if floors:
            chain = {"type": "TextBlock", "text": MOON, "size": "Large", "horizontalAlignment": "Center"}
            for c in reversed(range(COLS)):
                k = r * COLS + c
                chain = shown({"type": "Container", "id": f"f{k}", "items": [chain]}, not lit(k))
            moon["items"] = [chain]
        storeys.append({"type": "ColumnSet", "spacing": "Small", "columns": [label(f"{ROWS - r}F")] + cells + [moon]})
    lobby = [col("40px", [{"type": "TextBlock", "text": DOOR, "size": "Large", "horizontalAlignment": "Center"}]
                 if c == COLS // 2 else None, spacing="Small") for c in range(COLS)]
    storeys.append({"type": "ColumnSet", "spacing": "Small",
                    "columns": [label("G")] + lobby + [col("30px", spacing="Small")]})
    facade = {"type": "Container", "style": "emphasis", "items": [
        {"type": "TextBlock", "text": "NO. 25 · WINDOW STREET", "size": "Small", "weight": "Bolder",
         "isSubtle": True, "horizontalAlignment": "Center"}] + storeys}

    more = " Try the next level." if len(levels) > 1 else ""
    win = {"type": "Container", "style": "good", "items": [{"type": "ColumnSet", "columns": [
        col("auto", [{"type": "TextBlock", "text": NIGHT, "size": "ExtraLarge"}], verticalContentAlignment="Center"),
        col("stretch", [
            {"type": "TextBlock", "text": "Lights out.", "weight": "Bolder", "size": "Medium", "color": "Good"},
            {"type": "TextBlock", "text": f"Every window is dark and the tower is at zero load.{more}",
             "wrap": True, "isSubtle": True, "spacing": "None"}], verticalContentAlignment="Center")]}]}
    for k in reversed(range(N)):
        win = shown({"type": "Container", "id": f"w{k}", "items": [win]}, not lit(k))
    win["spacing"] = "Medium"

    level_labels = []
    for i, (presses, _) in enumerate(levels):
        texts = [{"type": "TextBlock", "text": f"par {presses.bit_count()}", "size": "Small", "isSubtle": True,
                  "horizontalAlignment": "Right", "spacing": "None"}]
        if len(levels) > 1:
            texts.insert(0, {"type": "TextBlock", "text": f"LEVEL {i + 1} / {len(levels)}", "weight": "Bolder",
                             "color": "Accent", "size": "Small", "horizontalAlignment": "Right"})
        level_labels.append(shown({"type": "Container", "id": f"lv{i}", "items": texts}, i == 0))

    buttons = [{"type": "Action.ToggleVisibility", "title": f"Level {i + 1}" if len(levels) > 1 else "Restart",
                "targetElements": level_targets(levels, i, hint, floors)} for i in range(len(levels))]
    if hint:
        buttons.insert(0, {"type": "Action.ToggleVisibility", "title": "Hint", "targetElements": ["hm"]})
    restart = "Level buttons also restart. " if len(levels) > 1 else ""
    body = [
        {"type": "ColumnSet", "columns": [
            col("stretch", [
                {"type": "TextBlock", "text": "LIGHTS OUT", "weight": "Bolder", "size": "Large"},
                {"type": "TextBlock", "text": "Click a window: it flips, and so do the four around it. "
                                              "Turn the whole tower dark.", "wrap": True, "isSubtle": True,
                 "spacing": "None"}]),
            col("auto", level_labels)]},
        centered([facade], spacing="Medium"),
        win,
        {"type": "ActionSet", "spacing": "Medium", "actions": buttons},
    ]
    if hint:
        dots = []
        for r in range(ROWS):
            cells = [col("30px")]
            for c in range(COLS):
                k = r * COLS + c
                on = bool(presses0 >> k & 1)
                cells.append(col("40px", [
                    glyph(f"p{k}", "●", on, size="Medium", color="Accent", fontType="Monospace"),
                    glyph(f"q{k}", "·", not on, size="Medium", isSubtle=True, fontType="Monospace")],
                    spacing="Small"))
            dots.append({"type": "ColumnSet", "spacing": "None", "columns": cells + [col("30px", spacing="Small")]})
        body.append({"type": "Container", "id": "hm", "isVisible": False, "spacing": "Medium", "items": [
            {"type": "TextBlock", "text": "**Solution from here.** Press the dotted windows, in any order. "
                                          "The dots redraw as you play.", "wrap": True, "size": "Small"},
            centered(dots, spacing="Small")]})
    body.append({"type": "TextBlock", "text": f"{restart}No script and no server: every click is one "
                                              "Action.ToggleVisibility.", "wrap": True, "size": "Small",
                 "isSubtle": True, "spacing": "Medium"})
    return ek.adaptive_card(body, hide_original_body=False)


# =================================================================== the hero GIF
def mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def px(v: float) -> int:
    return round(v * S)


def box(x0: float, y0: float, x1: float, y1: float) -> tuple:
    return px(x0), px(y0), px(x1) - 1, px(y1) - 1


def ttf(name: str, size: int, variation: bytes | None = None) -> ImageFont.FreeTypeFont:
    for path in (pathlib.Path(name), pathlib.Path("C:/Windows/Fonts") / name):
        if path.exists():
            font = ImageFont.truetype(str(path), size)
            if variation:
                try:
                    names = font.get_variation_names()
                    font.set_variation_by_name(next((n for n in names if n == variation), names[-1]))
                except (OSError, StopIteration):
                    pass  # not a variable font
            return font
    return ek._font(size, "semibold")


def spaced(draw: ImageDraw.ImageDraw, xy: tuple, text: str, font, fill, tracking: float):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += font.getlength(ch) + tracking


class Hero:
    """A night skyline whose centre tower is the 5x5 board. Everything static is drawn once."""
    W, H = 640, 320
    TX0, TX1, ROOF = 380, 530, 146
    WIN_W, WIN_H, PITCH_X, PITCH_Y, WIN_X0, WIN_Y0 = 16, 18, 27, 27, 393, 168
    TEXT_ZONE = (20, 28, 312, 200)  # no stars behind the title: a dot beside a word reads as punctuation
    MOON_XY, MOON_R = (590, 58), 17

    def __init__(self, caption: str, titled: bool = True):
        t = ek.theme()
        c = t.chrome
        self.titled = titled
        self.caption_xy, self.tall_from = (36, 190), 340  # the skyline stays low under the title
        if not titled:  # the email's masthead carries the title: centre the tower, caption top left
            self.TX0, self.TX1, self.WIN_X0 = 245, 395, 258
            self.TEXT_ZONE = (20, 34, 330, 70)
            self.caption_xy, self.tall_from = (36, 60), -1
        ink = ek._hex(c.ink)
        self.accent = ek._hex(c.accent)
        self.pop = ek._hex(getattr(c, "pop", c.accent))  # the one hot accent: press ring, punchline, beacon
        self.on_ink = ek._hex(c.on_ink)
        self.lit = (255, 201, 77)
        self.flat = hasattr(c, "night")
        if self.flat:  # two-tone night ground and flat fills: the poster look
            self.sky_top = self.sky_bot = ek._hex(c.night_deep)
            self.far, self.near = ek._hex(c.night), ink
            self.tower = mix(self.far, (255, 255, 255), 0.07)
        else:
            self.sky_top = mix(ink, (0, 0, 0), 0.55)
            self.sky_bot = mix(ink, self.lit, 0.07)
            self.far = mix(mix(self.sky_bot, self.sky_top, 0.4), (0, 0, 0), 0.2)
            self.near = mix(self.sky_top, (0, 0, 0), 0.5)
            self.tower = mix(self.near, (255, 255, 255), 0.10)
        self.glass = mix(self.tower, (130, 150, 185), 0.14)
        self.moon = (244, 236, 216)
        self.beacon_colour = self.pop if hasattr(c, "pop") else ek._hex(getattr(t.status, "critical", "#d03b3b"))
        raster = t.raster_fonts
        mono = getattr(raster, "mono", None)
        self.f_kicker = ttf(mono or getattr(raster, "semibold", raster.regular), px(11))
        self.kicker_tracking = px(1.4 if mono else 2.6)  # mono labels: ~0.12 em, HUD-style spacing
        display = getattr(raster, "display", "bahnschrift.ttf")
        self.f_title = ttf(display, px(54), b"Bold SemiCondensed")
        width = self.f_title.getlength("LIGHTS OUT") * 0.98
        if width > px(330):  # wide faces (Arial Black) must clear the tower
            self.f_title = ttf(display, int(px(54) * px(330) / width), b"Bold SemiCondensed")
        self.f_sub = ttf(raster.regular, px(15))
        self._layout(random.Random(25))
        self.base = self._base(caption)

    def window_box(self, k: int) -> tuple:
        r, c = divmod(k, COLS)
        x, y = self.WIN_X0 + c * self.PITCH_X, self.WIN_Y0 + r * self.PITCH_Y
        return box(x, y, x + self.WIN_W, y + self.WIN_H)

    def window_centre(self, k: int) -> tuple:
        r, c = divmod(k, COLS)
        return self.WIN_X0 + c * self.PITCH_X + self.WIN_W / 2, self.WIN_Y0 + r * self.PITCH_Y + self.WIN_H / 2

    def _layout(self, rnd: random.Random):
        self.far_blds, self.far_dots, self.near_blds, self.glass_slots, self.city = [], [], [], [], []
        x = -8
        while x < self.W:
            w, h = rnd.randint(20, 46), rnd.randint(60, 118 if x < self.tall_from else 172)
            self.far_blds.append((x, self.H - h, x + w, self.H))
            self.far_dots += [(wx, wy) for wy in range(self.H - h + 6, self.H - 4, 6)
                              for wx in range(x + 4, x + w - 4, 5) if rnd.random() < 0.10]
            x += w + rnd.randint(-6, 1)
        warm = [(255, 201, 77), (255, 226, 160), (255, 176, 64), (205, 225, 255)]
        x = -4
        while x < self.W:
            w, h = rnd.randint(28, 60), rnd.randint(46, 104 if x < self.tall_from else 148)
            top = self.H - h
            self.near_blds.append((x, top, x + w, self.H))
            for wy in range(top + 6, self.H - 6, 9):
                for wx in range(x + 5, x + w - 7, 7):
                    if self.TX0 - 6 < wx < self.TX1 + 2:
                        continue  # behind the tower
                    slot = (wx, wy, wx + 3, wy + 4)
                    self.glass_slots.append(slot)
                    if rnd.random() < 0.34:
                        self.city.append((slot, rnd.choices(warm, [5, 3, 2, 1])[0]))
            x += w + rnd.randint(1, 7)
        mx, my = self.MOON_XY
        self.stars = []
        while len(self.stars) < 85:
            sx, sy = rnd.uniform(0, self.W), rnd.uniform(4, 200)
            x0, y0, x1, y1 = self.TEXT_ZONE
            if math.hypot(sx - mx, sy - my) > 30 and not (x0 < sx < x1 and y0 < sy < y1):
                self.stars.append((sx, sy, rnd.uniform(0.45, 1.2), rnd.uniform(0.25, 0.95)))

    def _base(self, caption: str) -> Image.Image:
        W, H = px(self.W), px(self.H)
        grad = Image.linear_gradient("L").resize((W, H))
        img = Image.composite(Image.new("RGB", (W, H), self.sky_bot), Image.new("RGB", (W, H), self.sky_top), grad)
        if not self.flat:
            haze = Image.new("L", (W, H), 0)
            ImageDraw.Draw(haze).ellipse(box(120, 250, 760, 420), fill=115)
            img = Image.composite(Image.new("RGB", (W, H), mix(self.sky_bot, self.lit, 0.25)), img,
                                  haze.filter(ImageFilter.GaussianBlur(px(50))))
        img = img.convert("RGBA")

        stars = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
        sd = ImageDraw.Draw(stars)
        for sx, sy, r, a in self.stars:
            cx, cy, rr = sx * S * 2, sy * S * 2, r * S * 2
            sd.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(255, 248, 230, round(255 * a)))
        img.alpha_composite(stars.resize((W, H), Image.LANCZOS))

        (mx, my), mr = self.MOON_XY, self.MOON_R
        halo = Image.new("L", (W, H), 0)
        ImageDraw.Draw(halo).ellipse(box(mx - mr * 1.3, my - mr * 1.3, mx + mr * 1.3, my + mr * 1.3), fill=80)
        halo = halo.filter(ImageFilter.GaussianBlur(px(24)))
        img.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), v) for v in self.moon] + [halo]))
        disc = Image.new("L", (W * 2, H * 2), 0)
        dd, k2 = ImageDraw.Draw(disc), S * 2
        dd.ellipse(((mx - mr) * k2, (my - mr) * k2, (mx + mr) * k2, (my + mr) * k2), fill=255)
        dd.ellipse(((mx - mr + 9) * k2, (my - mr - 5) * k2, (mx + mr + 9) * k2, (my + mr - 5) * k2), fill=0)
        img.paste(self.moon + (255,), (0, 0, W, H), disc.resize((W, H), Image.LANCZOS))

        d = ImageDraw.Draw(img)
        for b in self.far_blds:
            d.rectangle(box(*b), fill=self.far)
        for wx, wy in self.far_dots:
            d.rectangle(box(wx, wy, wx + 2, wy + 2), fill=mix(self.far, self.lit, 0.3))
        for b in self.near_blds:
            d.rectangle(box(*b), fill=self.near)
        city_glass = mix(self.near, (130, 150, 185), 0.10)
        for slot in self.glass_slots:
            d.rectangle(box(*slot), fill=city_glass)

        tx0, tx1, roof = self.TX0, self.TX1, self.ROOF
        tc = (tx0 + tx1) / 2
        edge = mix(self.tower, self.moon, 0.22)
        for inset, y0, y1 in ((0, roof, self.H), (18, roof - 12, roof), (44, roof - 22, roof - 12)):
            d.rectangle(box(tx0 + inset, y0, tx1 - inset, y1), fill=self.tower)
            d.rectangle(box(tx1 - inset - 1.5, y0, tx1 - inset, y1), fill=edge)  # moonlit edge
        d.rectangle(box(tc - 0.8, roof - 64, tc + 0.8, roof - 22), fill=edge)  # mast
        for k in range(N):
            d.rectangle(self.window_box(k), fill=self.glass)

        if self.titled:
            spaced(d, (px(36), px(52)), "AN EMAIL YOU CAN PLAY", self.f_kicker, self.accent, self.kicker_tracking)
            spaced(d, (px(33), px(108)), "LIGHTS OUT", self.f_title, self.accent, -0.02 * self.f_title.size)
            sub = mix(self.on_ink, self.sky_top, 0.18)
            d.text((px(36), px(138)), "Every window is a switch.", font=self.f_sub, fill=sub, anchor="ls")
            d.text((px(36), px(159)), "Turn the whole tower dark.", font=self.f_sub, fill=sub, anchor="ls")

        self.caption = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cx, cy = self.caption_xy
        spaced(ImageDraw.Draw(self.caption), (px(cx), px(cy)), caption, self.f_kicker, self.pop, self.kicker_tracking)
        self.beacon = {}
        for on in (True, False):
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            bx, by = tc, roof - 65
            if on:
                glow = Image.new("L", (W, H), 0)
                ImageDraw.Draw(glow).ellipse(box(bx - 7, by - 7, bx + 7, by + 7), fill=200)
                layer = Image.merge("RGBA", [Image.new("L", (W, H), v) for v in self.beacon_colour]
                                    + [glow.filter(ImageFilter.GaussianBlur(px(4)))])
            ImageDraw.Draw(layer).ellipse(box(bx - 2.6, by - 2.6, bx + 2.6, by + 2.6),
                                          fill=(self.beacon_colour if on else mix(self.beacon_colour, self.near, 0.7))
                                          + (255,))
            self.beacon[on] = layer
        return img.convert("RGB")

    def frame(self, state: int, city_on: list[bool], ring: tuple | None = None, flash: dict | None = None,
              caption: float = 0.0, beacon: bool = True) -> Image.Image:
        lights = Image.new("RGB", self.base.size, (0, 0, 0))
        d = ImageDraw.Draw(lights)
        for (slot, colour), on in zip(self.city, city_on):
            if on:
                d.rectangle(box(*slot), fill=colour)
        for k in range(N):
            f = (flash or {}).get(k)
            if f == "on":
                d.rectangle(self.window_box(k), fill=mix(self.lit, (255, 255, 255), 0.6))
            elif f == "off":
                d.rectangle(self.window_box(k), fill=mix(self.lit, self.glass, 0.55))  # afterglow
            elif state >> k & 1:
                d.rectangle(self.window_box(k), fill=self.lit)
        img = ImageChops.add(self.base, ImageEnhance.Brightness(lights.filter(ImageFilter.GaussianBlur(px(3)))).enhance(0.85))
        img = ImageChops.add(img, ImageEnhance.Brightness(lights.filter(ImageFilter.GaussianBlur(px(12)))).enhance(0.5))
        img.paste(lights, (0, 0), lights.convert("L").point(lambda v: 255 if v else 0))
        img = img.convert("RGBA")
        img.alpha_composite(self.beacon[beacon])
        if ring:
            self._ring(img, *ring)
        if caption > 0:
            layer = self.caption.copy()
            layer.putalpha(layer.getchannel("A").point(lambda v: round(v * caption)))
            img.alpha_composite(layer)
        return img.convert("RGB")

    def _ring(self, img: Image.Image, k: int, radius: float, alpha: float):
        cx, cy = self.window_centre(k)
        half = int((radius + 3) * S * 2)
        patch = Image.new("RGBA", (half * 2, half * 2), (0, 0, 0, 0))
        r = radius * S * 2
        ImageDraw.Draw(patch).ellipse((half - r, half - r, half + r, half + r),
                                      outline=self.pop + (round(255 * alpha),), width=round(2 * S * 2))
        patch = patch.resize((half, half), Image.LANCZOS)
        img.alpha_composite(patch, (round(cx * S - half / 2), round(cy * S - half / 2)))


def save_gif(frames: list[Image.Image], durations: list[int], path: pathlib.Path, loop: int = 2):
    """One palette for every frame (sampled from the poster frame at full size plus thumbnails of all
    frames), no dithering, so static regions stay byte-identical and Pillow stores only what changed.
    loop=2 plays three times (Outlook for M365's own cap); loop=0 repeats for ever where the client allows."""
    w, h = frames[0].size
    tw, th = w // 4, h // 4
    sample = Image.new("RGB", (w, h + th * math.ceil(len(frames) / 4)))
    sample.paste(frames[0], (0, 0))
    for i, f in enumerate(frames):
        sample.paste(f.resize((tw, th), Image.BILINEAR), ((i % 4) * tw, h + (i // 4) * th))
    palette = sample.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=durations, loop=loop, disposal=1)


def build_hero(demo: tuple[int, int], path: pathlib.Path, titled: bool = True) -> int:
    """Frame 1 is the lit tower (what non-animating Outlooks show). Then a ring presses each window of
    the solution, the tower goes dark, the city follows, a caption lands, and it crossfades home.
    titled=False leaves the title to the email's masthead. Returns the number of frames."""
    presses, start = demo
    order = bits(presses)
    hero = Hero(f"ALL DARK IN {len(order)} MOVES", titled)
    city_on = [True] * len(hero.city)
    frames, durations, clock = [], [], [0]

    def add(img: Image.Image, ms: int):
        frames.append(img)
        durations.append(ms)
        clock[0] += ms

    blink = lambda: clock[0] // 900 % 2 == 0  # noqa: E731
    add(hero.frame(start, city_on), 1800)
    state = start
    for i, k in enumerate(order):
        add(hero.frame(state, city_on, ring=(k, 12, 1.0), beacon=blink()), 120)
        add(hero.frame(state, city_on, ring=(k, 15, 0.75), beacon=blink()), 70)
        new = press(state, k)
        flash = {j: "on" if new >> j & 1 else "off" for j in neighbourhood(k)}
        add(hero.frame(new, city_on, ring=(k, 18, 0.35), flash=flash, beacon=blink()), 70)
        state = new
        add(hero.frame(state, city_on, beacon=blink()), 420 if i < len(order) - 1 else 320)
    assert state == 0, "demo solution does not clear the board"
    tc = ((hero.TX0 + hero.TX1) / 2, 236)
    nearest = sorted(range(len(hero.city)), key=lambda i: math.dist(tc, hero.city[i][0][:2]))
    step = math.ceil(len(nearest) / 6)
    for g in range(0, len(nearest), step):
        for i in nearest[g:g + step]:
            city_on[i] = False
        add(hero.frame(state, city_on, beacon=blink()), 90)
    add(hero.frame(state, city_on, caption=0.5, beacon=blink()), 90)
    add(hero.frame(state, city_on, caption=1.0), 2800)
    dark, poster = frames[-1], frames[0]
    for i in range(1, 6):
        add(Image.blend(dark, poster, i / 6), 60)
    add(poster.copy(), 40)  # end on the poster: M365 stops after 3 plays and keeps the last frame
    save_gif(frames, durations, path)
    return len(frames)


def build_ambient(path: pathlib.Path, titled: bool = True, count: int = 24, ms: int = 260) -> int:
    """The same night tower with no game in it: a seamless loop. Windows in the tower and the city switch off
    and back on in staggered events, a window going dark passes through an afterglow frame, and the beacon
    blinks on a period that divides the loop. Every event ends before the last frame, so the last frame and
    frame 1 are the same tower at rest, which is also what a non-animating Outlook shows. Returns frames."""
    hero = Hero("", titled)
    rnd = random.Random(42)
    base = sum(1 << k for k in range(N) if rnd.random() < 0.72)
    tower_events = [(rnd.randrange(N), rnd.randrange(1, count - 3)) for _ in range(10)]
    tower_events = [(k, start, min(rnd.randint(3, 8), count - 1 - start)) for k, start in tower_events]
    city_events = [(i, start, min(rnd.randint(2, 6), count - 1 - start))
                   for i in range(len(hero.city)) if rnd.random() < 0.14
                   for start in [rnd.randrange(1, count - 2)]]
    frames = []
    for f in range(count):
        state, flash = base, {}
        for k, start, length in tower_events:
            if start <= f < start + length:
                state ^= 1 << k
                if f == start and base >> k & 1:
                    flash[k] = "off"                      # a soft fade, not a cut
        city_on = [True] * len(hero.city)
        for i, start, length in city_events:
            if start <= f < start + length:
                city_on[i] = False
        frames.append(hero.frame(state & ~sum(1 << k for k in flash), city_on, flash=flash, beacon=f // 3 % 2 == 0))
    save_gif(frames, [ms] * count, path, loop=0)
    return count


# =================================================================== the HTML body
def para(html: str, size: int = 14, color: str | None = None, margin: str = "0") -> str:
    t = ek.theme()
    return (f'<p style="margin:{margin};font-family:{t.font};font-size:{size}px;color:{color or t.text.secondary};'
            f'{ek.lh(round(size * 1.5))}">{html}</p>')


def full_table(cells: str) -> str:
    return (f'<table role="presentation" width="592" cellpadding="0" cellspacing="0" border="0" '
            f'style="width:592px;"><tr>{cells}</tr></table>')


def pop() -> str:
    """The accent for light grounds: pink in the signature theme (gold on gold would vanish), else the accent."""
    return getattr(ek.theme().chrome, "pop", ek.theme().chrome.accent)


def panel() -> str:
    """Ground for the code box and rule chips: ink, or the theme's raised panel when the page itself is ink."""
    return getattr(ek.theme().chrome, "panel", ek.theme().chrome.ink)


def heading(title: str, hint: str = "") -> str:
    """Masthead layout: a serif section title and a quiet one-line hint."""
    t = ek.theme()
    hint_html = (f'<p style="margin:6px 0 0;font-family:{t.font};font-size:15px;color:{t.text.secondary};'
                 f'{ek.lh(22)}">{hint}</p>') if hint else ""
    return (f'<tr><td style="padding:0 24px;font-family:{t.font};">'
            f'<p class="display" style="margin:0;font-family:{t.font_display};font-size:27px;font-weight:bold;'
            f'letter-spacing:-0.6px;color:{t.text.primary};{ek.lh(32)}">{title}</p>{hint_html}</td></tr>')


def passage(html: str) -> str:
    """Masthead layout: lead copy behind a 4 px gold bar."""
    t = ek.theme()
    return full_table(f'<td width="4" bgcolor="{t.chrome.accent}" style="width:4px;background:{t.chrome.accent};'
                      f'font-size:1px;">&nbsp;</td><td style="padding:2px 0 2px 20px;">{para(html, 18, t.text.primary)}</td>')


def card_box(html: str, label: str = "") -> str:
    """Masthead layout: a note in a 1 px frame on a lifted fill."""
    t = ek.theme()
    c = t.chrome
    label_html = (f'<p class="mono" style="margin:0 0 6px;font-family:Consolas,\'Courier New\',monospace;font-size:11px;'
                  f'letter-spacing:1.6px;color:{t.text.muted};{ek.lh(16)}">{label}</p>') if label else ""
    return full_table(f'<td bgcolor="{c.box}" style="background:{c.box};border:1px solid {c.line};padding:16px 20px;">'
                      f'{label_html}{para(html, 15)}</td>')


def footer_rule(html: str) -> str:
    """Masthead layout: a 1 px rule, then small mono print."""
    t = ek.theme()
    return (f'<tr><td style="padding:0 24px;"><table role="presentation" width="592" cellpadding="0" cellspacing="0" '
            f'border="0" style="width:592px;"><tr><td height="1" bgcolor="{t.chrome.line}" style="height:1px;'
            f'background:{t.chrome.line};font-size:1px;{ek.lh(1)}">&nbsp;</td></tr>'
            f'<tr><td class="mono" style="padding:16px 0 0;font-family:Consolas,\'Courier New\',monospace;font-size:11px;'
            f'color:{t.text.muted};{ek.lh(18)}">{html}</td></tr></table></td></tr>')


def callout(html: str) -> str:
    t = ek.theme()
    return full_table(
        f'<td width="4" bgcolor="{pop()}" style="width:4px;background:{pop()};font-size:1px;">'
        f'&nbsp;</td><td bgcolor="{t.chart.empty_cell}" style="background:{t.chart.empty_cell};padding:14px 18px;">'
        f'{para(html, 13)}</td>')


def rule(chip: str, lead: str, body: str) -> str:
    t = ek.theme()
    chip_cell = (f'<table role="presentation" width="64" cellpadding="0" cellspacing="0" border="0"><tr>'
                 f'<td class="mono" align="center" bgcolor="{panel()}" style="background:{panel()};'
                 f'padding:7px 0;font-family:Consolas,monospace;font-size:13px;font-weight:bold;letter-spacing:1px;'
                 f'color:{t.chrome.accent};{ek.lh(16)}">{chip}</td></tr></table>')
    lead_html = f'<b style="color:{t.text.primary};">{lead}</b> {body}'
    return full_table(f'<td width="64" valign="top" style="width:64px;">{chip_cell}</td>'
                      f'<td width="16" style="width:16px;font-size:1px;">&nbsp;</td>'
                      f'<td valign="top">{para(lead_html, 14)}</td>')


def code_box(k: int, hint: bool = True, floors: bool = True) -> str:
    """The real targetElements of window k, annotated and syntax-coloured."""
    t = ek.theme()
    ids = click_targets(k, hint, floors)
    per = 4 if floors else 3
    links = "both AND links" if floors else "its AND link"
    where = [f"this window: lit, dark, {links}", "the window above", "below", "left", "right"]
    quoted = lambda group: ", ".join(f'"{x}"' for x in group)  # noqa: E731
    entries = [(quoted(ids[i:i + per]), note) for i, note in zip(range(0, per * len(neighbourhood(k)), per), where)]
    if hint:
        entries.append((quoted(ids[-2:]), "its dot on the hint map"))
    width = max(len(text) for text, _ in entries) + 3
    lines = ['"selectAction": {', '  "type": "Action.ToggleVisibility",', '  "targetElements": [']
    for i, (text, note) in enumerate(entries):
        lines.append("    " + (text + ("," if i < len(entries) - 1 else "")).ljust(width) + "// " + note)
    lines += ["  ]", "}"]

    def paint(line: str) -> str:
        code, _, note = line.partition("//")
        out = ""
        for part in re.split(r'("[^"]*"\s*:?)', code):
            if part:
                colour = (t.chrome.accent if part.rstrip().endswith(":") else t.chrome.on_ink) \
                    if part.startswith('"') else t.chrome.on_ink_muted
                out += f'<span class="mono" style="color:{colour};">{part.replace(" ", "&nbsp;")}</span>'
        if note:
            out += f'<span class="mono" style="color:{t.chrome.on_ink_muted};">//&nbsp;{note.strip().replace(" ", "&nbsp;")}</span>'
        return out

    return full_table(f'<td class="mono" bgcolor="{panel()}" style="background:{panel()};padding:16px 18px;'
                      f'font-family:Consolas,\'Courier New\',monospace;font-size:12px;color:{t.chrome.on_ink};'
                      f'{ek.lh(18)}">{"<br>".join(paint(x) for x in lines)}</td>')


def stats(items: list[tuple[str, str]], mono: bool = False) -> str:
    """mono=True sets the figures in Consolas: a serif display face like Georgia has old-style digits that bounce."""
    t = ek.theme()
    cls, face = ("mono", "Consolas,'Courier New',monospace") if mono else ("display", t.font_display)
    return full_table("".join(
        f'<td width="148" valign="top" style="width:148px;font-family:{t.font};">'
        f'<p class="{cls}" style="margin:0;font-family:{face};font-size:30px;font-weight:bold;'
        f'color:{t.text.primary};{ek.lh(36)}">{value}</p>'
        f'<p style="margin:2px 8px 0 0;font-size:12px;color:{t.text.secondary};{ek.lh(16)}">{label}</p></td>'
        for value, label in items))


def card_kb(card: dict) -> float:
    return len(json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) / 1024


def build_body(card: dict, demo_moves: int, levels: int, hint: bool = True, floors: bool = True,
               note: str = "") -> str:
    t = ek.theme()
    alt = (f"Animated: a tower at night with lit windows. A ring presses {demo_moves} windows, each flipping its "
           "neighbours, until the tower and then the whole city go dark. Lights Out: an email you can play.")
    accent_strip = (f'<tr><td height="5" bgcolor="{pop()}" style="height:5px;background:{pop()};'
                    f'font-size:5px;{ek.lh(5)}">&nbsp;</td></tr>')
    extras = []
    if levels > 1:
        extras.append(f"There are {WORDS[levels]} levels, each with a par")
    if hint:
        extras.append("a solution map that redraws itself as you play")
    intro = ("Every window is a switch, but the wiring is shared: flip one and its four neighbours flip with it. "
             f"Get all {N} windows dark." + (" " + ", and ".join(extras) + "." if extras else ""))
    rules = [("XOR", "A click is an XOR.",
              "Action.ToggleVisibility flips whatever it names: shown becomes hidden, hidden becomes shown. "
              "That is already the rule of the game, so each window just names itself and its four neighbours."),
             ("AND", "Nesting is an AND.",
              f"A container shows only if its parent does. The win banner sits {N} containers deep, one per "
              "window, each visible while its window is dark, so it can only appear when every window is out."
              + (" Each floor has its own five-deep chain: that is the moon beside a floor you clear."
                 if floors else ""))]
    if hint:
        rules.append(("HINT", "The hint is more XOR.",
                      "Pressing a window twice undoes it, and order never matters. So the solution from wherever "
                      "you are is the starting solution with your clicks flipped in: every click flips its own "
                      "dot on the map."))
    where = ("<b>The puzzle is the card at the top of this email.</b> It runs in Outlook with a work account, on "
             "desktop and the web. No card? Your mail app doesn't run Actionable Messages (most phones and personal "
             "accounts don't), so the animation above plays a solve instead.")
    figures = [(str(N), "windows, each one a switch"), (str(N), "containers deep: the win check"),
               (f"{card_kb(card):.0f} KB", "of card JSON, the whole game"), ("0", "lines of script")]
    footer = ("Fictional tower. The game is Lights Out (Tiger Electronics, 1995). Built with the outlook-email "
              "skill. The card renders when you send the email to yourself; to send it to others, register a "
              "provider and add its originator ID.")
    hero = f'<tr><td style="padding:0;">{ek.img_tag("img/lights-out-hero.gif", 640, 320, alt)}</td></tr>'
    under_the_hood = f"{WORDS[len(rules)].capitalize()} rules and no script"
    if hasattr(t.chrome, "masthead"):  # the masthead layout: gold masthead above, a quiet page below
        return (
            hero + ek.spacer(36)
            + (ek.row(card_box(note)) + ek.spacer(28) if note else "")
            + heading("How to play", "Turn off every light in the tower.") + ek.spacer(16)
            + ek.row(passage(intro)) + ek.spacer(24)
            + ek.row(card_box(where, "WHERE TO PLAY")) + ek.spacer(40)
            + heading("Under the hood", under_the_hood + ".") + ek.spacer(18)
            + ek.spacer(14).join(ek.row(rule(*r)) for r in rules) + ek.spacer(24)
            + ek.row(para("One window's click, in full:", 13, t.text.muted)) + ek.spacer(8)
            + ek.row(code_box(N // 2, hint, floors)) + ek.spacer(30)
            + ek.row(stats(figures, mono=True)) + ek.spacer(32)
            + footer_rule(footer) + ek.spacer(28)
        )
    return (
        hero + accent_strip + ek.spacer(28)
        + (ek.row(callout(note)) + ek.spacer(24) if note else "")
        + ek.section_title("How to play", "Turn off every light in the tower") + ek.spacer(10)
        + ek.row(para(intro))
        + ek.spacer(18)
        + ek.row(callout(where.replace("<b>", "<b>&#9650; ", 1)))
        + ek.spacer(32)
        + ek.section_title("Under the hood", under_the_hood) + ek.spacer(14)
        + ek.spacer(14).join(ek.row(rule(*r)) for r in rules)
        + ek.spacer(22)
        + ek.row(para("One window's click, in full:", 12, t.text.muted)) + ek.spacer(6)
        + ek.row(code_box(N // 2, hint, floors))
        + ek.spacer(26)
        + ek.row(stats(figures))
        + ek.spacer(30)
        + ek.footer_band(footer)
    )


def build_masthead(levels: int) -> str:
    """The gold top band, for themes that define chrome.masthead ("" otherwise: the hero is the top)."""
    if not hasattr(ek.theme().chrome, "masthead"):
        return ""
    count = f"{WORDS[levels]} level{'s' if levels > 1 else ''}"
    detail = f"{levels} levels, each with a par" if levels > 1 else "control card, one level"
    return ek.masthead(
        "LIGHTS OUT / AN EMAIL YOU CAN PLAY / NO. 25 WINDOW STREET",
        "Put the tower<br>to bed.",
        f"Twenty-five windows, {count}, one rule. Turn the whole tower dark, right here in your inbox: a real game "
        "inside this email, with no script and no server.",
        notice=f"Plays in Outlook with a work account &middot; desktop and web &middot; {detail}",
        numeral=str(N))


def build_ambient_body(frames: int, ms: int, gif_kb: float) -> str:
    """The ambient email: the looping tower and a few honest lines about how it moves. No card, no game."""
    t = ek.theme()
    alt = "Animated: a city at night. Windows in a tower and the buildings around it flicker on and off."
    hero = f'<tr><td style="padding:0;">{ek.img_tag("img/lights-out-ambient.gif", 640, 320, alt)}</td></tr>'
    seconds = frames * ms / 1000
    intro = (f"Every few seconds a window goes dark, a neighbour wakes up and the beacon on the mast keeps time. "
             f"It is one animated GIF, {frames} frames that loop without a seam, so it plays in new Outlook, Outlook "
             "on the web, mobile and Outlook for Microsoft 365. Outlook 2013 to 2019 shows the first frame: the "
             "tower at rest.")
    figures = [(str(frames), "frames, one seamless loop"), (f"{seconds:.0f} s", "per loop"),
               (f"{gif_kb:.0f} KB", "the whole animation"), ("0", "lines of script")]
    footer = "Fictional tower. Built with the outlook-email kit."
    if hasattr(t.chrome, "masthead"):
        return (hero + ek.spacer(36) + heading("How it moves", "One GIF on a loop.") + ek.spacer(16)
                + ek.row(passage(intro)) + ek.spacer(30) + ek.row(stats(figures, mono=True)) + ek.spacer(32)
                + footer_rule(footer) + ek.spacer(28))
    return (hero + ek.spacer(28) + ek.section_title("How it moves", "One GIF on a loop") + ek.spacer(10)
            + ek.row(para(intro)) + ek.spacer(26) + ek.row(stats(figures)) + ek.spacer(30) + ek.footer_band(footer))


def build_ambient_masthead() -> str:
    if not hasattr(ek.theme().chrome, "masthead"):
        return ""
    return ek.masthead(
        "AFTER HOURS / NO. 25 WINDOW STREET",
        "Put the tower<br>to bed.",
        "The night shift at No. 25: windows flicker on and off in a soft loop while the beacon keeps time. "
        "One animated GIF and no script, in every modern Outlook.",
        notice="Animated GIF &middot; loops where the client allows &middot; Outlook 2013 to 2019 shows frame 1",
        numeral=str(N))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", default="default")
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("outlook-email-out/emails"))
    args = parser.parse_args()
    ek.use_theme(args.theme)
    out = args.out.resolve()
    img_dir = out / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    puzzles = symmetric_puzzles({par for par, _ in LEVELS} | {DEMO[0]})
    levels, used = [], set()
    for par, lit_target in LEVELS:
        levels.append(pick(puzzles[par], lit_target, used))
        used.add(levels[-1][1])
    demo = pick(puzzles[DEMO[0]], DEMO[1], used, avoid_presses=levels[0][0])  # don't spoil level 1
    for i, (presses, state) in enumerate(levels):
        print(f"  level {i + 1}: par {presses.bit_count()}, {state.bit_count()} lit  (# lit, * press)\n"
              f"{ascii_board(state, presses)}")
    print(f"  hero demo: {demo[0].bit_count()} moves, {demo[1].bit_count()} lit\n{ascii_board(demo[1], demo[0])}")
    frames = build_hero(demo, img_dir / "lights-out-hero.gif", titled=not hasattr(ek.theme().chrome, "masthead"))
    gif_kb = (img_dir / "lights-out-hero.gif").stat().st_size / 1024
    print(f"  hero GIF {gif_kb:.0f} KB, {frames} frames")

    full = build_card(levels)
    lite = build_card(levels[:1], hint=False, floors=False)
    variants = [
        ("lights-out.html", "Lights Out · a puzzle inside this email", full,
         "Every window is a switch. Turn the whole tower dark, right here in Outlook.",
         build_body(full, demo[0].bit_count(), len(levels)), build_masthead(len(levels))),
        ("lights-out-lite.html", "Lights Out (lite) · control card", lite,
         "The same puzzle on the smallest card: one level, no hint map, no moons.",
         build_body(lite, demo[0].bit_count(), 1, hint=False, floors=False,
                    note=f"<b>Control version.</b> The same game on the smallest card: one level, no hint map and "
                         f"no floor moons ({card_kb(lite):.0f} KB against {card_kb(full):.0f} KB for the full game). "
                         "If this card shows up and the full one doesn't, your Outlook has a card size limit."),
         build_masthead(1)),
    ]
    for name, title, card, preheader, rows, top in variants:
        html = ek.email_document(title, rows, preheader=preheader, card=card, masthead=top)
        (out / name).write_text(html, encoding="utf-8")
        print(f"  {name:22} {len(html) / 1024:.0f} KB (card {card_kb(card):.1f} KB)  theme={args.theme}")

    # The ambient variant: the tower on a soft loop, no card, nothing to play. It works in every modern Outlook.
    count, ms = 24, 260
    build_ambient(img_dir / "lights-out-ambient.gif", titled=not hasattr(ek.theme().chrome, "masthead"),
                  count=count, ms=ms)
    amb_kb = (img_dir / "lights-out-ambient.gif").stat().st_size / 1024
    html = ek.email_document("Lights Out · after hours", build_ambient_body(count, ms, amb_kb),
                             preheader="The night shift at No. 25: one GIF on a soft loop.",
                             masthead=build_ambient_masthead())
    (out / "lights-out-ambient.html").write_text(html, encoding="utf-8")
    print(f"  lights-out-ambient.html {len(html) / 1024:.0f} KB (no card; GIF {amb_kb:.0f} KB, {count} frames)")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
