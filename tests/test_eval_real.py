"""Real-statement evaluation: passwords, aggregate-only output, a saved fusion model."""

from __future__ import annotations

import importlib.util
import json
import pickle
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("weasyprint")

REPO = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("eval_real", REPO / "scripts" / "eval_real.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eval_real_reads_locked_files_and_writes_only_aggregates(tmp_path):
    import pymupdf
    from test_fusion import _statements

    from forgelens.fusion.fuse import fit_final, out_of_fold

    statements = _statements(40)
    for st in statements:
        st.scores["image"] = None  # a model of the PDF signals only, as without a GPU
    final = fit_final(statements, out_of_fold(statements))
    model = tmp_path / "model.pkl"
    model.write_bytes(pickle.dumps(final))

    gen = tmp_path / "gen"
    subprocess.run([sys.executable, str(REPO / "scripts" / "generate_statements.py"), "--bank",
                    "sahyadri", "--count", "3", "--seed", "2000", "--months", "1", "--out",
                    str(gen)], check=True, capture_output=True)
    real = tmp_path / "real_statements"
    real.mkdir(mode=0o700)
    pdfs = sorted(gen.rglob("*.pdf"))
    shutil.copy(pdfs[0], real / "S001.pdf")
    with pymupdf.open(pdfs[1]) as d:
        d.save(real / "S002.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw1",
               owner_pw="o")
    with pymupdf.open(pdfs[2]) as d:
        d.save(real / "S003.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw2",
               owner_pw="o")
    (real / "statements.tsv").write_text(
        "file\tbank\tpassword\nS001.pdf\tBank A\t\nS002.pdf\tBank B\tpw1\nS003.pdf\tBank B\twrong\n")

    summary = tmp_path / "out" / "real.md"
    assert _script().main(["--folder", str(real), "--fusion", str(model),
                           "--summary", str(summary)]) == 0
    data = json.loads(summary.with_suffix(".json").read_text())
    assert data["statements"] == 3 and data["read"] == 2
    assert data["errors"] == {"password missing or wrong": 1}
    assert data["flagged"]["fused_boosting@0.01"]["assessed"] == 2
    text = summary.read_text()
    assert "S00" not in text or "Flagged IDs" in text  # IDs only, never file contents
    assert sorted(p.name for p in summary.parent.iterdir()) == ["real.json", "real.md"]
    assert sorted(p.name for p in real.iterdir()) == ["S001.pdf", "S002.pdf", "S003.pdf",
                                                      "statements.tsv"]  # nothing written there


def test_eval_real_refuses_a_template_model(tmp_path):
    (tmp_path / "statements.tsv").write_text("file\tbank\tpassword\n")
    model = tmp_path / "m.pkl"
    model.write_bytes(pickle.dumps({"signals": ["template", "structure"]}))
    with pytest.raises(SystemExit, match="template"):
        _script().main(["--folder", str(tmp_path), "--fusion", str(model),
                        "--summary", str(tmp_path / "s.md")])


def test_text_statements_are_fused_without_image_and_ocr_scores():
    import importlib.util
    from pathlib import Path

    from forgelens.fusion.fuse import Statement

    spec = importlib.util.spec_from_file_location(
        "eval_real", Path(__file__).resolve().parents[1] / "scripts" / "eval_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    st = Statement("S001.pdf", "genuine", "real", "none", "b", "S001")
    st.scores = {"financial": 0.0, "structure": 0.1, "image": 0.9, "ocr_financial": 0.7}
    st.image_area = 0.01
    text = mod.for_fusion(st, {"image_only": False})
    assert text.scores["image"] is None and text.scores["ocr_financial"] is None
    assert st.scores["image"] == 0.9  # the original keeps its scores for the single signals
    assert mod.for_fusion(st, {"image_only": True}) is st
