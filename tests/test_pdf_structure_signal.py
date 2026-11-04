"""Tests for the PDF-structure signal."""

from __future__ import annotations

import pytest

pytest.importorskip("weasyprint")
pymupdf = pytest.importorskip("pymupdf")

from forgelens.forgery import forge
from forgelens.generator import build_statement, get_bank, locate_fields, render_pdf
from forgelens.signals.pdf_structure import analyze_pdf
from forgelens.signals.pdf_structure.analyzer import _font_key, _pdf_date

BANK = get_bank("himalaya_national")


def _genuine(tmp_path, seed: int):
    st = build_statement(seed=seed, bank=BANK, months=3)
    pdf = render_pdf(st, BANK, tmp_path / f"{st.statement_id}.pdf")
    record = st.ground_truth()
    record["layout"] = locate_fields(pdf, st, BANK)
    return pdf, record


@pytest.fixture(scope="module")
def genuine(tmp_path_factory):
    return _genuine(tmp_path_factory.mktemp("struct"), seed=400)


def _checks(pdf) -> set[str]:
    return {f.check for f in analyze_pdf(pdf).findings}


def _overlaps(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


@pytest.mark.parametrize("seed", [30, 31, 32, 33])
def test_genuine_statements_are_clean(tmp_path, seed):
    pdf, _ = _genuine(tmp_path, seed)
    report = analyze_pdf(pdf)
    assert not report.suspicious, [f.message for f in report.findings]
    assert report.score == 0.0
    assert report.stats["startxref_count"] == 1


def test_incremental_save_is_detected(genuine, tmp_path):
    pdf, record = genuine
    out = tmp_path / "incr.pdf"
    forge(pdf, record, out, operation="holder_name", seed=1, save_mode="incremental",
          font_strategy="matched")
    assert "incremental_update" in _checks(out)


def test_fallback_font_is_detected_and_localised(genuine, tmp_path):
    pdf, record = genuine
    out = tmp_path / "fallback.pdf"
    label = forge(pdf, record, out, operation="credit_amount", seed=2, save_mode="rewrite",
                  font_strategy="fallback")
    report = analyze_pdf(out)
    checks = {f.check for f in report.findings}
    assert {"non_embedded_font", "font_anomaly", "modified_after_creation"} <= checks
    locations = report.locations()
    for edit in label["edits"]:
        assert any(loc["page"] == edit["page"] and _overlaps(loc["bbox"], edit["new_bbox"])
                   for loc in locations)


def test_matched_font_still_leaves_a_duplicate_font(genuine, tmp_path):
    pdf, record = genuine
    out = tmp_path / "matched.pdf"
    forge(pdf, record, out, operation="closing_balance", seed=3, save_mode="rewrite",
          font_strategy="matched")
    checks = _checks(out)
    assert "duplicate_font" in checks
    assert "font_anomaly" in checks
    assert "non_embedded_font" not in checks


def test_extra_content_streams_on_edited_pages(genuine, tmp_path):
    pdf, record = genuine
    out = tmp_path / "streams.pdf"
    label = forge(pdf, record, out, operation="holder_name", seed=4, save_mode="rewrite")
    report = analyze_pdf(out)
    finding = next(f for f in report.findings if f.check == "extra_content_streams")
    assert finding.page == label["edits"][0]["page"]


def test_report_dict_and_features(genuine):
    pdf, _ = genuine
    data = analyze_pdf(pdf).to_dict()
    assert data["signal"] == "pdf_structure"
    assert data["suspicious"] is False
    assert data["features"]["pdf_text_layer"] == 1.0
    assert data["features"]["pdf_startxref_count"] == 1.0


def test_image_only_pdf_is_neutral(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
    pix.clear_with(200)
    page.insert_image(page.rect, pixmap=pix)
    path = tmp_path / "scan.pdf"
    doc.save(path)
    report = analyze_pdf(path)
    assert report.text_layer is False
    assert report.score == 0.5


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("XKQQSR+DejaVu-Sans", ("dejavusans", "regular")),
        ("DejaVuSans", ("dejavusans", "regular")),
        ("DejaVu Sans Book", ("dejavusans", "regular")),
        ("UWGIWA+DejaVu-Sans-Bold", ("dejavusans", "bold")),
        ("Helvetica-Bold", ("helvetica", "bold")),
        ("ArialMT", ("arial", "regular")),
    ],
)
def test_font_key_ignores_subset_tags_and_spelling(name, key):
    assert _font_key(name) == key


def test_pdf_date_parsing():
    a = _pdf_date("D:20260403090000+05'30")
    b = _pdf_date("D:20260403090000+05'30'")
    assert a == b and a.year == 2026 and a.utcoffset().total_seconds() == 19800
    assert _pdf_date("not a date") is None
