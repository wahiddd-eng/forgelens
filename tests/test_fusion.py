"""Fusion of the signals: loading, out-of-fold scores, single-threshold detection."""

from __future__ import annotations

import csv
import random

import pytest

pytest.importorskip("sklearn")

from forgelens.fusion import Statement, evaluate, join, load_image, load_signals, out_of_fold
from forgelens.fusion.fuse import auc, source_of, threshold_at


def test_threshold_auc_and_source():
    genuine = [i / 100 for i in range(100)]
    t = threshold_at(genuine, 0.01)
    assert sum(g > t for g in genuine) == 1
    assert auc([0.1, 0.2], [0.3]) == 1.0 and auc([0.5], [0.5]) == 0.5
    assert source_of("sahyadri_002000__raster_mixq.pdf") == "sahyadri_002000"
    assert source_of("gen_0007_006000.pdf") == "gen_0007_006000"


def _statements(n=60, seed=0):
    """Two kinds of forgery, each visible to a different signal: fusion should catch both."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        src = f"bank_{i:06d}"
        digital = i % 2 == 0
        g = Statement(f"{src}.pdf", "genuine", "genuine", "none" if digital else "raster",
                      "bank", src)
        g.scores = {"image": None if digital else rng.uniform(0, 0.4),
                    "financial": rng.uniform(0, 0.1) if digital else None,
                    "structure": rng.uniform(0, 0.2) if digital else None, "template": None}
        pdf = Statement(f"{src}__pdf.pdf", "forged", "pdf_edit", "none", "bank", src)
        pdf.scores = {"image": None, "financial": rng.uniform(0, 0.1),
                      "structure": rng.uniform(0.7, 1.0), "template": None}
        img = Statement(f"{src}__img.pdf", "forged", "image_splice", "raster", "bank", src)
        img.scores = {"image": rng.uniform(0.7, 1.0), "financial": None, "structure": None,
                      "template": None}
        out += [g, pdf, img]
    return out


def test_fusion_catches_what_each_signal_catches_alone():
    statements = _statements()
    fused = out_of_fold(statements, folds=5)
    assert set(fused) == {"fused_logistic", "fused_boosting"}
    result = evaluate(statements, fused)
    o = result["overall"]
    assert o["image"]["caught@0.05"] < 0.6 and o["structure"]["caught@0.05"] < 0.6
    for name in fused:
        assert o[name]["caught@0.05"] > 0.9, name
        assert o[name]["false_alarms@0.05"] <= 0.05
    assert result["by_kind"]["pdf_edit|none"]["fused_boosting@0.05"] > 0.9
    assert result["by_kind"]["image_splice|raster"]["fused_boosting@0.05"] > 0.9
    assert "template" not in result["signals"]  # never run: left out


def test_loading_csvs_marks_abstentions_as_missing(tmp_path):
    sig = tmp_path / "s.csv"
    with open(sig, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "label", "bank_id", "method", "laundering", "error",
                    "financial_score", "financial_abstained", "structure_score",
                    "structure_abstained"])
        w.writerow(["a.pdf", "genuine", "b", "genuine", "", "", "0.0", "False", "0.1", "False"])
        w.writerow(["a__raster.pdf", "genuine", "b", "genuine", "raster", "", "0.5", "True",
                    "0.5", "True"])
    pages = tmp_path / "p.csv"
    with open(pages, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "page", "peak", "area", "error"])
        w.writerows([["a__raster.pdf", 0, 0.2, 0.001, ""], ["a__raster.pdf", 1, 0.6, 0.0, ""]])
    st = {s.file: s for s in join(load_signals([sig]), load_image([pages]))}
    assert st["a.pdf"].scores == {"financial": 0.0, "structure": 0.1, "template": None,
                                  "image": None}
    assert st["a.pdf"].laundering == "none" and st["a__raster.pdf"].laundering == "raster"
    raster = st["a__raster.pdf"]
    assert raster.scores["financial"] is None and raster.scores["image"] == 0.6
    assert raster.image_area == 0.001 and raster.group == "a"
