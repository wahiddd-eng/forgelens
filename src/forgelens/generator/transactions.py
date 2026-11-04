"""Synthetic customers and Indian-style transaction histories with exact running balances.

Everything is driven by one integer seed, so the same seed always produces the same
statement. Merchants, employers, lenders and counterparty banks are invented.
"""

from __future__ import annotations

import calendar
import hashlib
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from faker import Faker

from .banks import COUNTERPARTY_IFSC_PREFIXES, BankProfile
from .models import Customer, Statement, Transaction
from .money import to_money

MERCHANTS = (
    "QuickBite Foods", "ShopKart Retail", "Metro Fresh Mart", "Zappy Rides", "CineStar Tickets",
    "PharmaPlus Chemists", "FuelPoint Petroleum", "BookNest Stores", "UrbanWear Fashion",
    "Daily Grocers", "Chai Corner Cafe", "Spark Electricals", "Valley Walnut House",
    "Saffron Sweets", "GreenLeaf Organics", "TechHive Gadgets", "HomeNest Furnishing",
)
UTILITIES = (
    ("State Power Distribution Co", "ELECTRICITY"),
    ("AirWave Mobile", "MOBILE"),
    ("FiberNet Broadband", "BROADBAND"),
    ("City Gas Ltd", "GAS"),
    ("Jal Board Water Supply", "WATER"),
)
LENDERS = ("Kestrel Finance Ltd", "Saffron Home Loans", "Indigo Auto Finance", "Pinecrest Credit")
EMPLOYER_SUFFIXES = ("Pvt Ltd", "Technologies Pvt Ltd", "Solutions LLP", "Industries Ltd")
BRANCH_AREAS = (
    "Main Branch", "Station Road", "MG Road", "Civil Lines", "Market Area", "Residency Road",
    "Bus Stand Road", "University Campus",
)
UPI_NOTES = ("Payment", "UPI", "Paid via app", "Order", "Bill", "Sent")

# Statement periods end between these dates. The window is fixed (not "today") so the same
# seed always gives the same statement, and it ends early enough that every date derived
# from a statement (generation, forgery edits, re-saves) lies before the dataset was made.
EARLIEST_PERIOD_END = date(2024, 7, 31)
LATEST_PERIOD_END = date(2026, 6, 30)


@dataclass
class _Event:
    """A planned transaction before balances are applied."""

    day: date
    order: int  # sort order within a day; credits like salary come first
    kind: str
    amount: Decimal
    counterparty: str = ""
    extra: str = ""


def _month_starts(start: date, months: int) -> list[date]:
    out, y, m = [], start.year, start.month
    for _ in range(months):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def _amount(rng: random.Random, low: float, high: float, whole: bool = True) -> Decimal:
    value = rng.uniform(low, high)
    return to_money(round(value) if whole else value)


def _upi_amount(rng: random.Random) -> Decimal:
    roll = rng.random()
    if roll < 0.70:
        return _amount(rng, 20, 500, whole=rng.random() < 0.8)
    if roll < 0.95:
        return _amount(rng, 500, 3000, whole=rng.random() < 0.8)
    return _amount(rng, 3000, 15000)


def make_customer(rng: random.Random, fake: Faker, bank: BankProfile) -> Customer:
    city = rng.choice(bank.cities)
    name = fake.name()
    salaried = rng.random() < 0.85
    employer = None
    if salaried:
        employer = f"{fake.last_name()} {rng.choice(EMPLOYER_SUFFIXES)}"
    local = "".join(c for c in name.lower() if c.isalpha())[:2] or "xx"
    return Customer(
        name=name.upper(),
        address_lines=[fake.street_address(), f"{city} - {fake.postcode()}"],
        phone_masked="XXXXXX" + _digits(rng, 4),
        email_masked=f"{local}****@{rng.choice(['gmail.com', 'yahoo.co.in', 'outlook.com'])}",
        customer_id=_digits(rng, 9),
        account_number=rng.choice("123456789") + _digits(rng, 13),
        account_type="Savings Account",
        branch_name=f"{city} - {rng.choice(BRANCH_AREAS)}",
        branch_city=city,
        ifsc=f"{bank.ifsc_prefix}0{_digits(rng, 6)}",
        micr=_digits(rng, 9),
        nominee_registered=rng.random() < 0.7,
        salaried=salaried,
        employer=employer,
    )


