"""
emailkit - building blocks for HTML email that survives every Outlook renderer.

    classic Outlook (Word engine) -> mso() branch:     VML shapes, tables, GIFs (M365 animates them)
    new Outlook / OWA / mobile    -> not_mso() branch:  HTML + PNG/GIF
    Actionable Messages           -> Adaptive Card JSON in <head> (card_* helpers)

Typical email script:

    import emailkit as ek
    ek.use_theme("mybrand")                    # assets/themes/local/mybrand.json, then assets/themes/mybrand.json
    chart = ek.LineChart(series={"Office": [...], "Retail": [...]}, x_labels={0: "Oct", 11: "Sep"},
                         y_ticks=[95, 100, 105])
    rows = ek.section_title("Market", "Price index") + ek.row(ek.line_chart_block(chart, img_dir, "price"))
    html = ek.email_document("Weekly pulse", ek.header_band(...) + rows, card=ek.adaptive_card(body=[...]))

Every chart block takes `classic=` and `modern=` so you choose, per chart, what each renderer gets:
VML (crisp, static) or GIF (animated in M365 desktop, frame 1 elsewhere) for classic; GIF or PNG for modern.
"""
from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field
from html import escape
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
THEME_DIRS = [SKILL_DIR / "assets" / "themes" / "local", SKILL_DIR / "assets" / "themes"]
VML_NS = 'xmlns:v="urn:schemas-microsoft-com:vml"'
STATUS_ICONS = {"critical": ("&#10006;", "\u2716", "Critical"), "serious": ("&#9650;", "\u25b2", "Serious"),
                "warning": ("&#9679;", "\u25cf", "Watch")}

_theme: SimpleNamespace | None = None


# =================================================================== theme
def use_theme(name_or_path: str = "default") -> SimpleNamespace:
    """Load a theme by name (local/ wins over shared) or by path, and make it active."""
    global _theme
    candidates = [pathlib.Path(name_or_path)] + [d / f"{name_or_path}.json" for d in THEME_DIRS]
    for path in candidates:
        if path.suffix == ".json" and path.exists():
            _theme = json.loads(path.read_text(encoding="utf-8"), object_hook=lambda d: SimpleNamespace(**d))
            return _theme
    raise FileNotFoundError(f"theme '{name_or_path}' not found in {[str(d) for d in THEME_DIRS]}")


def theme() -> SimpleNamespace:
    return _theme or use_theme("default")


