"""
Roast Report - a weekly KPI email for a small coffee roastery: the same anatomy as pulse.py (two donuts and a
headline number, an index line chart, a heatmap, a watchlist, an Adaptive Card) on a subject anyone can read.
All data is fictional.

    python roast.py --theme mybrand --out C:/temp/roast/emails

writes two variants plus img/:
    roast.html           classic Outlook gets VML vectors (crisp, static); everyone else gets PNG/GIF
    roast-animated.html  classic Outlook gets the GIFs too, so Outlook for M365 animates them
Both carry the same Adaptive Card (tabs, drill-down rows, decision inputs, Action.Http).
"""
import argparse
import pathlib
import sys
from html import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emailkit as ek  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

# ---------------------------------------------------------------- data (fictional)
WEEK, DATE = "Week 42", "17 Oct 2026"
CAPACITY, CAPACITY_PRIOR = 82.4, 79.3        # % of the roasters' available hours used this week
REPEAT, REPEAT_PRIOR = 71.8, 72.2            # % of this week's orders from returning customers
COVER_PRIOR = 5.9                            # weeks of green-coffee stock, last week
PRICE_INDEX = {                              # green coffee price by origin, Oct 25 = 100
    "Ethiopia": [100, 100.9, 101.5, 102.4, 103.0, 103.9, 104.6, 105.2, 106.1, 106.9, 107.6, 108.4],
    "Colombia": [100, 99.6, 99.1, 98.9, 99.2, 99.5, 99.9, 100.2, 100.4, 100.7, 101.0, 101.2],
    "Brazil": [100, 99.7, 99.5, 99.0, 98.6, 98.4, 98.1, 97.7, 97.5, 97.2, 97.0, 96.8],
}
WEEKS = ["W43", "W44", "W45", "W46", "W47", "W48", "W49", "W50"]
LOTS = [
    # ship = % of the lot's stock booked to ship per week; trend = % of stock left, last 12 weeks
    dict(id="konga", name="Konga", origin="Ethiopia", process="Washed", kg=120, cover=2.1, left=38,
         ship=[4, 38, 0, 0, 9, 0, 0, 5], trend=[100, 96, 91, 85, 80, 74, 67, 60, 54, 48, 43, 38]),
    dict(id="sidamo", name="Sidamo Guji", origin="Ethiopia", process="Natural", kg=75, cover=3.4, left=52,
         ship=[0, 41, 0, 0, 0, 7, 0, 0], trend=[100, 97, 93, 90, 85, 80, 76, 70, 65, 60, 56, 52]),
    dict(id="huila", name="Huila Pink Bourbon", origin="Colombia", process="Washed", kg=90, cover=4.6, left=61,
         ship=[6, 0, 27, 0, 0, 0, 15, 0], trend=[100, 98, 95, 92, 88, 84, 80, 76, 72, 68, 64, 61]),
    dict(id="cerrado", name="Cerrado Mineiro", origin="Brazil", process="Natural", kg=300, cover=5.4, left=72,
         ship=[0, 0, 8, 0, 14, 0, 0, 0], trend=[100, 98, 96, 93, 91, 88, 85, 82, 79, 77, 74, 72]),
    dict(id="nyeri", name="Nyeri AA", origin="Kenya", process="Washed", kg=50, cover=6.1, left=84,
         ship=[0, 3, 0, 0, 0, 0, 0, 0], trend=[100, 99, 97, 96, 94, 93, 91, 90, 88, 87, 85, 84]),
    dict(id="tarrazu", name="Tarraz\u00fa", origin="Costa Rica", process="Honey", kg=110, cover=6.7, left=80,
         ship=[0, 0, 0, 0, 0, 11, 0, 22], trend=[100, 98, 97, 95, 93, 92, 90, 88, 86, 84, 82, 80]),
    dict(id="antigua", name="Antigua", origin="Guatemala", process="Washed", kg=140, cover=7.9, left=91,
         ship=[0, 0, 0, 0, 0, 0, 0, 9], trend=[100, 99, 99, 98, 97, 96, 96, 95, 94, 93, 92, 91]),
    dict(id="kayanza", name="Kayanza", origin="Burundi", process="Natural", kg=60, cover=8.2, left=88,
         ship=[0, 0, 0, 6, 0, 0, 12, 0], trend=[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 89, 88]),
]
WATCHLIST = [
    ("konga", "critical", "38% of the stock ships in W44. The next container lands in December."),
    ("sidamo", "serious", "41% ships in W44 with one subscription run. Sells out before the new harvest."),
    ("huila", "warning", "Roaster 2 is down for service. 27% of this lot's orders wait for W45."),
]
DASHBOARD_URL = "https://example.com/roast"
DECISION_URL = "https://example.com/roast/decision"  # Action.Http target: a registered HTTPS endpoint in production

