"""PDF-structure signal: traces that editing leaves inside the file.

These checks look at how the PDF is built, not at what it says, and need no ground truth:

``incremental_update``
    The file was saved more than once: an update section was appended after the original
    (more than one ``startxref``). Genuine e-statements are written in one pass. Sections
    that a genuine file can have for other reasons are not counted: the extra section of a
    linearised ("Fast Web View") file, and one section per digital signature.
``modified_after_signing``
    The file was digitally signed and then changed: a save section follows the last
    signature (other than a Document Security Store added by a signature validator).
``signature_broken``
    A signature's byte range no longer matches the file, so the file was re-written after
    it was signed. (Signatures are checked for structure only, not cryptographically.)
``modified_after_creation``
    The modification date is later than the creation date. Not reported for signed files
    that were not changed after signing, because signing itself updates the date.
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

from ...reader import UnreadablePDF, full_font_names, open_pdf

WEIGHTS = {
    "incremental_update": 0.5,
    "modified_after_signing": 0.8,
    "signature_broken": 0.8,
    "modified_after_creation": 0.3,
    "non_embedded_font": 0.5,
    "duplicate_font": 0.6,
    "extra_content_streams": 0.4,
    "font_anomaly": 0.6,
}
MINOR_FAMILY_SHARE = 0.2  # a second font family used by fewer spans than this is suspicious
TEMPLATE_SHARE = 0.5  # a font whose text mostly repeats on other pages is template text
_BYTE_RANGE = re.compile(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]")
_LINEARIZED = re.compile(rb"/Linearized\s+[\d.]+")


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
    error: str | None = None  # why the file could not be read (locked, damaged)

    @property
    def suspicious(self) -> bool:
        return bool(self.findings)

    @property
    def abstained(self) -> bool:
        """True for unreadable and image-only files: their structure says nothing."""
        return self.error is not None or not self.text_layer

    @property
    def score(self) -> float:
        """Suspicion in [0, 1], combining the weights of the checks that fired."""
        if self.abstained:
            return 0.5  # image-only or unreadable PDF: structure says nothing
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
            "pdf_signatures": float(self.stats.get("signatures", 0)),
            "pdf_unreadable": float(self.error is not None),
            "pdf_score": self.score,
        })
        return out

    def to_dict(self) -> dict:
        return {
            "signal": "pdf_structure",
            "suspicious": self.suspicious,
            "abstained": self.abstained,
            "error": self.error,
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


def _revisions(raw: bytes) -> dict:
    """Count the file's save sections and how many of them a genuine file can explain."""
    sections = raw.count(b"startxref")
    linearized = bool(_LINEARIZED.search(raw[:4096]))
    ranges = [r for r in (tuple(int(v) for v in m) for m in _BYTE_RANGE.findall(raw))
              if any(r)]  # an all-zero range is an unfilled placeholder, not a signature
    signed_ends = sorted({c + d for _, _, c, d in ranges})
    # The gap in a byte range is the signature's /Contents hex string, "<...>".
    broken = [r for r in ranges
              if r[0] != 0 or r[2] + r[3] > len(raw) or raw[r[1]:r[1] + 1] != b"<"
              or raw[r[2] - 1:r[2]] != b">"]
    after = signed_ends and raw.rfind(b"startxref") > signed_ends[-1]
    dss_only = bool(after) and b"/DSS" in raw[signed_ends[-1]:]
    explained = 1 + int(linearized) + len(signed_ends) + int(dss_only)
    return {
        "sections": sections,
        "linearized": linearized,
        "signatures": len(ranges),
        "broken_signatures": len(broken),
        "modified_after_signing": bool(after) and not dss_only,
        "unexplained_updates": max(0, sections - explained),
    }


# What genuine bank software does that the font checks must not read as editing (seen on 28
# real statements from 10 banks, experiments/results/real_pilot_20261118.md):
# - weights of one family (Regular, Medium, SemiBold, Black) are one family, not a second one;
# - FPDF names styles by suffix ("montserrat", "montserratB", "montserratsb");
# - headings and labels in a second font repeat on every page (template text);
# - symbol fonts (ZapfDingbats) draw ticks and bullets;
# - Apple's print-to-PDF embeds a new subset of the same font for each page (and of every
#   font, once the body font shows it).
SYMBOL_FONTS = ("zapfdingbats", "dingbats", "symbol", "wingdings", "webdings")
_WEIGHTS = (("extrabold", "black"), ("ultrabold", "black"), ("semibold", "semibold"),
            ("demibold", "semibold"), ("extralight", "light"), ("ultralight", "light"),
            ("black", "black"), ("heavy", "black"), ("bold", "bold"), ("medium", "medium"),
            ("light", "light"), ("thin", "light"), ("book", "regular"), ("regular", "regular"),
            ("roman", "regular"), ("normal", "regular"))


