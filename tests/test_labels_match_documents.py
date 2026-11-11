"""Every label must describe its PDF exactly: what the forged document claims, and what the
edits replaced. Checked by reading each forged PDF back, for every bank and forgery type."""

from __future__ import annotations

from decimal import Decimal

import pytest

pytest.importorskip("weasyprint")
pytest.importorskip("pymupdf")

from forgelens.forgery import forge, rebuild
from forgelens.generator import BANKS, build_statement, get_bank, locate_fields, render_pdf
from forgelens.reader import parse_statement

PDF_EDITS = [("credit_amount", False), ("credit_amount", True), ("closing_balance", False),
             ("holder_name", False)]
SUMMARY = {"opening": "opening_balance", "total_debits": "total_debits",
           "total_credits": "total_credits", "closing": "closing_balance"}


@pytest.fixture(scope="module", params=sorted(BANKS))
def genuine(request, tmp_path_factory):
    bank = get_bank(request.param)
    st = build_statement(seed=44, bank=bank, months=2)
    pdf = render_pdf(st, bank, tmp_path_factory.mktemp(bank.bank_id) / "genuine.pdf")
    record = st.ground_truth()
    record["layout"] = locate_fields(pdf, st, bank)
    return pdf, record


def _assert_label_matches_pdf(pdf, label):
    parsed = parse_statement(pdf)
    claimed = label["transactions"]
    assert len(parsed.rows) == len(claimed)
    for row, t in zip(parsed.rows, claimed):
        assert (row.debit or Decimal(0)) == Decimal(t["debit"]), row.index
        assert (row.credit or Decimal(0)) == Decimal(t["credit"]), row.index
        assert row.balance == Decimal(t["balance"]), row.index
    for key, field in SUMMARY.items():
        if key in parsed.summary:
            assert parsed.summary[key] == Decimal(label[field]), key


def _printed(record: dict, edit: dict) -> str:
    """The text the genuine statement shows for an edited field."""
    layout = record["layout"]
    if edit["row"] is not None:
        cell = "amount" if edit["field"] == "credit" else edit["field"]
        return layout["rows"][edit["row"]][cell]["text"]
    return layout["fields"][edit["field"]]["text"]


@pytest.mark.parametrize(("operation", "consistent"), PDF_EDITS)
def test_pdf_edit_label_describes_the_forged_pdf(genuine, tmp_path, operation, consistent):
    pdf, record = genuine
    out = tmp_path / "forged.pdf"
    label = forge(pdf, record, out, operation=operation, consistent=consistent, seed=9)
    _assert_label_matches_pdf(out, label)
    for edit in label["edits"]:
        assert edit["old"] == _printed(record, edit)
        assert edit["old_bbox"] and edit["new_bbox"] and edit["mask_bbox"]


def test_naive_credit_edit_does_not_claim_a_new_total(genuine, tmp_path):
    pdf, record = genuine
    label = forge(pdf, record, tmp_path / "naive.pdf", operation="credit_amount", seed=9)
    assert label["total_credits"] == record["total_credits"]  # the summary was not touched
    assert sum(Decimal(t["credit"]) for t in label["transactions"]) > Decimal(
        record["total_credits"])


@pytest.mark.parametrize("variant", ["rebuilt_exact", "rebuilt_imitation"])
def test_rebuild_label_describes_the_rebuilt_pdf(genuine, tmp_path, variant):
    _, record = genuine
    out = tmp_path / "rebuilt.pdf"
    label = rebuild(record, out, variant=variant, seed=9, change_name=True)
    _assert_label_matches_pdf(out, label)
    assert label["customer"]["name"] != record["customer"]["name"]
    for edit in label["edits"]:
        assert edit["old"] == _printed(record, edit)  # formatted as the bank prints it
        assert edit["old_bbox"] is None and edit["new_bbox"]
    if variant == "rebuilt_imitation":
        assert label["forgery"]["imitation"]["rendered_fonts"]
        assert label["forgery"]["imitation"]["font_changed"] in (True, False)
