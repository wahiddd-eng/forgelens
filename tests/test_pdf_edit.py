"""Tests for field location in rendered PDFs and PDF-edit forgeries."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

pytest.importorskip("weasyprint")
pymupdf = pytest.importorskip("pymupdf")

from forgelens.forgery import forge, write_masks
from forgelens.generator import (
    build_statement,
    format_inr,
    get_bank,
    locate_fields,
    render_pdf,
)

BANK = get_bank("himalaya_national")


def _genuine(tmp_path, seed: int):
    st = build_statement(seed=seed, bank=BANK, months=3)
    pdf = render_pdf(st, BANK, tmp_path / f"{st.statement_id}.pdf")
    record = st.ground_truth()
    record["layout"] = locate_fields(pdf, st, BANK)
    return st, pdf, record


@pytest.fixture(scope="module")
def genuine(tmp_path_factory):
    return _genuine(tmp_path_factory.mktemp("genuine"), seed=100)


def _text_in(pdf_path, page: int, bbox) -> str:
    with pymupdf.open(pdf_path) as doc:
        return doc[page].get_text("text", clip=pymupdf.Rect(bbox)).strip()


def _chain_holds(record: dict) -> bool:
    balance = Decimal(record["opening_balance"])
    for t in record["transactions"]:
        balance = balance - Decimal(t["debit"]) + Decimal(t["credit"])
        if balance != Decimal(t["balance"]):
            return False
    totals_ok = (Decimal(record["opening_balance"]) + Decimal(record["total_credits"])
                 - Decimal(record["total_debits"]) == Decimal(record["closing_balance"]))
    return totals_ok and Decimal(record["closing_balance"]) == balance


# ---------------------------------------------------------------- layout


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_every_row_is_located(tmp_path, seed):
    st, pdf, record = _genuine(tmp_path, seed)
    layout = record["layout"]
    assert len(layout["rows"]) == len(st.transactions)
    with pymupdf.open(pdf) as doc:
        assert layout["pages"] == doc.page_count
    for row, t in zip(layout["rows"], st.transactions):
        assert row["balance"]["text"] == format_inr(t.balance)
        expected = t.debit if t.debit > 0 else t.credit
        assert row["amount"]["text"] == format_inr(expected)
        assert row["amount_column"] == ("debit" if t.debit > 0 else "credit")


def test_summary_fields_are_located(genuine):
    st, _, record = genuine
    f = record["layout"]["fields"]
    assert f["customer_name"]["text"] == st.customer.name
    assert f["summary_closing"]["text"] == format_inr(st.closing_balance)
    assert f["summary_total_credits"]["text"] == format_inr(st.total_credits)
    assert f["summary_closing"]["page"] == 0


# ---------------------------------------------------------------- forgeries


def test_naive_credit_edit_breaks_the_balance_chain(genuine, tmp_path):
    _, pdf, record = genuine
    out = tmp_path / "naive.pdf"
    label = forge(pdf, record, out, operation="credit_amount", seed=3,
                  save_mode="incremental", font_strategy="matched")
    assert label["label"] == "forged"
    assert label["forgery"]["balance_consistent"] is False
    assert len(label["edits"]) == 1
    edit = label["edits"][0]
    assert edit["field"] == "credit"
    assert Decimal(edit["new"].replace(",", "")) > Decimal(edit["old"].replace(",", ""))
    assert _text_in(out, edit["page"], edit["new_bbox"]) == edit["new"]
    assert not _chain_holds(label)
    assert _chain_holds(record)


def test_consistent_credit_edit_keeps_arithmetic_valid(genuine, tmp_path):
    _, pdf, record = genuine
    out = tmp_path / "consistent.pdf"
    label = forge(pdf, record, out, operation="credit_amount", consistent=True, seed=3,
                  save_mode="rewrite", font_strategy="fallback")
    assert label["forgery"]["balance_consistent"] is True
    assert _chain_holds(label)
    assert label["closing_balance"] != record["closing_balance"]
    fields = {e["field"] for e in label["edits"]}
    assert {"credit", "balance", "summary_total_credits", "summary_closing"} <= fields
    closing = next(e for e in label["edits"] if e["field"] == "summary_closing")
    assert _text_in(out, closing["page"], closing["new_bbox"]) == format_inr(
        Decimal(label["closing_balance"]))


def test_closing_balance_edit(genuine, tmp_path):
    _, pdf, record = genuine
    out = tmp_path / "closing.pdf"
    label = forge(pdf, record, out, operation="closing_balance", seed=5)
    assert Decimal(label["closing_balance"]) > Decimal(record["closing_balance"])
    assert label["transactions"][-1]["balance"] == label["closing_balance"]
    assert not _chain_holds(label)
    for e in label["edits"]:
        assert _text_in(out, e["page"], e["new_bbox"]) == e["new"]


def test_holder_name_edit_leaves_figures_unchanged(genuine, tmp_path):
    _, pdf, record = genuine
    out = tmp_path / "name.pdf"
    label = forge(pdf, record, out, operation="holder_name", seed=9)
    assert label["customer"]["name"] != record["customer"]["name"]
    assert label["transactions"] == record["transactions"]
    assert _chain_holds(label)
    edit = label["edits"][0]
    assert _text_in(out, 0, edit["new_bbox"]) == label["customer"]["name"]
    with pymupdf.open(out) as doc:
        assert record["customer"]["name"] not in doc[0].get_text()


@pytest.mark.parametrize(("save_mode", "eof_markers"), [("incremental", 2), ("rewrite", 1)])
def test_save_modes_leave_expected_structure(genuine, tmp_path, save_mode, eof_markers):
    _, pdf, record = genuine
    out = tmp_path / f"{save_mode}.pdf"
    forge(pdf, record, out, operation="holder_name", seed=1, save_mode=save_mode)
    assert out.read_bytes().count(b"%%EOF") == eof_markers


def test_masks_cover_edited_regions(genuine, tmp_path):
    _, pdf, record = genuine
    out = tmp_path / "masked.pdf"
    label = forge(pdf, record, out, operation="closing_balance", seed=2)
    paths = write_masks(label, record["layout"]["page_size"], tmp_path / "masked", dpi=100)
    assert {p.name for p in paths} == {f"masked_p{e['page']}_mask.png" for e in label["edits"]}
    with pymupdf.open(out) as doc:
        page_pix = doc[0].get_pixmap(dpi=100)
    for path in paths:
        pix = pymupdf.Pixmap(str(path))
        assert (pix.width, pix.height) == (page_pix.width, page_pix.height)
        assert 255 in set(pix.samples)


def test_same_seed_gives_same_forgery(genuine, tmp_path):
    _, pdf, record = genuine
    a = forge(pdf, record, tmp_path / "a.pdf", operation="credit_amount", seed=11)
    b = forge(pdf, record, tmp_path / "b.pdf", operation="credit_amount", seed=11)
    strip = lambda r: {k: v for k, v in r.items() if k not in ("statement_id", "pdf")}
    assert json.dumps(strip(a), sort_keys=True) == json.dumps(strip(b), sort_keys=True)


def test_rejects_bad_requests(genuine, tmp_path):
    _, pdf, record = genuine
    with pytest.raises(ValueError):
        forge(pdf, record, tmp_path / "x.pdf", operation="closing_balance", consistent=True)
    with pytest.raises(ValueError):
        forge(pdf, record, tmp_path / "x.pdf", operation="no_such_operation")
    no_layout = {k: v for k, v in record.items() if k != "layout"}
    with pytest.raises(ValueError):
        forge(pdf, no_layout, tmp_path / "x.pdf", operation="holder_name")


def test_missing_matching_font_falls_back_and_says_so(genuine, tmp_path, monkeypatch):
    """On a machine without the statement's font, a 'matched' forgery uses Helvetica and
    its label must say so; the structure signal must still see it."""
    from forgelens.forgery import pdf_edit
    from forgelens.signals.pdf_structure import analyze_pdf

    monkeypatch.setattr(pdf_edit, "_font_index", dict)
    _, pdf, record = genuine
    out = tmp_path / "no_fonts.pdf"
    label = forge(pdf, record, out, operation="holder_name", seed=2, save_mode="rewrite",
                  font_strategy="matched")
    assert label["forgery"]["font_strategy"] == "fallback"
    assert {"non_embedded_font", "font_anomaly"} & {f.check for f in analyze_pdf(out).findings}


def test_failed_forgery_leaves_no_file_behind(genuine, tmp_path, monkeypatch):
    from forgelens.forgery import pdf_edit

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(pdf_edit, "_apply", broken)
    _, pdf, record = genuine
    out = tmp_path / "forged.pdf"
    with pytest.raises(RuntimeError):
        forge(pdf, record, out, operation="holder_name", seed=2)
    assert list(tmp_path.iterdir()) == []
