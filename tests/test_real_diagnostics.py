from decimal import Decimal as D

from forgelens.evaluation.real_diagnostics import _bucket, _chain_breaks
from forgelens.reader.statement import Row


def _rows(balances, debits):
    return [Row(i, 0, "d", D(dr) if dr else None, None, D(b)) for i, (b, dr) in
            enumerate(zip(balances, debits))]


def test_chain_breaks_tell_a_reversed_table_apart():
    rows = _rows(["900", "800", "700"], ["100", "100", "100"])
    assert _chain_breaks(D("1000"), rows) == 0
    newest_first = rows[::-1]
    assert _chain_breaks(None, newest_first) > 0
    assert _chain_breaks(None, newest_first, reverse=True) == 0


def test_bucket_keeps_only_the_order_of_magnitude():
    assert _bucket(D("0.5")) == "0" and _bucket(D("-6000")) == "1e4" and _bucket(None) is None


def test_font_rules_for_genuine_bank_software():
    from forgelens.signals.pdf_structure.analyzer import _is_symbol, _same_family, family_weight

    # weights of one family are one family, each its own weight
    assert family_weight("ABCDEF+SourceSans3-SemiBold")[0] == family_weight("SourceSans3-Regular")[0]
    assert family_weight("Rubik-Medium")[1] != family_weight("Rubik-Regular")[1]
    assert family_weight("Mulish-Black") == ("mulish", "black", False)
    # FPDF style suffixes
    assert family_weight("utf8montserratB")[:2] == (family_weight("utf8montserrat")[0], "bold")
    assert _same_family(family_weight("utf8montserratsb")[0], family_weight("utf8montserrat")[0])
    assert not _same_family("arial", "helvetica")
    assert _is_symbol("ZapfDingbats") and not _is_symbol("Helvetica")
