"""
Headless smoke test for a built lab.html: every email, every pane, card parse warnings, console errors.
Screenshots land in <lab dir>/shots/.

    python verify_lab.py out/lab.html

Needs: python -m pip install playwright && python -m playwright install chromium
Exit code 1 on page errors or unknown Adaptive Card element/action types.
"""
import pathlib
import re
import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    lab = pathlib.Path(sys.argv[1]).resolve()
    shots = lab.parent / "shots"
    shots.mkdir(exist_ok=True)
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2200, "height": 1400})
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.on("console", lambda m: m.type == "error" and problems.append(f"console: {m.text}"))
        page.goto(lab.as_uri())
        options = page.locator("#pick option").all_inner_texts()
        for i, title in enumerate(options):
            page.select_option("#pick", index=i)
            page.wait_for_timeout(2500)  # images load, GIFs run
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
            for pane in ("classic", "owa", "card"):
                page.locator(f"#pane-{pane}").screenshot(path=str(shots / f"{slug}-{pane}.png"))
            card_log = page.locator("#card-log li").all_inner_texts()
            owa_log = page.locator("#owa-log li").all_inner_texts()
            actions = page.locator("#card-host .ac-selectable, #card-host .ac-pushButton").count()
            print(f"\n== {title}")
            print(f"   card: {actions} clickable elements")
            for line in card_log:
                print("   card:", line.replace("\n", " | "))
                if "Unknown" in line:
                    problems.append(f"{title}: {line}")
            for line in owa_log:
                print("   owa: ", line)
        browser.close()
    print(f"\nscreenshots -> {shots}")
    print("PROBLEMS:" if problems else "OK - no page errors, no unknown card types", *problems, sep="\n   ")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
