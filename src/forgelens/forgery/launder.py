"""Launder statements the way people re-save them, to remove file-level traces.

``reprint``
    Re-distil the PDF with Ghostscript, as "Print to PDF" or "Save as PDF" would. The text
    stays selectable, but the file is rebuilt from scratch: one save section, one content
    stream per page, all fonts embedded and fresh, equal creation and modification dates.
``raster``
    Render every page to a JPEG image and wrap the images in a new PDF, like a screenshot
    or a scan. The text layer disappears entirely.

Both are applied to genuine statements as well as forgeries, because applicants often
re-save genuine statements too. A detector must not treat re-saving itself as forgery.
Page geometry is unchanged, so masks of the original edits stay valid.
"""

from __future__ import annotations

import copy
import random
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

METHODS = ("reprint", "raster")


def ghostscript() -> str | None:
    """Return the Ghostscript executable if installed (``brew install ghostscript`` on macOS)."""
    for name in ("gs", "gswin64c", "gswin32c"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _pdf_date(dt: datetime) -> str:
    return dt.strftime("D:%Y%m%d%H%M%S+05'30'")


def _laundered_at(record: dict, rng: random.Random) -> datetime:
    base = date.fromisoformat(record["generated_on"])
    if record.get("forgery", {}).get("edited_at"):
        base = datetime.fromisoformat(record["forgery"]["edited_at"]).date()
    return datetime.combine(base, datetime.min.time()) + timedelta(
        days=rng.randint(0, 10), hours=rng.randint(9, 22), minutes=rng.randint(0, 59))


def _reprint(src: Path, out: Path, when: datetime) -> None:
    gs = ghostscript()
    if gs is None:
        raise RuntimeError("Ghostscript not found. Install it (macOS: brew install ghostscript; "
                           "Ubuntu: apt install ghostscript)")
    stamp = _pdf_date(when)
    cmd = [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite",
           "-dCompatibilityLevel=1.7", "-dEmbedAllFonts=true", "-dSubsetFonts=true",
           "-o", str(out),
           "-c", "<< /NeverEmbed [ ] >> setdistillerparams",  # embed even standard fonts
           "-f", str(src),
           "-c", f"[ /CreationDate ({stamp}) /ModDate ({stamp}) /DOCINFO pdfmark"]
    subprocess.run(cmd, check=True, capture_output=True)


def _raster(src: Path, out: Path, when: datetime, dpi: int, quality: int) -> None:
    import pymupdf

    with pymupdf.open(src) as doc, pymupdf.open() as new:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            target = new.new_page(width=page.rect.width, height=page.rect.height)
            target.insert_image(target.rect, stream=pix.tobytes("jpeg", jpg_quality=quality))
        stamp = _pdf_date(when)
        new.set_metadata({"creationDate": stamp, "modDate": stamp, "producer": "",
                          "creator": "", "title": "", "author": ""})
        new.save(out, garbage=3, deflate=True)


def launder(src_pdf: str | Path, record: dict, out_pdf: str | Path, *, method: str,
            seed: int = 0, dpi: int = 150, jpeg_quality: int = 85) -> dict:
    """Write a laundered copy of ``src_pdf`` and return its updated label record.

    ``record`` is the genuine or forged label of the source file. The returned record keeps
    the same label and edits and adds a ``laundering`` entry.
    """
    if method not in METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from {', '.join(METHODS)}")
    rng = random.Random(seed)
    src_pdf, out_pdf = Path(src_pdf), Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    when = _laundered_at(record, rng)
    if method == "reprint":
        _reprint(src_pdf, out_pdf, when)
    else:
        _raster(src_pdf, out_pdf, when, dpi, jpeg_quality)

    laundered = copy.deepcopy(record)
    laundered.pop("layout", None)  # text positions are no longer guaranteed
    laundered.pop("masks", None)
    laundered.update({
        "statement_id": out_pdf.stem,
        "pdf": out_pdf.name,
        "laundered_from": record["statement_id"],
        "laundering": {
            "method": method,
            "seed": seed,
            "laundered_at": when.isoformat(),
            "dpi": dpi if method == "raster" else None,
            "jpeg_quality": jpeg_quality if method == "raster" else None,
            "tool": "ghostscript" if method == "reprint" else "pymupdf",
        },
    })
    return laundered
