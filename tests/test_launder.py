"""Tests for laundering (reprint and raster)."""

from __future__ import annotations

import pytest

pytest.importorskip("weasyprint")
pymupdf = pytest.importorskip("pymupdf")

from forgelens.forgery import forge, ghostscript, launder, write_masks
from forgelens.generator import build_statement, get_bank, locate_fields, render_pdf
from forgelens.signals.financial import check_statement
from forgelens.signals.pdf_structure import analyze_pdf

BANK = get_bank("himalaya_national")
needs_gs = pytest.mark.skipif(ghostscript() is None, reason="Ghostscript not installed")


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("launder")
    st = build_statement(seed=500, bank=BANK, months=2)
    pdf = render_pdf(st, BANK, tmp / f"{st.statement_id}.pdf")
    record = st.ground_truth()
    record["layout"] = locate_fields(pdf, st, BANK)
    forged_pdf = tmp / "forged.pdf"
    forged = forge(pdf, record, forged_pdf, operation="credit_amount", seed=1,
                   save_mode="incremental", font_strategy="fallback")
    return pdf, record, forged_pdf, forged


@needs_gs
def test_reprint_removes_file_level_traces(files, tmp_path):
    _, _, forged_pdf, forged = files
    out = tmp_path / "reprint.pdf"
    label = launder(forged_pdf, forged, out, method="reprint", seed=3)
    assert label["label"] == "forged" and label["laundering"]["method"] == "reprint"
    assert label["edits"] == forged["edits"]
    checks = {f.check for f in analyze_pdf(out).findings}
    assert "incremental_update" not in checks
    assert "modified_after_creation" not in checks
    assert "non_embedded_font" not in checks
    assert "extra_content_streams" not in checks
    assert "font_anomaly" in checks  # the Helvetica text is still a different font family
    assert out.read_bytes().count(b"startxref") == 1


@needs_gs
def test_reprinted_genuine_statement_stays_clean(files, tmp_path):
    pdf, record, _, _ = files
    out = tmp_path / "genuine_reprint.pdf"
    label = launder(pdf, record, out, method="reprint", seed=4)
    assert label["label"] == "genuine"
    assert not analyze_pdf(out).suspicious
    assert check_statement(out).consistent


@needs_gs
def test_reprint_keeps_text_readable(files, tmp_path):
    _, _, forged_pdf, forged = files
    out = tmp_path / "reprint2.pdf"
    launder(forged_pdf, forged, out, method="reprint", seed=5)
    report = check_statement(out)
    assert report.parsed_rows == len(forged["transactions"])
    assert any(f.check == "running_balance" for f in report.findings)


def test_raster_removes_the_text_layer(files, tmp_path):
    _, _, forged_pdf, forged = files
    out = tmp_path / "raster.pdf"
    label = launder(forged_pdf, forged, out, method="raster", seed=6, dpi=72)
    assert label["laundering"]["dpi"] == 72
    with pymupdf.open(out) as doc, pymupdf.open(forged_pdf) as src:
        assert doc.page_count == src.page_count
        assert doc[0].rect == src[0].rect
        assert doc[0].get_text().strip() == ""
    struct = analyze_pdf(out)
    assert struct.text_layer is False and not struct.suspicious
    fin = check_statement(out)
    assert fin.parsed_rows == 0 and not fin.findings


def test_masks_still_fit_laundered_pages(files, tmp_path):
    _, _, forged_pdf, forged = files
    out = tmp_path / "raster_masked.pdf"
    label = launder(forged_pdf, forged, out, method="raster", seed=7, dpi=72)
    with pymupdf.open(out) as doc:
        size = (doc[0].rect.width, doc[0].rect.height)
        page_pix = doc[0].get_pixmap(dpi=100)
    paths = write_masks(label, size, tmp_path / "raster_masked", dpi=100)
    assert paths
    mask = pymupdf.Pixmap(str(paths[0]))
    assert (mask.width, mask.height) == (page_pix.width, page_pix.height)


def test_unknown_method_is_rejected(files, tmp_path):
    pdf, record, _, _ = files
    with pytest.raises(ValueError):
        launder(pdf, record, tmp_path / "x.pdf", method="photocopy")
