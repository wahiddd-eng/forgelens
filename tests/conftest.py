"""Shared test helpers that imitate what real bank PDFs and real forgers do."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def append_signature(src: Path, out: Path) -> Path:
    """Write ``src`` plus an incremental update that signs it, as e-statement signers do.

    The update adds a signature field to the catalog's ``/AcroForm`` and a signature
    dictionary whose ``/ByteRange`` covers the whole file except the ``/Contents`` hex
    string. The signature value is zeros: the structure signal checks the layout of the
    signature, not its cryptography.
    """
    import pymupdf

    base = src.read_bytes()
    with pymupdf.open(src) as doc:
        size, root, page0 = doc.xref_length(), doc.pdf_catalog(), doc[0].xref
        catalog = doc.xref_object(root, compressed=True)
    assert "/AcroForm" not in catalog
    prev = int(re.findall(rb"startxref\s+(\d+)", base)[-1])
    sig, widget = size, size + 1
    placeholder = b"9999999999"
    contents = b"<" + b"0" * 1024 + b">"
    objects = {
        root: catalog[:catalog.rindex(">>")].encode()
        + b"/AcroForm<</Fields[%d 0 R]/SigFlags 3>>>>" % widget,
        sig: b"<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached "
             b"/ByteRange [0 %s %s %s] /Contents %s /M (D:20250602091500+05'30') >>"
             % (placeholder, placeholder, placeholder, contents),
        widget: b"<< /Type /Annot /Subtype /Widget /FT /Sig /T (Signature1) /V %d 0 R "
                b"/Rect [0 0 0 0] /F 132 /P %d 0 R >>" % (sig, page0),
    }
    body = base if base.endswith(b"\n") else base + b"\n"
    offsets = {}
    for number, text in objects.items():
        offsets[number] = len(body)
        body += b"%d 0 obj\n%s\nendobj\n" % (number, text)
    xref_offset = len(body)
    body += b"xref\n0 1\n0000000000 65535 f \n%d 1\n%010d 00000 n \n" % (root, offsets[root])
    body += b"%d 2\n%010d 00000 n \n%010d 00000 n \n" % (sig, offsets[sig], offsets[widget])
    body += (b"trailer\n<< /Size %d /Root %d 0 R /Prev %d >>\nstartxref\n%d\n%%%%EOF\n"
             % (size + 2, root, prev, xref_offset))
    start = body.index(contents, offsets[sig])
    end = start + len(contents)
    ranges = b"%010d %010d %010d" % (start, end, len(body) - end)
    at = body.index(b"[0 " + placeholder, offsets[sig]) + 3
    body = body[:at] + ranges + body[at + len(ranges):]
    out.write_bytes(body)
    return out


def remove_repeated_headers(src: Path, out: Path, labels: tuple[str, ...]) -> Path:
    """Erase the table header on every page after the first, as many banks print it."""
    import pymupdf

    with pymupdf.open(src) as doc:
        for page in list(doc)[1:]:
            top = None
            for label in labels:
                for rect in page.search_for(label):
                    top = rect.y0 if top is None else min(top, rect.y0)
            if top is None:
                continue
            for label in labels:
                for rect in page.search_for(label):
                    if rect.y0 < top + 20:
                        page.add_redact_annot(rect)
            page.apply_redactions()
        doc.save(out, garbage=3)
    return out


@pytest.fixture
def pdf_tools():
    """Helpers for building realistic test PDFs (signed, header-less continuation pages)."""

    class Tools:
        sign = staticmethod(append_signature)
        remove_repeated_headers = staticmethod(remove_repeated_headers)

    return Tools
