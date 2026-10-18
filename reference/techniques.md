# Techniques reference

Load this when hand-writing VML or card JSON that `emailkit` doesn't cover, or when someone asks "does X work in Outlook?".

## Support matrix (verified Oct 2026)

| Technique | Classic Outlook (Word) | New Outlook / OWA | Mobile / Mac | Confidence |
|---|---|---|---|---|
| Tables, `bgcolor`, cell borders | yes | yes | yes | High (lab-verified) |
| `cellspacing` | **ignored** | yes | yes | High (lab-verified) |
| VML (rect, roundrect, oval, arc, shape path, group, textbox, line) | yes | ignored (comment) | ignored | High (lab-verified) |
| Conditional comments `[if mso]` | evaluated | treated as comments | comments | High |
| Animated GIF | M365: animates, max 3 loops; 2013-2019: frame 1 | animates | animates | Medium-High (vendor docs + msoutlook.info) |
| PNG/JPG via CID | yes | yes | yes | High |
| Data-URI images | no | partial | yes | Medium |
| External images | blocked by default (corp) | blocked by default (corp) | varies | Medium |
| `border-radius`, CSS gradients | no (fallback colour) | yes | yes | High (lab-verified) |
| `:hover`, `:checked`, keyframes | no | stripped | Apple Mail yes | Medium |
| `@media` | no | uncertain | yes | Low |
| Inline SVG | no | unreliable | Apple yes | Low |
| Adaptive Card (Actionable Message) | M365: yes | yes | buttons reported dead in Outlook.com personal / iOS (Mar 2026 report) | Medium |
| Unicode block sparklines | yes (Consolas) | yes | yes | High (lab-verified) |

Sources: Microsoft Learn (Actionable Messages, developer dashboard: "send email to yourself ... without any intervention from Microsoft"), MC1230457 (moderation approvals move to AM cards, 2026), msoutlook.info (M365 GIF: 3 loops then Play), Vidyard KB (Play animated GIFs option), Directions on Microsoft (classic Outlook until at least 2029; opt-out phase moved to ~Mar 2027), Email on Acid / freshinbox (Outlook.com strips `:hover`, mangles checkboxes).

## VML recipes (all inside `<!--[if mso]> ... <![endif]-->`)

Declare once on `<html>`: `xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"`.

**Gradient banner with text**
```html
<v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false" style="width:600px;height:80px;">
  <v:fill type="gradient" color="#FFC21A" color2="#FF2E7E" angle="90"/>
  <v:textbox inset="16px,16px,16px,16px"><span style="font-family:Arial;font-size:20px;">Title</span></v:textbox>
</v:rect>
```
Note `angle="90"` renders color2 on the left: flip the colours if needed.

**Donut** - a `v:group` (coordsize 1000) holding a track `v:oval` and a `v:arc` (`startangle="0"` = 12 o'clock, clockwise; `endangle = 360 * pct`). Inset both by half the stroke width. `<v:stroke endcap="round"/>` for rounded ends.

**Filled wedge / pie slice** - `path="m 100,100 ae 100,100,90,90,0,11796480 x e"`: `ae cx,cy,rx,ry,start,sweep` with angles in 16.16 fixed point (degrees x 65536).

**Line chart** - `v:group coordsize="W,H"` (1 unit = 1px), then per series a `v:shape` with the same coordsize and `path="m x0,y0 l x1,y1 x2,y2 ... e"` (integers only), `filled="f" strokeweight="1.5pt"`. Gridlines: `v:line from="x1,y" to="x2,y"`. Labels: a transparent `v:rect` with a `v:textbox` positioned in group units.

**Bulletproof button**
```html
<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" href="https://..." style="height:44px;v-text-anchor:middle;width:220px;"
  arcsize="14%" fillcolor="#0D0D0F" stroke="f"><center style="color:#FFC21A;font-family:Arial;font-size:15px;font-weight:bold;">Open</center></v:roundrect>
```

**Background image behind content** - `v:rect` + `<v:fill type="frame" src="...">` + `v:textbox` for the content.

## Adaptive Card patterns

- **Tabs** - one ColumnSet; each Column has `selectAction: Action.ToggleVisibility` whose `targetElements` sets every panel and every label variant explicitly (`isVisible: true/false`, not toggle). Two copies of each label (active = bold accent, inactive = subtle) fake the selected state. See `emailkit.card_tabs`.
- **Drill-down rows** - ColumnSet with `selectAction` toggling one hidden Container (`emailkit.card_drilldown`).
- **Decisions** - `Input.ChoiceSet` (`style: compact`) + `Input.Text` + `ActionSet` with `Action.Http`; body references inputs as `{{inputId.value}}`.
- **Charts** - text bars (`card_bar`) and monospace sparklines. Images need HTTPS URLs; Outlook proxies them.
- **Version** - declare `1.2` (ToggleVisibility, ActionSet, RichTextBlock, fallback). Give newer elements a `fallback`.
- **Logic** - string `targetElements` toggle (XOR), `{elementId, isVisible}` assigns, nesting is AND: visibility composes down the tree. A goal check is a chain of wrappers around a banner, each wrapper visible while its condition holds (Lights Out: 25 deep, plus a 5-deep chain per floor). If moves commute and undo themselves, each move can also toggle its own hint marker and the hint stays a valid solution from any position. Conditional moves (a state machine) work the same way: put each move button inside the wrappers of the states where it applies. The cost is bytes: every move lists all its targets, and a restart must assign every element explicitly (most of Lights Out's 46 KB). Verified in the AC JS 3.0.6 lab only (Oct 2026).
- **Size** - keep the payload compact (Pulse ~26 KB, Lights Out ~46 KB). No documented Outlook limit found (Oct 2026); `lights_out.py` also writes a 19 KB lite control so a real-inbox test can tell a size limit from a feature gap. Drop defaults (`isVisible: true`, `wrap: false`, Column `type`) to save bytes.

## GIF design rules

- Frame 1 = final state. Then crossfade rewind -> draw -> hold. `loop=2` (3 plays).
- Ease-out motion (`ease_out_cubic`); ~25 frames at 45 ms (~1.2 s draw); 3-4 s hold.
- Direct labels arrive on the last frame only; they would jitter if drawn mid-motion.
- One shared palette sampled from several frames; snap the background entry to the exact card colour.
- Render at 2x and set `width`/`height` attributes to 1x (retina-sharp; Word honours the attributes).
- GIF delays under 20 ms get bumped to 100 ms by browsers: never rely on "invisible" frames.
