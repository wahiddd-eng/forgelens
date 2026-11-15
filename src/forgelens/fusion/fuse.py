"""Combine the four signals into one score per statement, and measure what that gains.

Inputs, one row per statement:

* the rule-based signals from ``scripts/eval_signals.py`` (its ``*_per_file.csv``): a score in
  [0, 1] and an abstention flag for financial consistency, PDF structure and template
  matching (a signal abstains when it cannot read the file, e.g. any image-only PDF);
* the image signal from ``scripts/eval_adcdnet_pages.py`` (its ``pages.csv``): the page peak
  score (mean of the 500 most suspicious pixels) and the share of pixels flagged, taken as the
  maximum over a statement's pages.

A signal that abstains, or was not run on a file, is a missing value, never "genuine": the
fusion model sees a present/absent flag beside each score. Two fusion models are fitted:
logistic regression (missing scores set to 0.5, with the flags) and gradient boosting
(scikit-learn's histogram boosting, which handles missing values itself).

Every fused score is out-of-fold: statements are split into folds by source statement (a
genuine statement and every forgery made from it share a fold), each fold is scored by a
model fitted on the others. Detection is then measured as a real deployment would face it:
one threshold for all inputs, set so that a given share of all genuine statements (digital
and rasterised together) is flagged, and the share of each kind of forgery caught at that
threshold.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PDF_SIGNALS = ("financial", "structure", "template")
IMAGE = "image"
SINGLE = (IMAGE, *PDF_SIGNALS)
FUSED = ("fused_logistic", "fused_boosting")


@dataclass
class Statement:
    file: str
    label: str  # genuine | forged
    method: str  # genuine, pdf_edit, rebuild, image_splice, image_inpaint, ...
    laundering: str  # none | raster | reprint ...
    bank: str
    group: str  # source statement: a genuine statement and its forgeries share it
    scores: dict[str, float | None] = field(default_factory=dict)  # None = abstained/missing
    image_area: float | None = None

    @property
    def forged(self) -> bool:
        return self.label == "forged"


def source_of(file: str) -> str:
    """The genuine statement a file was made from: the part of its name before ``__``."""
    return Path(file).stem.split("__")[0]


def _float(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _true(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def load_signals(paths: list[Path]) -> dict[str, Statement]:
    """Statements from ``eval_signals.py`` per-file CSVs (later files win on duplicates)."""
    out: dict[str, Statement] = {}
    for path in paths:
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                st = Statement(file=row["file"], label=row["label"],
                               method=row.get("method") or "genuine",
                               laundering=row.get("laundering") or "none",
                               bank=row.get("bank_id", ""), group=source_of(row["file"]))
                for s in PDF_SIGNALS:
                    if f"{s}_score" not in row or row[f"{s}_score"] == "":
                        st.scores[s] = None  # not run (e.g. no template profiles)
                    elif _true(row.get(f"{s}_abstained")) or row.get("error"):
                        st.scores[s] = None
                    else:
                        st.scores[s] = _float(row[f"{s}_score"])
                out[st.file] = st
    return out


def load_image(paths: list[Path]) -> dict[str, tuple[float, float]]:
    """``file -> (peak, area)`` from ``eval_adcdnet_pages.py`` pages.csv files, max over pages."""
    best: dict[str, tuple[float, float]] = {}
    for path in paths:
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("error"):
                    continue
                peak, area = _float(row.get("peak")), _float(row.get("area"))
                if peak is None:
                    continue
                name = Path(row["file"]).name  # pages.csv records the full path
                old = best.get(name, (-1.0, -1.0))
                best[name] = (max(old[0], peak), max(old[1], area or 0.0))
    return best


def join(signals: dict[str, Statement], image: dict[str, tuple[float, float]]) -> list[Statement]:
    """Add the image scores to the statements (missing where the image model was not run)."""
    for file, st in signals.items():
        peak_area = image.get(file)
        st.scores[IMAGE] = peak_area[0] if peak_area else None
        st.image_area = peak_area[1] if peak_area else None
    return list(signals.values())


# ---------------------------------------------------------------- fusion

def present_signals(statements: list[Statement]) -> list[str]:
    """The signals with a score for at least one statement (a signal never run is left out)."""
    return [s for s in SINGLE if any(st.scores.get(s) is not None for st in statements)]


def features(statements: list[Statement], with_missing: bool):
    """Feature matrix: per signal a score and a present flag (and the image's flagged area).

    ``with_missing``: leave absent scores as NaN (for boosting); otherwise set them to 0.5.
    """
    import numpy as np

    signals = present_signals(statements)
    use_area = any(st.image_area is not None for st in statements)
    rows = []
    for st in statements:
        row = []
        for s in signals:
            v = st.scores.get(s)
            row += [v if v is not None else (np.nan if with_missing else 0.5),
                    0.0 if v is None else 1.0]
        if use_area:
            a = st.image_area
            row.append(a if a is not None else (np.nan if with_missing else 0.0))
        rows.append(row)
    return np.asarray(rows, dtype=float)


def out_of_fold(statements: list[Statement], folds: int = 5, seed: int = 0) -> dict[str, list[float]]:
    """Out-of-fold fused scores for each fusion model, in the order of ``statements``."""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    y = np.array([st.forged for st in statements], dtype=int)
    groups = np.array([st.group for st in statements])
    x_fill, x_nan = features(statements, False), features(statements, True)
    models = {
        "fused_logistic": (lambda: make_pipeline(StandardScaler(),
                                                 LogisticRegression(max_iter=2000, C=1.0)),
                           x_fill),
        "fused_boosting": (lambda: HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.05, max_leaf_nodes=15, random_state=seed), x_nan),
    }
    out = {name: np.zeros(len(statements)) for name in models}
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    for train, test in splitter.split(x_fill, y, groups):
        for name, (make, x) in models.items():
            model = make().fit(x[train], y[train])
            out[name][test] = model.predict_proba(x[test])[:, 1]
    return {k: v.tolist() for k, v in out.items()}


# ---------------------------------------------------------------- measurement

def threshold_at(genuine_scores: list[float], fpr: float) -> float:
    """The lowest threshold that flags at most ``fpr`` of genuine statements (score > t)."""
    s = sorted(genuine_scores, reverse=True)
    allowed = math.floor(fpr * len(s))
    return s[allowed] if allowed < len(s) else -math.inf


def auc(neg: list[float], pos: list[float]) -> float | None:
    if not neg or not pos:
        return None
    wins = 0.0
    neg_sorted = sorted(neg)
    import bisect

    for p in pos:
        lo = bisect.bisect_left(neg_sorted, p)
        hi = bisect.bisect_right(neg_sorted, p)
        wins += lo + 0.5 * (hi - lo)
    return wins / (len(neg) * len(pos))


def evaluate(statements: list[Statement], fused: dict[str, list[float]],
             fprs: tuple[float, ...] = (0.01, 0.05)) -> dict:
    """Per-signal and fused detection: overall AUC, and the share caught per forgery kind at
    a single threshold that flags ``fpr`` of all genuine statements.

    A single signal's missing score counts as 0.5 (no evidence), as in a deployment where an
    abstaining signal neither raises nor lowers suspicion.
    """
    def score(name: str, i: int) -> float:
        if name in fused:
            return fused[name][i]
        v = statements[i].scores.get(name)
        return 0.5 if v is None else v

    names = present_signals(statements) + list(fused)
    genuine = [i for i, st in enumerate(statements) if not st.forged]
    forged = [i for i, st in enumerate(statements) if st.forged]
    kinds: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i in forged:
        kinds[(statements[i].method, statements[i].laundering)].append(i)

    result = {"counts": {"genuine": len(genuine), "forged": len(forged),
                         "genuine_by_laundering": _count(statements, genuine)},
              "signals": names, "overall": {}, "by_kind": {}}
    for name in names:
        g = [score(name, i) for i in genuine]
        f = [score(name, i) for i in forged]
        entry = {"auc": auc(g, f), "present": sum(
            1 for st in statements if name in fused or st.scores.get(name) is not None)}
        for fpr in fprs:
            t = threshold_at(g, fpr)
            entry[f"caught@{fpr:g}"] = sum(x > t for x in f) / len(f) if f else None
            entry[f"false_alarms@{fpr:g}"] = sum(x > t for x in g) / len(g) if g else None
            for kind, idx in kinds.items():
                result["by_kind"].setdefault(f"{kind[0]}|{kind[1]}", {"n": len(idx)}) \
                    [f"{name}@{fpr:g}"] = sum(score(name, i) > t for i in idx) / len(idx)
        result["overall"][name] = entry
    return result


def _count(statements: list[Statement], idx: list[int]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for i in idx:
        out[statements[i].laundering] += 1
    return dict(out)
