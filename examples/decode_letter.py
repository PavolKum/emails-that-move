"""
A letter that decodes: the whole email is one GIF. Gold katakana rain falls behind the message, and the
message decodes out of it line by line - each letter scrambles in pink, flashes cream as it locks, then
settles to gold.

The GIF follows the kit's rules (reference/techniques.md, "GIF design rules"):
- Frame 1 is the finished letter, so an Outlook that shows only frame 1 (2013-2019, animations off, VDI)
  still shows the whole message. Animating clients hold it, scramble it back into the rain, decode it again,
  and end on the letter.
- loop=2: three plays, the Microsoft 365 cap; it stops on the last frame, which is the letter again.
- Drawn at 1x by default. The first test (600 x 340) was about 1.1 MB, 4 MB at 2x; bytes grow with the area. The kit's 2x rule costs too much here: rain changes a third
  of the image every frame, so 2x is about 4 MB (--scale 2). Fewer colours, 10 fps or coarser trails save
  only 10-25% (measured 2026-11-01).
- Every frame is written as a delta (unchanged pixels transparent) and read back as a client composes it;
  any pixel that differs from what was drawn stops the build.

The rain is ported from Stack's workbench-fx decode effect (mods/workbench-fx/hooks/fx.ts): the same hash,
streams, glyph mutation and colours, so it looks like the terminal pane.

    python $S/examples/decode_letter.py --out work/decode
    python $S/examples/decode_letter.py --out work/decode --text letter.txt   # your own message, one line per row
    python $S/examples/decode_letter.py --out work/decode --scale 2           # sharp on high-DPI, ~3.6x the bytes
    python $S/scripts/send_outlook.py work/decode/decode_letter.html --send   # to yourself; forward it from Outlook
"""
import argparse
import math
import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emailkit as ek  # noqa: E402

LETTER = """HELLO,

THIS WHOLE EMAIL IS ONE GIF.
EVERY LETTER YOU ARE READING
DECODED OUT OF THE RAIN.

NO JAVASCRIPT. NO VIDEO. JUST FRAMES.
OUTLOOK SHOWS THE FIRST ONE,
SO THE FIRST ONE IS THE LETTER.

- SENT FROM THE RAIN"""

# Signature Cyber ground (the canonical Signature) and decode's colours.
GROUND = 0x0D0D0F
GOLD = 0xFFC21A
GOLD_DEEP = 0xE89B00
PINK = 0xFF2E7E
CREAM = 0xF3EEE3

# The canvas is 1.5x the first test's 600 x 340 on each side, letters the same size, so it holds more text
# (2026-11-01). 900 px is wider than the usual 600-640 email: narrower reading panes scale it down.
WIDTH, HEIGHT = 900, 510  # shown size, px (the height grows if the message needs more rows)
CELL_W, CELL_H = 9, 20    # one character cell at 1x
SCALE = 1              # --scale 2: sharper on high-DPI screens, about 3.6x the bytes
COLOURS = 64           # palette size, one entry kept for transparency
MARGIN_COLS, MARGIN_ROWS = 5, 3
RAIN_DIM = 0.38        # decode dims its rain to 38% behind the quote
TRAIL_STEPS = 5        # trail brightness in steps: a cell changes colour only when it crosses one (bytes)

FRAME_MS = 80          # 12.5 fps
LEAD_MS = 1800         # frame 1, the finished letter, before it scrambles
REWIND_MS = 640        # the letters scramble back into the rain
DECODE_PACE = 1.2      # the decode runs 20% slower than the first test (2026-11-01)
LINE_GAP_MS = round(600 * DECODE_PACE)   # one line starts decoding this long after the one above
LOCK_SPAN_MS = round(900 * DECODE_PACE)  # a line's letters lock over this long, left to right with jitter
LOCK_LEAD_MS = round(150 * DECODE_PACE)  # scramble before a line's first letter locks
FLASH_MS = round(250 * DECODE_PACE)      # cream flash as a letter locks
HOLD_ANIM_MS = 1200    # rain keeps falling over the finished letter ...
HOLD_MS = 3500         # ... then the last frame (the letter again) holds


