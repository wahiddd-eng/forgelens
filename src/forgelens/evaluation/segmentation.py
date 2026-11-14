"""Pixel-level localisation metrics for forgery masks.

``image_scores`` reproduces the per-image F1 that ADCD-Net and the ForensicHub Doc Protocol
report (``Trainer.compute_f1`` in ``third_party/ADCD-Net/main.py``): precision, recall and F1
of the tampered class for one image, with the same epsilon, so our numbers are directly
comparable with the published table. ``summarise`` averages them over a dataset and also
reports the pooled (micro) pixel F1 and IoU, which do not let small masks dominate.

The functions take pixel counts, not arrays, so they need neither NumPy nor PyTorch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EPS = 1e-8  # the epsilon ADCD-Net uses


@dataclass(frozen=True)
class PixelCounts:
    """Pixel counts of one image: true positives, predicted-tampered and truly tampered."""

    tp: int
    pred: int
    gt: int

    def __post_init__(self):
        if not 0 <= self.tp <= min(self.pred, self.gt):
            raise ValueError(f"impossible counts: tp={self.tp}, pred={self.pred}, gt={self.gt}")


def image_scores(c: PixelCounts) -> dict[str, float]:
    """Precision, recall, F1 (ADCD-Net's formula) and IoU of the tampered class in one image."""
    p = c.tp / (c.pred + EPS)
    r = c.tp / (c.gt + EPS)
    union = c.pred + c.gt - c.tp
    return {
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r + EPS),
        "iou": c.tp / union if union else 1.0,  # nothing predicted and nothing tampered
    }


def _mean_ci(values: list[float]) -> tuple[float, float, float]:
    """Mean and its 95% confidence interval (normal approximation)."""
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, mean, mean
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    half = 1.96 * sd / math.sqrt(n)
    return mean, max(0.0, mean - half), min(1.0, mean + half)


def summarise(counts: list[PixelCounts]) -> dict[str, float | int | None]:
    """Dataset-level scores.

    ``f1``, ``precision``, ``recall`` and ``iou`` are means of per-image scores (``f1`` is the
    number the Doc Protocol reports); ``f1_ci_low``/``f1_ci_high`` bound the mean F1;
    ``pixel_f1`` and ``pixel_iou`` pool all pixels first. ``n_empty_gt`` counts images with
    no tampered pixels: the Doc Protocol skips authentic images, so it should be 0.
    """
    if not counts:
        return {"n": 0, "n_empty_gt": 0, "f1": None, "f1_ci_low": None, "f1_ci_high": None,
                "precision": None, "recall": None, "iou": None, "pixel_f1": None,
                "pixel_iou": None}
    scores = [image_scores(c) for c in counts]
    f1, low, high = _mean_ci([s["f1"] for s in scores])
    tp = sum(c.tp for c in counts)
    pred = sum(c.pred for c in counts)
    gt = sum(c.gt for c in counts)
    pooled = image_scores(PixelCounts(tp, pred, gt))
    return {
        "n": len(counts),
        "n_empty_gt": sum(c.gt == 0 for c in counts),
        "f1": f1,
        "f1_ci_low": low,
        "f1_ci_high": high,
        "precision": sum(s["precision"] for s in scores) / len(scores),
        "recall": sum(s["recall"] for s in scores) / len(scores),
        "iou": sum(s["iou"] for s in scores) / len(scores),
        "pixel_f1": pooled["f1"],
        "pixel_iou": pooled["iou"],
    }
