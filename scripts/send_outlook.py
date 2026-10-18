"""
Send an HTML email to YOURSELF through classic Outlook (COM), with local images embedded as CID attachments.
This is the real-world test: open the received message in classic Outlook, new Outlook, OWA and your phone.

    python send_outlook.py out/emails/roast.html             # dry run: shows what would be sent
    python send_outlook.py out/emails/roast.html --send      # sends to your own mailbox
    python send_outlook.py out/emails/roast.html --send --subject "Roast test 3"

Self-only by design. Forward from Outlook if it should go anywhere else.

Notes
- Needs classic Outlook with a configured profile, and pywin32.
- Some tenants show "A program is trying to send an e-mail on your behalf" or block programmatic send.
- The Adaptive Card lives in <head>. If it doesn't appear on the received mail, the send path stripped it:
  try the Actionable Messages Debugger add-in to inspect, or send the same HTML via Power Automate
  ("Send an email (V2)") or Graph sendMail. Cards sent to yourself need no provider registration.
"""
import argparse
import pathlib
import re
import sys

PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
PR_ATTACHMENT_HIDDEN = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
LOCAL_IMG = re.compile(r'''(src)=(["'])(?!https?:|cid:|data:)([^"']+?\.(?:png|gif|jpe?g))\2''', re.I)


def inline_images(html: str, base: pathlib.Path) -> tuple[str, dict[str, pathlib.Path]]:
    """Rewrite relative image paths to cid: references. Returns (html, {cid: path})."""
    cids: dict[str, pathlib.Path] = {}
    by_path: dict[pathlib.Path, str] = {}

    def swap(m):
        path = (base / m.group(3)).resolve()
        if not path.exists():
            raise SystemExit(f"image not found: {path}")
        if path not in by_path:
            cid = path.name if path.name not in cids else f"{len(cids)}-{path.name}"
            by_path[path] = cid
            cids[cid] = path
        return f'{m.group(1)}={m.group(2)}cid:{by_path[path]}{m.group(2)}'

    return LOCAL_IMG.sub(swap, html), cids


def own_address(namespace) -> str:
    entry = namespace.CurrentUser.AddressEntry
    try:
        exch = entry.GetExchangeUser()
        if exch is not None and exch.PrimarySmtpAddress:
            return exch.PrimarySmtpAddress
    except Exception:
        pass
    return entry.Address


def main() -> int:
    parser = argparse.ArgumentParser(description="Send an HTML email to yourself via classic Outlook.")
    parser.add_argument("html", type=pathlib.Path)
    parser.add_argument("--subject", help="default: the email's <title>")
    parser.add_argument("--send", action="store_true", help="actually send (default is a dry run)")
    parser.add_argument("--draft", action="store_true",
                        help="save to Drafts instead of sending (opening the draft round-trips it through Word)")
    args = parser.parse_args()

    path = args.html.resolve()
    html = path.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    subject = args.subject or (title.group(1).replace("&middot;", "·").strip() if title else path.stem)
    html, cids = inline_images(html, path.parent)
    has_card = "application/adaptivecard+json" in html
    size_kb = (len(html.encode("utf-8")) + sum(p.stat().st_size for p in cids.values())) / 1024

    import win32com.client
    outlook = win32com.client.Dispatch("Outlook.Application")
    me = own_address(outlook.GetNamespace("MAPI"))

    print(f"to        {me}  (self only)")
    print(f"subject   {subject}")
    print(f"images    {len(cids)} embedded as CID: {', '.join(cids) or '-'}")
    print(f"card      {'yes - Adaptive Card in <head>' if has_card else 'no'}")
    print(f"size      {size_kb:.0f} KB")
    if not (args.send or args.draft):
        print("dry run - add --send to send it, or --draft to save it to Drafts")
        return 0

    mail = outlook.CreateItem(0)
    mail.To = me
    mail.Subject = subject
    for cid, img in cids.items():
        att = mail.Attachments.Add(str(img), 1, 0, cid)
        att.PropertyAccessor.SetProperty(PR_ATTACH_CONTENT_ID, cid)
        att.PropertyAccessor.SetProperty(PR_ATTACHMENT_HIDDEN, True)
    mail.HTMLBody = html  # set after the attachments so the cid: references resolve
    if args.draft:
        mail.Save()       # Drafts; still no Display(), but opening it later goes through Word
        print("saved to Drafts")
        return 0
    mail.Send()           # no Display(): opening the compose window would round-trip the HTML through Word
    print("sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
