"""PDF-structure signal: traces that editing leaves inside the file.

These checks look at how the PDF is built, not at what it says, and need no ground truth:

``incremental_update``
    The file was saved more than once: an update section was appended after the original
    (more than one ``startxref``). Genuine e-statements are written in one pass.
``modified_after_creation``
    The modification date is later than the creation date.
``non_embedded_font``
    Some text uses a standard font that is not embedded (such as Helvetica) while the rest
    of the document uses embedded fonts. PDF editors often fall back to these.
``duplicate_font``
    The same font family and style is embedded more than once under different names, as
    happens when an editor adds its own copy of a font the document already had.
``extra_content_streams``
    Some pages have more content streams than the others: content was appended to them
    after the page was first drawn.
``font_anomaly``
    Individual text spans are drawn in a font that the rest of the document does not use
    for that kind of text. These spans are returned with their positions, so the signal
    can point at *where* the document was changed.

Caveat: these traces depend on the editing tool. A forger who "prints" the edited
statement to a fresh PDF can remove most of them, which is why ForgeLens also relies on
image, financial and template signals.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..financial.extract import full_font_names

WEIGHTS = {
    "incremental_update": 0.5,
    "modified_after_creation": 0.3,
    "non_embedded_font": 0.5,
    "duplicate_font": 0.6,
    "extra_content_streams": 0.4,
    "font_anomaly": 0.6,
}
STYLE_WORDS = ("bold", "italic", "oblique", "book", "regular", "roman", "medium", "light")
MINOR_FAMILY_SHARE = 0.2  # a second font family used by fewer spans than this is suspicious


@dataclass
class StructureFinding:
    check: str
    message: str
    page: int | None = None
    locations: list[dict] = field(default_factory=list)  # [{"page": int, "bbox": [...], "text"}]


@dataclass
class StructureReport:
    findings: list[StructureFinding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    text_layer: bool = True

    @property
    def suspicious(self) -> bool:
        return bool(self.findings)

    @property
    def score(self) -> float:
        """Suspicion in [0, 1], combining the weights of the checks that fired."""
        if not self.text_layer:
            return 0.5  # image-only PDF: structure says nothing about the content
        clean = 1.0
        for check in {f.check for f in self.findings}:
            clean *= 1 - WEIGHTS[check]
        return round(1 - clean, 4)

    def locations(self) -> list[dict]:
        return [loc for f in self.findings for loc in f.locations]

    def features(self) -> dict[str, float]:
        fired = {f.check for f in self.findings}
        out = {f"pdf_{name}": float(name in fired) for name in WEIGHTS}
        out.update({
            "pdf_startxref_count": float(self.stats.get("startxref_count", 0)),
            "pdf_anomalous_spans": float(len(self.locations())),
            "pdf_text_layer": float(self.text_layer),
            "pdf_score": self.score,
        })
        return out

    def to_dict(self) -> dict:
        return {
            "signal": "pdf_structure",
            "suspicious": self.suspicious,
            "score": self.score,
            "findings": [asdict(f) for f in self.findings],
            "stats": self.stats,
            "features": self.features(),
        }


def _pdf_date(value: str | None) -> datetime | None:
    """Parse a PDF date such as ``D:20260403090000+05'30'``."""
    if not value:
        return None
    m = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([+\-Z])?(\d{2})?'?(\d{2})?",
                 value)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(g) if g else default for g, default in
                          zip(m.groups()[:6], (0, 1, 1, 0, 0, 0)))
    tz = timezone.utc
    if m.group(7) in ("+", "-"):
        offset = timedelta(hours=int(m.group(8) or 0), minutes=int(m.group(9) or 0))
        tz = timezone(offset if m.group(7) == "+" else -offset)
    try:
        return datetime(y, mo, d, h, mi, s, tzinfo=tz)
    except ValueError:
        return None


def _font_key(name: str) -> tuple[str, str]:
    """Return (family, style) from a font name, ignoring subset tags and spelling."""
    name = name.split("+", 1)[-1].lower()
    letters = re.sub(r"[^a-z]", "", name)
    style = "".join(w for w in ("bold", "italic", "oblique") if w in letters) or "regular"
    family = letters
    for w in STYLE_WORDS:
        family = family.replace(w, "")
    family = family.removesuffix("mt").removesuffix("ps")
    return family, style


def analyze_pdf(pdf_path: str | Path) -> StructureReport:
    """Run the PDF-structure signal on ``pdf_path``."""
    import pymupdf

    raw = Path(pdf_path).read_bytes()
    report = StructureReport()
    add = report.findings.append

    with pymupdf.open(pdf_path) as doc:
        meta = doc.metadata or {}
        pages = doc.page_count
        fonts: dict[int, tuple[str, str, str]] = {}  # xref -> (ext, type, basefont)
        for p in range(pages):
            for xref, ext, ftype, basefont, *_ in doc.get_page_fonts(p):
                fonts[xref] = (ext, ftype, basefont)
        streams = [len(doc[p].get_contents()) for p in range(pages)]
        spans = []
        for p in range(pages):
            full = full_font_names(doc, p)
            for block in doc[p].get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for s in line["spans"]:
                        if s["text"].strip():
                            spans.append((p, full[s["font"]], [round(v, 2) for v in s["bbox"]],
                                          s["text"].strip()))

    report.text_layer = bool(spans)
    startxref = raw.count(b"startxref")
    report.stats = {
        "pages": pages,
        "startxref_count": startxref,
        "fonts": sorted({f[2] for f in fonts.values()}),
        "content_streams_per_page": streams,
        "producer": meta.get("producer", ""),
        "creator": meta.get("creator", ""),
        "creation_date": meta.get("creationDate", ""),
        "mod_date": meta.get("modDate", ""),
        "text_spans": len(spans),
    }
    if not report.text_layer:
        return report

    # 1. Incremental updates
    if startxref > 1:
        add(StructureFinding("incremental_update",
                             f"The file was saved {startxref} times: changes were appended after "
                             "it was first created."))

    # 2. Modified after creation
    created, modified = _pdf_date(meta.get("creationDate")), _pdf_date(meta.get("modDate"))
    if created and modified and modified - created > timedelta(minutes=1):
        days = (modified - created).days
        when = f"{days} day(s)" if days else "hours"
        add(StructureFinding("modified_after_creation",
                             f"The document was modified {when} after it was created "
                             f"({created:%d-%m-%Y} → {modified:%d-%m-%Y})."))

    # 3. Non-embedded standard fonts alongside embedded ones
    embedded = [f for f in fonts.values() if f[0] not in ("n/a", "")]
    missing = sorted({f[2] for f in fonts.values() if f[0] in ("n/a", "")})
    if embedded and missing:
        add(StructureFinding("non_embedded_font",
                             f"Text is drawn in non-embedded font(s) {', '.join(missing)} while the "
                             "rest of the document uses embedded fonts."))

    # 4. Same family and style embedded more than once
    by_key: dict[tuple[str, str], set[str]] = {}
    for ext, _, basefont in fonts.values():
        if ext not in ("n/a", ""):
            by_key.setdefault(_font_key(basefont), set()).add(basefont)
    dupes = {k: v for k, v in by_key.items() if len(v) > 1}
    if dupes:
        listed = "; ".join(" / ".join(sorted(v)) for v in dupes.values())
        add(StructureFinding("duplicate_font",
                             f"The same font is embedded more than once under different names "
                             f"({listed})."))

    # 5. Pages with extra content streams
    if pages > 1:
        typical = Counter(streams).most_common(1)[0][0]
        extra = [p for p, n in enumerate(streams) if n > typical]
        if extra and len(extra) < pages:
            add(StructureFinding("extra_content_streams",
                                 f"Page(s) {', '.join(str(p + 1) for p in extra)} have more content "
                                 f"streams than the other pages ({typical}): content was added "
                                 "after the page was drawn.", page=extra[0]))

    # 6. Span-level font anomalies (localised)
    span_keys = [(_font_key(font), font) for _, font, _, _ in spans]
    family_counts = Counter(k[0] for k, _ in span_keys)
    main_family = family_counts.most_common(1)[0][0]
    names_by_key: dict[tuple[str, str], Counter] = {}
    for key, font in span_keys:
        names_by_key.setdefault(key, Counter())[font] += 1
    odd = set()
    for (family, style), names in names_by_key.items():
        if family != main_family and family_counts[family] / len(spans) < MINOR_FAMILY_SHARE:
            odd.update((family, style, n) for n in names)
        elif len(names) > 1:  # same family and style under two names: the rarer one was added
            common = names.most_common(1)[0][0]
            odd.update((family, style, n) for n in names if n != common)
    locations = [
        {"page": p, "bbox": bbox, "text": text, "font": font}
        for (p, font, bbox, text), (key, _) in zip(spans, span_keys)
        if (key[0], key[1], font) in odd
    ]
    if locations:
        odd_fonts = sorted({loc["font"] for loc in locations})
        add(StructureFinding("font_anomaly",
                             f"{len(locations)} text span(s) use font(s) {', '.join(odd_fonts)}, "
                             "which the rest of the document does not use for this text.",
                             page=locations[0]["page"], locations=locations))
    return report
