"""Detection and localisation metrics with confidence intervals."""

from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for a proportion ``k / n`` (95% by default).

    Unlike the normal approximation it stays inside [0, 1] and is reliable for proportions
    near 0 or 1, such as a false-positive rate of 0 out of 300.
    """
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def _ratio(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def binary_metrics(labels: list[bool], flags: list[bool]) -> dict:
    """Confusion counts, rates and 95% intervals; ``labels`` is True for forged files."""
    tp = sum(y and f for y, f in zip(labels, flags))
    fp = sum(not y and f for y, f in zip(labels, flags))
    fn = sum(y and not f for y, f in zip(labels, flags))
    tn = sum(not y and not f for y, f in zip(labels, flags))
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f1 = (round(2 * precision * recall / (precision + recall), 4)
          if precision and recall else 0.0)
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "accuracy": _ratio(tp + tn, len(labels)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": _ratio(fp, fp + tn),
        "precision_ci95": wilson(tp, tp + fp),
        "recall_ci95": wilson(tp, tp + fn),
        "false_positive_rate_ci95": wilson(fp, fp + tn),
    }


def overlaps(a, b) -> bool:
    """True when boxes ``(x0, y0, x1, y1)`` share any area or touch."""
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def localisation(edits: list[dict], locations: list[dict]) -> dict:
    """Compare the regions a signal points at with the regions that were really edited.

    ``edits`` carry ``page`` and ``mask_bbox``; ``locations`` carry ``page`` and ``bbox``.
    Recall is the share of edits that some location overlaps; precision is the share of
    locations that overlap some edit. Both are needed: a signal that pointed at every word
    on the page would have perfect recall and useless precision.
    """
    found = sum(any(lc["page"] == e["page"] and overlaps(lc["bbox"], e["mask_bbox"])
                    for lc in locations) for e in edits)
    correct = sum(any(lc["page"] == e["page"] and overlaps(lc["bbox"], e["mask_bbox"])
                      for e in edits) for lc in locations)
    return {"edits": len(edits), "edits_found": found, "locations": len(locations),
            "locations_on_edits": correct}


def localisation_summary(counts: dict) -> dict:
    """Recall and precision (with 95% intervals) from summed ``localisation`` counts."""
    return {
        "edits": counts["edits"],
        "locations": counts["locations"],
        "recall": _ratio(counts["edits_found"], counts["edits"]),
        "recall_ci95": wilson(counts["edits_found"], counts["edits"]),
        "precision": _ratio(counts["locations_on_edits"], counts["locations"]),
        "precision_ci95": wilson(counts["locations_on_edits"], counts["locations"]),
    }
