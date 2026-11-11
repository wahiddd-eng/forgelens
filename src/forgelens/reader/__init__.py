"""Read what a statement PDF prints: text cells, fonts, the transaction table and summary.

Shared by the generator (to locate fields), the forgery tools and every signal, so they all
see a document the same way. It uses only what is printed in the PDF, never ground truth.
"""

from .cells import Cell, font_key, full_font_names, read_cells
from .document import PasswordRequired, UnreadablePDF, open_pdf
from .statement import ParsedStatement, Row, parse_amount, parse_cells, parse_statement

__all__ = [
    "Cell",
    "ParsedStatement",
    "PasswordRequired",
    "Row",
    "UnreadablePDF",
    "font_key",
    "full_font_names",
    "open_pdf",
    "parse_amount",
    "parse_cells",
    "parse_statement",
    "read_cells",
]