# ---------------------------------------------------------------- the rain, ported from fx.ts
def mix(a: int, b: int, t: float) -> int:
    k = max(0.0, min(1.0, t))
    out = 0
    for shift in (16, 8, 0):
        x, y = (a >> shift) & 255, (b >> shift) & 255
        out |= round(x + (y - x) * k) << shift
    return out


def _imul(a: int, b: int) -> int:
    return ((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF)) & 0xFFFFFFFF


def hash3(x: int, y: int, z: int = 0) -> float:
    """fx.ts hash(): deterministic noise 0..1 (Math.imul semantics, unsigned shifts)."""
    h = _imul(x * 374761393 + y * 668265263 + z * 2147483647, 1274126177)
    h = _imul(h ^ (h >> 13), 1274126177)
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 4294967296


KANA_FIRST, KANA_COUNT = 0xFF66, 56


def glyph(x: int, y: int, flip: int) -> str:
    g = hash3(x, y, flip)
    return chr(KANA_FIRST + math.floor(g / 0.82 * KANA_COUNT)) if g < 0.82 else chr(0x30 + math.floor((g - 0.82) / 0.18 * 10))


def rain_at(x: int, y: int, rows: int, t: float) -> float:
    best = 0.0
    for s in (0, 1):
        if s == 1 and hash3(x, 8) > 0.3:
            continue  # a second stream in about a third of the columns
        speed = 5 + hash3(x, 1, s) * 13
        length = 4 + math.floor(hash3(x, 2, s) * rows * 0.9)
        period = rows + length + math.floor(hash3(x, 4, s) * rows)
        head = math.floor((t * speed + hash3(x, 3, s) * period * 7) % period)
        d = head - y
        if 0 <= d < length:
            best = max(best, 1.0 if d == 0 else 0.92 * (1 - d / length))
    return best


def rain_color(v: float) -> int:
    if v >= 1:
        return CREAM
    v = math.ceil(v * TRAIL_STEPS) / TRAIL_STEPS * 0.92  # the terminal fades smoothly; a GIF pays per change
    if v > 0.75:
        return mix(GOLD_DEEP, GOLD, (v - 0.75) * 4)
    return mix(GROUND, GOLD_DEEP, (v / 0.75) ** 0.8)


def rain_cell(x: int, y: int, rows: int, t: float):
    v = rain_at(x, y, rows, t)
    if v <= 0.02:
        return None
    flip = math.floor(t * (2 + hash3(x, y, 5) * 6))
    spark = hash3(x, y, math.floor(t * 8)) > 0.997
    return glyph(x, y, flip), mix(GROUND, PINK if spark else rain_color(v), RAIN_DIM)


