"""Locate where each statement field was drawn in the rendered PDF.

Forgery scripts need the exact position, font, size and colour of a value to replace it,
and image-forensics models need pixel masks of what was changed. This module reads the
rendered PDF back with PyMuPDF and matches every value in the ground truth to the text
span that shows it. Positions are in PDF points with the origin at the top-left corner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .banks import BankProfile
from .models import Statement
from .money import format_inr

WHITE = 0xFFFFFF


@dataclass
class _Span:
    page: int
    text: str
    bbox: tuple[float, float, float, float]
    origin: tuple[float, float]
    size: float
    font: str
    color: int

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "text": self.text,
            "bbox": [round(v, 3) for v in self.bbox],
            "origin": [round(v, 3) for v in self.origin],
            "size": round(self.size, 3),
            "font": self.font,
            "color": self.color,
        }


class LayoutError(RuntimeError):
    """Raised when a value from the ground truth cannot be found in the PDF."""


def _spans(doc) -> list[_Span]:
    out: list[_Span] = []
    for page_no, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for s in line["spans"]:
                    text = s["text"].strip()
                    if text:
                        out.append(_Span(page_no, text, tuple(s["bbox"]), tuple(s["origin"]),
                                         s["size"], s["font"], s["color"]))
    return out


def locate_fields(pdf_path: str | Path, statement: Statement, bank: BankProfile) -> dict:
    """Return a layout record mapping every summary value and table cell to its span.

    The record has ``page_size`` (width, height in points), ``fields`` (header and summary
    values) and ``rows`` (one entry per transaction with its date, amount and balance cells).
    """
    import pymupdf

    def fmt(d: date) -> str:
        return d.strftime(bank.date_format)

    with pymupdf.open(pdf_path) as doc:
        width, height = doc[0].rect.width, doc[0].rect.height
        spans = _spans(doc)

    # The table header repeats on every page; its "Balance" label is drawn in white.
    header_bottom = {s.page: s.bbox[3] for s in spans if s.text == "Balance" and s.color == WHITE}
    if 0 not in header_bottom:
        raise LayoutError("Transaction table header not found on page 1")
    right_edge = 0.85 * width

    def first(pred, what: str) -> _Span:
        for s in spans:
            if pred(s):
                return s
        raise LayoutError(f"Could not locate {what}")

    page0_top = [s for s in spans if s.page == 0 and s.bbox[3] <= header_bottom[0]]

    def in_summary(value: str, what: str) -> _Span:
        for s in page0_top:
            if s.text == value:
                return s
        raise LayoutError(f"Could not locate {what} ({value})")

    c = statement.customer
    fields = {
        "customer_name": in_summary(c.name, "customer name"),
        "account_number": in_summary(c.account_number, "account number"),
        "summary_opening": in_summary(format_inr(statement.opening_balance), "opening balance"),
        "summary_total_debits": in_summary(format_inr(statement.total_debits), "total debits"),
        "summary_total_credits": in_summary(format_inr(statement.total_credits), "total credits"),
        "summary_closing": in_summary(format_inr(statement.closing_balance), "closing balance"),
    }

    # Walk the table body in reading order, matching balances one row at a time.
    body = [s for s in spans if s.page in header_bottom and s.bbox[1] >= header_bottom[s.page]]
    cursor = 0

    def next_balance(value: str, what: str) -> _Span:
        nonlocal cursor
        for i in range(cursor, len(body)):
            s = body[i]
            if s.text == value and s.bbox[2] >= right_edge:
                cursor = i + 1
                return s
        raise LayoutError(f"Could not locate {what} ({value})")

    def same_line(anchor: _Span, value: str, x_max: float, x_min: float = 0.0) -> _Span | None:
        for s in body:
            if (s.page == anchor.page and s.text == value and abs(s.origin[1] - anchor.origin[1]) < 1.0
                    and x_min <= s.bbox[0] and s.bbox[2] <= x_max):
                return s
        return None

    fields["opening_row_balance"] = next_balance(
        format_inr(statement.opening_balance), "opening balance row"
    )

    rows = []
    for i, t in enumerate(statement.transactions):
        bal = next_balance(format_inr(t.balance), f"balance of row {i}")
        amount = t.debit if t.debit > 0 else t.credit
        amt = same_line(bal, format_inr(amount), x_max=bal.bbox[0])
        if amt is None:
            raise LayoutError(f"Could not locate amount of row {i}")
        dt = same_line(bal, fmt(t.txn_date), x_max=0.2 * width)
        vdt = same_line(bal, fmt(t.value_date), x_max=amt.bbox[0], x_min=0.2 * width)
        if dt is None or vdt is None:
            raise LayoutError(f"Could not locate dates of row {i}")
        rows.append({
            "row": i,
            "page": bal.page,
            "amount_column": "debit" if t.debit > 0 else "credit",
            "txn_date": dt.to_dict(),
            "value_date": vdt.to_dict(),
            "amount": amt.to_dict(),
            "balance": bal.to_dict(),
        })

    return {
        "page_size": [round(width, 3), round(height, 3)],
        "pages": max(header_bottom) + 1,
        "fields": {k: v.to_dict() for k, v in fields.items()},
        "rows": rows,
    }
