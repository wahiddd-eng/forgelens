"""Evaluation metrics, stable seeds and reproducible output."""

from __future__ import annotations

import pytest

from forgelens.evaluation import binary_metrics, localisation, localisation_summary, wilson
from forgelens.generator import BANKS, build_statement
from forgelens.generator.transactions import LATEST_PERIOD_END
from forgelens.utils import run_info, stable_seed


def test_wilson_interval_known_values():
    assert wilson(0, 0) is None
    low, high = wilson(0, 300)
    assert low == 0.0 and 0.012 < high < 0.013  # zero false positives still allow ~1.3%
    low, high = wilson(228, 300)
    assert low < 228 / 300 < high and high - low < 0.1


def test_binary_metrics_counts_and_intervals():
    labels = [True] * 4 + [False] * 4
    flags = [True, True, True, False, False, False, False, True]
    m = binary_metrics(labels, flags)
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (3, 1, 1, 3)
    assert m["recall"] == 0.75 and m["false_positive_rate"] == 0.25
    assert m["recall_ci95"][0] < 0.75 < m["recall_ci95"][1]


def test_localisation_needs_precision_as_well_as_recall():
    edits = [{"page": 0, "mask_bbox": [100, 100, 150, 110]}]
    precise = [{"page": 0, "bbox": [101, 101, 149, 109]}]
    everything = precise + [{"page": 0, "bbox": [10 * i, 300, 10 * i + 5, 310]} for i in range(9)]
    assert localisation_summary(localisation(edits, precise))["precision"] == 1.0
    noisy = localisation_summary(localisation(edits, everything))
    assert noisy["recall"] == 1.0 and noisy["precision"] == 0.1
    assert localisation(edits, [{"page": 1, "bbox": [100, 100, 150, 110]}])["edits_found"] == 0


def test_stable_seed_depends_only_on_its_parts():
    assert stable_seed(0, "sahyadri_000001", 0) == stable_seed(0, "sahyadri_000001", 0)
    assert stable_seed(0, "sahyadri_000001", 0) != stable_seed(0, "sahyadri_000001", 1)
    assert 0 <= stable_seed("x") < 2**31


def test_run_info_records_code_and_environment():
    info = run_info({"tag": "v4"})
    assert info["packages"]["forgelens"] and info["python"]
    assert info["args"] == {"tag": "v4"}


@pytest.mark.parametrize("bank_id", sorted(BANKS))
def test_no_statement_dates_after_the_dataset_window(bank_id):
    for seed in range(25):
        st = build_statement(seed=seed, bank=BANKS[bank_id])
        assert st.period_end <= LATEST_PERIOD_END


def test_same_statement_renders_to_identical_bytes(tmp_path):
    pytest.importorskip("weasyprint")
    pymupdf = pytest.importorskip("pymupdf")
    from forgelens.generator import get_bank, render_pdf

    bank = get_bank("ganga_mercantile")
    st = build_statement(seed=2, bank=bank, months=1)
    a = render_pdf(st, bank, tmp_path / "a.pdf").read_bytes()
    b = render_pdf(st, bank, tmp_path / "b.pdf").read_bytes()
    assert a == b
    with pymupdf.open(tmp_path / "a.pdf") as doc:
        assert doc.metadata["creationDate"].startswith(f"D:{st.generated_on:%Y%m%d}")
