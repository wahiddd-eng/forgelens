"""Open statement PDFs safely: passwords, damaged files and clear errors.

Indian banks usually send e-statements protected with a password (often built from the
customer's name or date of birth), and applicants upload damaged or non-PDF files too.
Every reader and signal opens files through ``open_pdf`` so these cases raise one of two
errors instead of whatever PyMuPDF happens to raise.
"""

from __future__ import annotations

from pathlib import Path


class UnreadablePDF(ValueError):
    """The file cannot be read as a PDF: it is empty, damaged or another format."""


class PasswordRequired(UnreadablePDF):
    """The PDF is encrypted with a user password and the right password was not given."""


def open_pdf(path: str | Path, password: str | None = None):
    """Open ``path`` with PyMuPDF, decrypting it with ``password`` when it is locked.

    Raises ``PasswordRequired`` for a locked file without the right password,
    ``UnreadablePDF`` for anything that is not a readable PDF, and ``FileNotFoundError``
    when the file does not exist. The caller closes the returned document (or uses it in a
    ``with`` block).
    """
    import pymupdf

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:  # includes EmptyFileError
        raise UnreadablePDF(f"{path.name}: {exc}") from exc
    if not doc.is_pdf:  # e.g. an image renamed to .pdf
        doc.close()
        raise UnreadablePDF(f"{path.name}: not a PDF document")
    if doc.needs_pass and not (password and doc.authenticate(password)):
        doc.close()
        hint = "the password is wrong" if password else "pass password=..."
        raise PasswordRequired(f"{path.name} is password-protected ({hint})")
    if doc.page_count == 0:
        doc.close()
        raise UnreadablePDF(f"{path.name}: the PDF has no pages")
    return doc