def _plan_events(rng: random.Random, fake: Faker, customer: Customer, start: date, end: date,
                 months: int) -> list[_Event]:
    events: list[_Event] = []
    salary = to_money(_amount(rng, 25000, 150000) // 100 * 100)
    rent = to_money(_amount(rng, 8000, 35000) // 500 * 500) if rng.random() < 0.35 else None
    emi = _amount(rng, 3000, 25000) if rng.random() < 0.4 else None
    emi_day = rng.choice([5, 7, 10])
    lender = rng.choice(LENDERS)
    loan_ref = "LN" + _digits(rng, 10)
    utilities = rng.sample(UTILITIES, k=rng.randint(2, 4))
    contacts = [fake.name().upper() for _ in range(6)]

    def rand_day(month_start: date) -> date:
        return month_start + timedelta(days=rng.randint(0, _month_end(month_start).day - 1))

    for ms in _month_starts(start, months):
        me = _month_end(ms)
        if customer.salaried:
            events.append(_Event(ms + timedelta(days=rng.randint(0, 2)), 0, "salary", salary,
                                 customer.employer or "EMPLOYER"))
        else:
            for _ in range(rng.randint(1, 3)):
                events.append(_Event(rand_day(ms), 1, "neft_in", _amount(rng, 5000, 60000),
                                     rng.choice(contacts)))
        if rent:
            events.append(_Event(ms + timedelta(days=rng.randint(1, 5)), 5, "rent", rent,
                                 rng.choice(contacts)))
        if emi:
            events.append(_Event(ms.replace(day=emi_day), 5, "emi", emi, lender, loan_ref))
        for biller, kind in utilities:
            events.append(_Event(rand_day(ms), 6, "bill", _amount(rng, 199, 3500, whole=False),
                                 biller, kind))
        for _ in range(rng.randint(8, 30)):
            events.append(_Event(rand_day(ms), 8, "upi_out", _upi_amount(rng),
                                 rng.choice(MERCHANTS + tuple(contacts))))
        for _ in range(rng.randint(0, 4)):
            events.append(_Event(rand_day(ms), 2, "upi_in", _amount(rng, 100, 5000),
                                 rng.choice(contacts)))
        for _ in range(rng.randint(0, 3)):
            events.append(_Event(rand_day(ms), 7, "atm", to_money(rng.randint(2, 20) * 500)))
        for _ in range(rng.randint(0, 5)):
            events.append(_Event(rand_day(ms), 8, "pos", _amount(rng, 200, 6000, whole=False),
                                 rng.choice(MERCHANTS)))
        for _ in range(rng.randint(0, 2)):
            events.append(_Event(rand_day(ms), 7, "imps_out", _amount(rng, 1000, 20000),
                                 rng.choice(contacts)))
        if rng.random() < 0.15:
            events.append(_Event(rand_day(ms), 3, "cheque_in", _amount(rng, 2000, 50000),
                                 rng.choice(contacts)))
        if me.month in (3, 6, 9, 12):
            events.append(_Event(me, 9, "interest", Decimal("0.00")))
            events.append(_Event(me, 9, "sms_charges", to_money("17.70")))

    events = [e for e in events if start <= e.day <= end]
    events.sort(key=lambda e: (e.day, e.order, e.kind))
    return events


def _narrate(rng: random.Random, bank: BankProfile, event: _Event, customer: Customer
             ) -> tuple[str, str, bool]:
    """Return (narration, reference, is_credit) for an event."""
    cp = event.counterparty
    vpa_name = "".join(c for c in cp.lower() if c.isalnum())[:12] or "payee"
    other_bank = rng.choice(COUNTERPARTY_IFSC_PREFIXES)
    if event.kind == "salary":
        utr = f"{other_bank}N{event.day:%y}{event.day.timetuple().tm_yday:03d}{_digits(rng, 6)}"
        month = event.day.strftime("%b %Y").upper()
        return f"NEFT CR-{other_bank}0{_digits(rng, 6)}-{cp.upper()}-SALARY {month}", utr, True
    if event.kind == "neft_in":
        utr = f"{other_bank}N{event.day:%y}{event.day.timetuple().tm_yday:03d}{_digits(rng, 6)}"
        return f"NEFT CR-{other_bank}0{_digits(rng, 6)}-{cp}-TRANSFER", utr, True
    if event.kind == "upi_in":
        ref = _digits(rng, 12)
        return f"UPI/CR/{ref}/{cp}/{other_bank}/{vpa_name}@ok{other_bank.lower()[:3]}", ref, True
    if event.kind == "cheque_in":
        chq = _digits(rng, 6)
        return f"CLG/{chq}/{cp}/{other_bank}", chq, True
    if event.kind == "interest":
        q_start = date(event.day.year, event.day.month - 2, 1)
        return f"INT.PD:{customer.account_number[-4:]}:{q_start:%d-%m-%Y} TO {event.day:%d-%m-%Y}", "", True
    if event.kind in ("upi_out", "rent"):
        ref = _digits(rng, 12)
        note = "Rent" if event.kind == "rent" else rng.choice(UPI_NOTES)
        return f"UPI/DR/{ref}/{cp}/{vpa_name}@{bank.upi_handle}/{note}", ref, False
    if event.kind == "emi":
        return f"ACH D- {cp.upper()}-{event.extra}", event.extra, False
    if event.kind == "bill":
        ref = "BP" + _digits(rng, 10)
        return f"BIL/BPAY/{ref}/{cp.upper()}/{event.extra}", ref, False
    if event.kind == "atm":
        atm = f"S1AN{_digits(rng, 4)}"
        return f"ATM WDL/{atm}/{customer.branch_city.upper()}", atm, False
    if event.kind == "pos":
        return f"POS {_digits(rng, 6)}XXXXXX{_digits(rng, 4)} {cp.upper()}", "", False
    if event.kind == "imps_out":
        ref = _digits(rng, 12)
        return f"IMPS/P2A/{ref}/{cp}/{other_bank}", ref, False
    if event.kind == "sms_charges":
        return f"SMS ALERT CHGS QTR {event.day:%b%y}".upper() + " INCL GST", "", False
    raise ValueError(f"Unknown event kind: {event.kind}")


def _styled(narration: str, kind: str, is_credit: bool, style: str) -> str:
    """Rewrite a narration in the bank's house style.

    ``slash`` keeps ``UPI/DR/...``; ``hyphen`` uses hyphens (``UPI-DR-...``) and ``ATW-``
    for cash withdrawals; ``transfer`` prefixes ``BY TRANSFER-`` / ``TO TRANSFER-`` to
    electronic transfers, as some public-sector banks do.
    """
    if style == "slash":
        return narration
    if style == "hyphen":
        if kind == "atm":
            return narration.replace("ATM WDL/", "ATW-").replace("/", "-")
        if kind in ("upi_in", "upi_out", "rent", "imps_out", "bill", "cheque_in"):
            return narration.replace("/", "-")
        return narration
    if style == "transfer":
        if kind in ("upi_in", "upi_out", "rent", "imps_out", "neft_in", "salary"):
            return ("BY TRANSFER-" if is_credit else "TO TRANSFER-") + narration
        if kind == "atm":
            return "ATM CASH WDL-" + narration.removeprefix("ATM WDL/")
        return narration
    raise ValueError(f"Unknown narration style '{style}'")


CATEGORY = {
    "salary": "salary", "neft_in": "transfer_in", "upi_in": "upi_in", "cheque_in": "cheque_in",
    "interest": "interest", "upi_out": "upi_out", "rent": "rent", "emi": "emi", "bill": "bill",
    "atm": "atm", "pos": "pos", "imps_out": "transfer_out", "sms_charges": "charges",
}


def build_statement(seed: int, bank: BankProfile, months: int = 3,
                    period_end: date | None = None) -> Statement:
    """Generate one genuine statement for ``bank`` from ``seed``.

    The running balance is computed row by row from the opening balance, so every row,
    the account summary and the closing balance are always arithmetically consistent.
    Debits that would take the balance below the bank's minimum are skipped.
    """
    if not 1 <= months <= 12:
        raise ValueError("months must be between 1 and 12")
    # Mix the bank into the seed so the same seed gives different customers at each bank.
    mixed = int(hashlib.sha256(f"{bank.bank_id}:{seed}".encode()).hexdigest()[:15], 16)
    rng = random.Random(mixed)
    fake = Faker("en_IN")
    fake.seed_instance(mixed)

    if period_end is None:
        span = (LATEST_PERIOD_END - EARLIEST_PERIOD_END).days
        period_end = _month_end(EARLIEST_PERIOD_END + timedelta(days=rng.randint(0, span)))
    start_month = _month_starts(period_end.replace(day=1), 1)[0]
    for _ in range(months - 1):
        start_month = (start_month - timedelta(days=1)).replace(day=1)
    period_start = start_month

    customer = make_customer(rng, fake, bank)
    opening = _amount(rng, 5000, 250000, whole=False)
    floor = to_money(bank.min_balance)

    balance = opening
    rows: list[Transaction] = []
    for event in _plan_events(rng, fake, customer, period_start, period_end, months):
        amount = event.amount
        if event.kind == "interest":
            amount = to_money(balance * Decimal("0.027") / 4)
            if amount <= 0:
                continue
        narration, reference, is_credit = _narrate(rng, bank, event, customer)
        narration = _styled(narration, event.kind, is_credit, bank.narration_style)
        if not is_credit and balance - amount < floor:
            continue
        value_date = event.day
        if event.kind == "cheque_in":
            value_date = event.day + timedelta(days=rng.randint(1, 2))
        balance = balance + amount if is_credit else balance - amount
        rows.append(Transaction(
            txn_date=event.day,
            value_date=value_date,
            narration=narration,
            reference=reference,
            debit=Decimal("0.00") if is_credit else amount,
            credit=amount if is_credit else Decimal("0.00"),
            balance=balance,
            category=CATEGORY[event.kind],
        ))

    return Statement(
        statement_id=f"{bank.bank_id}_{seed:06d}",
        bank_id=bank.bank_id,
        layout=bank.template.removesuffix(".html.j2"),
        seed=seed,
        period_start=period_start,
        period_end=period_end,
        generated_on=period_end + timedelta(days=rng.randint(1, 5)),
        customer=customer,
        opening_balance=opening,
        transactions=rows,
        number_format=bank.number_format,
    )
