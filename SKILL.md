---
name: outlook-email
description: Build HTML emails that work in every Outlook - classic (Word engine), new Outlook/OWA and mobile - with real charts, animated GIF charts, VML vector graphics and an interactive Adaptive Card (Actionable Message) layer. Preview each email in a 3-pane lab whose classic pane is a genuine Word render, then send it to yourself through Outlook to test. Use for "Outlook email", "HTML email", "KPI / report / newsletter email", "animated chart in an email", "VML", "actionable message", "adaptive card in email", "make this work in Outlook", or any deliverable that is an email body rather than a web page.
---

# Outlook Email

Outlook is not one renderer, it is three. Design for all three at once and let each get its best version.

| Renderer | Engine | What works | Lab pane |
|---|---|---|---|
| **Classic Outlook** (Windows desktop; enterprise default until at least 2029) | Word's HTML import | Tables, `bgcolor`, **VML** (vector shapes, gradients, arcs, paths, text boxes), GIFs (M365 animates them; 2013-2019 shows frame 1). No CSS3, no `border-radius`, no `:hover`, no JS. | **REAL**: Word renders it via COM |
| **New Outlook / OWA / mobile / Mac** | Chromium/WebKit + Microsoft sanitizer | Modern CSS mostly, images, GIFs. Stripped: scripts, forms, iframes, inline SVG, external CSS, `:hover`/`:checked`, keyframes, positioning. | Simulated sanitizer (approximate) |
| **Actionable Message** (M365 tenants) | Adaptive Card JSON in `<head>` | Real interactivity: tabs/drill-downs (`Action.ToggleVisibility`), inputs, `Action.Http` POSTs, `ShowCard`. | Official AC renderer, Outlook-like host config |

The `<!--[if mso]>` branch is what classic Outlook sees; `<!--[if !mso]><!-->` is everyone else. The card renders on top (and with `hideOriginalBody`, instead) where supported; the HTML is its fallback.

## Workflow

```bash
S=~/.claude/skills/outlook-email          # or wherever this skill lives
python $S/examples/roast.py --theme flat --out work/emails          # scaffold: copy this file for a new email
python $S/examples/gif_gallery.py --theme default --out work/emails # animated-chart test email
python $S/examples/lights_out.py --theme default --out work/emails  # a playable puzzle card (+ lite control, + ambient loop)
python $S/scripts/build_lab.py work/emails        # Word-renders every *.html, writes work/lab.html (+ vendor/)
python $S/scripts/verify_lab.py work/lab.html     # headless: every pane, card parse warnings, screenshots
python $S/scripts/send_outlook.py work/emails/roast.html          # dry run
python $S/scripts/send_outlook.py work/emails/roast.html --send   # to YOUR mailbox only, images as CID
```

