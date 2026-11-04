"""Run the experiment scripts end to end on a tiny dataset, as the paper's numbers are made.

The scripts are what produce every reported figure, so they are tested as a pipeline:
generate → forge (PDF edits, rebuilds) → launder → fit templates → evaluate → compare.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("weasyprint")
pytest.importorskip("pymupdf")

from forgelens.forgery import ghostscript

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _run(script: str, *args) -> str:
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                            capture_output=True, text=True, timeout=600, check=False)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return result.stdout


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    root = tmp_path_factory.mktemp("pipeline")
    gen, train, forged = root / "genuine", root / "train", root / "forged"
    _run("generate_statements.py", "--bank", "all", "--count", 1, "--seed", 0, "--months", 1,
         "--out", gen)
    _run("generate_statements.py", "--bank", "all", "--count", 2, "--seed", 900, "--months", 1,
         "--out", train)
    _run("forge_pdf_edits.py", "--genuine", gen, "--out", forged / "pdf_edit", "--masks",
         "--dpi", 40)
    _run("forge_rebuild.py", "--genuine", gen, "--out", forged / "rebuild", "--masks",
         "--dpi", 40)
    _run("launder_pdfs.py", "--input", forged / "pdf_edit", "--out", forged / "pdf_edit_raster",
         "--method", "raster", "--dpi", 40, "--masks")
    if ghostscript():
        _run("launder_pdfs.py", "--input", forged / "rebuild", "--out",
             forged / "rebuild_reprint", "--method", "reprint")
    _run("fit_templates.py", "--genuine", train, "--out", root / "templates.json")
    _run("eval_signals.py", "--genuine", gen, "--forged", forged, "--templates",
         root / "templates.json", "--out", root / "results", "--tag", "smoke")
    return root


def test_generator_writes_a_manifest_with_fonts(pipeline):
    manifest = json.loads((pipeline / "genuine" / "manifest.json").read_text())
    assert manifest["run"]["packages"]["forgelens"]
    assert all(b["statements"] == 1 and b["fonts"] for b in manifest["banks"].values())


def test_every_forgery_has_a_label_and_masks(pipeline):
    for folder in ("pdf_edit", "rebuild", "pdf_edit_raster"):
        labels = [json.loads(p.read_text()) for p in (pipeline / "forged" / folder).glob("*.json")]
        assert len(labels) == 10, folder
        for label in labels:
            assert label["label"] == "forged" and label["edits"]
            for mask in label["masks"]["files"]:
                assert (pipeline / "forged" / folder / mask).exists()
    assert not list((pipeline / "forged").rglob("*.partial.pdf"))


def test_forgeries_do_not_depend_on_the_other_files(pipeline, tmp_path):
    one_bank = pipeline / "genuine" / "sahyadri"
    _run("forge_pdf_edits.py", "--genuine", one_bank, "--out", tmp_path, "--masks", "--dpi", 40)
    labels = list(tmp_path.glob("*.json"))
    assert labels
    for label in labels:
        assert label.read_text() == (pipeline / "forged" / "pdf_edit" / label.name).read_text()


def test_evaluation_summary_is_complete_and_traceable(pipeline):
    summary = json.loads((pipeline / "results" / "signals_smoke_summary.json").read_text())
    assert summary["counts"] == {"genuine": 10, "forged": 30 + 10 * bool(ghostscript()),
                                 "errors": 0}
    assert summary["run"]["packages"]["pymupdf"]
    assert summary["template_profiles"]["statements"] == 20
    for signal in ("financial", "structure", "template", "either"):
        assert summary["overall"][signal]["false_positive_rate"] == 0.0, signal
        assert summary["overall"][signal]["recall_ci95"] is not None
    assert {"structure|pdf_edit", "template|rebuild"} <= set(summary["localisation"])
    assert summary["abstention_rate"]["financial"] > 0  # the rasterised files


def test_compare_results_reads_the_summaries(pipeline):
    out = pipeline / "results" / "robustness.md"
    _run("compare_results.py", "--results", pipeline / "results", "--tags", "smoke",
         "--out", out)
    assert "Any signal" in out.read_text()
