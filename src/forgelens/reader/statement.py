"""Read the transaction table and account summary from a statement PDF.

This reader uses only what is printed in the PDF, never the generator's ground truth, so it
works on forged and real statements alike and on many layouts:

* The table header is the line that has a balance label plus debit- and credit-like labels
  (``Withdrawal``/``Debit``/``Dr``, ``Deposit``/``Credit``/``Cr``) and is followed by dated
  rows. Labels that start with "Total" (summary boxes) are ignored.
* Numeric columns are right-aligned, so each amount is assigned to the column whose right
  edge is nearest. The edge is measured from the amounts under each header label, because a
  label may be centred over its column or overflow it; the label's own right edge is the
  fallback.
* Every transaction row has a balance cell; the row's date is the leftmost date on that
  line. A line reading "Opening balance" (or "B/F") is the opening-balance row.
* Pages that continue the table without repeating its header use the columns of the last
  page that had one.
* The account summary may sit above the table or below it, with values under their labels
  or beside them.
* Amounts may use Indian (12,34,567.50), western (1,234,567.50) or no digit grouping and may
  end in ``Cr``/``Dr``.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from .cells import Cell, read_cells
from .document import open_pdf

AMOUNT_RE = re.compile(
    r"^(?P<num>-?(?:\d{1,3}(?:,\d{2,3})+|\d+)\.\d{2})\s*(?P<sfx>\(?(?:Cr|CR|cr|Dr|DR|dr)\)?)?$"
)
DATE_RE = re.compile(r"^\d{1,2}([-/. ])(\d{1,2}|[A-Za-z]{3})\1\d{2,4}$")
COUNT_RE = re.compile(r"\((\d+)\)")
OPENING_RE = re.compile(r"^(opening balance|balance b/?f|balance brought forward|b/?f)$", re.IGNORECASE)

SUMMARY_LABELS = {
    "opening": ("opening balance",),
    "total_debits": ("total debit", "total withdrawal"),
    "total_credits": ("total credit", "total deposit"),
    "closing": ("closing balance",),
}


def parse_amount(text: str) -> Decimal | None:
    """Return the value of a printed amount, or None if ``text`` is not an amount."""
    m = AMOUNT_RE.match(text.strip())
    if not m:
        return None
    value = Decimal(m.group("num").replace(",", ""))
    if m.group("sfx") and "d" in m.group("sfx").lower():
        value = -value  # "Dr" balance means overdrawn
    return value


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
    cells: dict[str, Cell] = field(default_factory=dict)  # date, value_date, debit, credit, balance


@dataclass
class ParsedStatement:
    rows: list[Row] = field(default_factory=list)
    opening_row: Row | None = None
    summary: dict[str, Decimal] = field(default_factory=dict)
    summary_cells: dict[str, Cell] = field(default_factory=dict)
    summary_counts: dict[str, int] = field(default_factory=dict)
    columns: dict[int, dict[str, float]] = field(default_factory=dict)  # page -> right edges
    header_labels: dict[int, list[str]] = field(default_factory=dict)  # page -> header texts
    header_top: dict[int, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.rows)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def _is_debit_label(text: str) -> bool:
    w = _words(text)
    return bool(w) and w[0] != "total" and any(
        x.startswith(("withdraw", "debit")) or x == "dr" for x in w)


def _is_credit_label(text: str) -> bool:
    w = _words(text)
    return bool(w) and w[0] != "total" and any(
        x.startswith(("deposit", "credit")) or x == "cr" for x in w)


def _find_header(cells: list[Cell]):
    """Return (labels, band_top, band_bottom, band_cells) for the table header, or None.

    ``labels`` maps ``debit``, ``credit`` and ``balance`` to their header cells.
    """
    for bal in cells:
        if "balance" not in bal.text.lower() or len(bal.text) > 30 or bal.text.lower().startswith(
                ("opening", "total")):
            continue
        band = [c for c in cells if bal.bbox[1] - 16 <= c.bbox[1] < bal.bbox[3] - 1
                and c.bbox[2] <= bal.bbox[2] + 1]
        debit = next((c for c in band if _is_debit_label(c.text)), None)
        credit = next((c for c in band if _is_credit_label(c.text) and c is not debit), None)
        if not (debit and credit) or not (debit.bbox[2] < bal.bbox[2] and
                                          credit.bbox[2] < bal.bbox[2]):
            continue
        # Header cells are the band's cells that sit between the leftmost label and Balance.
        top = min(c.bbox[1] for c in band)
        bottom = max(c.bbox[3] for c in band)
        below = [c for c in cells if bottom <= c.bbox[1] <= bottom + 60]
        if not any(DATE_RE.match(c.text) or OPENING_RE.match(c.text) for c in below):
            continue  # a summary box with similar labels, not the table header
        return {"debit": debit, "credit": credit, "balance": bal}, top, bottom, band
    return None


def _under(label: Cell, cell: Cell) -> bool:
    """True when an amount sits under a header label or ends near the label's right edge."""
    overlaps = cell.bbox[0] < label.bbox[2] and cell.bbox[2] > label.bbox[0]
    return overlaps or abs(cell.bbox[2] - label.bbox[2]) < 14


