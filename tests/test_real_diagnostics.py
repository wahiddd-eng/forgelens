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
