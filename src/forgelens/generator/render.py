"""Render a generated statement to HTML and PDF."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from .banks import BankProfile
from .models import Statement
from .money import format_inr

_env = Environment(
    loader=PackageLoader("forgelens.generator", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(statement: Statement, bank: BankProfile) -> str:
    """Return the statement as an HTML string using the bank's layout template."""
    template = _env.get_template(bank.template)

    def fmt_date(d: date) -> str:
        return d.strftime(bank.date_format)

    return template.render(
        statement=statement, bank=bank, c=statement.customer, inr=format_inr, fmt_date=fmt_date
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
