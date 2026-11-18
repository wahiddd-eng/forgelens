"""Privacy-safe diagnostics for real statements: why a signal fired on a genuine file.

Real statements may not leave the run that reads them (``scripts/eval_real.sh``), so this
module records only facts about how a file is built and parsed, never what it says: the
software that wrote it, its page count, the names of its fonts (with subset tags), which
checks fired and on how many spans or rows, and how many balance breaks would remain under
other readings of the table (rows in reverse order, debit and credit swapped). No text,
dates, amounts, names or account numbers.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

_SUBSET = re.compile(r"^[A-Z]{6}\+")


def _short(s: str | None, n: int = 48) -> str:
    return (s or "").strip()[:n]


def _chain_breaks(opening, rows, reverse=False, swap=False, tol=Decimal("0.011")) -> int | None:
    """Balance breaks if the table were read in another order or with the columns swapped."""
    rows = [r for r in rows if r.balance is not None]
    if not rows:
        return None
    if reverse:
        rows = rows[::-1]
    prev = opening
    if prev is None:  # start from the first row's own balance
        r0 = rows[0]
        d, c = (r0.credit, r0.debit) if swap else (r0.debit, r0.credit)
        prev = r0.balance + (d or 0) - (c or 0)
    breaks = 0
    for r in rows:
        d, c = (r.credit, r.debit) if swap else (r.debit, r.credit)
        if abs(prev - (d or 0) + (c or 0) - r.balance) > tol:
            breaks += 1
        prev = r.balance
    return breaks


def _bucket(x: Decimal | None) -> str | None:
    """Order of magnitude of a balance error, e.g. '1e3' for hundreds to thousands."""
    if x is None:
        return None
    x = abs(float(x))
    return "0" if x < 1 else f"1e{int(math.log10(x)) + 1}"


def diagnose(pdf: Path, password: str | None, fin=None, struct=None, ocr=None,
             image: float | None = None) -> dict:
    from forgelens.reader import open_pdf, parse_statement

    out: dict = {}
    try:
        with open_pdf(pdf, password) as doc:
            meta = doc.metadata or {}
            out["producer"] = _short(meta.get("producer"))
            out["creator"] = _short(meta.get("creator"))
            out["pages"] = len(doc)
            fonts = Counter()
            per_page = []
            for page in doc:
                names = sorted({f[3] for f in page.get_fonts(full=True)})
                per_page.append(len(names))
                fonts.update(names)
            out["fonts"] = {n: c for n, c in sorted(fonts.items())}  # name -> pages using it
            out["fonts_per_page"] = per_page
            out["subset_fonts"] = sum(bool(_SUBSET.match(n)) for n in fonts)
    except Exception as exc:  # noqa: BLE001
        out["open_error"] = type(exc).__name__
        return out

    if struct is not None:
        s = []
        for f in struct.findings:
            item = {"check": f.check, "page": f.page}
            if f.check == "font_anomaly":
                item["spans"] = len(f.locations)
                item["fonts"] = sorted({loc["font"] for loc in f.locations})
                item["pages"] = sorted({loc["page"] for loc in f.locations})
            elif f.check in ("duplicate_font", "non_embedded_font"):
                item["message"] = f.message  # font names only
            s.append(item)
        out["structure"] = s
        out["structure_stats"] = {k: v for k, v in (struct.stats or {}).items()
                                  if isinstance(v, (int, float, bool))}

    if fin is not None:
        rb = [f for f in fin.findings if f.check == "running_balance"]
        out["financial"] = {
            "parsed_rows": fin.parsed_rows, "checks_run": fin.checks_run,
            "fired": dict(Counter(f.check for f in fin.findings)),
            "parse_warnings": len(fin.parse_warnings),
            "break_rows": [round(f.row / max(1, fin.parsed_rows), 2) for f in rb if f.row is not None],
            "break_sizes": [_bucket(Decimal(f.found) - Decimal(f.expected)) for f in rb
                            if f.found and f.expected],
        }
        try:
            parsed = parse_statement(pdf, password)
            opening = parsed.opening_row.balance if parsed.opening_row else parsed.summary.get("opening")
            out["financial"]["headers"] = sorted({h for hs in parsed.header_labels.values() for h in hs})[:20]
            out["financial"]["summary_keys"] = sorted(parsed.summary)
            out["financial"]["has_opening"] = opening is not None
            out["financial"]["readings"] = {
                name: _chain_breaks(opening, parsed.rows, rev, swap)
                for name, rev, swap in (("as_read", False, False), ("reversed", True, False),
                                        ("swapped", False, True), ("reversed_swapped", True, True))}
            out["financial"]["rows_both_amounts"] = sum(
                r.debit is not None and r.credit is not None for r in parsed.rows)
            out["financial"]["rows_no_amount"] = sum(
                r.debit is None and r.credit is None for r in parsed.rows)
        except Exception as exc:  # noqa: BLE001
            out["financial"]["parse_error"] = type(exc).__name__

    if ocr is not None:
        out["ocr"] = {"rows": ocr.rows, "breaks": ocr.breaks, "explained": ocr.explained,
                      "unexplained": ocr.unexplained, "summary_breaks": ocr.summary_breaks,
                      "largest": _bucket(ocr.largest), "abstained": ocr.abstained}
    if image is not None:
        out["image_peak"] = round(image, 4)
    return out
