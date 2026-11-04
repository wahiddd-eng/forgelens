"""PDF-level forgeries of generated statements, with exact labels.

A forger who edits a statement in a PDF editor typically erases a value and types a new
one over it. This module does the same with PyMuPDF: it paints over the original text
with the cell's background colour, removes the underlying text, and writes the new value
at the same position and size.

Operations
----------
``credit_amount``
    Inflate one credit (salary or incoming transfer if present). With ``consistent=False``
    only that cell changes, so the running balance no longer adds up. With
    ``consistent=True`` the forger also raises every later balance, the total credits and
    the closing balance, so all arithmetic checks still pass.
``closing_balance``
    Inflate the closing balance in the summary box and in the last table row.
``holder_name``
    Replace the account holder's name. The figures are untouched.

Every forgery returns a record with the edits made (field, page, old and new text, and
the region that changed), the values the forged document now claims, and how it was
made (font strategy, save mode). Masks for image models are drawn from these regions.
"""

from __future__ import annotations

import copy
import os
import random
import shutil
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from faker import Faker

from ..generator.money import format_amount, to_money
from ..signals.pdf_structure.analyzer import _font_key

OPERATIONS = ("credit_amount", "closing_balance", "holder_name")
SAVE_MODES = ("incremental", "rewrite")
FONT_STRATEGIES = ("matched", "fallback")

_FONT_DIRS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    "/Library/Fonts",
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    os.path.expanduser("~/Library/Fonts"),
    "C:/Windows/Fonts",
)
_font_index_cache: dict[tuple[str, str], str] | None = None


def _key(name: str) -> tuple[str, str]:
    family, style = _font_key(name)
    return family.replace("semicondensed", "condensed"), style


def _font_index() -> dict[tuple[str, str], str]:
    """Map (family, style) to a font file on this machine, keyed from file names."""
    global _font_index_cache
    if _font_index_cache is None:
        index: dict[tuple[str, str], str] = {}
        for root in _FONT_DIRS:
            if not os.path.isdir(root):
                continue
            for dirpath, _, files in os.walk(root):
                for f in files:
                    if f.lower().endswith((".ttf", ".otf")):
                        index.setdefault(_key(os.path.splitext(f)[0]), os.path.join(dirpath, f))
        _font_index_cache = index
    return _font_index_cache


class _FontKit:
    """Chooses the font a forger types with for each span, and measures text in it.

    ``matched`` looks for the same family and style on this machine (as a careful forger
    would); if it is not installed, or with ``fallback``, Helvetica is used instead.
    """

    def __init__(self, strategy: str):
        import pymupdf

        self._pymupdf = pymupdf
        self.requested = strategy
        self._resolved: dict[str, tuple[str, object | None, str | None]] = {}
        self._inserted: set[tuple[int, str]] = set()
        self.outcomes: set[str] = set()

    def _resolve(self, span_font: str):
        if span_font not in self._resolved:
            family, style = _key(span_font)
            path = _font_index().get((family, style)) if self.requested == "matched" else None
            if path:
                name = f"FL{len(self._resolved)}"
                self._resolved[span_font] = (name, self._pymupdf.Font(fontfile=path), path)
            else:
                bold, italic = "bold" in style, "italic" in style or "oblique" in style
                name = {(False, False): "helv", (True, False): "hebo",
                        (False, True): "heit", (True, True): "hebi"}[(bold, italic)]
                self._resolved[span_font] = (name, None, None)
        name, font, path = self._resolved[span_font]
        self.outcomes.add("matched" if path else "fallback")
        return name, font, path

    @property
    def used(self) -> str:
        if not self.outcomes:
            return self.requested
        return next(iter(self.outcomes)) if len(self.outcomes) == 1 else "mixed"

    def name(self, span_font: str) -> str:
        return self._resolve(span_font)[0]

    def width(self, text: str, size: float, span_font: str) -> float:
        name, font, _ = self._resolve(span_font)
        if font is not None:
            return font.text_length(text, fontsize=size)
        return self._pymupdf.get_text_length(text, fontname=name, fontsize=size)

    def ensure(self, page, span_font: str) -> None:
        name, _, path = self._resolve(span_font)
        if path and (page.number, name) not in self._inserted:
            page.insert_font(fontname=name, fontfile=path)
            self._inserted.add((page.number, name))


