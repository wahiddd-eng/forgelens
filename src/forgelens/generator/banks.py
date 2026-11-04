"""Invented bank profiles.

Every bank here is fictional. Names, codes and colours are made up so that the public
ForgeLens benchmark contains no real bank branding. Each profile pairs a bank with one
HTML layout template; more profiles and layouts are added as the dataset grows.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BankProfile:
    """Static description of a fictional bank and how its statements look."""

    bank_id: str
    name: str
    short_name: str
    ifsc_prefix: str  # four letters, as in real IFSC codes
    tagline: str
    template: str  # template file name inside generator/templates
    primary_colour: str
    accent_colour: str
    font_family: str
    date_format: str  # strftime format used in the transaction table
    upi_handle: str  # VPA suffix used for this bank's customers
    min_balance: str  # minimum balance the generator keeps, in rupees
    cities: tuple[str, ...] = field(default_factory=tuple)


HIMALAYA_NATIONAL = BankProfile(
    bank_id="himalaya_national",
    name="Himalaya National Bank",
    short_name="HNB",
    ifsc_prefix="HMNB",
    tagline="Banking at every altitude",
    template="classic_table.html.j2",
    primary_colour="#1f3a5f",
    accent_colour="#c8a24a",
    font_family="DejaVu Sans, Arial, sans-serif",
    date_format="%d-%m-%Y",
    upi_handle="okhnb",
    min_balance="1000",
    cities=("Srinagar", "Jammu", "Chennai", "Bengaluru", "Pune", "Delhi", "Mumbai", "Hyderabad"),
)

BANKS: dict[str, BankProfile] = {HIMALAYA_NATIONAL.bank_id: HIMALAYA_NATIONAL}

# Fictional counterparty bank codes used in NEFT/IMPS narrations and IFSC codes.
COUNTERPARTY_IFSC_PREFIXES = ("DKNB", "SVRB", "KSMB", "VNDB", "CRLB", "GNGB", "NRMB", "TPTB")


def get_bank(bank_id: str) -> BankProfile:
    """Return the profile for ``bank_id`` or raise ``KeyError`` listing valid ids."""
    try:
        return BANKS[bank_id]
    except KeyError:
        raise KeyError(f"Unknown bank '{bank_id}'. Available: {', '.join(sorted(BANKS))}") from None