def _densest_median(values: list[float], width: float = 2.0) -> tuple[float, int]:
    """Median and size of the largest group of values that lie within ``width`` of each other."""
    values = sorted(values)
    best, start = (0, 0, -1), 0
    for end in range(len(values)):
        while values[end] - values[start] > width:
            start += 1
        if end - start + 1 > best[0]:
            best = (end - start + 1, start, end)
    count, start, end = best
    return (statistics.median(values[start:end + 1]) if count else 0.0), count


def _column_offsets(headers: dict[int, tuple], by_page: dict[int, list[Cell]]) -> dict[str, float]:
    """How far right of each header label its column of amounts ends, over all pages."""
    offsets = {}
    for key in ("debit", "credit", "balance"):
        diffs = []
        for page_no, (labels, _, bottom, _) in headers.items():
            label = labels[key]
            diffs += [c.bbox[2] - label.bbox[2] for c in by_page[page_no]
                      if c.bbox[1] >= bottom and parse_amount(c.text) is not None
                      and _under(label, c)]
        offset, count = _densest_median(diffs)
        offsets[key] = offset if count >= 2 else 0.0
    return offsets


def _columns(labels: dict[str, Cell], offsets: dict[str, float]) -> dict[str, float]:
    cols = {k: label.bbox[2] + offsets[k] for k, label in labels.items()}
    edges = sorted(cols.values())
    if any(b - a < 3 for a, b in pairwise(edges)):  # two labels over one column
        return {k: label.bbox[2] for k, label in labels.items()}
    return cols


def _assign(cols: dict[str, float], cell: Cell) -> str | None:
    column = min(cols, key=lambda c: abs(cols[c] - cell.bbox[2]))
    return column if abs(cols[column] - cell.bbox[2]) < 14 else None


def _parse_summary(candidates: list[Cell], parsed: ParsedStatement) -> None:
    for key, names in SUMMARY_LABELS.items():
        label = next((c for c in candidates if c.text.lower().startswith(names)), None)
        if label is None:
            continue
        m = COUNT_RE.search(label.text)
        if m:
            parsed.summary_counts[key] = int(m.group(1))
        amounts = [c for c in candidates if parse_amount(c.text) is not None]
        beside = [c for c in amounts if c.page == label.page and abs(c.baseline - label.baseline) < 2
                  and c.bbox[0] > label.bbox[2]]
        below = [c for c in amounts if c.page == label.page and c.bbox[1] >= label.bbox[3] - 1
                 and c.bbox[1] - label.bbox[3] < 40
                 and c.bbox[0] < label.bbox[2] + 2 and c.bbox[2] > label.bbox[0] - 2]
        value = None
        if beside:
            value = min(beside, key=lambda c: c.bbox[0])
        elif below:
            value = min(below, key=lambda c: c.bbox[1])
        if value is not None:
            parsed.summary[key] = parse_amount(value.text)
            parsed.summary_cells[key] = value


