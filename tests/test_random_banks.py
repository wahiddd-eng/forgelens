"""Procedurally generated banks: deterministic, resolvable by id, readable by the reader."""

from __future__ import annotations

import pytest

from forgelens.generator import BANKS, get_bank
from forgelens.generator.random_banks import _REAL, is_generated, random_bank
from forgelens.reader.statement import _is_credit_label, _is_debit_label

N = 200


def test_same_index_same_bank_and_get_bank_resolves_ids():
    assert random_bank(7) == random_bank(7)
    assert get_bank("gen_0007") == random_bank(7)
    assert is_generated("gen_0007") and not is_generated("sahyadri") and not is_generated("gen_x")
    with pytest.raises(KeyError):
        get_bank("no_such_bank")


def test_generated_banks_vary_and_stay_apart_from_the_hand_made_ones():
    banks = [random_bank(i) for i in range(N)]
    assert len({b.bank_id for b in banks}) == N
    assert not {b.bank_id for b in banks} & set(BANKS)
    looks = {(b.template, b.columns, b.font_family, b.style["th"], b.style["rules"],
              b.style["header"]) for b in banks}
    assert len(looks) > 0.9 * N
    for key, minimum in (("template", 3), ("font_family", 6), ("date_format", 8)):
        assert len({getattr(b, key) for b in banks}) >= minimum
    assert {b.orientation for b in banks} == {"portrait", "landscape"}


def test_names_avoid_real_bank_words():
    for i in range(N):
        assert not any(word in random_bank(i).name.lower() for word in _REAL)


@pytest.mark.parametrize("i", range(N))
def test_columns_and_labels_are_ones_the_reader_understands(i):
    b = random_bank(i)
    assert b.columns[-1] == "balance"
    assert {"date", "narration", "debit", "credit", "balance"} <= set(b.columns)
    assert _is_debit_label(b.label("debit")) and not _is_credit_label(b.label("debit"))
    assert _is_credit_label(b.label("credit")) and not _is_debit_label(b.label("credit"))
    assert "balance" in b.label("balance").lower()


def test_generated_statements_render_and_read_back(tmp_path):
    pytest.importorskip("weasyprint")
    from forgelens.generator import build_statement, locate_fields, render_pdf

    for i in range(0, 40, 4):  # a spread of templates and styles
        bank = random_bank(i)
        statement = build_statement(seed=3000, bank=bank, months=1)
        pdf = render_pdf(statement, bank, tmp_path / f"{bank.bank_id}.pdf", check_fonts=False)
        layout = locate_fields(pdf, statement, bank)  # raises if anything does not read back
        assert len(layout["rows"]) == len(statement.transactions)
