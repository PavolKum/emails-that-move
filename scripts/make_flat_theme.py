"""
Write assets/themes/flat.json: the default theme with the white card removed. The card takes the page colour,
so the email reads as one grey sheet edge to edge instead of a white panel floating in the middle. Chart GIFs
and PNGs are drawn on chrome.card, so they blend too; empty heatmap cells move one step darker so they still
read against the grey. Re-run after changing default.json.

    python make_flat_theme.py
"""
import json
import pathlib

themes = pathlib.Path(__file__).resolve().parent.parent / "assets" / "themes"
theme = json.loads((themes / "default.json").read_text(encoding="utf-8"))
theme["name"] = "flat"
theme["notes"] = ("The default palette with no card: chrome.card = chrome.page, so the body blends into the page "
                  "edge to edge. Empty heatmap cells one step darker to stay visible on the grey. Generated from "
                  "default.json by scripts/make_flat_theme.py.")
theme["chrome"]["card"] = theme["chrome"]["page"]
theme["chart"]["empty_cell"] = "#e9e8e3"
(themes / "flat.json").write_text(json.dumps(theme, indent=2) + "\n", encoding="utf-8")
print("flat.json: card =", theme["chrome"]["card"])
