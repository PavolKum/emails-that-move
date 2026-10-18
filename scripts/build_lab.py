"""
Bundle a folder of HTML emails into Outlook Lab: one page, three renderer panes per email.

    python build_lab.py out/emails                    # Word-render every *.html, write out/lab.html
    python build_lab.py out/emails --no-word          # reuse existing *.classic.png
    python build_lab.py out/emails --out C:/x/lab.html

The lab and its vendored JS (Adaptive Cards renderer, markdown-it) work offline.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent
ASSETS = SCRIPTS.parent / "assets"


def word_version() -> str:
    try:
        import winreg
        import win32api
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Winword.exe")
        exe = winreg.QueryValue(key, None)
        info = win32api.GetFileVersionInfo(exe, "\\")
        ms, ls = info["FileVersionMS"], info["FileVersionLS"]
        return f"WINWORD {ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return "WINWORD (version unknown)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("emails", type=pathlib.Path, help="folder of *.html emails (images relative to it)")
    parser.add_argument("--out", type=pathlib.Path, help="lab.html path (default: next to the emails folder)")
    parser.add_argument("--no-word", action="store_true", help="skip Word renders, reuse existing PNGs")
    args = parser.parse_args()

    email_dir = args.emails.resolve()
    out = (args.out or email_dir.parent / "lab.html").resolve()
    emails = sorted(p for p in email_dir.glob("*.html"))
    if not emails:
        raise SystemExit(f"no *.html in {email_dir}")

    if not args.no_word:
        print(f"rendering {len(emails)} email(s) through Word (classic Outlook engine)")
        for path in emails:
            res = subprocess.run([sys.executable, str(SCRIPTS / "render_classic.py"), str(path), "--scale", "2"],
                                 capture_output=True, text=True)
            if res.returncode != 0:
                print(res.stdout, res.stderr, file=sys.stderr)
                raise SystemExit(f"Word render failed for {path.name}")
            print("  ", (res.stdout.strip().splitlines() or ["(no output)"])[-1])

    engine = word_version()
    rel_dir = pathlib.Path(os.path.relpath(email_dir, out.parent)).as_posix() + "/"
    bundle = []
    for path in emails:
        html = path.read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        png, pdf = path.with_suffix(".classic.png"), path.with_suffix(".classic.pdf")
        rendered = png if png.exists() else pdf if pdf.exists() else None
        bundle.append({
            "title": (title.group(1).strip() if title else path.stem).replace("&middot;", "\u00b7"),
            "file": path.name,
            "html": html,
            "base": rel_dir,
            "classicPng": rel_dir + png.name if png.exists() else "",
            "classicPdf": rel_dir + pdf.name if (not png.exists() and pdf.exists()) else "",
            "renderedAt": dt.datetime.fromtimestamp(rendered.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if rendered else "",
            "engine": engine,
        })

    template = (ASSETS / "lab_template.html").read_text(encoding="utf-8")
    if "/*__EMAILS__*/[]" not in template:
        raise SystemExit("placeholder /*__EMAILS__*/[] missing from lab_template.html")
    payload = json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/")
    out.write_text(template.replace("/*__EMAILS__*/[]", payload), encoding="utf-8")
    shutil.copytree(ASSETS / "vendor", out.parent / "vendor", dirs_exist_ok=True)
    print(f"lab -> {out}  ({len(bundle)} emails)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
