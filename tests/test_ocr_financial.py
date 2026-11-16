"""OCR arithmetic signal: number clean-up, and telling OCR misreads from edits (no OCR run)."""

from __future__ import annotations

from decimal import Decimal as D

from forgelens.reader.cells import Cell
from forgelens.reader.statement import ParsedStatement, Row
from forgelens.signals.ocr_financial import OcrFinancialReport, check_rows, clean_text


def test_clean_text_fixes_numbers_only():
    assert clean_text("1,23,4O5.00") == "1,23,405.00"
    assert clean_text("5O.0O") == "50.00"
    assert clean_text("12,345,67") == "12,345.67"
    assert clean_text(" 1 15,000.00") == "115,000.00"
    assert clean_text("225,571.42 Cr") == "225,571.42 Cr"
    assert clean_text("01 Dec 2025") == "01 Dec 2025"
    assert clean_text("UPI/DR/4887/Valley") == "UPI/DR/4887/Valley"


def _cell(text, x1, y, page=0):
    return Cell(page=page, text=text, bbox=(x1 - 30, y, x1, y + 9), origin=(x1 - 30, y + 7),
                size=7, font="OCR", color=0)


def _statement(rows_spec, extra_cells=()):
    """rows_spec: (debit, credit, balance, confidence of the amount) per row, 24 pt apart."""
    parsed = ParsedStatement()
    parsed.columns = {0: {"debit": 410.0, "credit": 480.0, "balance": 550.0}}
    parsed.header_top = {0: 100.0}
    conf, cells = {}, []
    opening = Row(index=-1, page=0, date="", debit=None, credit=None, balance=D("1000.00"),
                  is_opening=True)
    opening.cells = {"balance": _cell("1,000.00", 550, 110)}
    parsed.opening_row = opening
    for i, (dr, cr, bal, c) in enumerate(rows_spec):
        y = 130 + 24 * i
        def num(x):
            return x and D(x.replace(",", ""))

        row = Row(index=i, page=0, date="01-01-2026", debit=num(dr), credit=num(cr),
                  balance=num(bal))
        row.cells = {"date": _cell("01-01-2026", 80, y), "balance": _cell(bal, 550, y)}
        key, val = ("debit", dr) if dr else ("credit", cr)
        row.cells[key] = _cell(val, 410 if key == "debit" else 480, y)
        conf[id(row.cells[key])] = c
        parsed.rows.append(row)
        cells += list(row.cells.values())
    cells += list(extra_cells)
    return parsed, conf, cells


def test_a_clean_statement_passes():
    parsed, conf, cells = _statement([("100.00", None, "900.00", 0.99),
                                      (None, "50.00", "950.00", 0.99),
                                      ("450.00", None, "500.00", 0.99)])
    rep = check_rows(parsed, conf, cells)
    assert (rep.breaks, rep.unexplained, rep.score) == (0, 0, 0.0)


def test_an_edited_credit_is_caught():
    parsed, conf, cells = _statement([("100.00", None, "900.00", 0.99),
                                      (None, "5,050.00", "950.00", 0.99),  # was 50.00
                                      ("450.00", None, "500.00", 0.99)])
    rep = check_rows(parsed, conf, cells)
    assert rep.unexplained == 1 and rep.score > 0.5


def test_a_lost_leading_digit_read_without_confidence_is_explained():
    rows = [("100.00", None, "900.00", 0.99), ("500.00", None, "-5600.00", 0.6),  # 6,500 read 500
            ("10.00", None, "-5610.00", 0.99)]
    rep = check_rows(*_statement(rows))
    assert rep.breaks == 1 and rep.unexplained == 0
    rows[1] = ("500.00", None, "-5600.00", 0.99)  # read confidently: still a misread
    assert check_rows(*_statement(rows)).unexplained == 0


def test_a_skipped_row_is_explained():
    # a row between rows 1 and 2 was not parsed (its date misread), but its debit was read
    skipped = _cell("340.00", 410, 142)
    rows = [("100.00", None, "900.00", 0.99), ("50.00", None, "510.00", 0.99),
            ("10.00", None, "500.00", 0.99)]
    parsed, conf, cells = _statement(rows, [skipped])
    rep = check_rows(parsed, conf, cells)
    assert rep.breaks == 1 and rep.unexplained == 0
    assert check_rows(parsed, conf, [c for c in cells if c is not skipped]).unexplained == 1


def test_a_misread_balance_breaks_twice_and_is_explained():
    rows = [("100.00", None, "900.00", 0.99), ("50.00", None, "880.00", 0.99),  # 850 read 880
            ("10.00", None, "840.00", 0.99)]
    rep = check_rows(*_statement(rows))
    assert rep.breaks == 2 and rep.unexplained == 0


def test_too_few_rows_abstains():
    rep = check_rows(*_statement([("100.00", None, "900.00", 0.99)]))
    assert rep.abstained and rep.score == 0.5 and OcrFinancialReport().abstained


def test_misreads_seen_on_genuine_test_statements_are_explained():
    # debit 69.00 read as 59.00 (one digit), with the balances right
    rows = [("100.00", None, "900.00", 0.99), ("59.00", None, "831.00", 0.95),
            ("31.00", None, "800.00", 0.99)]
    assert check_rows(*_statement(rows)).unexplained == 0
    # credit 1,699.00 read as 699.00 (leading digits lost), confidently
    rows = [("100.00", None, "900.00", 0.99), (None, "699.00", "2599.00", 0.99),
            ("99.00", None, "2500.00", 0.99)]
    assert check_rows(*_statement(rows)).unexplained == 0


def test_a_missing_amount_is_explained():
    parsed, conf, cells = _statement([("100.00", None, "900.00", 0.99),
                                      ("40.00", None, "860.00", 0.99),
                                      ("60.00", None, "800.00", 0.99)])
    del parsed.rows[1].cells["debit"]
    parsed.rows[1].debit = None
    assert check_rows(parsed, conf, cells).unexplained == 0


def test_a_truncated_balance_is_explained_and_the_chain_continues():
    rows = [("100.00", None, "1,900.00", 0.99), ("100.00", None, "800.00", 0.99),  # 1,800
            ("300.00", None, "1,500.00", 0.99)]
    parsed, conf, cells = _statement(rows)
    parsed.opening_row.balance = D("2000.00")
    rep = check_rows(parsed, conf, cells)
    assert rep.breaks == 1 and rep.unexplained == 0


def test_inflated_credits_and_balances_are_still_caught():
    # a credit of 20,000 changed to 60,000 (one digit, read higher): kept
    rows = [("100.00", None, "900.00", 0.99), (None, "60,000.00", "20,900.00", 0.99),
            ("900.00", None, "20,000.00", 0.99)]
    assert check_rows(*_statement(rows)).unexplained == 1
    # a closing balance raised without the amounts following
    rows = [("100.00", None, "900.00", 0.99), ("100.00", None, "800.00", 0.99),
            ("300.00", None, "8,500.00", 0.99)]
    assert check_rows(*_statement(rows)).unexplained == 1


def test_a_truncated_balance_followed_by_a_one_digit_misread_is_explained():
    # 1,800 read as 800, and the next debit 200 read as 100 (one digit)
    rows = [("100.00", None, "1,900.00", 0.99), ("100.00", None, "800.00", 0.99),
            ("100.00", None, "1,600.00", 0.99)]
    parsed, conf, cells = _statement(rows)
    parsed.opening_row.balance = D("2000.00")
    assert check_rows(parsed, conf, cells).unexplained == 0