1. **Scaffold from `examples/roast.py`** (the scaffold method: match it, don't invent structure). Data block at the top, derived values computed (single source of truth), then body + card built from `scripts/emailkit.py`.
2. **Build the lab and look at all three panes.** Fix what the Word pane shows; it is the real thing.
3. **Run `verify_lab.py`.** Zero page errors and zero "Unknown" card types before sending.
4. **Send to yourself** and open the received mail in classic Outlook, new Outlook, OWA and on a phone. The lab is a preview; the inbox is the test.

## Per chart: choose what each renderer gets

Every chart block in `emailkit` takes `classic=` and `modern=`:

| Goal | classic | modern | Notes |
|---|---|---|---|
| Crisp and static | `vml` (line, donut) / `table` (bars) | `png` / `table` | Vectors in Word; best for print and zoom |
| Animated wherever possible | `gif` | `gif` | M365 desktop animates; frame 1 elsewhere |
| Default mix (`roast.html`) | `vml` | `gif` | Classic gets vectors, others get motion |

Blocks: `donut_block`, `line_chart_block` (+ `LineChart`), `bar_chart_block` (+ `BarChart`, `html_bar_chart`), `heatmap_table`, `sparkline_html`, `kpi_tile`/`stat_tile`/`tiles_row`, `button`, `header_band`/`footer_band`, `masthead` (full-bleed top band, passed to `email_document(masthead=...)`), `email_document`. Card: `tb`, `card_bar`, `card_tabs`, `card_drilldown`, `card_http`, `adaptive_card`.

## Animated GIF charts (does it work? yes, with rules)

- **Where it animates:** Outlook for Microsoft 365 desktop, new Outlook, OWA, iOS/Android, Mac. **Not** Outlook 2013-2019 (frame 1 only). Also frozen if Outlook's *File > Options > Advanced > Play animated GIFs* is off, Windows *Animation effects* is off, or a VDI/Citrix session disables animation.
- **M365 loops a GIF at most 3 times, then shows a Play button.** `Anim(loop=2)` = 3 plays, matched to that cap. Never loop forever.
- **Frame 1 is the finished chart** (`first_frame="final"`), so non-animating clients still show the data. The sequence then crossfades back and draws (ease-out), with labels landing on the last frame.
- **The GIF starts when the email opens, not when it scrolls into view.** Put the animated chart high, or rely on the 3 loops.
- The lab's classic pane is a static export: it shows frame 1 by design and flags GIFs in the classic branch. Use the new-Outlook pane's Replay button to watch the motion.
- Keep GIFs under ~150 KB: few colours, short sequences. Count-up numbers cost the most bytes.

## Hard-won rules (each one bit us)

- **Word ignores `cellspacing`** - make cell gaps with `border:2px solid <card colour>`.
- **Row backgrounds seam at fractional scaling.** Each table row's fill is its own rectangle; at non-integer scale (Word's PDF export, Outlook at 125%+) a 1 px line of whatever sits behind the card shows between rows. Invisible on a white card over a light page, obvious on a coloured card over a dark one. `email_document` puts the card inside a single-cell table of the same colour, so a seam shows card colour.
- **VML path coordinates must be integers.** Declare `xmlns:v` on `<html>` and include the `o:OfficeDocumentSettings` DPI block (`email_document` does both).
- **Word font stacks:** web/licensed fonts fall back badly. `email_document` injects an mso-only override from the theme's `font_mso` / `font_display_mso`.
- **Prefer lining-figure serifs for numeric headlines** (Cambria, not Georgia: old-style digits bounce).
- **Text bars/sparklines: stick to WGL4 block glyphs** (`█ ▌ ░ ▁-█`). Eighth-blocks are missing from Consolas and fall back to another font with different metrics, which notches the bar.
- **Adaptive Card styled containers get padded in every host**, so "bar charts from coloured columns" distort. Use `card_bar` (text bars).
- **Adaptive Card colours come from Outlook's host config, not your theme.** Only the HTML is themeable.
- **The AC JS renderer ships `HttpAction` but doesn't register `Action.Http`** - the lab registers it. `Action.Submit` doesn't work in Outlook; use `Action.Http`.
- **Images:** relative `img/` paths are for the lab; `send_outlook.py` rewrites them to CID attachments. Data URIs don't show in classic Outlook. External images are blocked by default in most corporate Outlook setups.
- **Never `Display()` before sending via COM** - the compose window round-trips the HTML through Word and can mangle both branches.
- **Pillow median-cut drifts white to #fcfcfc** (grey box on the card). `emailkit` snaps the background palette entry back.
- **Dead ends:** JS, forms, CSS checkbox/`:hover` interactivity (classic ignores it; OWA strips it), inline SVG, HTML attachments (quarantined as phishing).

## Adaptive Card notes

- Put the JSON in `<head>` as `<script type="application/adaptivecard+json">` (`email_document(card=...)`).
- **Sent to yourself, it renders with no registration.** Sending to others needs an Actionable Email provider (`originator`) from the developer dashboard; org scope needs tenant admin approval. Since June 2026 `Action.Http` targets receive Entra ID tokens (legacy auth retired).
- If the card is missing on a self-send, the send path stripped it. Inspect with the *Actionable Messages Debugger* add-in, or resend the same HTML via Power Automate *Send an email (V2)* or Graph `sendMail`. Power Automate's own approval emails are actionable messages under Microsoft's registration (zero-paperwork route).
- Tabs and drill-downs need no backend: they are pure `ToggleVisibility` state flips (see `card_tabs`).
- **`ToggleVisibility` is logic, so a card can hold a game.** A string target toggles (XOR), an object target assigns, and nesting is AND (an element shows only if every ancestor does). `examples/lights_out.py` is a full Lights Out puzzle: each window toggles itself and its neighbours, a 25-deep chain of wrappers is the win detector, and the hint map stays correct because moves commute. Simulate the JSON before rendering (`examples/lights_out_test.py`); logic bugs are invisible in screenshots.