def family_weight(name: str) -> tuple[str, str, bool]:
    """(family, weight class, italic) of a font name, ignoring subset tags and spelling."""
    base = name.split("+", 1)[-1]
    weight, italic = None, False
    m = re.search(r"(?<=[a-z0-9])(BI|B|I)$", base)  # FPDF style suffix: "montserratB"
    if m:
        base = base[:m.start()]
        weight = "bold" if "B" in m.group(1) else None
        italic = "I" in m.group(1)
    letters = re.sub(r"[^a-z]", "", base.lower())
    if "italic" in letters or "oblique" in letters:
        italic = True
        letters = letters.replace("italic", "").replace("oblique", "")
    for word, cls in _WEIGHTS:
        if word in letters:
            letters = letters.replace(word, "")
            weight = weight or cls
    family = letters.removesuffix("mt").removesuffix("ps").replace("semicondensed", "condensed")
    return family, weight or "regular", italic


def _is_symbol(name: str) -> bool:
    return any(w in name.lower() for w in SYMBOL_FONTS)


def _same_family(a: str, b: str) -> bool:
    """Equal families, or one a style-suffixed spelling of the other ("montserrat"/"montserratsb")."""
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short) >= 5 and long_.startswith(short) and len(long_) - len(short) <= 2)


def analyze_pdf(pdf_path: str | Path, password: str | None = None) -> StructureReport:
    """Run the PDF-structure signal on ``pdf_path``.

    A locked or damaged file gives an abstaining report whose ``error`` says why.
    """
    report = StructureReport()
    add = report.findings.append
    try:
        doc = open_pdf(pdf_path, password)
    except UnreadablePDF as exc:
        report.error, report.text_layer = str(exc), False
        return report
    raw = Path(pdf_path).read_bytes()

    with doc:
        meta = doc.metadata or {}
        pages = doc.page_count
        fonts: dict[int, tuple[str, str, str]] = {}  # xref -> (ext, type, basefont)
        font_pages: dict[str, set[int]] = {}  # basefont -> pages that use it
        for p in range(pages):
            for xref, ext, ftype, basefont, *_ in doc.get_page_fonts(p):
                fonts[xref] = (ext, ftype, basefont)
                font_pages.setdefault(basefont, set()).add(p)
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
    revisions = _revisions(raw)
    startxref = revisions["sections"]
    report.stats = {
        "pages": pages,
        "startxref_count": startxref,
        "linearized": revisions["linearized"],
        "signatures": revisions["signatures"],
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

    # 1. Incremental updates and signatures
    if revisions["unexplained_updates"]:
        add(StructureFinding("incremental_update",
                             f"The file has {startxref} save sections; "
                             f"{revisions['unexplained_updates']} of them cannot be explained by "
                             "digital signatures or fast-web-view optimisation, so changes were "
                             "appended after the file was first created."))
    if revisions["modified_after_signing"]:
        add(StructureFinding("modified_after_signing",
                             "The file was changed after it was digitally signed: a save section "
                             "follows the last signature."))
    if revisions["broken_signatures"]:
        add(StructureFinding("signature_broken",
                             f"{revisions['broken_signatures']} digital signature(s) no longer "
                             "match the file: it was re-written after it was signed."))

    # 2. Modified after creation (signing legitimately updates the date)
    created, modified = _pdf_date(meta.get("creationDate")), _pdf_date(meta.get("modDate"))
    signed_untouched = revisions["signatures"] and not (
        revisions["modified_after_signing"] or revisions["broken_signatures"])
    if (created and modified and modified - created > timedelta(minutes=1)
            and not signed_untouched):
        days = (modified - created).days
        when = f"{days} day(s)" if days else "hours"
        add(StructureFinding("modified_after_creation",
                             f"The document was modified {when} after it was created "
                             f"({created:%d-%m-%Y} → {modified:%d-%m-%Y})."))

    # 3. Non-embedded standard fonts alongside embedded ones (not symbol fonts, and not a font
    #    the template uses on most pages)
    #    A font is template text when most of what it draws repeats, word for word, on other
    #    pages (headings, column labels, the bank's name). An edited amount does not repeat.
    pages_by_text: dict[str, set[int]] = {}
    for p, _, _, text in spans:
        pages_by_text.setdefault(text, set()).add(p)

    def template_share(selected) -> float:
        texts = [t for p, f, _, t in spans if selected(f)]
        return sum(len(pages_by_text[t]) >= 2 for t in texts) / len(texts) if texts else 0.0

    def is_template(selected) -> bool:
        return pages > 1 and template_share(selected) >= TEMPLATE_SHARE

    #    A font that draws a large share of the text (the document's own body font, as IDBI's
    #    and PNB's are) is not patched-in text either.
    spans_by_family = Counter(family_weight(f)[0] for _, f, _, _ in spans)

    def main_text(name: str) -> bool:
        return spans_by_family[family_weight(name)[0]] >= MINOR_FAMILY_SHARE * len(spans)

    embedded = [f for f in fonts.values() if f[0] not in ("n/a", "")]
    missing = sorted({f[2] for f in fonts.values() if f[0] in ("n/a", "")
                      and not _is_symbol(f[2]) and not main_text(f[2])
                      and not is_template(lambda name, b=f[2]: name == b)})
    if embedded and missing:
        add(StructureFinding("non_embedded_font",
                             f"Text is drawn in non-embedded font(s) {', '.join(missing)} while the "
                             "rest of the document uses embedded fonts."))

    # 4. Same family and style embedded more than once
    by_key: dict[tuple[str, str, bool], set[str]] = {}
    for ext, _, basefont in fonts.values():
        if ext not in ("n/a", ""):
            by_key.setdefault(family_weight(basefont), set()).add(basefont)

    # Apple's print-to-PDF (Quartz PDFContext) writes a new subset of each font for every page:
    # when the document's main font comes as many one-page subsets, every font does.
    one_page_subsets = Counter(family_weight(n) for n, pg in font_pages.items()
                               if "+" in n and len(pg) == 1)
    print_subsetting = bool(one_page_subsets) and max(one_page_subsets.values()) >= 5

    def per_page_subsets(names: set[str]) -> bool:
        """One subset per page, on pages no other copy uses: print-to-PDF, not an edit."""
        used = [font_pages.get(n, set()) for n in names]
        if print_subsetting and all(len(u) <= 2 for u in used):
            return True
        return len(names) >= 3 and all(len(u) == 1 for u in used) \
            and len(set().union(*used)) == len(names)

    dupes = {k: v for k, v in by_key.items() if len(v) > 1 and not per_page_subsets(v)}
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
    span_keys = [(family_weight(font), font) for _, font, _, _ in spans]
    raw_counts = Counter(k[0] for k, _ in span_keys)
    main_family = raw_counts.most_common(1)[0][0]

    def fam(f: str) -> str:  # style-suffixed spellings of the main family are the main family
        return main_family if _same_family(f, main_family) else f

    family_counts = Counter(fam(key[0]) for key, _ in span_keys)
    names_by_key: dict[tuple, Counter] = {}
    for key, font in span_keys:
        names_by_key.setdefault((fam(key[0]),) + key[1:], Counter())[font] += 1
    odd = set()
    for key, names in names_by_key.items():
        family = key[0]
        if any(_is_symbol(n) for n in names) or is_template(lambda f, n=set(names): f in n):
            continue
        if family != main_family and family_counts[family] / len(spans) < MINOR_FAMILY_SHARE:
            odd.update(names)
        elif len(names) > 1 and not per_page_subsets(set(names)):
            common = names.most_common(1)[0][0]  # same font under two names: the rarer was added
            odd.update(n for n in names if n != common)
    locations = [
        {"page": p, "bbox": bbox, "text": text, "font": font}
        for (p, font, bbox, text) in spans if font in odd
    ]
    if locations:
        odd_fonts = sorted({loc["font"] for loc in locations})
        add(StructureFinding("font_anomaly",
                             f"{len(locations)} text span(s) use font(s) {', '.join(odd_fonts)}, "
                             "which the rest of the document does not use for this text.",
                             page=locations[0]["page"], locations=locations))
    return report
