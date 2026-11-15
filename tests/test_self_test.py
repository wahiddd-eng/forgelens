"""The self-test kit: what it shares, and the summary of results sent back."""

from __future__ import annotations

import importlib.util
import json
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("weasyprint")
REPO = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def statement(tmp_path_factory):
    import pymupdf

    root = tmp_path_factory.mktemp("self")
    subprocess.run([sys.executable, str(REPO / "scripts" / "generate_statements.py"), "--bank",
                    "sahyadri", "--count", "1", "--seed", "2000", "--months", "1", "--out",
                    str(root / "g")], check=True, capture_output=True)
    pdf = next((root / "g").rglob("*.pdf"))
    locked = root / "locked.pdf"
    with pymupdf.open(pdf) as d:
        d.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="o")
    return pdf, locked


def test_result_holds_scores_and_no_statement_content(statement, tmp_path):
    pdf, locked = statement
    tool = _load("self_test")
    assert tool.main([str(locked), "--bank", "Test Bank", "--no-ocr", "--password", "pw",
                      "--out", str(tmp_path)]) == 0
    out = next(tmp_path.glob("forgelens_result_*.json"))
    result = json.loads(out.read_text())
    assert set(result) == {"id", "bank", "how_obtained", "pages", "image_only", "signals",
                           "forgelens"}
    assert set(result["signals"]) == {"financial", "structure"}
    assert result["signals"]["financial"]["abstained"] is False
    text = out.read_text()
    record = json.loads(pdf.with_suffix(".json").read_text())
    customer = record["customer"]
    for secret in (customer["name"], customer["account_number"], record["closing_balance"],
                   pdf.stem):
        assert secret not in text  # no name, account number or file name leaves the machine


def test_collected_results_give_a_false_alarm_summary(tmp_path):
    from test_fusion import _statements

    from forgelens.fusion.fuse import fit_final, out_of_fold

    statements = _statements(40)
    for st in statements:
        st.scores["image"] = None
    final = fit_final(statements, out_of_fold(statements))
    model = tmp_path / "m.pkl"
    model.write_bytes(pickle.dumps(final))
    for i, score in enumerate([0.0, 0.0, 0.95]):
        (tmp_path / f"r{i}.json").write_text(json.dumps({
            "id": f"id{i}", "bank": "Bank A" if i < 2 else "Bank B", "pages": 2,
            "signals": {"financial": {"score": 0.0, "abstained": False, "checks_fired": []},
                        "structure": {"score": score, "abstained": False,
                                      "checks_fired": ["incremental_update"] if score else []}}}))
    summary = tmp_path / "s.md"
    assert _load("collect_self_tests").main([*map(str, sorted(tmp_path.glob("r*.json"))),
                                             "--fusion", str(model), "--summary",
                                             str(summary)]) == 0
    data = json.loads(summary.with_suffix(".json").read_text())
    assert data["statements"] == 3 and data["flagged"]["fused_boosting@0.01"]["assessed"] == 3
    assert data["flagged"]["structure@0.01"]["ids"] == ["id2"]