# ---------------------------------------------------------------- derived (single source of truth)
BY_ID = {lot["id"]: lot for lot in LOTS}
TOTAL_KG = sum(lot["kg"] for lot in LOTS)
COVER = sum(lot["cover"] * lot["kg"] for lot in LOTS) / TOTAL_KG
WEEKLY_SHARE = [sum(lot["ship"][w] * lot["kg"] for lot in LOTS) / TOTAL_KG for w in range(len(WEEKS))]
HEADLINE = (f"Roasters at {CAPACITY:.1f}% of capacity, up {CAPACITY - CAPACITY_PRIOR:.1f}pt. "
            f"Two lots sell out before the next harvest.")


# ---------------------------------------------------------------- steam glyph (header signature)
def steam_points(w=168, h=40):
    mid = h // 2
    return [(0, mid), (56, mid), (66, mid - 6), (74, mid + 4), (84, 3), (94, h - 3), (102, mid - 3), (110, mid), (w, mid)]


def glyph_html(img_dir: pathlib.Path) -> str:
    t = ek.theme()
    w, h, ss = 168, 40, 8
    img = Image.new("RGB", (w * ss, h * ss), t.chrome.ink)
    ImageDraw.Draw(img).line([(x * ss, y * ss) for x, y in steam_points()], fill=t.chrome.accent, width=int(2.5 * ss),
                             joint="curve")
    img.resize((w * 2, h * 2), Image.LANCZOS).save(img_dir / "roast-glyph.png")
    pts = steam_points()
    path = f"m {pts[0][0]},{pts[0][1]} l " + " ".join(f"{x},{y}" for x, y in pts[1:]) + " e"
    vml = (f'<v:shape {ek.VML_NS} coordsize="{w},{h}" style="width:{w}px;height:{h}px;" filled="f" stroked="t" '
           f'strokecolor="{t.chrome.accent}" strokeweight="1.9pt" path="{path}"><v:stroke joinstyle="round" endcap="round"/></v:shape>')
    return ek.mso(vml) + ek.not_mso(ek.img_tag("img/roast-glyph.png", w, h, ""))


# ---------------------------------------------------------------- HTML body
def watch_rows() -> str:
    t = ek.theme()
    out = []
    for lot_id, status, note in WATCHLIST:
        lot = BY_ID[lot_id]
        out.append(
            f'<tr><td style="padding:12px 0;border-top:1px solid {t.chart.grid};font-family:{t.font};">'
            f'<table role="presentation" width="592" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="96" valign="top" style="width:96px;font-family:{t.font};font-size:12px;{ek.lh(18)}">'
            f'{ek.status_label(status)}</td>'
            f'<td valign="top" style="font-family:{t.font};">'
            f'<p style="margin:0;font-size:14px;font-weight:bold;color:{t.text.primary};{ek.lh(18)}">{escape(lot["name"])} '
            f'<span style="font-weight:normal;color:{t.text.muted};font-size:12px;">{lot["origin"]} &middot; {lot["process"]}</span></p>'
            f'<p style="margin:3px 0 0;font-size:13px;color:{t.text.secondary};{ek.lh(18)}">{escape(note)}</p></td>'
            f'<td width="130" valign="top" align="right" style="width:130px;font-family:{t.font};">'
            f'<p style="margin:0;{ek.lh(18)}">{ek.sparkline_html(lot["trend"])}</p>'
            f'<p style="margin:2px 0 0;font-size:11px;color:{t.text.muted};">stock left 12w &middot; '
            f'<b style="color:{t.text.primary};">{lot["left"]:.0f}%</b></p></td></tr></table></td></tr>')
    return f'<table role="presentation" width="592" cellpadding="0" cellspacing="0" border="0">{"".join(out)}</table>'


