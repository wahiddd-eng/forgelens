"""Tests for the financial-consistency signal."""

from __future__ import annotations

from decimal import Decimal

import pytest

pytest.importorskip("weasyprint")
pytest.importorskip("pymupdf")

from forgelens.forgery import forge
from forgelens.generator import build_statement, get_bank, locate_fields, render_pdf
from forgelens.signals.financial import (
    ParsedStatement,
    Row,
    check_parsed,
    check_statement,
    parse_statement,
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
    return _genuine(tmp_path_factory.mktemp("fin"), seed=300)


@pytest.mark.parametrize("seed", [10, 11, 12, 13, 14, 15])
def test_parser_reads_every_row_exactly(tmp_path, seed):
    st, pdf, _ = _genuine(tmp_path, seed)
    parsed = parse_statement(pdf)
    assert len(parsed.rows) == len(st.transactions)
    for row, t in zip(parsed.rows, st.transactions):
        assert row.balance == t.balance
        assert (row.debit or Decimal(0)) == t.debit
        assert (row.credit or Decimal(0)) == t.credit
        assert row.date == t.txn_date.strftime(BANK.date_format)
    assert parsed.opening_row.balance == st.opening_balance
    assert parsed.summary == {
        "opening": st.opening_balance,
        "total_debits": st.total_debits,
        "total_credits": st.total_credits,
        "closing": st.closing_balance,
    }
    assert parsed.summary_counts == {"total_debits": st.debit_count,
                                     "total_credits": st.credit_count}


@pytest.mark.parametrize("seed", [20, 21, 22, 23])
def test_genuine_statements_pass(tmp_path, seed):
    _, pdf, _ = _genuine(tmp_path, seed)
    report = check_statement(pdf)
    assert report.consistent, [f.message for f in report.findings]
    assert report.score == 0.0
    assert {"running_balance", "closing_balance", "opening_balance"} <= set(report.checks_run)


def test_naive_credit_edit_is_caught_at_the_edited_row(genuine, tmp_path):
    _, pdf, record = genuine
    out = tmp_path / "naive.pdf"
    label = forge(pdf, record, out, operation="credit_amount", seed=4)
    report = check_statement(out)
    assert not report.consistent
    edited_row = label["edits"][0]["row"]
    breaks = [f for f in report.findings if f.check == "running_balance"]
    assert [f.row for f in breaks] == [edited_row]
    assert any(f.check == "totals" for f in report.findings)
    assert report.score > 0.5


def test_closing_balance_edit_is_caught(genuine, tmp_path):
    _, pdf, record = genuine
    out = tmp_path / "closing.pdf"
    forge(pdf, record, out, operation="closing_balance", seed=4)
    report = check_statement(out)
    checks = {f.check for f in report.findings}
    assert {"running_balance", "closing_balance"} <= checks


@pytest.mark.parametrize(("operation", "consistent"), [("credit_amount", True),
                                                        ("holder_name", False)])
def test_arithmetic_preserving_forgeries_pass(genuine, tmp_path, operation, consistent):
    _, pdf, record = genuine
    out = tmp_path / f"{operation}.pdf"
    forge(pdf, record, out, operation=operation, consistent=consistent, seed=4)
    report = check_statement(out)
    assert report.consistent, [f.message for f in report.findings]


def test_findings_explain_the_numbers(genuine, tmp_path):
    _, pdf, record = genuine
    out = tmp_path / "explain.pdf"
    forge(pdf, record, out, operation="credit_amount", seed=8)
    finding = next(f for f in check_statement(out).findings if f.check == "running_balance")
    assert "₹" in finding.message and "previous balance" in finding.message
    assert finding.expected != finding.found


def test_report_dict_and_features(genuine):
    _, pdf, _ = genuine
    data = check_statement(pdf).to_dict()
    assert data["signal"] == "financial_consistency"
    assert data["consistent"] is True
    assert set(data["features"]) >= {"fin_row_breaks", "fin_closing_mismatches", "fin_score"}


def test_unreadable_table_gives_neutral_score():
    report = check_parsed(ParsedStatement())
    assert not report.consistent
    assert report.score == 0.5
    assert report.features()["fin_parse_failed"] == 1.0


def test_row_with_both_debit_and_credit_is_flagged():
    parsed = ParsedStatement(
        rows=[Row(0, 0, "01-01-2026", Decimal("10.00"), Decimal("5.00"), Decimal("95.00"))],
        opening_row=Row(-1, 0, "", None, None, Decimal("100.00"), True),
    )
    report = check_parsed(parsed)
    assert any(f.check == "row_format" for f in report.findings)