def _rgb(color: int) -> tuple[float, float, float]:
    return ((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255


def _background(pix, bbox, scale: float) -> tuple[float, float, float]:
    """Sample the cell background just left and right of the text."""
    y = (bbox[1] + bbox[3]) / 2 * scale
    samples = []
    for x in (bbox[0] - 1.5, bbox[2] + 1.0):
        px = min(max(int(x * scale), 0), pix.width - 1)
        py = min(max(int(y), 0), pix.height - 1)
        samples.append(pix.pixel(px, py)[:3])
    best = max(samples, key=sum)  # the lighter sample is the background, not a border
    return tuple(c / 255 for c in best)


def _pdf_date(dt: datetime) -> str:
    return dt.strftime("D:%Y%m%d%H%M%S+05'30'")


def _plausible_increase(rng: random.Random, old: Decimal, low: float, high: float) -> Decimal:
    new = old * Decimal(str(rng.uniform(low, high)))
    if old == old.to_integral_value():
        step = Decimal(100) if old >= 10000 else Decimal(10)
        new = (new / step).to_integral_value() * step
    new = to_money(new)
    return new if new > old else to_money(old + 100)


def _plan(record: dict, operation: str, consistent: bool, rng: random.Random, seed: int):
    """Decide which spans change and what the forged document will claim."""
    layout = record["layout"]
    fields, rows = layout["fields"], layout["rows"]
    claimed = copy.deepcopy(record)
    txns = claimed["transactions"]
    edits: list[dict] = []
    fmt = record.get("format", {})
    grouping, suffix = fmt.get("grouping", "indian"), fmt.get("balance_suffix", "")

    def amt(value: Decimal) -> str:  # amounts and totals, in the bank's own format
        return format_amount(value, grouping)

    def bal(value: Decimal) -> str:  # balances carry the bank's suffix, e.g. " Cr"
        return format_amount(value, grouping, suffix)

    def edit(field: str, span: dict | None, new_text: str, align: str, row: int | None = None):
        if span is None:
            return  # this layout does not print the field
        edits.append({"field": field, "row": row, "span": span, "old": span["text"],
                      "new": new_text, "align": align})

    if operation == "credit_amount":
        credits = [t for t in txns if Decimal(t["credit"]) > 0]
        if not credits:
            raise ValueError("statement has no credit rows to inflate")
        preferred = [t for t in credits if t["category"] in ("salary", "transfer_in")]
        target = rng.choice(preferred or credits)
        r = target["row"]
        old = Decimal(target["credit"])
        new = _plausible_increase(rng, old, 1.4, 3.0)
        delta = new - old
        target["credit"] = str(new)
        edit("credit", rows[r]["amount"], amt(new), "right", r)
        claimed["total_credits"] = str(to_money(Decimal(claimed["total_credits"]) + delta))
        if consistent:
            for t in txns[r:]:
                t["balance"] = str(to_money(Decimal(t["balance"]) + delta))
                edit("balance", rows[t["row"]]["balance"], bal(Decimal(t["balance"])),
                     "right", t["row"])
            claimed["closing_balance"] = txns[-1]["balance"]
            edit("summary_total_credits", fields.get("summary_total_credits"),
                 amt(Decimal(claimed["total_credits"])), "right")
            edit("summary_closing", fields.get("summary_closing"),
                 bal(Decimal(claimed["closing_balance"])), "right")
        return claimed, edits

    if consistent:
        raise ValueError(f"operation '{operation}' has no balance-consistent variant")

    if operation == "closing_balance":
        old = Decimal(record["closing_balance"])
        new = _plausible_increase(rng, old.to_integral_value() or Decimal(1000), 1.5, 5.0)
        new = to_money(new + (old - old.to_integral_value()))  # keep the paise, as forgers do
        claimed["closing_balance"] = str(new)
        txns[-1]["balance"] = str(new)
        edit("summary_closing", fields.get("summary_closing"), bal(new), "right")
        edit("balance", rows[-1]["balance"], bal(new), "right", len(rows) - 1)
        return claimed, edits

    if operation == "holder_name":
        fake = Faker("en_IN")
        fake.seed_instance(seed)
        new_name = fake.name().upper()
        while new_name == record["customer"]["name"]:
            new_name = fake.name().upper()
        claimed["customer"]["name"] = new_name
        edit("customer_name", fields["customer_name"], new_name, "left")
        return claimed, edits

    raise ValueError(f"Unknown operation '{operation}'. Choose from {', '.join(OPERATIONS)}")


def forge(
    genuine_pdf: str | Path,
    record: dict,
    out_pdf: str | Path,
    *,
    operation: str,
    consistent: bool = False,
    seed: int = 0,
    save_mode: str | None = None,
    font_strategy: str | None = None,
) -> dict:
    """Create a forged copy of ``genuine_pdf`` and return its label record.

    ``record`` is the genuine ground truth written by ``scripts/generate_statements.py``,
    including its ``layout``. ``save_mode`` and ``font_strategy`` are chosen at random
    from ``seed`` when not given.
    """
    import pymupdf

    if "layout" not in record:
        raise ValueError("record has no 'layout'; regenerate it with the current generator")
    rng = random.Random(seed)
    save_mode = save_mode or rng.choice(SAVE_MODES)
    font_strategy = font_strategy or rng.choice(FONT_STRATEGIES)
    if save_mode not in SAVE_MODES or font_strategy not in FONT_STRATEGIES:
        raise ValueError("invalid save_mode or font_strategy")

    claimed, edits = _plan(record, operation, consistent, rng, seed)

    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(genuine_pdf, out_pdf)
    doc = pymupdf.open(out_pdf)
    fonts = _FontKit(font_strategy)
    scale = 2.0

    by_page: dict[int, list[dict]] = {}
    for e in edits:
        by_page.setdefault(e["span"]["page"], []).append(e)

    for page_no, page_edits in by_page.items():
        page = doc[page_no]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        for e in page_edits:
            e["fill"] = _background(pix, e["span"]["bbox"], scale)
            page.add_redact_annot(pymupdf.Rect(e["span"]["bbox"]), fill=e["fill"])
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        for e in page_edits:
            span = e["span"]
            fonts.ensure(page, span["font"])
            width = fonts.width(e["new"], span["size"], span["font"])
            x0 = span["bbox"][2] - width if e["align"] == "right" else span["bbox"][0]
            page.insert_text((x0, span["origin"][1]), e["new"], fontname=fonts.name(span["font"]),
                             fontsize=span["size"], color=_rgb(span["color"]))
            new_bbox = [x0, span["bbox"][1], x0 + width, span["bbox"][3]]
            e["new_bbox"] = [round(v, 3) for v in new_bbox]
            e["mask_bbox"] = [round(v, 3) for v in (
                min(span["bbox"][0], new_bbox[0]), span["bbox"][1],
                max(span["bbox"][2], new_bbox[2]), span["bbox"][3])]

    generated = date.fromisoformat(record["generated_on"])
    edited_at = datetime.combine(generated, datetime.min.time()) + timedelta(
        days=rng.randint(2, 60), hours=rng.randint(9, 22), minutes=rng.randint(0, 59))
    metadata_updated = save_mode == "rewrite" or rng.random() < 0.5
    if metadata_updated:
        meta = dict(doc.metadata)
        meta["modDate"] = _pdf_date(edited_at)
        doc.set_metadata(meta)

    if save_mode == "incremental":
        doc.saveIncr()
        doc.close()
    else:
        tmp = out_pdf.with_suffix(".tmp.pdf")
        doc.save(tmp, garbage=3, deflate=True)
        doc.close()
        os.replace(tmp, out_pdf)

    variant = operation + ("_consistent" if consistent else "")
    claimed.update({
        "statement_id": out_pdf.stem,
        "label": "forged",
        "pdf": out_pdf.name,
        "source_statement_id": record["statement_id"],
        "forgery": {
            "method": "pdf_edit",
            "operation": operation,
            "variant": variant,
            "balance_consistent": operation == "holder_name" or consistent,
            "seed": seed,
            "save_mode": save_mode,
            "font_strategy": fonts.used,
            "metadata_updated": metadata_updated,
            "edited_at": edited_at.isoformat() if metadata_updated else None,
        },
        "edits": [
            {
                "field": e["field"],
                "row": e["row"],
                "page": e["span"]["page"],
                "old": e["old"],
                "new": e["new"],
                "old_bbox": e["span"]["bbox"],
                "new_bbox": e["new_bbox"],
                "mask_bbox": e["mask_bbox"],
            }
            for e in edits
        ],
    })
    claimed.pop("layout", None)
    return claimed


def write_masks(record: dict, page_size: tuple[float, float], out_prefix: str | Path,
                dpi: int = 150) -> list[Path]:
    """Write one binary PNG mask (255 = edited) for each page that has edits.

    Masks match a page rendered at the same ``dpi``, e.g. with
    ``page.get_pixmap(dpi=dpi)``.
    """
    import pymupdf

    scale = dpi / 72
    # Use PyMuPDF's own rounding so the mask has exactly the size of a rendered page.
    page_irect = (pymupdf.Rect(0, 0, *page_size) * pymupdf.Matrix(scale, scale)).irect
    pages = sorted({e["page"] for e in record["edits"]})
    paths = []
    for page_no in pages:
        pix = pymupdf.Pixmap(pymupdf.csGRAY, page_irect, False)
        pix.clear_with(0)
        for e in record["edits"]:
            if e["page"] == page_no:
                x0, y0, x1, y1 = e["mask_bbox"]
                rect = pymupdf.IRect(int(x0 * scale), int(y0 * scale),
                                     int(x1 * scale + 0.999), int(y1 * scale + 0.999))
                pix.set_rect(rect, (255,))
        path = Path(f"{out_prefix}_p{page_no}_mask.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(path)
        paths.append(path)
    return paths
