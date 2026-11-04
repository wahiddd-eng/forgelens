"""Money helpers: exact decimal arithmetic and Indian-style number formatting."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")


def to_money(value: float | str | Decimal) -> Decimal:
    """Convert a number to a Decimal rounded to two decimal places (paise)."""
    return Decimal(str(value)).quantize(PAISE, rounding=ROUND_HALF_UP)


def format_inr(amount: Decimal) -> str:
    """Format an amount with Indian digit grouping, e.g. 1234567.5 -> '12,34,567.50'.

    The last three digits form one group and the remaining digits are grouped in twos.
    Negative amounts keep a leading minus sign.
    """
    amount = to_money(amount)
    sign = "-" if amount < 0 else ""
    whole, frac = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}{whole}.{frac}"


GROUPINGS = ("indian", "western", "none")


def format_amount(amount: Decimal, grouping: str = "indian", suffix: str = "") -> str:
    """Format an amount the way a bank prints it.

    ``grouping``: ``indian`` (12,34,567.50), ``western`` (1,234,567.50) or ``none``
    (1234567.50). ``suffix`` is appended as printed, e.g. ``" Cr"``.
    """
    amount = to_money(amount)
    if grouping == "indian":
        text = format_inr(amount)
    elif grouping == "western":
        text = f"{amount:,.2f}"
    elif grouping == "none":
        text = f"{amount:.2f}"
    else:
        raise ValueError(f"Unknown grouping '{grouping}'. Choose from {', '.join(GROUPINGS)}")
    return text + suffix
