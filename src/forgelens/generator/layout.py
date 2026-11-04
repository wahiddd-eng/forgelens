"""Locate where each statement field was drawn in the rendered PDF.

Forgery scripts need the exact position, font, size and colour of a value to replace it,
and image-forensics models need pixel masks of what was changed. This module reads the
rendered PDF back with the same table reader the financial signal uses, checks every value
against the ground truth, and records the text cell that shows it. Positions are in PDF
points with the origin at the top-left corner.
"""

from __future__ import annotations

from pathlib import Path

from ..reader import open_pdf, parse_cells, read_cells
from .banks import BankProfile
from .models import Statement


class LayoutError(RuntimeError):
    """Raised when a value from the ground truth cannot be found in the PDF."""


def locate_fields(pdf_path: str | Path, statement: Statement, bank: BankProfile) -> dict:
    """Return a layout record mapping every summary value and table cell to its text cell.

    The record has ``page_size`` (width, height in points), ``pages``, ``fonts`` (the fonts
    the PDF actually embeds, which depend on the fonts installed where it was rendered),
    ``fields`` (customer name, account number and summary values) and ``rows`` (one entry
    per transaction with its date, amount and balance cells).
    """
    with open_pdf(pdf_path) as doc:
        width, height = doc[0].rect.width, doc[0].rect.height
        pages = doc.page_count
        fonts = sorted({f[3].split("+", 1)[-1] for p in range(pages) for f in doc.get_page_fonts(p)})
        cells = read_cells(doc)
    parsed = parse_cells(cells, pages)
    page0 = [c for c in cells if c.page == 0]

    if len(parsed.rows) != len(statement.transactions):
        raise LayoutError(f"Read {len(parsed.rows)} rows but the statement has "
                          f"{len(statement.transactions)}")
    rows = []
    for row, t in zip(parsed.rows, statement.transactions):
        amount = t.debit if t.debit > 0 else t.credit
        column = "debit" if t.debit > 0 else "credit"
        printed = row.debit if column == "debit" else row.credit
        if row.balance != t.balance or printed != amount or column not in row.cells:
            raise LayoutError(f"Row {row.index} does not match the ground truth")
        entry = {
            "row": row.index,
            "page": row.page,
            "amount_column": column,
            "txn_date": row.cells["date"].to_dict(),
            "amount": row.cells[column].to_dict(),
            "balance": row.cells["balance"].to_dict(),
        }
        if "value_date" in row.cells:
            entry["value_date"] = row.cells["value_date"].to_dict()
        rows.append(entry)

    if parsed.opening_row is None or parsed.opening_row.balance != statement.opening_balance:
        raise LayoutError("Opening-balance row not found")

    def exact(value: str, what: str) -> dict:
        for c in page0:
            if c.text == value:
                return c.to_dict()
        raise LayoutError(f"Could not locate {what} ({value})")

    fields = {
        "customer_name": exact(statement.customer.name, "customer name"),
        "account_number": exact(statement.customer.account_number, "account number"),
        "opening_row_balance": parsed.opening_row.cells["balance"].to_dict(),
    }
    expected = {
        "opening": statement.opening_balance,
        "total_debits": statement.total_debits,
        "total_credits": statement.total_credits,
        "closing": statement.closing_balance,
    }
    names = {"opening": "summary_opening", "total_debits": "summary_total_debits",
             "total_credits": "summary_total_credits", "closing": "summary_closing"}
    for key, value in expected.items():
        if key in parsed.summary:
            if parsed.summary[key] != value:
                raise LayoutError(f"Summary {key} does not match the ground truth")
            fields[names[key]] = parsed.summary_cells[key].to_dict()

    return {
        "page_size": [round(width, 3), round(height, 3)],
        "pages": pages,
        "fonts": fonts,
        "fields": fields,
        "rows": rows,
    }
