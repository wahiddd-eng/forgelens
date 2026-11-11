"""Render a generated statement to HTML and PDF."""

from __future__ import annotations

import os
import warnings
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from .banks import BankProfile
from .models import Statement
from .money import format_amount

_env = Environment(
    loader=PackageLoader("forgelens.generator", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

# Relative column widths; the narration column takes whatever is left.
_WIDTH = {"sno": 6, "date": 10, "value_date": 10, "ref": 14, "debit": 11, "credit": 11,
          "balance": 12}


def _text_width_pct(chars: int, bank: BankProfile) -> float:
    """Approximate width of ``chars`` table characters plus cell padding, in % of the page."""
    usable = 774 if bank.orientation == "landscape" else 527  # A4 minus side margins, in pt
    return (chars * 0.6 * bank.base_font_size + 12) / usable * 100


def column_widths(bank: BankProfile) -> dict[str, float]:
    """Return percentage widths for the bank's columns, summing to 100.

    Date and amount columns are sized from the longest text they hold, so no cell overflows
    into its neighbour.
    """
    widths = {c: _WIDTH[c] for c in bank.columns if c != "narration"}
    date_chars = len(date(2026, 12, 28).strftime(bank.date_format))
    for c in ("date", "value_date"):
        if c in widths:
            widths[c] = max(_text_width_pct(date_chars, bank), 8)
    amount_chars = len(format_amount(Decimal("9999999.99"), bank.grouping))
    for c in ("debit", "credit"):
        if c in widths:
            widths[c] = max(_text_width_pct(amount_chars, bank), widths[c] * 0.75)
    if "balance" in widths:
        widths["balance"] = max(_text_width_pct(amount_chars + len(bank.balance_suffix), bank),
                                widths["balance"] * 0.75)
    if "narration" in bank.columns:
        widths["narration"] = max(100 - sum(widths.values()), 24)
    total = sum(widths.values())
    return {c: round(widths[c] * 100 / total, 2) for c in bank.columns}


def render_html(statement: Statement, bank: BankProfile) -> str:
    """Return the statement as an HTML string using the bank's layout template."""
    template = _env.get_template(bank.template)

    def fmt_date(d: date) -> str:
        return d.strftime(bank.date_format)

    def amt(value: Decimal) -> str:
        return format_amount(value, bank.grouping)

    def bal(value: Decimal) -> str:
        return format_amount(value, bank.grouping, bank.balance_suffix)

    return template.render(
        statement=statement, bank=bank, c=statement.customer, amt=amt, bal=bal,
        fmt_date=fmt_date, cols=list(bank.columns), widths=column_widths(bank),
    )


_IST = timezone(timedelta(hours=5, minutes=30))


@contextmanager
def _source_date(day: date):
    """Pin the timestamps that font subsetting writes into the PDF to the statement's date.

    Without this, the embedded font subsets carry the time of rendering, so the same seed
    gives different bytes on every run and a statement dated 2025 contains fonts stamped
    with today's date. ``SOURCE_DATE_EPOCH`` is the reproducible-builds convention that
    fontTools follows.
    """
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(int(datetime.combine(day, time(9, 0), _IST).timestamp()))
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old


def embedded_fonts(pdf_path: str | Path) -> list[str]:
    """Return the names of the fonts a PDF uses, without subset tags."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        return sorted({f[3].split("+", 1)[-1] for p in range(doc.page_count)
                       for f in doc.get_page_fonts(p)})


def _warn_if_font_missing(pdf_path: Path, bank: BankProfile) -> None:
    from ..reader import font_key

    used = embedded_fonts(pdf_path)
    if font_key(bank.primary_font)[0] not in {font_key(f)[0] for f in used}:
        warnings.warn(
            f"Font '{bank.primary_font}' is not installed, so {bank.bank_id} statements are "
            f"rendered with {', '.join(used)} and will differ from other machines. Install "
            "the fonts listed in the README.", stacklevel=3)


def render_pdf(statement: Statement, bank: BankProfile, out_path: str | Path, *,
               check_fonts: bool = True) -> Path:
    """Write the statement as a PDF to ``out_path`` and return the path.

    The output is byte-for-byte reproducible for a given statement, bank and set of
    installed fonts. With ``check_fonts`` a warning is raised when the bank's font is not
    installed and a substitute was used.

    WeasyPrint needs the Pango system library. On macOS install it with
    ``brew install pango``; on Ubuntu, ``apt install libpango-1.0-0 libpangoft2-1.0-0``.
    """
    from weasyprint import HTML  # imported lazily so the rest of the package works without it

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with _source_date(statement.generated_on):
        HTML(string=render_html(statement, bank)).write_pdf(out_path)
    if check_fonts:
        _warn_if_font_missing(out_path, bank)
    return out_path
