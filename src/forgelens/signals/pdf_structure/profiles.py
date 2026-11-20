"""Bank profiles: structure findings that a bank's own genuine statements show.

Some bank software builds every statement in a way the structure checks cannot tell from an
edit by looking at one file: PNB's statements (OpenPDF) all draw one page in a non-embedded
font and use a second font for a few spans on the last page. A lender knows which bank a
statement claims to come from, and sees many genuine statements from each, so ForgeLens keeps,
per bank and producing software, the *signatures* of the structure findings their genuine
statements show, and does not count a finding whose signature the profile already holds.

A signature names the check, the fonts it is about (families, without subset tags) and where
in the document it occurs (first page, last page, middle, several pages), never any text. A
profile entry comes from genuine statements only. Evaluated leaving each statement out: a
statement is judged against profiles built from the *other* genuine statements.

A forger who imitates exactly what a bank's software does (the same font, on the same page)
is not caught by these checks for that bank; the arithmetic, OCR, template and image signals
still apply.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .analyzer import WEIGHTS, StructureReport, family_weight

PROFILED = ("non_embedded_font", "duplicate_font", "font_anomaly")


def producer_key(producer: str | None) -> str:
    """Producing software without versions or build numbers: 'OpenPDF 1.3.32' -> 'openpdf'."""
    s = re.sub(r"\(.*?\)", " ", (producer or "").lower())
    words = [w for w in re.findall(r"[a-z]+", s) if w not in ("version", "build", "http", "www")]
    return " ".join(words[:4])


def bank_key(bank: str | None) -> str:
    return re.sub(r"[^a-z]", "", (bank or "").lower().replace("bank", ""))


def _where(pages: list[int], n_pages: int) -> str:
    if not pages:
        return "doc"
    if len(set(pages)) > 1:
        return "several"
    p = pages[0]
    return "first" if p == 0 else "last" if p == n_pages - 1 else "middle"


def signatures(report: StructureReport) -> list[str]:
    """One signature per profilable finding of ``report``."""
    n_pages = (report.stats or {}).get("pages") or 0
    out = []
    for f in report.findings:
        if f.check not in PROFILED:
            continue
        fams = sorted({family_weight(n)[0] for n in f.fonts})
        pages = sorted({loc["page"] for loc in f.locations})
        out.append(f"{f.check}|{','.join(fams)}|{_where(pages, n_pages)}")
    return out


class BankProfiles:
    def __init__(self) -> None:
        # (bank, producer) -> signature -> ids of the genuine statements that showed it
        self.seen: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    def add(self, statement_id: str, bank: str, producer: str, report: StructureReport) -> None:
        key = (bank_key(bank), producer_key(producer))
        for sig in signatures(report):
            self.seen[key][sig].add(statement_id)

    def known(self, bank: str, producer: str, sig: str, exclude: str | None = None) -> bool:
        ids = self.seen.get((bank_key(bank), producer_key(producer)), {}).get(sig, set())
        return bool(ids - {exclude})

    def score(self, report: StructureReport, bank: str, producer: str,
              exclude: str | None = None) -> float:
        """The structure score without findings the bank's genuine statements also show
        (``exclude``: the statement being judged, left out of its own profile)."""
        if report.abstained:
            return report.score
        n_pages = (report.stats or {}).get("pages") or 0
        clean = 1.0
        kept = set()
        for f in report.findings:
            if f.check in PROFILED:
                fams = sorted({family_weight(n)[0] for n in f.fonts})
                pages = sorted({loc["page"] for loc in f.locations})
                if self.known(bank, producer, f"{f.check}|{','.join(fams)}|{_where(pages, n_pages)}",
                              exclude):
                    continue
            kept.add(f.check)
        for check in kept:
            clean *= 1 - WEIGHTS[check]
        return round(1 - clean, 4)

    def to_json(self) -> dict:
        return {f"{b}|{p}": {sig: len(ids) for sig, ids in sigs.items()}
                for (b, p), sigs in self.seen.items()}

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), indent=1, sort_keys=True))

    @classmethod
    def load(cls, path: Path) -> "BankProfiles":
        prof = cls()
        for key, sigs in json.loads(Path(path).read_text()).items():
            b, p = key.split("|", 1)
            for sig, n in sigs.items():
                prof.seen[(b, p)][sig] = {f"stored{i}" for i in range(int(n))}
        return prof

    def summary(self) -> Counter:
        return Counter({f"{b}|{p}": len(s) for (b, p), s in self.seen.items()})
