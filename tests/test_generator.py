"""Tests for the synthetic genuine statement generator."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from forgelens.generator import build_statement, format_inr, get_bank, render_html

BANK = get_bank("himalaya_national")
SEEDS = range(25)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal(0), "0.00"),
        (Decimal("999.5"), "999.50"),
        (Decimal(1000), "1,000.00"),
        (Decimal("123456.78"), "1,23,456.78"),
        (Decimal("1234567.5"), "12,34,567.50"),
        (Decimal(123456789), "12,34,56,789.00"),
        (Decimal("-45678.9"), "-45,678.90"),
    ],
)
def test_format_inr_uses_indian_grouping(amount, expected):
    assert format_inr(amount) == expected


@pytest.mark.parametrize("seed", SEEDS)
def test_running_balance_is_exact(seed):
    st = build_statement(seed=seed, bank=BANK, months=3)
    balance = st.opening_balance
    for row in st.transactions:
        assert (row.debit > 0) != (row.credit > 0), "each row is either a debit or a credit"
        balance = balance - row.debit + row.credit
        assert row.balance == balance
    assert st.closing_balance == st.opening_balance + st.total_credits - st.total_debits


@pytest.mark.parametrize("seed", SEEDS)
def test_balance_never_below_minimum(seed):
    st = build_statement(seed=seed, bank=BANK, months=3)
    floor = Decimal(BANK.min_balance)
    assert all(row.balance >= floor for row in st.transactions)


@pytest.mark.parametrize("seed", SEEDS)
def test_dates_are_sorted_and_inside_period(seed):
    st = build_statement(seed=seed, bank=BANK, months=3)
    dates = [row.txn_date for row in st.transactions]
    assert dates == sorted(dates)
    assert all(st.period_start <= d <= st.period_end for d in dates)
    assert all(row.value_date >= row.txn_date for row in st.transactions)
    assert st.generated_on > st.period_end


def test_amounts_have_two_decimal_places():
    st = build_statement(seed=3, bank=BANK, months=6)
    for row in st.transactions:
        for value in (row.debit, row.credit, row.balance):
            assert value.as_tuple().exponent == -2


def test_same_seed_gives_same_statement():
    a = build_statement(seed=7, bank=BANK, months=3).ground_truth()
    b = build_statement(seed=7, bank=BANK, months=3).ground_truth()
    assert a == b


def test_different_seeds_give_different_statements():
    a = build_statement(seed=1, bank=BANK).ground_truth()
    b = build_statement(seed=2, bank=BANK).ground_truth()
    assert a["customer"]["account_number"] != b["customer"]["account_number"]
    assert a["transactions"] != b["transactions"]


def test_fixed_period_end_sets_the_period():
    st = build_statement(seed=5, bank=BANK, months=3, period_end=date(2026, 9, 30))
    assert st.period_start == date(2026, 7, 1)
    assert st.period_end == date(2026, 9, 30)


def test_ground_truth_matches_statement():
    st = build_statement(seed=11, bank=BANK, months=3)
    gt = st.ground_truth()
    assert gt["label"] == "genuine"
    assert len(gt["transactions"]) == len(st.transactions)
    assert gt["closing_balance"] == str(st.closing_balance)
    assert gt["debit_count"] + gt["credit_count"] == len(st.transactions)


def test_rejects_invalid_months():
    with pytest.raises(ValueError):
        build_statement(seed=0, bank=BANK, months=0)


def test_unknown_bank_lists_available_banks():
    with pytest.raises(KeyError, match="himalaya_national"):
        get_bank("no_such_bank")


def test_html_contains_summary_and_rows():
    st = build_statement(seed=4, bank=BANK, months=3)
    html = render_html(st, BANK)
    assert format_inr(st.closing_balance) in html
    assert format_inr(st.opening_balance) in html
    assert "fictional bank" in html
    assert html.count("<tr>") >= len(st.transactions)


def test_pdf_text_matches_ground_truth(tmp_path):
    pytest.importorskip("weasyprint")
    pymupdf = pytest.importorskip("pymupdf")
    from forgelens.generator import render_pdf

    st = build_statement(seed=9, bank=BANK, months=2)
    pdf = render_pdf(st, BANK, tmp_path / "statement.pdf")
    with pymupdf.open(pdf) as doc:
        text = "\n".join(page.get_text() for page in doc)
        assert doc.metadata["author"] == BANK.name
    assert format_inr(st.closing_balance) in text
    assert st.customer.account_number in text
    for row in st.transactions[:5]:
        assert format_inr(row.balance) in text
