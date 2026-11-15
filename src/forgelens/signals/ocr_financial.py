"""Running-balance arithmetic read by OCR from page images.

The financial-consistency signal reads a PDF's text layer, so it abstains on scans,
screenshots and rasterised statements, where a forger's edit is then invisible to every
rule-based signal. This signal reads the page images with an OCR engine (EasyOCR), turns
the words into the same text cells the PDF reader produces, parses the table with the same
reader (``reader.statement.parse_cells``), and checks the balances row by row.

OCR misreads look like edits, so breaks a misread explains are set aside:

* a balance misread by ``e`` breaks the chain at that row by ``+e`` and at the next by
  ``-e``: such cancelling pairs are dropped;
* a break on a row whose amount or balance was read with low confidence is dropped;
* a break that adding back would turn the amount read into one that ends with it
  ("500.00" read for "6,500.00": leading digits lost) is dropped when the OCR was unsure of
  that amount (a forger's printed edit is read confidently);
* a break after rows the reader skipped (a misread date makes the reader miss a row, which
  then breaks the chain by that row's amount) is dropped: such rows leave figures in the
  amount columns between two parsed rows.

What remains (an amount changed without the balances following, or a balance changed
without the next rows following) is evidence of an edit. The score rises with the number of
such breaks; the signal abstains when it cannot read a table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import numpy as np

TOLERANCE = Decimal("0.011")
MIN_CONFIDENCE = 0.5  # below this, a break on the row may be the OCR's own mistake
TRUNCATION_CONFIDENCE = 0.85  # below this, a read that lost leading digits is explained
_NUMERIC = re.compile(r"^[\d,.\sOoIlSsBDCcRr()-]+$")
_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "s": "5", "B": "8"})


@dataclass
class OcrFinancialReport:
    rows: int = 0
    pages: int = 0
    breaks: int = 0  # rows where the balance does not follow
    explained: int = 0  # breaks set aside as OCR misreads
    summary_breaks: int = 0  # summary values (opening, closing, totals) the table contradicts
    findings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def abstained(self) -> bool:
        return self.error is not None or self.rows < 3

    @property
    def unexplained(self) -> int:
        return self.breaks - self.explained + self.summary_breaks

    @property
    def score(self) -> float:
        if self.abstained:
            return 0.5
        if self.unexplained == 0:
            return 0.0
        return min(1.0, 0.6 + 0.1 * self.unexplained)


def clean_text(text: str) -> str:
    """Undo common OCR confusions in numbers (O for 0, l for 1, ...) and stray spaces.

    Only text that looks like an amount is touched: a Cr/Dr suffix is kept as written.
    """
    t = text.strip()
    if not _NUMERIC.match(t) or not any(ch.isdigit() for ch in t):
        return t
    m = re.match(r"^(.*?)(\s*\(?(?:Cr|CR|cr|Dr|DR|dr)\)?)?$", t)
    body, suffix = m.group(1), m.group(2) or ""
    body = body.translate(_FIX).replace(" ", "")
    if re.fullmatch(r"\d[\d,]*,\d{2}", body) and "." not in body:
        body = body[:-3] + "." + body[-2:]  # the decimal point read as a comma
    return body + suffix


class OcrReader:
    """EasyOCR, loaded once. ``read(rgb)`` gives (box, text, confidence) per text line."""

    def __init__(self, gpu: bool | None = None):
        import easyocr

        if gpu is None:
            import torch

            gpu = torch.cuda.is_available()
        self.reader = easyocr.Reader(["en"], gpu=gpu, verbose=False)

    def read(self, rgb: np.ndarray):
        # width_ths low: keep table cells that sit close together as separate boxes
        return self.reader.readtext(rgb, detail=1, paragraph=False, width_ths=0.3)


def ocr_cells(results, page: int, dpi: int) -> tuple[list, dict[int, float]]:
    """Reader cells (PDF points) from OCR results, and each cell's confidence by ``id``."""
    from forgelens.reader.cells import Cell

    scale = 72.0 / dpi
    cells, conf = [], {}
    for box, text, c in results:
        text = clean_text(text)
        if not text:
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        x0, y0, x1, y1 = (min(xs) * scale, min(ys) * scale, max(xs) * scale, max(ys) * scale)
        height = y1 - y0
        cell = Cell(page=page, text=text, bbox=(x0, y0, x1, y1), origin=(x0, y1 - 0.2 * height),
                    size=0.75 * height, font="OCR", color=0)
        cells.append(cell)
        conf[id(cell)] = float(c)
    return cells, conf


def _y(row) -> tuple[int, float]:
    c = row.cells.get("balance") or row.cells.get("date") or next(iter(row.cells.values()))
    return row.page, (c.bbox[1] + c.bbox[3]) / 2


def _skipped_between(parsed, cells: list, a, b) -> bool:
    """True when figures in the amount columns lie between rows ``a`` and ``b`` but belong to
    no parsed row: the reader skipped a row there."""
    used = {id(c) for r in parsed.rows for c in r.cells.values()}
    used |= {id(c) for c in parsed.summary_cells.values()}
    (pa, ya), (pb, yb) = _y(a), _y(b)
    for c in cells:
        if id(c) in used or not any(ch.isdigit() for ch in c.text):
            continue
        edges = parsed.columns.get(c.page) or {}
        if not any(abs(c.bbox[2] - edges[k]) < 25 for k in ("debit", "credit", "balance")
                   if k in edges):
            continue
        y = (c.bbox[1] + c.bbox[3]) / 2
        after_a = (c.page, y) > (pa, ya + 2)
        before_b = (c.page, y) < (pb, yb - 2)
        header = parsed.header_top.get(c.page)
        if after_a and before_b and (header is None or y > header + 12):
            return True
    return False


