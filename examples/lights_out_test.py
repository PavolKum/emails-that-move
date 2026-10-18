"""
Play-test the Lights Out card two ways, so a change to lights_out.py can't silently break the game:

  A) a pure-JSON simulator of Action.ToggleVisibility (string target = toggle, object = set, an element is
     effectively visible only if it and every ancestor are): 3000 random clicks with every invariant checked
     after each one (one glyph per window, banner iff all dark, moon iff floor dark, hint solves the board);
  B) the real Adaptive Cards renderer inside a built lab.html via Playwright, every step compared with A.

    python lights_out.py --out work/emails && python ../scripts/build_lab.py work/emails
    python lights_out_test.py work/emails/lights-out.html work/lab.html work/shots
    python lights_out_test.py work/emails/lights-out-lite.html work/lab.html work/shots
"""
import json
import pathlib
import random
import re
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lights_out as lo  # noqa: E402

ROWS = COLS = 5
N = ROWS * COLS


class Sim:
    def __init__(self, card):
        self.parent, self.visible, self.cell_action, self.buttons = {}, {}, {}, {}
        self._walk(card["body"], None)

    def _walk(self, items, parent):
        for el in items:
            eid = el.get("id")
            if eid:
                self.parent[eid] = parent
                self.visible[eid] = el.get("isVisible", True)
            here = eid or parent
            sa = el.get("selectAction")
            if sa:
                m = re.match(r"Window (\d)([A-E])", sa["title"])
                k = (ROWS - int(m.group(1))) * COLS + "ABCDE".index(m.group(2))
                self.cell_action[k] = sa["targetElements"]
            for a in el.get("actions", []):
                self.buttons[a["title"]] = a["targetElements"]
            for key in ("items", "columns"):
                if key in el:
                    self._walk(el[key], here)

    def run(self, targets):
        for t in targets:
            if isinstance(t, str):
                self.visible[t] = not self.visible[t]
            else:
                self.visible[t["elementId"]] = t["isVisible"]

    def eff(self, eid):
        while eid:
            if not self.visible[eid]:
                return False
            eid = self.parent[eid]
        return True

    def lit(self):
        return [self.eff(f"a{k}") for k in range(N)]

    def check(self, where):
        lit = self.lit()
        for k in range(N):
            assert self.eff(f"a{k}") != self.eff(f"b{k}"), f"{where}: window {k} shows both/neither glyph"
        assert self.eff(f"w{N - 1}") == (not any(lit)), f"{where}: banner wrong"
        if "f0" in self.visible:
            for r in range(ROWS):
                floor_dark = not any(lit[r * COLS:(r + 1) * COLS])
                assert self.eff(f"f{r * COLS + COLS - 1}") == floor_dark, f"{where}: moon {r} wrong"
        if "p0" not in self.visible:
            return
        state = [bool(x) for x in lit]  # the hint must be a real solution from here
        for k in range(N):
            if self.visible[f"p{k}"]:
                assert not self.visible[f"q{k}"], f"{where}: dot {k} both"
                for j in lo.neighbourhood(k):
                    state[j] = not state[j]
        assert not any(state), f"{where}: hint does not solve the board"


def state_bits(sim):
    return sum(1 << k for k, on in enumerate(sim.lit()) if on)


def solution(sim):
    """Follow the card's own hint dots when it has them, else ask the example's GF(2) solver."""
    if "p0" in sim.visible:
        return [k for k in range(N) if sim.visible[f"p{k}"]]
    return lo.bits(lo.solve(state_bits(sim)))


def compare(page, sim, where):
    dom = page.evaluate("""(ids) => {
        const vis = (id) => { const el = document.querySelector('#card-host [id="' + id + '"]');
                              return !!el && el.getClientRects().length > 0; };
        return Object.fromEntries(ids.map((id) => [id, vis(id)]));
    }""", list(sim.visible))
    bad = [eid for eid, v in dom.items() if v != sim.eff(eid)]
    assert not bad, f"{where}: DOM differs from simulator at {bad[:12]}"


def main():
    html_path, lab, shots = (pathlib.Path(a).resolve() for a in sys.argv[1:4])
    tag = html_path.stem
    shots.mkdir(parents=True, exist_ok=True)
    html = html_path.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    payload = re.search(r'<script type="application/adaptivecard\+json">(.*?)</script>', html, re.S).group(1)
    card = json.loads(payload.replace("<\\/", "</"))
    sim = Sim(card)
    sim.check("start")
    has_hint = "p0" in sim.visible
    levels = [b for b in sim.buttons if b != "Hint"]
    print(f"[{tag}] sim: {len(sim.visible)} ids, {len(sim.cell_action)} windows, buttons {list(sim.buttons)}")

    rnd = random.Random(1)
    for step in range(3000):
        if step % 400 == 0:
            sim.run(sim.buttons[rnd.choice(levels)])
        sim.run(sim.cell_action[rnd.randrange(N)])
        sim.check(f"sim step {step}")
    for lvl in levels:
        sim.run(sim.buttons[lvl])
        for _ in range(7):
            sim.run(sim.cell_action[rnd.randrange(N)])
        for k in solution(sim):
            sim.run(sim.cell_action[k])
        sim.check(f"solve {lvl}")
        assert sim.eff(f"w{N - 1}"), f"{lvl}: solving did not win"
    print(f"[{tag}] sim: 3000 random clicks + a solve from a scrambled position on every level: invariants hold")

    sim = Sim(card)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1800, "height": 1300}, device_scale_factor=2)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(lab.as_uri())
        page.wait_for_timeout(600)
        options = page.locator("#pick option").all_inner_texts()
        page.select_option("#pick", index=next(i for i, o in enumerate(options) if title in o or o in title))
        page.wait_for_timeout(900)
        host = page.locator("#card-host")
        assert page.locator('#card-host [id="a0"]').count() == 1, "AC JS did not put element ids in the DOM"
        compare(page, sim, "start")
        host.screenshot(path=str(shots / f"{tag}-1-start.png"))

        def click(k):
            eid = f"a{k}" if sim.eff(f"a{k}") else f"b{k}"
            page.locator(f'#card-host [id="{eid}"]').click()
            sim.run(sim.cell_action[k])

        def button(name):
            host.get_by_role("button", name=name, exact=True).click()
            sim.run(sim.buttons[name])

        first, *rest = solution(sim)
        click(first)
        compare(page, sim, "after one press")
        host.screenshot(path=str(shots / f"{tag}-2-midway.png"))
        for k in rest:
            click(k)
        compare(page, sim, "level 1 solved")
        assert sim.eff(f"w{N - 1}")
        host.screenshot(path=str(shots / f"{tag}-3-win.png"))
        if has_hint:
            button(levels[-1])
            click(0)
            click(12)
            button("Hint")
            compare(page, sim, "hint shown")
            host.screenshot(path=str(shots / f"{tag}-4-hint.png"))
        for step in range(60):
            if step == 30:
                button(levels[len(levels) // 2])
            click(rnd.randrange(N))
            compare(page, sim, f"random step {step}")
        for k in solution(sim):
            click(k)
        compare(page, sim, "solved from a scramble")
        assert sim.eff(f"w{N - 1}"), "renderer: solving from a scramble did not win"
        log = page.locator("#card-log li").all_inner_texts()
        browser.close()
    print(f"[{tag}] renderer: every step matched the simulator; won level 1 and won again from a scramble")
    for line in log:
        if "ToggleVisibility" not in line:
            print("   card:", line[:150])
    print("   page errors:", errors or "none")


if __name__ == "__main__":
    main()
