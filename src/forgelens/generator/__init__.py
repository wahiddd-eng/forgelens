"""Synthetic genuine bank-statement generator for the ForgeLens dataset.

Example::

    from forgelens.generator import build_statement, get_bank, render_pdf

    bank = get_bank("himalaya_national")
    statement = build_statement(seed=42, bank=bank, months=3)
    render_pdf(statement, bank, "data/synthetic/genuine/himalaya_national_000042.pdf")
"""

from .banks import BANKS, BankProfile, get_bank
from .layout import LayoutError, locate_fields
from .models import Customer, Statement, Transaction
from .money import format_inr, to_money
from .render import embedded_fonts, render_html, render_pdf
from .transactions import build_statement

__all__ = [
    "BANKS",
    "BankProfile",
    "Customer",
    "LayoutError",
    "Statement",
    "Transaction",
    "build_statement",
    "embedded_fonts",
    "format_inr",
    "get_bank",
    "locate_fields",
    "render_html",
    "render_pdf",
    "to_money",
]
