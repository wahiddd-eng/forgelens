"""Read the transaction table and account summary from a statement PDF.

This reader uses only what is printed in the PDF, never the generator's ground truth, so it
works on forged and real statements alike and on many layouts:

* The table header is the line that has a balance label plus debit- and credit-like labels
  (``Withdrawal``/``Debit``/``Dr``, ``Deposit``/``Credit``/``Cr``) and is followed by dated
  rows. Labels that start with "Total" (summary boxes) are ignored.
* Numeric columns are right-aligned, so each amount is assigned to the column whose header
  has the nearest right edge.
* Every transaction row has a balance cell; the row's date is the leftmost date on that
  line. A line reading "Opening balance" (or "B/F") is the opening-balance row.
* The account summary may sit above the table or below it, with values under their labels
  or beside them.
* Amounts may use Indian (12,34,567.50), western (1,234,567.50) or no digit grouping and may
  end in ``Cr``/``Dr``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

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
class Cell:
    """A printed text span with its position and style (PDF points, top-left origin)."""

    page: int
    text: str
    bbox: tuple[float, float, float, float]
    origin: tuple[float, float]
    size: float
    font: str
    color: int

    @property
    def baseline(self) -> float:
        return self.origin[1]

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
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.rows)


def full_font_names(doc, page_no: int) -> dict[str, str]:
    """Map shortened span font names to the page's full font names.

    Text extraction reports at most about 24 characters of a font name
    (``Liberation-Serif-Bold-It``); the page's font list has the full name.
    """
    names = [f[3].split("+", 1)[-1] for f in doc.get_page_fonts(page_no)]
    lookup = {n: n for n in names}

    def resolve(short: str) -> str:
        if short in lookup:
            return lookup[short]
        matches = [n for n in names if n.startswith(short)]
        return matches[0] if len(matches) == 1 else short

    return _ResolvingDict(resolve)


class _ResolvingDict(dict):
    def __init__(self, resolve):
        super().__init__()
        self._resolve = resolve

    def __missing__(self, key):
        value = self._resolve(key)
        self[key] = value
        return value


def read_cells(doc, gap: float = 3.0) -> list[Cell]:
    """Return text cells with positions, splitting runs where characters are ``gap`` apart.

    PDF text extractors join neighbouring table cells into one run when they share a font
    and sit on the same line. A gap wider than a normal letter spacing marks a new cell.
    """
    out = []
    for page_no, page in enumerate(doc):
        fonts = full_font_names(doc, page_no)
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                for s in line["spans"]:
                    chars = s["chars"]
                    groups, current = [], []
                    for ch in chars:
                        if current and ch["bbox"][0] - current[-1]["bbox"][2] > max(gap, 0.35 * s["size"]):
                            groups.append(current)
                            current = []
                        current.append(ch)
                    if current:
                        groups.append(current)
                    for g in groups:
                        text = "".join(ch["c"] for ch in g)
                        stripped = text.strip()
                        if not stripped:
                            continue
                        visible = [ch for ch in g if ch["c"].strip()]
                        x0 = min(ch["bbox"][0] for ch in visible)
                        x1 = max(ch["bbox"][2] for ch in visible)
                        bbox = (x0, s["bbox"][1], x1, s["bbox"][3])
                        origin = (visible[0]["origin"][0], visible[0]["origin"][1])
                        out.append(Cell(page_no, stripped, bbox, origin, s["size"],
                                        fonts[s["font"]], s["color"]))
    return out


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
    """Return (columns, band_top, band_bottom) for the table header on one page, or None."""
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
        return {"debit": debit.bbox[2], "credit": credit.bbox[2], "balance": bal.bbox[2]}, top, bottom
    return None


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


def parse_statement(pdf_path: str | Path) -> ParsedStatement:
    """Parse the account summary and transaction rows printed in ``pdf_path``."""
    import pymupdf

    parsed = ParsedStatement()
    with pymupdf.open(pdf_path) as doc:
        cells = read_cells(doc)
        pages = doc.page_count

    by_page = {p: [c for c in cells if c.page == p] for p in range(pages)}
    used: set[int] = set()  # ids of cells that belong to the header or table rows
    index = 0
    for page_no in range(pages):
        page_cells = by_page[page_no]
        header = _find_header(page_cells)
        if header is None:
            continue
        cols, band_top, band_bottom = header
        parsed.columns[page_no] = cols
        used.update(id(c) for c in page_cells if band_top - 1 <= c.bbox[1] and c.bbox[3] <= band_bottom + 1)

        body = sorted((c for c in page_cells if c.bbox[1] >= band_bottom),
                      key=lambda c: (c.baseline, c.bbox[0]))
        balances = [c for c in body if parse_amount(c.text) is not None and _assign(cols, c) == "balance"]
        for bal in balances:
            line = [c for c in body if abs(c.baseline - bal.baseline) < 1.5]
            if any(OPENING_RE.match(c.text) for c in line):
                if parsed.opening_row is not None or parsed.rows:
                    continue  # e.g. "Opening Balance" in a summary box below the table
                parsed.opening_row = Row(-1, page_no, "", None, None, parse_amount(bal.text), True,
                                         {"balance": bal})
                used.update(id(c) for c in line)
                continue
            dates = sorted((c for c in line if DATE_RE.match(c.text) and c.bbox[2] < min(cols.values())),
                           key=lambda c: c.bbox[0])
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