## Themes

`emailkit.use_theme(name)` looks in `assets/themes/local/` first, then `assets/themes/`.
- `default.json` - ink/gold chrome + dataviz reference palette (validated).
- `flat.json` - the default palette with no card: `chrome.card` = `chrome.page`, so the body blends into the page edge to edge instead of a white panel floating in the middle. Generated from `default.json` by `scripts/make_flat_theme.py`; re-run it after changing the default.
- `signature.json` - gold / pink / ink, a poster look, for loud pieces (posters, launches, games): gold card, ink type, Arial Black display. Not for charts (its series are validated on white, not gold).
- `signature-light.json` / `signature-dark.json` - the same palette in a masthead layout: a full-bleed gold masthead closed by a 3 px ink rule, then a cream or ink page. Georgia headlines and body, Consolas labels and figures, pink only for the masthead numeral. Not for charts either.
- **Optional tokens** (examples fall back when a theme lacks them): `chrome.pop` is the hot accent for light grounds (pink; gold-on-gold would vanish), `chrome.night` / `night_deep` give a hero a flat two-tone night ground, `raster_fonts.display` / `mono` set the hero title and label faces. `chrome.masthead` / `on_masthead` switch an example to the masthead layout; `panel` (code boxes, chips), `box` and `line` (framed notes, rules) are its surfaces.
- `local/*.json` - **gitignored**. Private brand themes (yours or a client's) live here, never in a shared repo. Copy them by hand.
- **Brand palettes usually fail as chart colours** (too dark, too light, too grey). Keep the brand for chrome; for series, keep the brand *hues* and re-step them into the passing band, then run the dataviz validator (`node <dataviz>/scripts/validate_palette.js "<hex,...>" --mode light --surface "#ffffff" --pairs all`). Record the result in the theme's `notes`.

## Setting up on another machine

1. Get the skill there: clone or copy this folder to `%USERPROFILE%\.claude\skills\outlook-email` (Claude Code picks it up as a skill). Copy any `assets/themes/local/*.json` by hand.
2. `python -m pip install pillow pywin32 pymupdf` (optional: `playwright` + `python -m playwright install chromium` for `verify_lab.py`).
3. Needs Word for the classic render and a configured classic Outlook profile for `send_outlook.py`. Some tenants prompt "a program is trying to send e-mail" or block programmatic send.
4. The lab is offline-safe (vendored `adaptivecards` 3.0.6 + `markdown-it` 13.0.2, both MIT).

## Files

| Path | What |
|---|---|
| `scripts/emailkit.py` | The library: theme, HTML primitives, VML/PNG/GIF charts, heatmap, sparklines, card helpers |
| `scripts/render_classic.py` | Word COM -> PDF -> PNG (the classic Outlook engine) |
| `scripts/build_lab.py` | Folder of emails -> `lab.html` + `vendor/` |
| `scripts/verify_lab.py` | Playwright smoke test of a built lab |
| `scripts/send_outlook.py` | Self-only send via Outlook COM, CID images |
| `assets/lab_template.html` | The 3-pane lab (sanitizer simulation, AC host config) |
| `examples/roast.py` | Reference email on a fictional coffee roastery: VML + GIF + heatmap + full Adaptive Card. Writes static and animated variants |
| `scripts/make_flat_theme.py` | Writes `assets/themes/flat.json` from the default theme |
| `examples/gif_gallery.py` | GIF test email: line draw-on, donut sweep, bar grow + count-up, a static control, a "why frozen" checklist |
| `examples/probe.html` | Capability probe: which technique renders where |
| `examples/lights_out.py` | Lights Out in an Actionable Message: 3 levels, live hint map, floor moons, animated hero GIF. Also writes a lite control card (19 KB vs 46 KB) to tell a size limit from a feature gap. With a masthead theme the gold band carries the title and the hero drops its baked-in text. Also writes `lights-out-ambient.html`: no card, the tower on a seamless 24-frame loop with softly flickering windows, the honest version for inboxes without Actionable Messages |
| `examples/lights_out_test.py` | Its play test: JSON simulator (3000 random clicks, invariants) + the real renderer in a built lab |
| `reference/techniques.md` | VML recipes, AC patterns, support-matrix sources and confidence |
