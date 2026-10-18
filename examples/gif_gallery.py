"""
GIF animation test - send this to yourself to find out what YOUR Outlook does with animated charts.

    python gif_gallery.py --theme mybrand --out work/emails      -> gif-test.html + img/

Every chart here is a GIF in BOTH branches (classic Outlook included). Frame 1 is the finished chart,
so a client that doesn't animate still shows the data - it just never moves.
All data is fictional.
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emailkit as ek  # noqa: E402

PRICE_INDEX = {   # green coffee price by origin, Oct 25 = 100
    "Ethiopia": [100, 100.9, 101.5, 102.4, 103.0, 103.9, 104.6, 105.2, 106.1, 106.9, 107.6, 108.4],
    "Colombia": [100, 99.6, 99.1, 98.9, 99.2, 99.5, 99.9, 100.2, 100.4, 100.7, 101.0, 101.2],
    "Brazil": [100, 99.7, 99.5, 99.0, 98.6, 98.4, 98.1, 97.7, 97.5, 97.2, 97.0, 96.8],
}
DONUTS = [("Capacity used", 82.4), ("Repeat customers", 71.8), ("Pre-orders", 62.0)]
WEEKLY = [("W43", 1.6), ("W44", 13.3), ("W45", 4.1), ("W46", 0.8), ("W47", 4.5), ("W48", 1.9)]


def para(html: str, size: int = 13, color: str | None = None, margin: str = "0") -> str:
    t = ek.theme()
    return (f'<p style="margin:{margin};font-family:{t.font};font-size:{size}px;color:{color or t.text.secondary};'
            f'{ek.lh(round(size * 1.45))}">{html}</p>')


def checklist() -> str:
    t = ek.theme()
    items = [
        "<b>Outlook (classic, M365):</b> File &rsaquo; Options &rsaquo; Advanced &rsaquo; Display &rsaquo; <i>Play animated GIFs</i>.",
        "<b>Windows:</b> Settings &rsaquo; Accessibility &rsaquo; Visual effects &rsaquo; <i>Animation effects</i> must be on.",
        "<b>Citrix / VDI sessions</b> often switch animations off for performance.",
        "<b>Outlook 2013&ndash;2019</b> never animates: you see frame 1, which is why frame 1 is the finished chart.",
        "<b>Three-loop limit:</b> Outlook for M365 stops after three loops and shows a Play button. Click it.",
    ]
    lis = "".join(f'<tr><td valign="top" width="18" style="width:18px;font-family:{t.font};font-size:13px;'
                  f'color:{t.chrome.ink};{ek.lh(20)}">&#9632;</td><td style="font-family:{t.font};font-size:13px;'
                  f'color:{t.text.secondary};{ek.lh(20)}padding-bottom:4px;">{i}</td></tr>' for i in items)
    return (f'<table role="presentation" width="592" cellpadding="0" cellspacing="0" border="0" '
            f'bgcolor="{t.chart.empty_cell}" style="width:592px;background:{t.chart.empty_cell};">'
            f'<tr><td style="padding:16px 18px;"><p style="margin:0 0 8px;font-family:{t.font};font-size:14px;'
            f'font-weight:bold;color:{t.text.primary};">Charts frozen? Check these in order</p>'
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0">{lis}</table></td></tr></table>')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", default="default")
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("outlook-email-out/emails"))
    args = parser.parse_args()
    ek.use_theme(args.theme)
    out = args.out.resolve()
    img_dir = out / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    t = ek.theme()

    line = ek.LineChart(series=PRICE_INDEX, x_labels={0: "Oct 25", 3: "Jan", 6: "Apr", 9: "Jul", 11: "Sep 26"},
                        y_ticks=[95, 100, 105, 110], y_min=94, y_max=110, baseline=100)
    bars = ek.BarChart(items=WEEKLY, highlight={"W44": t.chart.series[0]}, color=t.chart.axis)
    donuts = "".join(
        f'<td width="197" align="center" valign="top" style="width:197px;">'
        f'{ek.donut_block(v, img_dir, f"gif-donut-{i}", f"{label} {v:.1f}%", size=96, classic="gif", modern="gif")}'
        f'{para(f"<b>{v:.1f}%</b> {label}", 12, margin="8px 0 0")}</td>'
        for i, (label, v) in enumerate(DONUTS))

    rows = (
        ek.header_band("GIF ANIMATION TEST", "outlook-email skill &middot; send to yourself",
                       "Do your charts move? Every chart below should draw itself.")
        + ek.spacer(20)
        + ek.row(para("Each chart is an animated GIF, in classic Outlook too. Frame 1 is the finished chart, then it "
                      "rewinds and draws. If you only ever see the finished chart, your client shows frame 1 only. "
                      "The checklist at the bottom says why."))
        + ek.spacer(24) + ek.section_title("1 &middot; Line draw-on", "Green coffee prices by origin, Oct 25 = 100") + ek.spacer(10)
        + ek.row(ek.line_chart_block(line, img_dir, "gif-line", classic="gif", modern="gif"))
        + ek.spacer(28) + ek.section_title("2 &middot; Donut sweep", "Three KPIs, one GIF each") + ek.spacer(10)
        + f'<tr><td style="padding:0 16px;"><table role="presentation" width="608" cellpadding="0" cellspacing="0" '
          f'border="0"><tr>{donuts}</tr></table></td></tr>'
        + ek.spacer(28) + ek.section_title("3 &middot; Bars grow, numbers count up",
                                           "Share of green-coffee stock shipping, by week") + ek.spacer(10)
        + ek.row(ek.bar_chart_block(bars, img_dir, "gif-bars", classic="gif", modern="gif"))
        + ek.spacer(20) + ek.row(para("<b>Control:</b> the same bars as plain table cells. They never animate, "
                                      "but they render identically everywhere.", 12, t.text.muted))
        + ek.spacer(8) + ek.row(ek.html_bar_chart(bars))
        + ek.spacer(28) + ek.row(checklist()) + ek.spacer(28)
        + ek.footer_band("Fictional data. GIFs: frame 1 = final state, crossfade rewind, 3 loops, ~1.2s draw.")
    )
    html = ek.email_document("GIF animation test \u00b7 outlook-email", rows,
                             preheader="Animated charts in Outlook: does yours play them?")
    (out / "gif-test.html").write_text(html, encoding="utf-8")
    print(f"  gif-test.html  {len(html) / 1024:.0f} KB  theme={args.theme} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