def parse_cells(cells: list[Cell], pages: int) -> ParsedStatement:
    """Parse the account summary and transaction rows from the cells of a document."""
    parsed = ParsedStatement()
    by_page: dict[int, list[Cell]] = {p: [] for p in range(pages)}
    for c in cells:
        by_page[c.page].append(c)
    used: set[int] = set()  # ids of cells that belong to the header or table rows
    index = 0
    headers = {p: h for p in range(pages) if (h := _find_header(by_page[p])) is not None}
    offsets = _column_offsets(headers, by_page)
    cols: dict[str, float] | None = None
    for page_no in range(pages):
        page_cells = by_page[page_no]
        header = headers.get(page_no)
        if header is not None:
            labels, band_top, band_bottom, band = header
            cols = _columns(labels, offsets)
            parsed.header_labels[page_no] = [c.text for c in sorted(band, key=lambda c: (
                c.bbox[0], c.bbox[1]))]
            parsed.header_top.setdefault(page_no, band_top)
            used.update(id(c) for c in page_cells
                        if band_top - 1 <= c.bbox[1] and c.bbox[3] <= band_bottom + 1)
        elif cols is not None:
            band_bottom = float("-inf")  # the table continues from the top of the page
        else:
            continue
        parsed.columns[page_no] = cols

        body = sorted((c for c in page_cells if c.bbox[1] >= band_bottom),
                      key=lambda c: (c.baseline, c.bbox[0]))
        balances = [c for c in body if parse_amount(c.text) is not None
                    and _assign(cols, c) == "balance"]
        for bal in balances:
            line = [c for c in body if abs(c.baseline - bal.baseline) < 1.5]
            if any(OPENING_RE.match(c.text) for c in line):
                if parsed.opening_row is not None or parsed.rows:
                    continue  # e.g. "Opening Balance" in a summary box below the table
                parsed.opening_row = Row(-1, page_no, "", None, None, parse_amount(bal.text), True,
                                         {"balance": bal})
                used.update(id(c) for c in line)
                continue
            dates = sorted((c for c in line if DATE_RE.match(c.text)
                            and c.bbox[2] < min(cols.values())), key=lambda c: c.bbox[0])
            if not dates:
                continue  # a balance-like number without a date: not a transaction row
            row_cells = {"date": dates[0], "balance": bal}
            if len(dates) > 1:
                row_cells["value_date"] = dates[1]
            values: dict[str, Decimal] = {}
            for c in line:
                if c is bal or parse_amount(c.text) is None:
                    continue
                column = _assign(cols, c)
                if column in ("debit", "credit"):
                    values[column] = parse_amount(c.text)
                    row_cells[column] = c
            parsed.rows.append(Row(index, page_no, dates[0].text, values.get("debit"),
                                   values.get("credit"), parse_amount(bal.text), False, row_cells))
            used.update(id(c) for c in line)
            index += 1

    # Everything not in the header or on a row's line can hold the summary.
    _parse_summary([c for c in cells if id(c) not in used], parsed)

    if not parsed.rows:
        parsed.warnings.append("No transaction table found")
    return parsed


def parse_statement(pdf_path: str | Path, password: str | None = None) -> ParsedStatement:
    """Parse the account summary and transaction rows printed in ``pdf_path``.

    Raises ``PasswordRequired`` or ``UnreadablePDF`` (see ``forgelens.reader.document``)
    when the file cannot be opened.
    """
    with open_pdf(pdf_path, password) as doc:
        return parse_cells(read_cells(doc), doc.page_count)
