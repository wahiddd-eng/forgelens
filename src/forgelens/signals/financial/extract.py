"""Read the transaction table and account summary from a statement PDF.

This parser uses only what is printed in the PDF, never the generator's ground truth, so
it works on forged and real statements alike. It finds the table header on each page,
works out the debit, credit and balance columns from the header labels, and groups text
on the same baseline into rows. A row starts with a date in the first column.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

AMOUNT_RE = re.compile(r"^-?\d{1,3}(,\d{2,3})*\.\d{2}$|^-?\d+\.\d{2}$")
DATE_RE = re.compile(r"^\d{2}[-/.]\d{2}[-/.]\d{2,4}$|^\d{2} [A-Za-z]{3} \d{2,4}$")
COUNT_RE = re.compile(r"\((\d+)\)")

DEBIT_WORDS = ("withdrawal", "debit", "dr")
CREDIT_WORDS = ("deposit", "credit", "cr")


def parse_amount(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


@dataclass
class _Span:
    page: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    baseline: float


@dataclass
class Row:
    """One table row as printed. ``debit``/``credit`` are None when the cell is empty."""

    index: int
    page: int
    date: str
    debit: Decimal | None
    credit: Decimal | None
    balance: Decimal | None
    is_opening: bool = False


@dataclass
class ParsedStatement:
    rows: list[Row] = field(default_factory=list)
    opening_row: Row | None = None
    summary: dict[str, Decimal] = field(default_factory=dict)
    summary_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.rows)


def _spans(doc) -> list[_Span]:
    out = []
    for page_no, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for s in line["spans"]:
                    text = s["text"].strip()
                    if text:
                        x0, y0, x1, y1 = s["bbox"]
                        out.append(_Span(page_no, text, x0, y0, x1, y1, s["origin"][1]))
    return out


def _header_columns(page_spans: list[_Span]) -> tuple[dict[str, float], float] | None:
    """Return the right edge of the debit, credit and balance headers and the header bottom.

    The header is the line holding a span that reads exactly "Balance" together with
    debit- and credit-like labels nearby; summary labels such as "Closing Balance" are
    separate spans and are ignored.
    """
    for bal in (s for s in page_spans if s.text.lower() == "balance"):
        band = [s for s in page_spans if abs(s.y1 - bal.y1) < 14 and s.x1 <= bal.x1 + 1]
        debit = credit = None
        for s in band:
            words = re.findall(r"[a-z]+", s.text.lower())
            if debit is None and any(w in DEBIT_WORDS for w in words):
                debit = s
            elif credit is None and any(w in CREDIT_WORDS for w in words):
                credit = s
        if debit and credit:
            bottom = max(s.y1 for s in band)
            return {"debit": debit.x1, "credit": credit.x1, "balance": bal.x1}, bottom
    return None


def _summary(page_spans: list[_Span], table_top: float, parsed: ParsedStatement) -> None:
    labels = {
        "opening": ("opening balance",),
        "total_debits": ("total debits", "total withdrawals"),
        "total_credits": ("total credits", "total deposits"),
        "closing": ("closing balance",),
    }
    top = [s for s in page_spans if s.y1 <= table_top]
    for key, names in labels.items():
        label = next((s for s in top if any(s.text.lower().startswith(n) for n in names)), None)
        if label is None:
            continue
        m = COUNT_RE.search(label.text)
        if m:
            parsed.summary_counts[key] = int(m.group(1))
        below = [s for s in top if AMOUNT_RE.match(s.text) and s.y0 >= label.y1 - 1
                 and s.x0 < label.x1 + 2 and s.x1 > label.x0 - 2]
        if below:
            value = min(below, key=lambda s: s.y0)
            parsed.summary[key] = parse_amount(value.text)


def parse_statement(pdf_path: str | Path) -> ParsedStatement:
    """Parse the account summary and transaction rows printed in ``pdf_path``."""
    import pymupdf

    parsed = ParsedStatement()
    with pymupdf.open(pdf_path) as doc:
        spans = _spans(doc)
        pages = doc.page_count

    index = 0
    for page_no in range(pages):
        page_spans = [s for s in spans if s.page == page_no]
        header = _header_columns(page_spans)
        if header is None:
            continue
        cols, header_bottom = header
        if page_no == 0 or not parsed.summary:
            _summary(page_spans, header_bottom, parsed)

        body = [s for s in page_spans if s.y0 >= header_bottom]
        date_limit = min(cols.values()) * 0.25
        starts = sorted((s for s in body if DATE_RE.match(s.text) and s.x1 <= date_limit),
                        key=lambda s: s.baseline)
        openings = [s for s in body if s.text.upper() == "OPENING BALANCE"]
        anchors = [(s, False) for s in starts] + [(s, True) for s in openings]
        anchors.sort(key=lambda a: a[0].baseline)

        for anchor, is_opening in anchors:
            line = [s for s in body if abs(s.baseline - anchor.baseline) < 1.5
                    and AMOUNT_RE.match(s.text)]
            cells: dict[str, Decimal] = {}
            for s in line:
                column = min(cols, key=lambda c: abs(cols[c] - s.x1))
                if abs(cols[column] - s.x1) < 12:
                    cells[column] = parse_amount(s.text)
            if is_opening:
                parsed.opening_row = Row(-1, page_no, "", None, None, cells.get("balance"), True)
                continue
            if any(abs(a.baseline - anchor.baseline) < 1.5 for a, op in anchors if op):
                continue  # the date printed on the opening-balance line
            parsed.rows.append(Row(index, page_no, anchor.text, cells.get("debit"),
                                   cells.get("credit"), cells.get("balance")))
            index += 1

    if not parsed.rows:
        parsed.warnings.append("No transaction table found")
    return parsed