def build_body(img_dir: pathlib.Path, animated: bool) -> str:
    t = ek.theme()
    donut_mode = dict(classic="gif", modern="gif") if animated else dict(classic="vml", modern="png")
    chart = ek.LineChart(series=PRICE_INDEX, x_labels={0: "Oct 25", 3: "Jan", 6: "Apr", 9: "Jul", 11: "Sep 26"},
                         y_ticks=[95, 100, 105, 110], y_min=94, y_max=110, baseline=100)
    tiles = ek.tiles_row([
        ek.kpi_tile(ek.donut_block(CAPACITY, img_dir, "donut-capacity", f"Roaster capacity used {CAPACITY:.1f}%",
                                   **donut_mode),
                    f"{CAPACITY:.1f}%", "Capacity used", ek.delta(CAPACITY - CAPACITY_PRIOR, "pt", suffix="w/w")),
        ek.kpi_tile(ek.donut_block(REPEAT, img_dir, "donut-repeat", f"Repeat customers {REPEAT:.1f}%", **donut_mode),
                    f"{REPEAT:.1f}%", "Repeat customers", ek.delta(REPEAT - REPEAT_PRIOR, "pt", suffix="w/w")),
        ek.stat_tile(f'{COVER:.1f}<span style="font-size:16px;"> wks</span>', "Stock cover",
                     f'<span style="color:{t.text.secondary};">&#9660; {COVER_PRIOR - COVER:.2f}</span> '
                     f'<span style="color:{t.text.muted};">vs last week</span>'),
    ])
    heat = ek.heatmap_table(
        rows=[(lot["name"], f'{lot["origin"]} &middot; {lot["kg"]} kg', lot["ship"]) for lot in LOTS],
        col_labels=WEEKS, thresholds=[1, 5, 10, 20, 30, 40], legend_title="Share of lot stock booked to ship:")
    cta = (ek.button(DASHBOARD_URL, "Open the roast dashboard &rarr;")
           + f'<p style="margin:14px 0 0;font-family:{t.font};font-size:12px;color:{t.text.secondary};">Or '
             f'<a href="mailto:roast@example.com?subject=FLAG%20Konga%20-%20Week%2042&amp;body=Action%3A%20reorder" '
             f'style="color:{t.text.primary};">flag a lot by reply</a>. A flow parses the subject line.</p>')
    footer = (ek.mso(f'<span style="color:{t.chrome.accent};">&#9632;</span> You are seeing the <b style="color:#fff;">'
                     f'classic Outlook</b> build: charts are {"animated GIFs" if animated else "native VML vectors drawn by Word"}.')
              + ek.not_mso(f'<span style="color:{t.chrome.accent};">&#9632;</span> You are seeing the <b style="color:#fff;">'
                           f'HTML</b> build: charts are PNG/GIF. M365 Outlook can also show an interactive card.')
              + "<br>Fictional roastery, fictional data. Built with the outlook-email kit.")
    return (
        ek.header_band("ROAST REPORT", f"{WEEK} &middot; {DATE}", HEADLINE, glyph_html(img_dir))
        + ek.spacer(24) + tiles + ek.spacer(28)
        + ek.section_title("Market", "Green coffee prices by origin, Oct 25 = 100") + ek.spacer(10)
        + ek.row(ek.line_chart_block(chart, img_dir, "price-index", classic="gif" if animated else "vml", modern="gif"))
        + ek.spacer(28)
        + ek.section_title("Roasting", "When the beans go out: next 8 weeks") + ek.spacer(10)
        + ek.row(heat, pad="0 22px") + ek.spacer(28)
        + ek.section_title("Watchlist", "Three lots need attention") + ek.spacer(6)
        + ek.row(watch_rows()) + ek.spacer(20) + ek.row(cta) + ek.spacer(28) + ek.footer_band(footer)
    )


