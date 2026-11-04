"""Every bank layout must render, be read back exactly, and support every forgery."""

from __future__ import annotations

from decimal import Decimal

import pytest

from forgelens.generator import BANKS, build_statement, get_bank
from forgelens.generator.money import format_amount
from forgelens.generator.render import column_widths
from forgelens.generator.transactions import _styled

BANK_IDS = sorted(BANKS)


# ---------------------------------------------------------------- pure helpers


@pytest.mark.parametrize(
    ("grouping", "suffix", "expected"),
    [
        ("indian", "", "12,34,567.50"),
        ("western", "", "1,234,567.50"),
        ("none", "", "1234567.50"),
        ("indian", " Cr", "12,34,567.50 Cr"),
    ],
)
def test_format_amount(grouping, suffix, expected):
    assert format_amount(Decimal("1234567.5"), grouping, suffix) == expected


def test_format_amount_rejects_unknown_grouping():
    with pytest.raises(ValueError):
        format_amount(Decimal(1), "roman")


@pytest.mark.parametrize("bank_id", BANK_IDS)
def test_column_widths_sum_to_100(bank_id):
    widths = column_widths(get_bank(bank_id))
    assert list(widths) == list(get_bank(bank_id).columns)
    assert abs(sum(widths.values()) - 100) < 0.1


def test_narration_styles():
    upi = "UPI/DR/123/SHOP/shop@okhnb/Order"
    assert _styled(upi, "upi_out", False, "slash") == upi
    assert _styled(upi, "upi_out", False, "hyphen") == "UPI-DR-123-SHOP-shop@okhnb-Order"
    assert _styled(upi, "upi_out", False, "transfer").startswith("TO TRANSFER-UPI/DR/")
    assert _styled("ATM WDL/S1AN1234/PUNE", "atm", False, "hyphen") == "ATW-S1AN1234-PUNE"


def test_banks_are_fictional_and_distinct():
    assert len(BANKS) >= 10
    assert len({b.ifsc_prefix for b in BANKS.values()}) == len(BANKS)
    assert len({(b.template, b.columns, b.date_format, b.font_family) for b in BANKS.values()}) \
        == len(BANKS)


@pytest.mark.parametrize("bank_id", BANK_IDS)
def test_statement_records_its_number_format(bank_id):
    bank = get_bank(bank_id)
    record = build_statement(seed=1, bank=bank).ground_truth()
    assert record["format"] == bank.number_format
    assert record["template"] == bank.template.removesuffix(".html.j2")


# ---------------------------------------------------------------- rendering round trip

weasyprint = pytest.importorskip("weasyprint")
pymupdf = pytest.importorskip("pymupdf")

from forgelens.forgery import forge
from forgelens.generator import locate_fields, render_pdf
from forgelens.signals.financial import check_statement, parse_statement
from forgelens.signals.pdf_structure import analyze_pdf


@pytest.fixture(scope="module", params=BANK_IDS)
def rendered(request, tmp_path_factory):
    bank = get_bank(request.param)
    st = build_statement(seed=21, bank=bank, months=2)
    pdf = render_pdf(st, bank, tmp_path_factory.mktemp(bank.bank_id) / "statement.pdf")
    record = st.ground_truth()
    record["layout"] = locate_fields(pdf, st, bank)
    return bank, st, pdf, record


def test_reader_recovers_every_value(rendered):
    bank, st, pdf, _ = rendered
    parsed = parse_statement(pdf)
    assert [r.balance for r in parsed.rows] == [t.balance for t in st.transactions]
    assert [(r.debit or Decimal(0)) for r in parsed.rows] == [t.debit for t in st.transactions]
    assert [(r.credit or Decimal(0)) for r in parsed.rows] == [t.credit for t in st.transactions]
    assert [r.date for r in parsed.rows] == [t.txn_date.strftime(bank.date_format)
                                             for t in st.transactions]
    assert parsed.opening_row.balance == st.opening_balance
    assert parsed.summary["closing"] == st.closing_balance
    assert parsed.summary_counts["total_debits"] == st.debit_count


def test_genuine_statement_passes_both_signals(rendered):
    _, _, pdf, _ = rendered
    fin = check_statement(pdf)
    assert fin.consistent, [f.message for f in fin.findings]
    struct = analyze_pdf(pdf)
    assert not struct.suspicious, [f.message for f in struct.findings]


def test_layout_text_uses_the_bank_format(rendered):
    bank, st, _, record = rendered
    last = record["layout"]["rows"][-1]
    assert last["balance"]["text"] == format_amount(st.transactions[-1].balance, bank.grouping,
                                                    bank.balance_suffix)


@pytest.mark.parametrize(("operation", "consistent"), [
    ("credit_amount", False), ("credit_amount", True), ("closing_balance", False),
    ("holder_name", False),
])
def test_every_forgery_works_on_every_layout(rendered, tmp_path, operation, consistent):
    bank, _, pdf, record = rendered
    out = tmp_path / "forged.pdf"
    label = forge(pdf, record, out, operation=operation, consistent=consistent, seed=5,
                  save_mode="rewrite", font_strategy="matched")
    for edit in label["edits"]:
        with pymupdf.open(out) as doc:
            shown = doc[edit["page"]].get_text("text", clip=pymupdf.Rect(edit["new_bbox"])).strip()
        assert shown == edit["new"]
        if edit["field"] in ("balance", "summary_closing") and bank.balance_suffix:
            assert edit["new"].endswith(bank.balance_suffix.strip())
    fin = check_statement(out)
    arithmetic_kept = consistent or operation == "holder_name"
    assert bool(fin.findings) is not arithmetic_kept, [f.message for f in fin.findings]
    assert analyze_pdf(out).suspicious
