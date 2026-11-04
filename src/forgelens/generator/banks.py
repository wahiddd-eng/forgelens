"""Invented bank profiles.

Every bank here is fictional. Names, codes and colours are made up so that the public
ForgeLens benchmark contains no real bank branding. Profiles differ in the ways real
statements differ: template, column order and labels, date and number formats, fonts,
page orientation, where the summary sits, and how transactions are described.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Column keys a template can show, in any order.
COLUMN_KEYS = ("sno", "date", "value_date", "narration", "ref", "debit", "credit", "balance")

DEFAULT_LABELS = {
    "sno": "S.No.",
    "date": "Txn Date",
    "value_date": "Value Date",
    "narration": "Narration",
    "ref": "Chq./Ref. No.",
    "debit": "Withdrawal (Dr)",
    "credit": "Deposit (Cr)",
    "balance": "Balance",
}

SANS = "Arial, 'Liberation Sans', 'Nimbus Sans', sans-serif"
SERIF = "'Times New Roman', 'Liberation Serif', 'Nimbus Roman', serif"
CALIBRI = "Calibri, Carlito, 'Liberation Sans', sans-serif"
DEJAVU = "'DejaVu Sans', Verdana, Arial, sans-serif"
DEJAVU_CONDENSED = "'DejaVu Sans Condensed', 'Arial Narrow', 'Liberation Sans Narrow', sans-serif"
DEJAVU_SERIF = "'DejaVu Serif', Georgia, 'Liberation Serif', serif"


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
    columns: tuple[str, ...] = ("date", "narration", "ref", "value_date", "debit", "credit",
                                "balance")
    labels: dict = field(default_factory=dict)  # overrides of DEFAULT_LABELS
    grouping: str = "indian"  # indian | western | none
    balance_suffix: str = ""  # printed after balances, e.g. " Cr"
    orientation: str = "portrait"  # portrait | landscape
    summary_position: str = "top"  # top | bottom
    zebra: bool = True
    narration_style: str = "slash"  # slash | hyphen | transfer
    base_font_size: float = 8.4
    branch_address: str = ""

    def label(self, key: str) -> str:
        return self.labels.get(key, DEFAULT_LABELS[key])

    @property
    def number_format(self) -> dict:
        return {"grouping": self.grouping, "balance_suffix": self.balance_suffix,
                "date_format": self.date_format}


_CITIES_NORTH = ("Srinagar", "Jammu", "Delhi", "Chandigarh", "Lucknow", "Dehradun")
_CITIES_SOUTH = ("Chennai", "Bengaluru", "Hyderabad", "Kochi", "Madurai", "Mysuru")
_CITIES_WEST = ("Mumbai", "Pune", "Nagpur", "Ahmedabad", "Surat", "Nashik")
_CITIES_EAST = ("Kolkata", "Bhubaneswar", "Patna", "Guwahati", "Ranchi", "Cuttack")
_CITIES_CENTRAL = ("Bhopal", "Indore", "Jabalpur", "Raipur", "Gwalior", "Ujjain")

BANK_LIST = (
    BankProfile(
        bank_id="himalaya_national", name="Himalaya National Bank", short_name="HNB",
        ifsc_prefix="HMNB", tagline="Banking at every altitude", template="classic_table.html.j2",
        primary_colour="#1f3a5f", accent_colour="#c8a24a",
        font_family="DejaVu Sans, Arial, sans-serif", date_format="%d-%m-%Y",
        upi_handle="okhnb", min_balance="1000",
        cities=("Srinagar", "Jammu", "Chennai", "Bengaluru", "Pune", "Delhi", "Mumbai",
                "Hyderabad"),
    ),
    BankProfile(
        bank_id="deccan_cooperative", name="Deccan Co-operative Bank Ltd.", short_name="DCB",
        ifsc_prefix="DCCB", tagline="A scheduled co-operative bank", template="ledger_grid.html.j2",
        primary_colour="#5b1f1f", accent_colour="#b88a3b", font_family=SERIF,
        date_format="%d/%m/%Y", upi_handle="okdcb", min_balance="500", cities=_CITIES_SOUTH,
        columns=("date", "narration", "ref", "debit", "credit", "balance"),
        labels={"date": "Date", "narration": "Particulars", "ref": "Cheque No.",
                "debit": "Debit", "credit": "Credit", "balance": "Balance"},
        balance_suffix=" Cr", summary_position="bottom", narration_style="transfer",
        base_font_size=8.8,
    ),
    BankProfile(
        bank_id="sahyadri", name="Sahyadri Bank", short_name="SHB", ifsc_prefix="SHYB",
        tagline="Rooted in the Western Ghats", template="modern_band.html.j2",
        primary_colour="#0f6b5c", accent_colour="#f2a541", font_family=CALIBRI,
        date_format="%d-%b-%Y", upi_handle="oksahyadri", min_balance="2000",
        cities=_CITIES_WEST,
        columns=("date", "value_date", "narration", "ref", "debit", "credit", "balance"),
        labels={"date": "Date", "narration": "Description", "ref": "Reference",
                "debit": "Withdrawals", "credit": "Deposits", "balance": "Balance"},
        narration_style="hyphen", base_font_size=8.8,
    ),
    BankProfile(
        bank_id="konark_urban", name="Konark Urban Bank", short_name="KUB", ifsc_prefix="KNRK",
        tagline="Your city, your bank", template="classic_table.html.j2",
        primary_colour="#7a3e00", accent_colour="#e07a1f", font_family=SANS,
        date_format="%d/%m/%y", upi_handle="okkonark", min_balance="1000",
        cities=_CITIES_EAST, orientation="landscape",
        labels={"date": "Tran Date", "debit": "Dr Amount", "credit": "Cr Amount",
                "balance": "Balance (INR)", "narration": "Transaction Details"},
        zebra=False, narration_style="slash", base_font_size=8.6,
    ),
    BankProfile(
        bank_id="narmada_gramin", name="Narmada Gramin Bank", short_name="NGB",
        ifsc_prefix="NRGB", tagline="Sponsored rural bank", template="ledger_grid.html.j2",
        primary_colour="#2e4a1f", accent_colour="#8fb339", font_family=DEJAVU_CONDENSED,
        date_format="%d.%m.%Y", upi_handle="okngb", min_balance="250", cities=_CITIES_CENTRAL,
        columns=("sno", "date", "narration", "debit", "credit", "balance"),
        labels={"date": "Date", "narration": "Description", "debit": "Withdrawal",
                "credit": "Deposit", "balance": "Balance"},
        grouping="none", summary_position="bottom", narration_style="transfer",
    ),
    BankProfile(
        bank_id="bayview_international", name="Bayview International Bank (India)",
        short_name="BIB", ifsc_prefix="BYVW", tagline="Global banking, local care",
        template="modern_band.html.j2", primary_colour="#14213d", accent_colour="#fca311",
        font_family=SANS, date_format="%d %b %Y", upi_handle="okbayview", min_balance="10000",
        cities=("Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata", "Hyderabad"),
        columns=("date", "narration", "ref", "debit", "credit", "balance"),
        labels={"date": "Date", "narration": "Transaction Description", "ref": "Ref. No.",
                "debit": "Debit", "credit": "Credit", "balance": "Balance"},
        grouping="western", narration_style="slash", base_font_size=8.4,
    ),
    BankProfile(
        bank_id="vindhya_state", name="Vindhya State Bank", short_name="VSB",
        ifsc_prefix="VNSB", tagline="Serving the heartland since 1952",
        template="classic_table.html.j2", primary_colour="#283593", accent_colour="#9fa8da",
        font_family=DEJAVU, date_format="%d-%m-%Y", upi_handle="okvsb", min_balance="500",
        cities=_CITIES_CENTRAL,
        columns=("sno", "date", "narration", "ref", "debit", "credit", "balance"),
        labels={"date": "Date", "narration": "Description", "ref": "Cheque/Ref",
                "debit": "Withdrawal Amt.", "credit": "Deposit Amt.",
                "balance": "Closing Balance"},
        balance_suffix=" Cr", narration_style="transfer", base_font_size=8.0,
    ),
    BankProfile(
        bank_id="ganga_mercantile", name="Ganga Mercantile Bank", short_name="GMB",
        ifsc_prefix="GNGM", tagline="Trusted since generations", template="ledger_grid.html.j2",
        primary_colour="#004d61", accent_colour="#d4a017", font_family=DEJAVU_SERIF,
        date_format="%d-%m-%Y", upi_handle="okgmb", min_balance="1000", cities=_CITIES_NORTH,
        columns=("date", "value_date", "narration", "ref", "debit", "credit", "balance"),
        labels={"date": "Txn Date", "narration": "Particulars", "ref": "Chq No.",
                "debit": "Withdrawals (Dr)", "credit": "Deposits (Cr)", "balance": "Balance"},
        summary_position="bottom", narration_style="hyphen", base_font_size=7.8,
    ),
    BankProfile(
        bank_id="tapti_valley", name="Tapti Valley Bank", short_name="TVB", ifsc_prefix="TPTV",
        tagline="Growing together", template="modern_band.html.j2", primary_colour="#6a1b9a",
        accent_colour="#ffb300", font_family=DEJAVU, date_format="%d/%m/%Y",
        upi_handle="oktvb", min_balance="1000", cities=_CITIES_WEST, orientation="landscape",
        labels={"date": "Date", "narration": "Narration", "ref": "Ref No.",
                "debit": "Debit (₹)", "credit": "Credit (₹)", "balance": "Balance (₹)"},
        narration_style="hyphen", base_font_size=8.2,
    ),
    BankProfile(
        bank_id="malabar_coastal", name="Malabar Coastal Bank", short_name="MCB",
        ifsc_prefix="MLBC", tagline="By the sea, for the people", template="classic_table.html.j2",
        primary_colour="#00695c", accent_colour="#4db6ac", font_family=SERIF,
        date_format="%d-%b-%y", upi_handle="okmcb", min_balance="500", cities=_CITIES_SOUTH,
        columns=("date", "narration", "debit", "credit", "balance"),
        labels={"date": "Date", "narration": "Remarks", "debit": "Withdrawal",
                "credit": "Deposit", "balance": "Balance"},
        balance_suffix=" CR", summary_position="bottom", zebra=False,
        narration_style="slash", base_font_size=8.8,
    ),
)

BANKS: dict[str, BankProfile] = {b.bank_id: b for b in BANK_LIST}
HIMALAYA_NATIONAL = BANKS["himalaya_national"]

# Fictional counterparty bank codes used in NEFT/IMPS narrations and IFSC codes.
COUNTERPARTY_IFSC_PREFIXES = ("DKNB", "SVRB", "KSMB", "VNDB", "CRLB", "GNGB", "NRMB", "TPTB")


def get_bank(bank_id: str) -> BankProfile:
    """Return the profile for ``bank_id`` or raise ``KeyError`` listing valid ids."""
    try:
        return BANKS[bank_id]
    except KeyError:
        raise KeyError(f"Unknown bank '{bank_id}'. Available: {', '.join(sorted(BANKS))}") from None
