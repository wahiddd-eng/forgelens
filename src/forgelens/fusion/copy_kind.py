"""What kind of copy a statement file is, read from the file itself.

The same detector score means different things on a bank's own PDF, a scan, a phone screenshot
and a WhatsApp copy (`experiments/results/phone_laundering.md`), so ForgeLens sets its
threshold per kind. The kind is observed, never taken from labels:

``digital``     the file has a text layer (a bank's e-statement, edited or not)
``screenshot``  image-only, each page one lossless image (PNG), as a phone screenshot is
``phone_jpeg``  image-only, each page one JPEG below 140 pixels per inch of page width (a phone
                screenshot sent over WhatsApp or another messenger: a 1080 px wide page is
                about 130 per inch)
``scan``        any other image-only file (a scan or a "print to image", 150 per inch or more)

The line between phone copies and scans is drawn by resolution alone; a messenger that shrinks
a screenshot further only moves it further from the scans.
"""

from __future__ import annotations

from pathlib import Path

KINDS = ("digital", "scan", "screenshot", "phone_jpeg")
PHONE_MAX_PPI = 140  # pixels per inch of page width
# For files evaluated before the kind was recorded: our laundering settings and the kind each
# produces (checked by tests/test_copy_kind.py on files made by each).
FROM_LAUNDERING = {"": "digital", "none": "digital", "reprint": "digital", "raster": "scan",
                   "screenshot": "screenshot", "whatsapp": "phone_jpeg"}


def copy_kind(pdf: str | Path, password: str | None = None) -> str:
    from forgelens.reader import open_pdf

    with open_pdf(pdf, password) as doc:
        if any(page.get_text("text").strip() for page in doc):
            return "digital"
        exts, ppis = set(), []
        for page in doc:
            images = page.get_images(full=True)
            if len(images) != 1:
                return "scan"
            info = doc.extract_image(images[0][0]) or {}
            exts.add((info.get("ext") or "").lower())
            ppis.append((info.get("width") or 0) * 72 / page.rect.width)
    if exts <= {"png"}:
        return "screenshot"
    if exts <= {"jpeg", "jpg"} and ppis and max(ppis) < PHONE_MAX_PPI:
        return "phone_jpeg"
    return "scan"