def _font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    name = getattr(theme().raster_fonts, weight, None) or theme().raster_fonts.regular
    for path in (pathlib.Path(name), pathlib.Path("C:/Windows/Fonts") / name):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _hex(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _luminance(h: str) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _hex(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(fill: str) -> str:
    """Primary ink or white, whichever reads better on `fill`."""
    return "#ffffff" if contrast("#ffffff", fill) >= contrast(theme().text.primary, fill) else theme().text.primary


# =================================================================== HTML primitives
def mso(html: str) -> str:
    """Only classic Outlook (Word engine) renders this."""
    return f"<!--[if mso]>{html}<![endif]-->"


def not_mso(html: str) -> str:
    """Everything except classic Outlook renders this."""
    return f"<!--[if !mso]><!-->{html}<!--<![endif]-->"


def lh(px: int) -> str:
    """Line height that Word respects."""
    return f"mso-line-height-rule:exactly;line-height:{px}px;"


def row(inner: str, pad: str = "0 24px") -> str:
    return f'<tr><td style="padding:{pad};">{inner}</td></tr>'


def spacer(h: int) -> str:
    return f'<tr><td height="{h}" style="height:{h}px;font-size:{h}px;{lh(h)}">&nbsp;</td></tr>'


def section_title(eyebrow: str, title: str) -> str:
    t = theme()
    return (f'<tr><td style="padding:0 24px;font-family:{t.font};">'
            f'<p style="margin:0;font-size:11px;letter-spacing:1px;text-transform:uppercase;color:{t.text.muted};{lh(16)}">'
            f'{eyebrow}</p><p class="display" style="margin:2px 0 0;font-family:{t.font_display};font-size:18px;'
            f'font-weight:bold;color:{t.text.primary};{lh(24)}">{title}</p></td></tr>')


def delta(value: float, unit: str, good_when_up: bool = True, digits: int = 1, suffix: str = "") -> str:
    """Arrow + magnitude, coloured by whether the move is good. Never colour alone: the arrow carries direction."""
    t = theme()
    up = value >= 0
    color = t.text.good if up == good_when_up else t.text.bad
    tail = f' <span style="color:{t.text.muted};">{suffix}</span>' if suffix else ""
    return f'<span style="color:{color};">{"&#9650;" if up else "&#9660;"} {abs(value):.{digits}f}{unit}</span>{tail}'


def kpi_tile(chart_html: str, value: str, label: str, delta_html: str = "", width: int = 197) -> str:
    """A <td>: small chart on the left, label / big value / delta on the right."""
    t = theme()
    return (f'<td width="{width}" valign="top" style="width:{width}px;padding:0 8px;font-family:{t.font};">'
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td valign="middle">{chart_html}</td>'
            f'<td valign="middle" style="padding-left:10px;font-family:{t.font};">'
            f'<p style="margin:0;font-size:12px;color:{t.text.secondary};{lh(16)}">{label}</p>'
            f'<p style="margin:2px 0 0;font-size:22px;font-weight:bold;color:{t.text.primary};{lh(28)}">{value}</p>'
            f'<p style="margin:0;font-size:12px;{lh(16)}">{delta_html}</p></td></tr></table></td>')


def stat_tile(value: str, label: str, delta_html: str = "", width: int = 197) -> str:
    """A <td>: a hero number with no chart. Not everything needs a chart."""
    t = theme()
    return (f'<td width="{width}" valign="top" style="width:{width}px;padding:0 8px;font-family:{t.font};">'
            f'<p style="margin:0;font-size:12px;color:{t.text.secondary};{lh(16)}">{label}</p>'
            f'<p style="margin:6px 0 0;font-size:34px;font-weight:bold;color:{t.text.primary};{lh(40)}">{value}</p>'
            f'<p style="margin:2px 0 0;font-size:12px;{lh(16)}">{delta_html}</p></td>')


def tiles_row(tiles: list[str], width: int = 608) -> str:
    return (f'<tr><td style="padding:0 16px;"><table role="presentation" width="{width}" cellpadding="0" '
            f'cellspacing="0" border="0"><tr>{"".join(tiles)}</tr></table></td></tr>')


def vml_button(href: str, label: str, width: int = 236, fill: str | None = None, text: str | None = None) -> str:
    t = theme()
    return (f'<v:roundrect {VML_NS} href="{href}" style="height:44px;v-text-anchor:middle;width:{width}px;" '
            f'arcsize="14%" fillcolor="{fill or t.chrome.accent}" stroke="f"><center style="color:{text or t.chrome.on_accent};'
            f'font-family:{t.font_mso};font-size:15px;font-weight:bold;">{label}</center></v:roundrect>')


def button(href: str, label: str, width: int = 236) -> str:
    """Bulletproof button: VML roundrect for Word, styled link for everyone else."""
    t = theme()
    return mso(vml_button(href, label, width)) + not_mso(
        f'<a href="{href}" style="display:inline-block;background:{t.chrome.accent};color:{t.chrome.on_accent};'
        f'font-family:{t.font};font-size:15px;font-weight:bold;text-decoration:none;padding:12px 22px;'
        f'border-radius:6px;">{label}</a>')


def header_band(eyebrow: str, meta: str, headline: str, glyph_html: str = "", width: int = 592) -> str:
    t = theme()
    c = t.chrome
    return (f'<tr><td bgcolor="{c.ink}" style="background:{c.ink};padding:22px 24px 20px;">'
            f'<table role="presentation" width="{width}" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td valign="top" style="font-family:{t.font};">'
            f'<p style="margin:0;font-size:11px;letter-spacing:2px;font-weight:bold;color:{c.accent};{lh(16)}">{eyebrow}</p>'
            f'<p style="margin:4px 0 0;font-size:12px;color:{c.on_ink_muted};{lh(16)}">{meta}</p></td>'
            f'<td align="right" valign="middle">{glyph_html}</td></tr></table>'
            f'<p class="display" style="margin:16px 0 0;font-family:{t.font_display};font-size:23px;font-weight:bold;'
            f'color:{c.on_ink};{lh(30)}">{escape(headline)}</p></td></tr>'
            f'<tr><td height="5" bgcolor="{c.accent}" style="height:5px;background:{c.accent};font-size:5px;{lh(5)}">'
            f'&nbsp;</td></tr>')


def footer_band(html: str) -> str:
    t = theme()
    return (f'<tr><td bgcolor="{t.chrome.ink}" style="background:{t.chrome.ink};padding:16px 24px;font-family:{t.font};'
            f'font-size:11px;color:{t.chrome.on_ink_muted};{lh(16)}">{html}</td></tr>')


def masthead(eyebrow: str, headline: str, intro: str, notice: str = "", numeral: str = "", width: int = 640) -> str:
    """Full-bleed top band in the theme's chrome.masthead colour, closed by a 3 px ink rule: a poster-style
    header (gold band, serif headline, mono labels). `headline` is HTML (<br> for the break). `numeral` is a big
    decorative number in chrome.pop: display size only. Pass the result to email_document(masthead=...)."""
    t = theme()
    c = t.chrome
    mono = "font-family:Consolas,'Courier New',monospace;"
    # The numeral centres on the headline block (level with the gap between its lines), clear of the intro below.
    number = (f'<td class="mono" align="right" valign="middle" aria-hidden="true" style="{mono}font-size:72px;'
              f'font-weight:bold;color:{c.pop};{lh(72)}">{numeral}</td>') if numeral else ""
    notice_html = (f'<p class="mono" style="margin:14px 0 0;{mono}font-size:12px;color:{c.on_masthead};{lh(18)}">'
                   f'{notice}</p>') if notice else ""
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{c.masthead}" '
            f'style="background:{c.masthead};"><tr><td align="center" bgcolor="{c.masthead}" style="background:{c.masthead};">'
            f'<table role="presentation" class="wrap" width="{width}" cellpadding="0" cellspacing="0" border="0" '
            f'style="width:{width}px;"><tr><td style="padding:28px 24px 30px;font-family:{t.font};">'
            f'<p class="mono" style="margin:0;{mono}font-size:12px;letter-spacing:1.8px;color:{c.on_masthead};{lh(18)}">'
            f'{eyebrow}</p>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td valign="bottom">'
            f'<p class="display" style="margin:16px 0 14px;font-family:{t.font_display};font-size:56px;font-weight:normal;'
            f'letter-spacing:-2.5px;color:{c.on_masthead};{lh(56)}">{headline}</p></td>{number}</tr></table>'
            f'<p style="margin:0;font-family:{t.font};font-size:18px;color:{c.on_masthead};{lh(27)}">{intro}</p>'
            f'{notice_html}</td></tr></table></td></tr>'
            f'<tr><td height="3" bgcolor="{c.ink}" style="height:3px;background:{c.ink};font-size:3px;{lh(3)}">&nbsp;</td>'
            f'</tr></table>')


def email_document(title: str, rows: str, preheader: str = "", card: dict | None = None, width: int = 640,
                   masthead: str = "") -> str:
    """Full HTML document: VML namespaces, Word DPI fix, font override for Word, optional Adaptive Card,
    optional full-bleed masthead band above the card (see masthead())."""
    t = theme()
    card_script = ""
    if card:
        payload = json.dumps(card, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        card_script = f'<script type="application/adaptivecard+json">{payload}</script>\n'
    return f"""<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<title>{escape(title)}</title>
<!--[if gte mso 9]><xml><o:OfficeDocumentSettings><o:AllowPNG/><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
<!--[if mso]><style>body,table,td,p,a,span,b,center{{font-family:{t.font_mso} !important;}} .display{{font-family:{t.font_display_mso} !important;}} .mono{{font-family:Consolas,'Courier New',monospace !important;}}</style><![endif]-->
<style>
  body {{ margin:0; padding:0; }}
  table {{ border-collapse:collapse; }}
  img {{ border:0; display:block; }}
  @media (max-width:{width}px) {{ .wrap {{ width:100% !important; }} }}
</style>
{card_script}</head>
<body style="margin:0;padding:0;background:{t.chrome.page};">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{escape(preheader)}</div>
{masthead}<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{t.chrome.page}" style="background:{t.chrome.page};">
<tr><td align="center" style="padding:{"0 0 24px" if masthead else "24px 0"};">
<table role="presentation" class="wrap" width="{width}" cellpadding="0" cellspacing="0" border="0" bgcolor="{t.chrome.card}" style="width:{width}px;background:{t.chrome.card};">
<tr><td bgcolor="{t.chrome.card}" style="background:{t.chrome.card};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{t.chrome.card}" style="width:100%;background:{t.chrome.card};">
{rows}
</table>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def img_tag(src: str, width: int, height: int, alt: str, fluid: bool = False) -> str:
    style = "display:block;border:0;"
    if fluid:
        style += f"width:100%;max-width:{width}px;height:auto;"
    return f'<img src="{src}" width="{width}" height="{height}" alt="{escape(alt)}" style="{style}">'


# =================================================================== animation (GIF)
@dataclass
class Anim:
    """GIF timing. Defaults are tuned for Outlook M365, which loops a GIF at most 3 times then shows Play.

    first_frame="final": frame 1 is the finished chart, so clients that don't animate (Outlook 2013-2019,
    Windows animations off, VDI) still show the data. Animating clients see it, crossfade back, then draw.
    """
    frames: int = 26
    frame_ms: int = 45
    hold_ms: int = 3500
    lead_ms: int = 1400
    rewind_frames: int = 4
    loop: int | None = 2          # NETSCAPE loop count; None = play once; 0 = forever (avoid)
    first_frame: str = "final"    # "final" | "blank"
    scale: int = 2                # retina


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def _save_gif(images: list[Image.Image], durations: list[int], path: pathlib.Path, loop: int | None, bg: str):
    # One shared palette, sampled from the final frame plus a few others so crossfade tints survive
    # (a final-frame-only palette turns the fade grey).
    picks = [images[-1]] + [images[i] for i in range(1, len(images) - 1, max(1, len(images) // 4))][:3]
    w, h = images[-1].size
    sample = Image.new("RGB", (w, h * len(picks)))
    for i, im in enumerate(picks):
        sample.paste(im, (0, h * i))
    palette = sample.quantize(colors=160, method=Image.Quantize.MEDIANCUT)
    frames = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
    # Median-cut drifts the background (e.g. white -> #fcfcfc), which shows as a box on the card. Snap it back.
    for fr in frames:
        pal = fr.getpalette()
        idx = fr.getpixel((0, 0))
        pal[3 * idx:3 * idx + 3] = list(_hex(bg))
        fr.putpalette(pal)
    kwargs = dict(save_all=True, append_images=frames[1:], duration=durations, optimize=True, disposal=1)
    if loop is not None:
        kwargs["loop"] = loop
    frames[0].save(path, **kwargs)


def animate(path: pathlib.Path, draw, anim: Anim | None = None):
    """Render draw(progress 0..1) -> RGB image into an animated GIF with the Anim timing rules."""
    anim = anim or Anim()
    steps = [draw(ease_out_cubic(k / anim.frames)) for k in range(anim.frames + 1)]
    images = list(steps)
    durations = [anim.frame_ms] * anim.frames + [anim.hold_ms]
    if anim.first_frame == "final":
        final, start = steps[-1], steps[0]
        fades = [Image.blend(final, start, (i + 1) / (anim.rewind_frames + 1)) for i in range(anim.rewind_frames)]
        images = [final] + fades + steps
        durations = [anim.lead_ms] + [40] * len(fades) + durations
    _save_gif(images, durations, pathlib.Path(path), anim.loop, theme().chrome.card)


# =================================================================== donut
def vml_donut(value: float, size: int = 76, color: str | None = None, thickness: int = 9) -> str:
    t = theme()
    units = 1000 / size
    inset = round(thickness / 2 * units)
    dia = 1000 - 2 * inset
    stroke = f"{thickness * 0.75:.2f}pt"
    return (f'<v:group {VML_NS} coordsize="1000,1000" coordorigin="0,0" style="width:{size}px;height:{size}px;">'
            f'<v:oval style="position:absolute;left:{inset};top:{inset};width:{dia};height:{dia};" filled="f" '
            f'strokecolor="{t.chart.track}" strokeweight="{stroke}"/>'
            f'<v:arc style="position:absolute;left:{inset};top:{inset};width:{dia};height:{dia};" startangle="0" '
            f'endangle="{360 * value / 100:.1f}" filled="f" strokecolor="{color or t.chart.single}" '
            f'strokeweight="{stroke}"><v:stroke endcap="round"/></v:arc></v:group>')


def draw_donut(value: float, size: int = 76, color: str | None = None, thickness: int = 9,
               progress: float = 1.0, scale: int = 2) -> Image.Image:
    t = theme()
    ss = 4 * scale
    s, th = size * ss, thickness * ss
    img = Image.new("RGB", (s, s), t.chrome.card)
    d = ImageDraw.Draw(img)
    box = [0, 0, s - 1, s - 1]
    d.ellipse(box, outline=t.chart.track, width=th)
    sweep = 360 * value / 100 * progress
    col = color or t.chart.single
    if sweep > 0.5:
        end = -90 + sweep
        d.arc(box, start=-90, end=end, fill=col, width=th)
        r, c = (s - th) / 2, s / 2
        for ang in (-90, end):  # round caps
            x, y = c + r * math.cos(math.radians(ang)), c + r * math.sin(math.radians(ang))
            d.ellipse([x - th / 2, y - th / 2, x + th / 2, y + th / 2], fill=col)
    return img.resize((size * scale, size * scale), Image.LANCZOS)


def donut_block(value: float, img_dir: pathlib.Path, name: str, alt: str, size: int = 76,
                classic: str = "vml", modern: str = "png", anim: Anim | None = None, rel: str = "img/") -> str:
    """classic: vml | gif | png   modern: png | gif"""
    files = {}
    if "png" in (classic, modern):
        draw_donut(value, size).save(img_dir / f"{name}.png")
        files["png"] = f"{rel}{name}.png"
    if "gif" in (classic, modern):
        animate(img_dir / f"{name}.gif", lambda p: draw_donut(value, size, progress=p), anim)
        files["gif"] = f"{rel}{name}.gif"
    classic_html = vml_donut(value, size) if classic == "vml" else img_tag(files[classic], size, size, alt)
    return mso(classic_html) + not_mso(img_tag(files[modern], size, size, alt))


# =================================================================== line chart
@dataclass
class LineChart:
    series: dict[str, list[float]]
    x_labels: dict[int, str]
    y_ticks: list[float]
    y_min: float | None = None
    y_max: float | None = None
    baseline: float | None = None      # emphasised gridline (e.g. 100 on an index)
    width: int = 592
    height: int = 210
    pad_l: int = 34
    pad_r: int = 104                   # room for direct end labels
    pad_t: int = 12
    pad_b: int = 28
    value_fmt: str = "{:.1f}"
    colors: list[str] | None = None    # defaults to theme series, in insertion order (colour follows entity)

    def __post_init__(self):
        self.y_min = self.y_min if self.y_min is not None else min(self.y_ticks)
        self.y_max = self.y_max if self.y_max is not None else max(self.y_ticks)
        names = list(self.series)
        palette = self.colors or theme().chart.series
        if len(names) > len(palette):
            raise ValueError(f"{len(names)} series but only {len(palette)} validated colours - fold into 'Other' or facet")
        self.color = dict(zip(names, palette))
        self.n = len(next(iter(self.series.values())))

    def x(self, i: float) -> float:
        return self.pad_l + i * (self.width - self.pad_l - self.pad_r) / (self.n - 1)

    def y(self, v: float) -> float:
        return self.pad_t + (self.y_max - v) / (self.y_max - self.y_min) * (self.height - self.pad_t - self.pad_b)

    def end_label_y(self) -> dict[str, float]:
        """End-label positions nudged at least 16px apart so they never collide."""
        out, last = {}, -1e9
        for name in sorted(self.series, key=lambda s: self.y(self.series[s][-1])):
            last = max(self.y(self.series[name][-1]), last + 16)
            out[name] = last
        return out


def _vml_text(left, top, width, height, html: str) -> str:
    return (f'<v:rect style="position:absolute;left:{left:.0f};top:{top:.0f};width:{width:.0f};height:{height:.0f};" '
            f'filled="f" stroked="f"><v:textbox inset="0,0,0,0">{html}</v:textbox></v:rect>')


def vml_line_chart(c: LineChart) -> str:
    """Native vector line chart for Word: gridlines, ticks, series paths, end dots, direct labels."""
    t = theme()
    W, H = c.width, c.height
    tick = f"margin:0;font-family:{t.font_mso};font-size:10px;color:{t.text.muted};{lh(14)}"
    out = [f'<v:group {VML_NS} coordsize="{W},{H}" coordorigin="0,0" style="width:{W}px;height:{H}px;">']
    for tv in c.y_ticks:
        y = round(c.y(tv))
        col = t.chart.axis if tv == c.baseline else t.chart.grid
        out.append(f'<v:line style="position:absolute;" from="{c.pad_l},{y}" to="{W - c.pad_r},{y}" '
                   f'strokecolor="{col}" strokeweight="0.75pt"/>')
        out.append(_vml_text(0, y - 7, c.pad_l - 6, 14, f'<p style="{tick}text-align:right;">{tv:g}</p>'))
    for i, label in c.x_labels.items():
        out.append(_vml_text(c.x(i) - 30, H - c.pad_b + 7, 60, 14, f'<p style="{tick}text-align:center;">{label}</p>'))
    for name, vals in c.series.items():
        pts = [(round(c.x(i)), round(c.y(v))) for i, v in enumerate(vals)]  # VML paths need integers
        path = f"m {pts[0][0]},{pts[0][1]} l " + " ".join(f"{x},{y}" for x, y in pts[1:]) + " e"
        out.append(f'<v:shape style="position:absolute;left:0;top:0;width:{W};height:{H};" coordsize="{W},{H}" '
                   f'filled="f" stroked="t" strokecolor="{c.color[name]}" strokeweight="1.5pt" path="{path}">'
                   f'<v:stroke joinstyle="round" endcap="round"/></v:shape>')
        ex, ey = pts[-1]
        out.append(f'<v:oval style="position:absolute;left:{ex - 5};top:{ey - 5};width:10;height:10;" '
                   f'fillcolor="{c.color[name]}" strokecolor="{t.chrome.card}" strokeweight="1.5pt"/>')
    for name, y in c.end_label_y().items():
        out.append(_vml_text(c.x(c.n - 1) + 12, y - 8, c.pad_r - 12, 16,
                             f'<p style="margin:0;font-family:{t.font_mso};font-size:11px;color:{t.text.secondary};{lh(16)}">'
                             f'<b style="color:{t.text.primary};">{c.value_fmt.format(c.series[name][-1])}</b> {name}</p>'))
    out.append("</v:group>")
    return "".join(out)


def draw_line_chart(c: LineChart, progress: float = 1.0, scale: int = 2) -> Image.Image:
    """Raster frame. progress < 1 draws each series up to that fraction of the x range."""
    t = theme()
    s = scale
    img = Image.new("RGB", (c.width * s, c.height * s), t.chrome.card)
    d = ImageDraw.Draw(img)
    f_tick, f_val, f_name = _font(10 * s), _font(11 * s, "semibold"), _font(11 * s)
    for tv in c.y_ticks:
        y = c.y(tv) * s
        d.line([(c.pad_l * s, y), ((c.width - c.pad_r) * s, y)], fill=t.chart.axis if tv == c.baseline else t.chart.grid,
               width=s)
        d.text(((c.pad_l - 6) * s, y), f"{tv:g}", font=f_tick, fill=t.text.muted, anchor="rm")
    for i, label in c.x_labels.items():
        d.text((c.x(i) * s, (c.height - c.pad_b + 14) * s), label, font=f_tick, fill=t.text.muted, anchor="mm")
    reach = (c.n - 1) * progress
    for name, vals in c.series.items():
        whole = int(reach)
        pts = [(c.x(i) * s, c.y(vals[i]) * s) for i in range(whole + 1)]
        frac = reach - whole
        if frac > 1e-6 and whole + 1 < c.n:
            v = vals[whole] + (vals[whole + 1] - vals[whole]) * frac
            pts.append((c.x(whole + frac) * s, c.y(v) * s))
        if len(pts) > 1:
            d.line(pts, fill=c.color[name], width=2 * s, joint="curve")
        hx, hy = pts[-1]
        r = 4 * s
        d.ellipse([hx - r - s, hy - r - s, hx + r + s, hy + r + s], fill=t.chrome.card)
        d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=c.color[name])
    if progress >= 0.999:  # direct labels arrive with the finished lines
        for name, y in c.end_label_y().items():
            x = (c.x(c.n - 1) + 12) * s
            val = c.value_fmt.format(c.series[name][-1])
            d.text((x, y * s), val, font=f_val, fill=t.text.primary, anchor="lm")
            d.text((x + d.textlength(val + " ", font=f_val), y * s), name, font=f_name, fill=t.text.secondary,
                   anchor="lm")
    return img


def legend(names_colors: dict[str, str]) -> str:
    t = theme()
    cells = "".join(
        f'<td width="12" height="12" bgcolor="{col}" style="width:12px;height:12px;background:{col};font-size:1px;'
        f'line-height:1px;">&nbsp;</td><td style="font-family:{t.font};font-size:12px;color:{t.text.secondary};'
        f'padding:0 14px 0 6px;">{escape(n)}</td>' for n, col in names_colors.items())
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>{cells}</tr></table>'


def line_chart_block(c: LineChart, img_dir: pathlib.Path, name: str, alt: str = "", classic: str = "vml",
                     modern: str = "gif", anim: Anim | None = None, rel: str = "img/") -> str:
    """Legend + chart. classic: vml | gif | png   modern: gif | png"""
    alt = alt or "; ".join(f"{n} {c.value_fmt.format(v[-1])}" for n, v in c.series.items())
    files = {}
    if "gif" in (classic, modern):
        animate(img_dir / f"{name}.gif", lambda p: draw_line_chart(c, p), anim)
        files["gif"] = f"{rel}{name}.gif"
    if "png" in (classic, modern):
        draw_line_chart(c).save(img_dir / f"{name}.png")
        files["png"] = f"{rel}{name}.png"
    classic_html = vml_line_chart(c) if classic == "vml" else img_tag(files[classic], c.width, c.height, alt)
    chart = mso(classic_html) + not_mso(img_tag(files[modern], c.width, c.height, alt, fluid=True))
    head = legend(c.color) + '<div style="height:8px;line-height:8px;font-size:8px;">&nbsp;</div>' if len(c.series) > 1 else ""
    return head + chart


# =================================================================== bar chart (horizontal)
@dataclass
class BarChart:
    items: list[tuple[str, float]]
    max_value: float | None = None
    width: int = 592
    row_h: int = 30
    bar_h: int = 14
    label_w: int = 130
    value_w: int = 64
    value_fmt: str = "{:.1f}%"
    color: str | None = None
    highlight: dict[str, str] = field(default_factory=dict)  # label -> colour, for the one bar that matters

    def __post_init__(self):
        self.max_value = self.max_value or max(v for _, v in self.items) * 1.05
        self.height = self.row_h * len(self.items) + 6

    def bar_color(self, label: str) -> str:
        return self.highlight.get(label) or self.color or theme().chart.single

    def bar_px(self, v: float) -> float:
        return (self.width - self.label_w - self.value_w) * v / self.max_value


def draw_bar_chart(c: BarChart, progress: float = 1.0, scale: int = 2) -> Image.Image:
    """Bars grow from the baseline and the value labels count up with them."""
    t = theme()
    s = scale
    img = Image.new("RGB", (c.width * s, c.height * s), t.chrome.card)
    d = ImageDraw.Draw(img)
    f_lab, f_val = _font(12 * s), _font(12 * s, "semibold")
    x0 = c.label_w * s
    d.line([(x0, 0), (x0, c.height * s)], fill=t.chart.axis, width=s)
    for i, (label, v) in enumerate(c.items):
        cy = (i * c.row_h + c.row_h / 2 + 3) * s
        d.text(((c.label_w - 10) * s, cy), label, font=f_lab, fill=t.text.primary, anchor="rm")
        w = c.bar_px(v * progress) * s
        if w >= 1:
            r = min(4 * s, w / 2)
            box = [x0, cy - c.bar_h * s / 2, x0 + w, cy + c.bar_h * s / 2]
            if w < 2 * r + 2:  # early grow frames: too short to round, and Pillow 10 raises
                d.rectangle(box, fill=c.bar_color(label))
            else:
                try:  # rounded data-end only; corners= needs Pillow >= 9.5
                    d.rounded_rectangle(box, radius=r, fill=c.bar_color(label), corners=(False, True, True, False))
                except TypeError:
                    d.rounded_rectangle(box, radius=r, fill=c.bar_color(label))
        d.text((x0 + w + 8 * s, cy), c.value_fmt.format(v * progress), font=f_val, fill=t.text.primary, anchor="lm")
    return img


def html_bar_chart(c: BarChart) -> str:
    """Table-cell bars: crisp in every client, selectable text, no images."""
    t = theme()
    rows = []
    track_w = c.width - c.label_w - c.value_w
    for label, v in c.items:
        w = max(1, round(c.bar_px(v)))
        rest = track_w - w
        rest_cell = (f'<td width="{rest}" style="width:{rest}px;font-size:1px;line-height:1px;">&nbsp;</td>'
                     if rest > 0 else "")
        rows.append(
            f'<tr><td width="{c.label_w}" height="{c.row_h}" align="right" style="width:{c.label_w}px;height:{c.row_h}px;'
            f'padding-right:10px;font-family:{t.font};font-size:12px;color:{t.text.primary};">{escape(label)}</td>'
            f'<td width="{track_w}" style="width:{track_w}px;border-left:1px solid {t.chart.axis};">'
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="{w}" height="{c.bar_h}" bgcolor="{c.bar_color(label)}" style="width:{w}px;height:{c.bar_h}px;'
            f'background:{c.bar_color(label)};font-size:1px;line-height:1px;">&nbsp;</td>'
            f'<td style="padding-left:8px;font-family:{t.font};font-size:12px;font-weight:bold;color:{t.text.primary};'
            f'white-space:nowrap;">{c.value_fmt.format(v)}</td>{rest_cell}</tr></table></td></tr>')
    return (f'<table role="presentation" width="{c.width}" cellpadding="0" cellspacing="0" border="0" '
            f'style="width:{c.width}px;">{"".join(rows)}</table>')


def bar_chart_block(c: BarChart, img_dir: pathlib.Path, name: str, alt: str = "", classic: str = "table",
                    modern: str = "gif", anim: Anim | None = None, rel: str = "img/") -> str:
    """classic: table | gif   modern: gif | table"""
    alt = alt or "; ".join(f"{label} {c.value_fmt.format(v)}" for label, v in c.items)
    src = f"{rel}{name}.gif"
    if "gif" in (classic, modern):
        animate(img_dir / f"{name}.gif", lambda p: draw_bar_chart(c, p), anim)
    pick = {"table": html_bar_chart(c), "gif": img_tag(src, c.width, c.height, alt, fluid=True)}
    return mso(pick[classic]) + not_mso(pick[modern])


# =================================================================== heatmap + text marks
def heatmap_table(rows: list[tuple[str, str, list[float]]], col_labels: list[str], thresholds: list[float],
                  legend_title: str = "", unit: str = "%", label_w: int = 138, cell_w: int = 50, cell_h: int = 26) -> str:
    """Table-cell heatmap on the theme's sequential ramp. thresholds[i] is the lower bound of ramp step i.
    Word ignores cellspacing, so a card-coloured 2px border makes the gaps."""
    t = theme()
    ramp = t.chart.sequential
    if len(thresholds) != len(ramp):
        raise ValueError(f"need {len(ramp)} thresholds for the {len(ramp)}-step ramp")
    gap = f"border:2px solid {t.chrome.card};"
    cell = f"font-family:{t.font};font-size:11px;{lh(14)}text-align:center;"

    def step(v):
        idx = None
        for i, lo in enumerate(thresholds):
            if v >= lo:
                idx = i
        return idx

    out = [f'<tr><td width="{label_w}" style="width:{label_w}px;"></td>' + "".join(
        f'<td width="{cell_w}" style="width:{cell_w}px;{cell}color:{t.text.muted};padding-bottom:4px;">{q}</td>'
        for q in col_labels) + "</tr>"]
    for label, sub, values in rows:
        cells = []
        for v in values:
            i = step(v)
            if i is None:
                cells.append(f'<td width="{cell_w}" height="{cell_h}" bgcolor="{t.chart.empty_cell}" style="width:{cell_w}px;'
                             f'height:{cell_h}px;background:{t.chart.empty_cell};{gap}{cell}color:{t.chart.axis};">&middot;</td>')
            else:
                fill = ramp[i]
                cells.append(f'<td width="{cell_w}" height="{cell_h}" bgcolor="{fill}" style="width:{cell_w}px;'
                             f'height:{cell_h}px;background:{fill};{gap}{cell}color:{text_on(fill)};font-weight:bold;">'
                             f'{v:g}</td>')
        out.append(f'<tr><td width="{label_w}" style="width:{label_w}px;font-family:{t.font};font-size:12px;'
                   f'color:{t.text.primary};{lh(15)}padding-right:6px;">{escape(label)}<br>'
                   f'<span style="font-size:10px;color:{t.text.muted};">{sub}</span></td>{"".join(cells)}</tr>')
    keys = []
    for i, (lo, fill) in enumerate(zip(thresholds, ramp)):
        rng = f"{lo:g}+" if i == len(ramp) - 1 else f"{lo:g}&ndash;{thresholds[i + 1] - 1:g}"
        keys.append(f'<td width="14" height="12" bgcolor="{fill}" style="width:14px;height:12px;background:{fill};'
                    f'font-size:1px;line-height:1px;">&nbsp;</td><td style="font-family:{t.font};font-size:10px;'
                    f'color:{t.text.secondary};padding:0 10px 0 4px;">{rng}{unit}</td>')
    width = label_w + cell_w * len(col_labels)
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="{width}" style="width:{width}px;">'
            + "".join(out) + '</table><table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin-top:10px;"><tr><td style="font-family:{t.font};font-size:10px;color:{t.text.muted};'
            f'padding-right:8px;">{legend_title}</td>{"".join(keys)}</tr></table>')


def sparkline(values: list[float], min_span: float = 6.0) -> str:
    """Unicode block sparkline - survives replies, forwards and plain text.
    min_span stops a half-point wobble from filling the whole glyph range."""
    blocks = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    lo, hi = min(values), max(values)
    if hi - lo < min_span:
        mid = (hi + lo) / 2
        lo, hi = mid - min_span / 2, mid + min_span / 2
    return "".join(blocks[round((v - lo) / (hi - lo) * 7)] for v in values)


def sparkline_html(values: list[float], min_span: float = 6.0) -> str:
    """Monospace keeps the block glyphs even. Consolas has the full U+2581-2588 set; Segoe UI falls back."""
    t = theme()
    return (f'<span style="font-family:Consolas,Menlo,\'Courier New\',monospace;font-size:14px;color:{t.text.muted};">'
            f'{sparkline(values, min_span)}</span>')


def status_label(status: str) -> str:
    t = theme()
    icon, _, label = STATUS_ICONS[status]
    return (f'<span style="color:{getattr(t.status, status)};font-size:13px;">{icon}</span> '
            f'<b style="color:{t.text.primary};">{label}</b>')


# =================================================================== Adaptive Card helpers
def tb(text: str, **kw) -> dict:
    return {"type": "TextBlock", "text": text, "wrap": True, **kw}


def card_bar(value: float, max_value: float = 100, cells: int = 20) -> dict:
    """Text bar with half-cell precision (1/40 of full scale at 20 cells).
    Styled containers get padded by every AC host (distorts widths); eighth-blocks are missing from Consolas
    (fallback font notches the bar). Full / left-half / light-shade are WGL4 and render everywhere."""
    halves = round(value / max_value * cells * 2)
    full, half = divmod(halves, 2)
    filled = "\u2588" * full + ("\u258c" if half else "")
    track = "\u2591" * (cells - full - half)
    return {"type": "RichTextBlock", "inlines": [
        {"type": "TextRun", "text": filled, "fontType": "Monospace", "color": "Accent"},
        {"type": "TextRun", "text": track, "fontType": "Monospace", "isSubtle": True}],
        "fallback": {"type": "TextBlock", "text": filled + track, "fontType": "Monospace", "color": "Accent"}}


def card_tabs(tabs: list[tuple[str, str, list]]) -> list:
    """Tabs from ToggleVisibility: [(key, title, items), ...] -> [tab strip, panel, panel, ...].
    Each tab label exists twice (active/inactive) plus an underline; one click flips all of them."""
    def toggle(active: str) -> dict:
        targets = []
        for key, _, _ in tabs:
            on = key == active
            targets += [{"elementId": f"p_{key}", "isVisible": on}, {"elementId": f"lbl_{key}_on", "isVisible": on},
                        {"elementId": f"lbl_{key}_off", "isVisible": not on}, {"elementId": f"ul_{key}", "isVisible": on}]
        return {"type": "Action.ToggleVisibility", "title": dict((k, t) for k, t, _ in tabs)[active],
                "targetElements": targets}

    strip = {"type": "ColumnSet", "spacing": "Medium", "columns": []}
    panels = []
    for i, (key, title, items) in enumerate(tabs):
        first = i == 0
        strip["columns"].append({"type": "Column", "width": "stretch", "selectAction": toggle(key), "items": [
            tb(title, id=f"lbl_{key}_on", weight="Bolder", color="Accent", horizontalAlignment="Center", isVisible=first),
            tb(title, id=f"lbl_{key}_off", isSubtle=True, horizontalAlignment="Center", isVisible=not first),
            tb("\u2501" * 10, id=f"ul_{key}", color="Accent", horizontalAlignment="Center", spacing="None",
               isVisible=first, wrap=False)]})
        panels.append({"type": "Container", "id": f"p_{key}", "isVisible": first, "items": items})
    return [strip] + panels


def card_drilldown(row_id: str, columns: list, detail_items: list) -> list:
    """A clickable row that reveals a detail container under it."""
    return [{"type": "ColumnSet", "id": f"row_{row_id}", "spacing": "Small", "columns": columns,
             "selectAction": {"type": "Action.ToggleVisibility", "title": "Details", "targetElements": [f"d_{row_id}"]}},
            {"type": "Container", "id": f"d_{row_id}", "isVisible": False, "style": "emphasis", "spacing": "Small",
             "items": detail_items}]


def card_http(title: str, url: str, body: dict) -> dict:
    """Action.Http (Outlook-only). Reference inputs in body values as '{{inputId.value}}'."""
    return {"type": "Action.Http", "title": title, "method": "POST", "url": url, "body": json.dumps(body),
            "headers": [{"name": "Content-Type", "value": "application/json"}]}


def adaptive_card(body: list, actions: list | None = None, hide_original_body: bool = True,
                  originator: str | None = None, version: str = "1.2") -> dict:
    """Card for <script type="application/adaptivecard+json">. Without an originator it renders only when
    sent to yourself; register a provider (Actionable Email Developer Dashboard) to send to others."""
    card = {"type": "AdaptiveCard", "version": version, "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "hideOriginalBody": hide_original_body, "body": body}
    if actions:
        card["actions"] = actions
    if originator:
        card["originator"] = originator
    return card
