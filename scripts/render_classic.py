"""
Render an HTML email the way classic Outlook for Windows does.

Classic Outlook has no HTML engine of its own - it hands the message to Word's HTML import filter.
So we do the same: open the file in a private, hidden Word instance, export to PDF, rasterise with
PyMuPDF and stitch the pages into one tall PNG. Without PyMuPDF the PDF is kept instead.

Needs: Windows + Word, pywin32. Optional: pymupdf + Pillow (for the PNG).
Note: Word's PDF export is static - animated GIFs show their first frame (that is what
Outlook 2013-2019 shows too; Outlook for Microsoft 365 animates them).

Usage:
    python render_classic.py emails/pulse.html              -> emails/pulse.classic.png
    python render_classic.py emails/pulse.html out.png --width 680 --scale 2
"""
import argparse
import pathlib
import sys

import pythoncom
import win32com.client

WD_EXPORT_FORMAT_PDF = 17
WD_OPEN_FORMAT_WEBPAGES = 7
POINTS_PER_PX = 0.75
MAX_PAGE_POINTS = 1584  # Word's hard limit: 22 inches


def export_pdf_with_word(html_path: pathlib.Path, pdf_path: pathlib.Path, width_px: int) -> None:
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")  # private instance, never the user's open Word
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(FileName=str(html_path), ConfirmConversions=False, ReadOnly=True,
                                  AddToRecentFiles=False, Format=WD_OPEN_FORMAT_WEBPAGES)
        try:
            setup = doc.PageSetup
            setup.TopMargin = setup.BottomMargin = setup.LeftMargin = setup.RightMargin = 0
            setup.PageWidth = min(width_px * POINTS_PER_PX, MAX_PAGE_POINTS)
            setup.PageHeight = MAX_PAGE_POINTS
            doc.ExportAsFixedFormat(OutputFileName=str(pdf_path), ExportFormat=WD_EXPORT_FORMAT_PDF)
        finally:
            doc.Close(SaveChanges=False)
    finally:
        word.Quit()
        pythoncom.CoUninitialize()


def stitch_pdf_to_png(pdf_path: pathlib.Path, png_path: pathlib.Path, scale: float) -> tuple[int, int]:
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # older PyMuPDF
    from PIL import Image

    pdf = pymupdf.open(str(pdf_path))
    pages = []
    for page in pdf:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    pdf.close()

    # Trim trailing blank space so the image ends where the email ends.
    last = pages[-1]
    bbox = Image.eval(last.convert("L"), lambda v: 255 - v).getbbox()
    if bbox:
        pages[-1] = last.crop((0, 0, last.width, min(last.height, bbox[3] + int(16 * scale))))

    width, height = max(p.width for p in pages), sum(p.height for p in pages)
    sheet = Image.new("RGB", (width, height), "white")
    y = 0
    for p in pages:
        sheet.paste(p, (0, y))
        y += p.height
    sheet.save(png_path)
    return width, height


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an HTML email through Word (classic Outlook engine).")
    parser.add_argument("html", type=pathlib.Path)
    parser.add_argument("png", type=pathlib.Path, nargs="?")
    parser.add_argument("--width", type=int, default=680, help="viewport width in CSS px")
    parser.add_argument("--scale", type=float, default=2.0, help="raster scale (2 = retina)")
    args = parser.parse_args()

    html_path = args.html.resolve()
    if not html_path.exists():
        print(f"ERROR: {html_path} not found", file=sys.stderr)
        return 1
    png_path = (args.png or html_path.with_suffix(".classic.png")).resolve()
    pdf_path = png_path.with_suffix(".pdf")

    export_pdf_with_word(html_path, pdf_path, args.width)
    try:
        w, h = stitch_pdf_to_png(pdf_path, png_path, args.scale / POINTS_PER_PX)  # PDF is in points
    except ImportError:
        print(f"WARNING: PyMuPDF/Pillow missing - kept PDF only: {pdf_path}  (python -m pip install pymupdf pillow)")
        return 0
    pdf_path.unlink()
    print(f"classic render -> {png_path} ({w}x{h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