# ---------------------------------------------------------------- Adaptive Card
def build_card() -> dict:
    overview = [
        {"type": "ColumnSet", "columns": [
            {"type": "Column", "width": "stretch", "items": [
                ek.tb("Capacity used", size="Small", isSubtle=True, spacing="None"),
                ek.tb(f"{CAPACITY:.1f}%", size="ExtraLarge", weight="Bolder", spacing="None"),
                ek.tb(f"\u25b2 {CAPACITY - CAPACITY_PRIOR:.1f}pt w/w", size="Small", color="Good", spacing="None")]},
            {"type": "Column", "width": "stretch", "items": [
                ek.tb("Repeat customers", size="Small", isSubtle=True, spacing="None"),
                ek.tb(f"{REPEAT:.1f}%", size="ExtraLarge", weight="Bolder", spacing="None"),
                ek.tb(f"\u25bc {REPEAT_PRIOR - REPEAT:.1f}pt w/w", size="Small", color="Attention", spacing="None")]},
            {"type": "Column", "width": "stretch", "items": [
                ek.tb("Stock cover", size="Small", isSubtle=True, spacing="None"),
                ek.tb(f"{COVER:.1f} wks", size="ExtraLarge", weight="Bolder", spacing="None"),
                ek.tb(f"\u25bc {COVER_PRIOR - COVER:.2f} wks w/w", size="Small", isSubtle=True, spacing="None")]}]},
        ek.tb("Lots \u00b7 tap a row to drill in", weight="Bolder", spacing="Large", separator=True)]
    for lot in sorted(LOTS, key=lambda x: x["left"]):
        big_w = max(range(len(WEEKS)), key=lambda w: lot["ship"][w])
        overview += ek.card_drilldown(lot["id"], columns=[
            {"type": "Column", "width": 40, "items": [ek.tb(lot["name"], weight="Bolder", spacing="None"),
                                                      ek.tb(f"{lot['origin']} \u00b7 {lot['process']}", size="Small", isSubtle=True, spacing="None")]},
            {"type": "Column", "width": 44, "verticalContentAlignment": "Center", "items": [ek.card_bar(lot["left"])]},
            {"type": "Column", "width": 16, "verticalContentAlignment": "Center",
             "items": [ek.tb(f"{lot['left']:.0f}% \u25be", horizontalAlignment="Right", weight="Bolder")]},
        ], detail_items=[{"type": "FactSet", "facts": [
            {"title": "In stock", "value": f"{lot['kg']} kg ({lot['kg'] / TOTAL_KG * 100:.0f}% of green stock)"},
            {"title": "Cover", "value": f"{lot['cover']:.1f} weeks"},
            {"title": "Biggest week", "value": f"{lot['ship'][big_w]}% of stock in {WEEKS[big_w]}" if lot["ship"][big_w] else "nothing booked in 8 weeks"},
            {"title": "Stock left", "value": f"{lot['trend'][0]:.0f}% \u2192 {lot['left']:.0f}% over 12 weeks"}]}])

    peak = max(WEEKLY_SHARE)
    roasting = [ek.tb("Stock booked to ship by week", weight="Bolder"),
                ek.tb("Share of all green coffee in stock", size="Small", isSubtle=True, spacing="None")]
    for w, v in zip(WEEKS, WEEKLY_SHARE):
        roasting.append({"type": "ColumnSet", "spacing": "Small", "columns": [
            {"type": "Column", "width": "60px", "items": [ek.tb(w, size="Small")]},
            {"type": "Column", "width": "stretch", "verticalContentAlignment": "Center", "items": [ek.card_bar(v, peak * 1.1)]},
            {"type": "Column", "width": "48px", "items": [ek.tb(f"{v:.1f}%", size="Small", weight="Bolder", horizontalAlignment="Right")]}]})
    big = sorted(((lot["ship"][w], lot, w) for lot in LOTS for w in range(len(WEEKS)) if lot["ship"][w] >= 20),
                 key=lambda r: (r[2], -r[0]))
    roasting += [ek.tb("Reorders due", weight="Bolder", spacing="Large", separator=True),
                 {"type": "FactSet", "facts": [{"title": WEEKS[w], "value": f"{lot['name']}: {v}% of the lot "
                                                 f"({lot['kg'] * v / 100:.0f} kg)"} for v, lot, w in big]}]

    color = {"critical": "Attention", "serious": "Warning", "warning": "Warning"}
    watch = []
    for n, (lot_id, status, note) in enumerate(WATCHLIST):
        lot = BY_ID[lot_id]
        _, icon, label = ek.STATUS_ICONS[status]
        watch.append({"type": "Container", "separator": n > 0, "spacing": "Medium", "items": [
            {"type": "ColumnSet", "columns": [
                {"type": "Column", "width": "auto", "items": [ek.tb(f"{icon} {label}", weight="Bolder", color=color[status])]},
                {"type": "Column", "width": "stretch", "items": [ek.tb(lot["name"], weight="Bolder")]},
                {"type": "Column", "width": "auto", "items": [ek.tb(f"{ek.sparkline(lot['trend'])} {lot['left']:.0f}%",
                                                                    isSubtle=True, fontType="Monospace")]}]},
            ek.tb(note, spacing="Small"),
            {"type": "Input.ChoiceSet", "id": f"act_{lot_id}", "style": "compact", "value": "monitor", "choices": [
                {"title": "Keep monitoring", "value": "monitor"}, {"title": "Reorder green coffee", "value": "reorder"},
                {"title": "Move orders to another lot", "value": "swap"}, {"title": "Email the affected customers", "value": "email"}]},
            {"type": "Input.Text", "id": f"note_{lot_id}", "placeholder": "Note for the head roaster (optional)",
             "isMultiline": True},
            {"type": "ActionSet", "actions": [ek.card_http(
                f"Send decision \u2192 {lot['name']}", DECISION_URL,
                {"lot": lot_id, "action": f"{{{{act_{lot_id}.value}}}}", "note": f"{{{{note_{lot_id}.value}}}}",
                 "week": WEEK})]}]})

    body = [{"type": "Container", "style": "emphasis", "bleed": True, "items": [
        ek.tb(f"ROAST REPORT \u00b7 {WEEK.upper()} \u00b7 {DATE.upper()}", size="Small", weight="Bolder", isSubtle=True),
        ek.tb(HEADLINE, size="Medium", weight="Bolder", spacing="Small")]}]
    body += ek.card_tabs([("over", "Overview", overview), ("roast", "Roasting", roasting), ("watch", "Watchlist", watch)])
    actions = [
        {"type": "Action.OpenUrl", "title": "Open the roast dashboard", "url": DASHBOARD_URL},
        {"type": "Action.ShowCard", "title": "Ask the head roaster", "card": {"type": "AdaptiveCard", "body": [
            {"type": "Input.Text", "id": "question", "isMultiline": True, "placeholder": "e.g. Can we swap Konga for Sidamo in W44?"}],
            "actions": [ek.card_http("Send", DECISION_URL, {"question": "{{question.value}}", "week": WEEK})]}}]
    return ek.adaptive_card(body, actions)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", default="default")
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("outlook-email-out/emails"))
    args = parser.parse_args()
    ek.use_theme(args.theme)
    out = args.out.resolve()
    img_dir = out / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    card = build_card()
    for animated, name in ((False, "roast"), (True, "roast-animated")):
        title = f"Roast Report \u00b7 {WEEK}" + (" \u00b7 animated" if animated else "")
        html = ek.email_document(title, build_body(img_dir, animated), preheader=HEADLINE, card=card)
        (out / f"{name}.html").write_text(html, encoding="utf-8")
        print(f"  {name}.html  {len(html) / 1024:.0f} KB")
    print(f"  theme={args.theme}  capacity={CAPACITY:.1f}  cover={COVER:.2f}  -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