def _digits(x: Decimal) -> str:
    return f"{abs(x):.2f}".replace(".", "")


def _truncated(row, delta: Decimal, conf: dict[int, float]) -> bool:
    """True when the break is the amount's lost leading digits, read without confidence."""
    for name, true_value in (("debit", (row.debit or 0) - delta),
                             ("credit", (row.credit or 0) + delta)):
        value, cell = getattr(row, name), row.cells.get(name)
        if value is None or cell is None or true_value <= value:
            continue
        if conf.get(id(cell), 1.0) < TRUNCATION_CONFIDENCE \
                and _digits(true_value).endswith(_digits(value)):
            return True
    return False


def check_rows(parsed, conf: dict[int, float], cells: list | None = None) -> OcrFinancialReport:
    """The balance chain of the parsed rows, with OCR-explained breaks set aside."""
    rows = [r for r in parsed.rows if r.balance is not None]
    report = OcrFinancialReport(rows=len(rows))
    if len(rows) < 3:
        return report
    deltas = []  # (row, delta) where the balance does not follow from the previous one
    prev = parsed.opening_row.balance if parsed.opening_row is not None else None
    for r in rows:
        if prev is not None and not r.is_opening:
            expected = prev + (r.credit or 0) - (r.debit or 0)
            d = r.balance - expected
            if abs(d) > TOLERANCE:
                deltas.append((r, d))
        prev = r.balance
    report.breaks = len(deltas)
    explained: set[int] = set()
    for (a, da), (b, db) in pairwise(deltas):
        if b.index == a.index + 1 and abs(da + db) <= TOLERANCE:
            explained |= {a.index, b.index}  # one balance misread: cancelling pair
    by_index = {r.index: r for r in rows}
    for r, d in deltas:
        own = [c for k, c in r.cells.items() if k in ("debit", "credit", "balance")]
        if own and min(conf.get(id(c), 1.0) for c in own) < MIN_CONFIDENCE:
            explained.add(r.index)
        if _truncated(r, d, conf):
            explained.add(r.index)
        prev_row = max((q for i, q in by_index.items() if i < r.index), key=lambda q: q.index,
                       default=parsed.opening_row)
        if cells is not None and prev_row is not None and _skipped_between(parsed, cells,
                                                                           prev_row, r):
            explained.add(r.index)
    report.explained = sum(1 for r, _ in deltas if r.index in explained)
    report.findings = [f"row {r.index + 1}: balance off by {d}" for r, d in deltas
                       if r.index not in explained]

    # The summary against the table: opening, closing and (when every amount was read
    # confidently, since one misread digit changes a total) the totals.
    def sure(cell) -> bool:
        return cell is None or conf.get(id(cell), 1.0) >= MIN_CONFIDENCE

    summary, cells = parsed.summary, parsed.summary_cells
    checks = []
    if parsed.opening_row is not None and parsed.opening_row.balance is not None:
        checks.append(("opening", parsed.opening_row.balance))
    checks.append(("closing", rows[-1].balance))
    amount_cells = [c for r in parsed.rows for k, c in r.cells.items() if k in ("debit", "credit")]
    skipped_any = any(r.index in explained for r, _ in deltas)
    if all(sure(c) for c in amount_cells) and not skipped_any:
        checks += [("total_debits", sum((r.debit for r in parsed.rows if r.debit is not None),
                                        Decimal(0))),
                   ("total_credits", sum((r.credit for r in parsed.rows if r.credit is not None),
                                         Decimal(0)))]
    for key, table_value in checks:
        if key in summary and sure(cells.get(key)) and abs(summary[key] - table_value) > TOLERANCE:
            report.summary_breaks += 1
            report.findings.append(f"summary {key} differs from the table by "
                                   f"{summary[key] - table_value}")
    return report


def check_images(pages: list[np.ndarray], reader: OcrReader, dpi: int) -> OcrFinancialReport:
    """OCR every page image, parse the statement, check the balances."""
    from forgelens.reader.statement import parse_cells

    cells, conf = [], {}
    for p, rgb in enumerate(pages):
        c, k = ocr_cells(reader.read(rgb), p, dpi)
        cells += c
        conf.update(k)
    try:
        parsed = parse_cells(cells, len(pages))
    except Exception as exc:  # noqa: BLE001 - an unreadable table means abstaining
        return OcrFinancialReport(pages=len(pages), error=type(exc).__name__)
    report = check_rows(parsed, conf, cells)
    report.pages = len(pages)
    if not parsed.rows:
        report.error = "no table read"
    return report


def check_pdf(pdf: str | Path, reader: OcrReader, dpi: int = 150,
              password: str | None = None) -> OcrFinancialReport:
    from forgelens.signals.image.pages import render_pages

    try:
        pages = render_pages(pdf, dpi=dpi, password=password)
    except Exception as exc:  # noqa: BLE001
        return OcrFinancialReport(error=type(exc).__name__)
    return check_images(pages, reader, dpi)