# ---------------------------------------------------------------- the letter
class Letter:
    def __init__(self, text: str):
        self.lines = text.split("\n")
        width = max(len(line) for line in self.lines)
        self.columns = int(WIDTH // CELL_W)
        if width > self.columns - 2 * MARGIN_COLS:
            raise SystemExit(f"a line is {width} characters; the most that fits is {self.columns - 2 * MARGIN_COLS}")
        self.rows = max(len(self.lines) + 2 * MARGIN_ROWS, HEIGHT // CELL_H)
        self.top = (self.rows - len(self.lines)) // 2  # the letter sits in the middle of the canvas
        # each non-empty line decodes in turn
        self.starts = {}
        for i, line in enumerate(self.lines):
            if line.strip():
                self.starts[i] = len(self.starts) * LINE_GAP_MS
        self.reveal_ms = max(self.starts.values()) + LOCK_LEAD_MS + LOCK_SPAN_MS + FLASH_MS

    def lock_at(self, i: int, k: int) -> float:
        line = self.lines[i]
        return self.starts[i] + LOCK_LEAD_MS + LOCK_SPAN_MS * (k / max(1, len(line) - 1)) * (0.7 + 0.3 * hash3(k, i, 3))

    def cells(self, phase: str, local_ms: float, t: float):
        """{(x, y): (char, colour)} for one frame. phase: 'final' | 'rewind' | 'reveal'."""
        out = {}
        for y in range(self.rows):
            for x in range(self.columns):
                c = rain_cell(x, y, self.rows, t)
                if c:
                    out[(x, y)] = c
        for i, line in enumerate(self.lines):
            if not line.strip():
                continue
            y = self.top + i
            x0 = MARGIN_COLS
            active = phase == "final" or (phase == "rewind" and local_ms < REWIND_MS - FRAME_MS) or (
                phase == "reveal" and local_ms >= self.starts[i])
            if not active:
                continue
            # the line carves its row out of the rain, one cell past each end, so nothing falls between letters
            for x in range(max(0, x0 - 1), min(self.columns, x0 + len(line) + 1)):
                out.pop((x, y), None)
            for k, ch in enumerate(line):
                if ch == " ":
                    continue
                x = x0 + k
                scramble = (glyph(x, y, math.floor(t * 18)), mix(GROUND, PINK, 0.55 + 0.45 * hash3(x, math.floor(t * 12))))
                if phase == "final":
                    out[(x, y)] = (ch, GOLD)
                elif phase == "rewind":
                    unlock = REWIND_MS * 0.7 * hash3(k, i, 9)
                    out[(x, y)] = (ch, GOLD) if local_ms < unlock else scramble
                else:
                    lock = self.lock_at(i, k)
                    if local_ms < lock:
                        out[(x, y)] = scramble
                    else:
                        flash = max(0.0, 1 - (local_ms - lock) / FLASH_MS)
                        out[(x, y)] = (ch, mix(GOLD, CREAM, flash))
        return out


# ---------------------------------------------------------------- drawing
def draw(letter: Letter, cells, scale: int) -> Image.Image:
    font_text = ImageFont.truetype("consolab.ttf", round(CELL_H * 0.75 * scale))
    font_rain = ImageFont.truetype("msgothic.ttc", round(CELL_H * 0.8 * scale))
    w, h = WIDTH * scale, round(letter.rows * CELL_H * scale)
    im = Image.new("RGB", (w, h), f"#{GROUND:06x}")
    d = ImageDraw.Draw(im)
    left = round((WIDTH - letter.columns * CELL_W) / 2 * scale)
    for (x, y), (ch, colour) in cells.items():
        font = font_rain if ord(ch) >= 0xFF00 else font_text
        cx = left + (x + 0.5) * CELL_W * scale
        cy = (y + 0.5) * CELL_H * scale
        d.text((cx, cy), ch, font=font, fill=f"#{colour:06x}", anchor="mm")
    return im


def save_delta_gif(images: list[Image.Image], durations: list[int], path: pathlib.Path, loop: int):
    """One shared palette, and every pixel a frame leaves unchanged written as transparent. Rain changes a
    small share of the pixels per frame, so the long transparent runs compress far better than full frames
    (the kit's _save_gif writes full frames: 5.3 MB here at 2x). Checked by decode_letter's read-back."""
    picks = [images[0]] + images[1::max(1, len(images) // 6)]
    w, h = images[0].size
    sample = Image.new("RGB", (w, h * len(picks)))
    for i, im in enumerate(picks):
        sample.paste(im, (0, h * i))
    palette = sample.quantize(colors=COLOURS - 1, method=Image.Quantize.MEDIANCUT)
    pal = palette.getpalette()[: 3 * (COLOURS - 1)]
    ground = palette.getpixel((0, 0))
    pal[3 * ground:3 * ground + 3] = [(GROUND >> 16) & 255, (GROUND >> 8) & 255, GROUND & 255]  # median cut drifts it
    clear = COLOURS - 1
    # Quantize against the real colours only: the spare entries repeat the ground colour, and anything that
    # lands on one is folded back to the ground's own index. (A real magenta entry here caught pink pixels.)
    palette.putpalette(pal + pal[3 * ground:3 * ground + 3] * (256 - clear))
    indexed = []
    for im in images:
        arr = np.array(im.quantize(palette=palette, dither=Image.Dither.NONE))
        arr[arr >= clear] = ground
        indexed.append(arr)
    pal += [255, 0, 255]  # the transparent entry: never drawn, so it never shows
    frames = []
    for i, arr in enumerate(indexed):
        out = arr.copy()
        if i:
            out[arr == indexed[i - 1]] = clear
        fr = Image.fromarray(out, mode="P")
        fr.putpalette(pal + [0, 0, 0] * (256 - COLOURS))
        fr.info["transparency"] = clear  # Pillow reads it per frame; set only on save, frames 2+ lose it
        frames.append(fr)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=loop, disposal=1,
                   transparency=clear, optimize=False)
    return indexed, pal


def build(text: str, out: pathlib.Path, scale: int = SCALE) -> pathlib.Path:
    letter = Letter(text)
    reveal_frames = math.ceil(letter.reveal_ms / FRAME_MS)
    rewind_frames = REWIND_MS // FRAME_MS
    hold_frames = HOLD_ANIM_MS // FRAME_MS
    t_end = (rewind_frames + reveal_frames + hold_frames) * FRAME_MS / 1000
    images, durations = [], []
    # frame 1: the finished letter, rain where it will be on the last frame, so the loop seam is clean
    images.append(draw(letter, letter.cells("final", 0, t_end), scale))
    durations.append(LEAD_MS)
    n = 0
    for f in range(rewind_frames):
        images.append(draw(letter, letter.cells("rewind", f * FRAME_MS, n * FRAME_MS / 1000), scale))
        durations.append(FRAME_MS)
        n += 1
    for f in range(reveal_frames):
        images.append(draw(letter, letter.cells("reveal", f * FRAME_MS, n * FRAME_MS / 1000), scale))
        durations.append(FRAME_MS)
        n += 1
    for f in range(hold_frames):
        images.append(draw(letter, letter.cells("final", 0, n * FRAME_MS / 1000), scale))
        durations.append(FRAME_MS)
        n += 1
    images.append(images[0])  # the letter again, held; also where Microsoft 365 stops after three plays
    durations.append(HOLD_MS)

    out.mkdir(parents=True, exist_ok=True)
    gif = out / "decode_letter.gif"
    indexed, pal = save_delta_gif(images, durations, gif, loop=2)
    # read the GIF back as a client composes it and compare with what was drawn: a broken delta shows here
    with Image.open(gif) as back:
        if back.n_frames != len(images):
            raise SystemExit(f"read-back: {back.n_frames} frames, drew {len(images)}")
        colours = np.asarray(pal, dtype=np.int16).reshape(-1, 3)
        for i in range(back.n_frames):
            back.seek(i)
            got = np.asarray(back.convert("RGB"), dtype=np.int16)
            bad = np.argwhere(np.abs(got - colours[indexed[i]]).max(axis=2) > 0)
            if len(bad):
                y, x = bad[0]
                raise SystemExit(f"read-back: frame {i} has {len(bad)} wrong pixels, first at ({x}, {y}): "
                                 f"shows {tuple(got[y, x])}, drawn {tuple(colours[indexed[i]][y, x])}")

    height = round(letter.rows * CELL_H)
    alt = " ".join(line.strip() for line in letter.lines if line.strip())
    ek.use_theme("signature-dark")
    rows = ek.row(ek.img_tag(gif.name, WIDTH, height, alt=alt, fluid=True), pad="0")
    html = ek.email_document("A letter that decodes", rows, preheader=alt[:90], width=WIDTH)
    page = out / "decode_letter.html"
    page.write_text(html, encoding="utf-8")
    kb = gif.stat().st_size / 1024
    print(f"{gif}  {WIDTH}x{height} shown ({WIDTH * scale}x{height * scale} drawn), {len(images)} frames, "
          f"{sum(durations) / 1000:.1f} s a play, {kb:,.0f} KB")
    print(page)
    return page


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("work/decode"))
    parser.add_argument("--text", type=pathlib.Path, help="a text file: the message, one line per row")
    parser.add_argument("--scale", type=int, default=SCALE, choices=(1, 2))
    args = parser.parse_args()
    text = args.text.read_text(encoding="utf-8").strip("\n") if args.text else LETTER
    build(text, args.out, args.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
