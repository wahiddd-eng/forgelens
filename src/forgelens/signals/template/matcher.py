"""Template-matching signal: does this statement look like the bank's real statements?

A bank's statements come from one system, so they share a fingerprint: the same fonts, page
size, "Creator" metadata, table header labels, column positions, text sizes, date and number
formats, and masthead. ``fit_profiles`` learns that fingerprint from genuine statements;
``TemplateMatcher.check`` compares a new statement with the profile of the bank it claims to
be from and explains every difference.

This catches forgeries rebuilt from an imitation of the template and edits typed in a font
the bank never uses. It cannot catch a forgery rendered with the bank's exact template.
Re-saving ("Print to PDF") changes the producer but not these properties, so the producer
is deliberately not compared.

Profiles depend on the fonts installed where the statements were rendered, so fit and
check on the same set-up; ``fit_templates.py`` records the environment in the profile file.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ...reader import UnreadablePDF, open_pdf, parse_cells, read_cells

WEIGHTS = {
    "page_size": 0.3,
    "creator": 0.3,
    "unexpected_font": 0.6,
    "header_labels": 0.4,
    "column_positions": 0.5,
    "table_font": 0.5,
    "table_font_size": 0.4,
    "date_format": 0.5,
    "amount_format": 0.5,
    "masthead": 0.4,
}
MIN_TOLERANCE_PT = 1.5  # column and masthead positions
SIZE_TOLERANCE_PT = 0.15  # text sizes; imitations differ by 0.3 pt or more


def _date_shape(text: str) -> str:
    return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", text))


def _amount_style(text: str) -> tuple[str, str] | None:
    """Return (grouping, suffix) for an amount with at least six integer digits."""
    m = re.match(r"^(-?[\d,]+)\.\d{2}\s*(.*)$", text)
    if not m or len(m.group(1).replace(",", "").lstrip("-")) < 6:
        return None
    whole, suffix = m.group(1).lstrip("-"), m.group(2).strip()
    if "," not in whole:
        grouping = "none"
    elif re.fullmatch(r"\d{1,3}(,\d{3})+", whole):
        grouping = "western"
    elif re.fullmatch(r"\d{1,2}(,\d{2})*,\d{3}", whole):
        grouping = "indian"
    else:
        grouping = "other"
    return grouping, suffix


def _measure(doc) -> tuple[dict, list]:
    """Return the fingerprint of an open document and its text cells."""
    meta = doc.metadata or {}
    page = doc[0]
    size = [round(page.rect.width), round(page.rect.height)]
    fonts = sorted({f[3].split("+", 1)[-1] for p in range(doc.page_count)
                    for f in doc.get_page_fonts(p)})
    cells = read_cells(doc)
    parsed = parse_cells(cells, doc.page_count)
    page0 = [c for c in cells if c.page == 0]
    top = [c for c in page0 if c.bbox[1] < (parsed.header_top.get(0, 200))]
    masthead = max(top or page0, key=lambda c: (c.size, -c.bbox[1]), default=None)
    balances = [r.cells["balance"] for r in parsed.rows if "balance" in r.cells]
    styles = {s for s in (_amount_style(c.text) for c in balances) if s}
    fp = {
        "page_size": size,
        "creator": meta.get("creator", ""),
        "fonts": fonts,
        "text_layer": bool(cells),
        "rows": len(parsed.rows),
        "header_labels": parsed.header_labels.get(0, []),
        "columns": parsed.columns.get(0, {}),
        "table_font": Counter(c.font for c in balances).most_common(1)[0][0] if balances else "",
        "table_font_size": (round(statistics.median(c.size for c in balances), 1)
                            if balances else None),
        "date_shapes": sorted({_date_shape(r.date) for r in parsed.rows}),
        "amount_styles": sorted(styles),
        "masthead": ({"text": masthead.text, "font": masthead.font, "size": round(masthead.size, 1),
                      "x0": round(masthead.bbox[0], 1)} if masthead else None),
        "page0_text": " ".join(c.text for c in page0),
    }
    return fp, cells


def fingerprint(pdf_path: str | Path, password: str | None = None) -> dict:
    """Measure the template properties of one statement."""
    with open_pdf(pdf_path, password) as doc:
        return _measure(doc)[0]


def _near(value: float, allowed) -> bool:
    return any(abs(value - a) <= SIZE_TOLERANCE_PT for a in allowed)


def fit_profiles(samples: list[tuple[str, str | Path]]) -> dict:
    """Learn one profile per bank from ``(bank_id, genuine_pdf)`` pairs."""
    by_bank: dict[str, list[dict]] = {}
    for bank_id, pdf in samples:
        fp = fingerprint(pdf)
        if fp["rows"]:
            by_bank.setdefault(bank_id, []).append(fp)
    profiles = {}
    for bank_id, fps in by_bank.items():
        cols = {}
        for key in ("debit", "credit", "balance"):
            values = [fp["columns"][key] for fp in fps if key in fp["columns"]]
            if values:
                cols[key] = {"mean": round(statistics.mean(values), 3),
                             "std": round(statistics.pstdev(values), 3)}
        mx = [fp["masthead"]["x0"] for fp in fps if fp["masthead"]]
        profiles[bank_id] = {
            "n": len(fps),
            "bank_name": Counter(fp["masthead"]["text"] for fp in fps
                                 if fp["masthead"]).most_common(1)[0][0],
            "page_sizes": sorted({tuple(fp["page_size"]) for fp in fps}),
            "creators": sorted({fp["creator"] for fp in fps}),
            "fonts": sorted({f for fp in fps for f in fp["fonts"]}),
            "header_labels": sorted({t for fp in fps for t in fp["header_labels"]}),
            "columns": cols,
            "table_fonts": sorted({fp["table_font"] for fp in fps}),
            "table_font_sizes": sorted({fp["table_font_size"] for fp in fps}),
            "date_shapes": sorted({s for fp in fps for s in fp["date_shapes"]}),
            "amount_styles": sorted({tuple(s) for fp in fps for s in fp["amount_styles"]}),
            "masthead": {
                "fonts": sorted({fp["masthead"]["font"] for fp in fps if fp["masthead"]}),
                "sizes": sorted({fp["masthead"]["size"] for fp in fps if fp["masthead"]}),
                "x0_mean": round(statistics.mean(mx), 2) if mx else None,
                "x0_std": round(statistics.pstdev(mx), 3) if mx else None,
            },
        }
    return profiles


@dataclass
class TemplateFinding:
    check: str
    message: str
    locations: list[dict] = field(default_factory=list)


@dataclass
class TemplateReport:
    bank_id: str | None
    findings: list[TemplateFinding] = field(default_factory=list)
    abstained: bool = False
    reason: str = ""

    @property
    def suspicious(self) -> bool:
        return bool(self.findings)

    @property
    def score(self) -> float:
        if self.abstained:
            return 0.5
        clean = 1.0
        for check in {f.check for f in self.findings}:
            clean *= 1 - WEIGHTS[check]
        return round(1 - clean, 4)

    def locations(self) -> list[dict]:
        return [loc for f in self.findings for loc in f.locations]

    def features(self) -> dict[str, float]:
        fired = {f.check for f in self.findings}
        out = {f"tpl_{name}": float(name in fired) for name in WEIGHTS}
        out.update({"tpl_abstained": float(self.abstained), "tpl_score": self.score})
        return out

    def to_dict(self) -> dict:
        return {"signal": "template", "bank_id": self.bank_id, "suspicious": self.suspicious,
                "abstained": self.abstained, "reason": self.reason, "score": self.score,
                "findings": [asdict(f) for f in self.findings], "features": self.features()}


class TemplateMatcher:
    """Compare statements with the learned profile of the bank they claim to come from.

    ``meta`` is free-form information about how the profiles were fitted (for example the
    machine's fonts and library versions); it is saved with the profiles.
    """

    def __init__(self, profiles: dict, meta: dict | None = None):
        self.profiles = profiles
        self.meta = meta or {}

    @classmethod
    def load(cls, path: str | Path) -> TemplateMatcher:
        data = json.loads(Path(path).read_text())
        if "profiles" in data and isinstance(data.get("meta"), dict):
            return cls(data["profiles"], data["meta"])
        return cls(data)  # profile files written before meta was added

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({"meta": self.meta, "profiles": self.profiles},
                                         indent=2))

    def identify(self, fp: dict) -> str | None:
        text = re.sub(r"\s+", " ", fp["page0_text"]).lower()
        hits = [b for b, p in self.profiles.items() if p["bank_name"].lower() in text]
        return max(hits, key=lambda b: len(self.profiles[b]["bank_name"])) if hits else None

    def check(self, pdf_path: str | Path, bank_id: str | None = None,
              password: str | None = None) -> TemplateReport:
        try:
            with open_pdf(pdf_path, password) as doc:
                fp, cells = _measure(doc)
        except UnreadablePDF as exc:
            return TemplateReport(bank_id, abstained=True, reason=str(exc))
        if not fp["text_layer"]:
            return TemplateReport(None, abstained=True, reason="no text layer")
        bank_id = bank_id or self.identify(fp)
        if bank_id not in self.profiles:
            return TemplateReport(bank_id, abstained=True, reason="bank not recognised")
        p = self.profiles[bank_id]
        report = TemplateReport(bank_id)
        add = report.findings.append
        name = p["bank_name"]

        if tuple(fp["page_size"]) not in {tuple(s) for s in p["page_sizes"]}:
            add(TemplateFinding("page_size", f"Page size {fp['page_size'][0]}×{fp['page_size'][1]} pt "
                                f"differs from {name} statements."))
        if fp["creator"] not in p["creators"]:
            add(TemplateFinding("creator", f"The PDF was created by '{fp['creator'] or '(blank)'}'; "
                                f"{name} statements are created by '{', '.join(p['creators'])}'."))
        unexpected = sorted(set(fp["fonts"]) - set(p["fonts"]))
        if unexpected:
            add(TemplateFinding(
                "unexpected_font",
                f"Font(s) {', '.join(unexpected)} are never used in {name} statements.",
                [{"page": c.page, "bbox": [round(v, 2) for v in c.bbox], "text": c.text,
                  "font": c.font} for c in cells if c.font in unexpected]))
        new_labels = [t for t in fp["header_labels"] if t not in p["header_labels"]]
        if new_labels:
            add(TemplateFinding("header_labels", f"Table header text {new_labels} does not match "
                                f"{name}'s usual headings."))
        for key, ref in p["columns"].items():
            value = fp["columns"].get(key)
            tol = max(MIN_TOLERANCE_PT, 4 * ref["std"])
            if value is not None and abs(value - ref["mean"]) > tol:
                add(TemplateFinding("column_positions",
                                    f"The {key} column ends at x={value:.1f} pt; in {name} "
                                    f"statements it ends at {ref['mean']:.1f} pt."))
        if fp["table_font"] and fp["table_font"] not in p["table_fonts"]:
            add(TemplateFinding("table_font", f"Table figures use {fp['table_font']}; {name} uses "
                                f"{', '.join(p['table_fonts'])}."))
        if fp["table_font_size"] is not None and not _near(fp["table_font_size"],
                                                           p["table_font_sizes"]):
            add(TemplateFinding("table_font_size",
                                f"Table text is {fp['table_font_size']} pt; {name} uses "
                                f"{', '.join(str(s) for s in p['table_font_sizes'])} pt."))
        odd_dates = [s for s in fp["date_shapes"] if s not in p["date_shapes"]]
        if odd_dates:
            add(TemplateFinding("date_format", f"Dates shaped {odd_dates} differ from {name}'s "
                                f"format {p['date_shapes']}."))
        ref_styles = {tuple(s) for s in p["amount_styles"]}
        odd_amounts = [s for s in fp["amount_styles"] if tuple(s) not in ref_styles]
        if odd_amounts and ref_styles:
            add(TemplateFinding("amount_format", f"Amounts are written as {odd_amounts}; {name} "
                                f"writes {sorted(ref_styles)} (grouping, suffix)."))
        mh, ref = fp["masthead"], p["masthead"]
        if mh and ref["fonts"]:
            off_x = ref["x0_mean"] is not None and abs(mh["x0"] - ref["x0_mean"]) > max(
                MIN_TOLERANCE_PT, 4 * (ref["x0_std"] or 0))
            if mh["font"] not in ref["fonts"] or not _near(mh["size"], ref["sizes"]) or off_x:
                add(TemplateFinding("masthead", f"The bank name is set in {mh['font']} "
                                    f"{mh['size']} pt at x={mh['x0']}; {name} uses "
                                    f"{', '.join(ref['fonts'])} {ref['sizes']} pt."))
        return report
