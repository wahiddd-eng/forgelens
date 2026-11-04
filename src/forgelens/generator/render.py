"""Render a generated statement to HTML and PDF."""

from __future__ import annotations

from datetime import date
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


def render_pdf(statement: Statement, bank: BankProfile, out_path: str | Path) -> Path:
    """Write the statement as a PDF to ``out_path`` and return the path.

    WeasyPrint needs the Pango system library. On macOS install it with
    ``brew install pango``; on Ubuntu, ``apt install libpango-1.0-0 libpangoft2-1.0-0``.
    """
    from weasyprint import HTML  # imported lazily so the rest of the package works without it

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=render_html(statement, bank)).write_pdf(out_path)
    return out_path
