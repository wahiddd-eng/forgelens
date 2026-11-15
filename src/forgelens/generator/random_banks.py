"""Procedurally generated fictional banks, for more layouts than the ten hand-made ones.

A model trained on ten bank layouts partly learns what those ten look like, and loses a
large share of its accuracy on a layout it has not seen (``experiments/results/
adcdnet_unseen_banks.md``). Generated banks vary everything the hand-made profiles vary,
plus the look of the page: table header and rule styles, row spacing, masthead alignment,
logo shape, title wording, text colour and monospace fonts.

``random_bank(i)`` always returns the same profile for the same ``i``, and its id is
``gen_<i>`` (e.g. ``gen_0007``), so labels that name a generated bank can be resolved again
later by :func:`forgelens.generator.get_bank`. Names, codes and colours are invented;
names are built from parts that avoid the names of real Indian banks.

Column labels stay within words the statement reader recognises (a debit label contains
withdraw, debit or Dr; a credit label deposit, credit or Cr; the balance column comes last),
and dates within formats it reads; every rendered statement is checked against its ground
truth anyway (``locate_fields``), and one that does not read back is not kept.
"""

from __future__ import annotations

import colorsys
import random

from .banks import CALIBRI, DEJAVU, DEJAVU_SERIF, SANS, SERIF, BankProfile

PREFIX = "gen_"
MONO = "'Liberation Mono', 'DejaVu Sans Mono', 'Courier New', monospace"
DEJAVU_MONO = "'DejaVu Sans Mono', 'Liberation Mono', monospace"

TEMPLATES = ("classic_table.html.j2", "ledger_grid.html.j2", "modern_band.html.j2")
FONTS = ((SANS, 4), (SERIF, 3), (DEJAVU, 3), (DEJAVU_SERIF, 2), (MONO, 1), (DEJAVU_MONO, 1),
         (CALIBRI, 1))
DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y", "%d/%m/%y", "%d.%m.%Y",
                "%d-%b-%y", "%d-%m-%y")
LABELS = {
    "sno": ("S.No.", "Sr. No.", "Sl. No."),
    "date": ("Date", "Txn Date", "Tran Date", "Transaction Date", "Posting Date", "Trans. Date"),
    "value_date": ("Value Date", "Value Dt", "Val. Date"),
    "narration": ("Narration", "Description", "Particulars", "Remarks", "Transaction Details",
                  "Details", "Transaction Description"),
    "ref": ("Chq./Ref. No.", "Cheque No.", "Reference", "Ref. No.", "Cheque/Ref", "Chq No.",
            "Instrument No."),
}
# Debit and credit labels come in matching pairs, as on real statements.
AMOUNT_LABELS = (
    ("Withdrawal (Dr)", "Deposit (Cr)"), ("Debit", "Credit"), ("Withdrawals", "Deposits"),
    ("Dr Amount", "Cr Amount"), ("Withdrawal", "Deposit"), ("Withdrawal Amt.", "Deposit Amt."),
    ("Debit (₹)", "Credit (₹)"), ("Debits", "Credits"), ("Withdrawals (Dr)", "Deposits (Cr)"),
    ("Debit Amount", "Credit Amount"),
)
BALANCE_LABELS = ("Balance", "Balance (INR)", "Running Balance", "Balance (₹)",
                  "Available Balance", "Closing Balance")
TITLES = ("Statement of Account", "Account Statement", "e-Statement", "Statement of Transactions",
          "Account Summary and Transactions", "Passbook Statement")

# Name parts: invented compounds, kept clear of real bank names (checked below).
_ROOTS = ("Neel", "Swarn", "Vana", "Shail", "Megh", "Tara", "Kiran", "Pushp", "Akash",
          "Sagar", "Hima", "Surya", "Chandra", "Prakash", "Varsha", "Vidya", "Amrit", "Navya",
          "Ruchi", "Aranya", "Kesar", "Mayur", "Hamsa", "Tilak", "Vinaya", "Shanti")
_ENDS = ("giri", "pur", "dhara", "kunj", "nagar", "vati", "tal", "kshetra", "pradesh",
         "valli", "sthal", "deep", "vihar", "kosh", "rekha", "mandal")
_KINDS = (("Bank", 5), ("Co-operative Bank Ltd.", 2), ("Gramin Bank", 1),
          ("Urban Co-operative Bank", 2), ("Bank Ltd.", 2), ("Small Finance Bank", 1))
_REAL = ("lakshmi", "laxmi", "dhan", "ratnakar", "saraswat", "karur", "vysya", "federal",
         "kotak", "bandhan", "equitas", "ujjivan", "jana", "suryoday", "utkarsh", "punjab",
         "sind", "baroda", "canara", "union", "central", "indian", "overseas", "maharashtra",
         "karnataka", "kerala", "tamilnad", "catholic", "nainital", "cosmos", "janata",
         "bharat", "abhyudaya", "kalupur", "apna", "shamrao", "suco", "akola", "nutan")
_TAGLINES = ("Banking made simple", "Trusted by generations", "Your money, our care",
             "Growing with you", "Serving every community", "A bank for every season",
             "Secure. Simple. Yours.", "Rooted in the region", "Since 1961", "Since 1978",
             "Banking close to home", "Committed to your progress")
_GENERATORS = ("", "", "CoreBank e-Statements 4.2", "SOA Generator", "eStatement Service 2.1",
               "Digital Banking Portal", "Statement Engine")
_CITIES = ("Srinagar", "Jammu", "Delhi", "Chandigarh", "Lucknow", "Dehradun", "Chennai",
           "Bengaluru", "Hyderabad", "Kochi", "Madurai", "Mysuru", "Mumbai", "Pune", "Nagpur",
           "Ahmedabad", "Surat", "Nashik", "Kolkata", "Bhubaneswar", "Patna", "Guwahati",
           "Ranchi", "Bhopal", "Indore", "Raipur", "Jaipur", "Udaipur", "Vadodara", "Mangaluru")


def _hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, l, s)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _weighted(rng: random.Random, options):
    values, weights = zip(*options, strict=True)
    return rng.choices(values, weights=weights)[0]


def _name(rng: random.Random) -> str:
    while True:
        root = rng.choice(_ROOTS) + rng.choice(_ENDS)
        if not any(r in root.lower() for r in _REAL):
            return f"{root} {_weighted(rng, _KINDS)}"


def _columns(rng: random.Random) -> tuple[str, ...]:
    cols = ["date"]
    if rng.random() < 0.4:
        cols.append("value_date")
    cols.append("narration")
    if rng.random() < 0.6:
        cols.insert(rng.choice([1, len(cols)]), "ref")  # after the date, or after narration
    amounts = ["debit", "credit"] if rng.random() < 0.8 else ["credit", "debit"]
    cols += amounts + ["balance"]  # the balance column is always last
    if rng.random() < 0.3:
        cols.insert(0, "sno")
    return tuple(cols)


def random_bank(index: int) -> BankProfile:
    """The generated bank number ``index`` (the same every time)."""
    rng = random.Random(f"forgelens-generated-bank-{index}")
    name = _name(rng)
    words = [w for w in name.replace(".", "").replace("-", " ").split() if w[0].isupper()]
    short = "".join(w[0] for w in words)[:4]
    hue = rng.random()
    primary = _hex(hue, rng.uniform(0.45, 0.75), rng.uniform(0.18, 0.34))
    accent = _hex(hue + 0.5 + rng.uniform(-0.12, 0.12), rng.uniform(0.6, 0.85),
                  rng.uniform(0.5, 0.62))
    cols = _columns(rng)
    debit_label, credit_label = rng.choice(AMOUNT_LABELS)
    labels = {k: rng.choice(v) for k, v in LABELS.items()}
    labels.update(debit=debit_label, credit=credit_label, balance=rng.choice(BALANCE_LABELS))
    style = {
        "th": rng.choice(("filled", "tint", "underline", "boxed")),
        "rules": rng.choice(("rows", "grid", "none", "dotted")),
        "pad": round(rng.uniform(2.0, 4.5), 1),
        "header": rng.choice(("left", "right", "center")),
        "logo": rng.choice(("square", "circle", "shield", "none")),
        "glyph": rng.choice(("peak", "waves", "sun", "pillars")),
        "title": rng.choice(TITLES),
        "text": _hex(hue, 0.15, rng.uniform(0.06, 0.16)),
        "uppercase_th": rng.random() < 0.4,
    }
    letters = "BCDFGHJKLMNPRSTVWXZ"
    return BankProfile(
        bank_id=f"{PREFIX}{index:04d}", name=name, short_name=short or "GB",
        ifsc_prefix="Q" + "".join(rng.choice(letters) for _ in range(3)),
        tagline=rng.choice(_TAGLINES), template=rng.choice(TEMPLATES),
        primary_colour=primary, accent_colour=accent, font_family=_weighted(rng, FONTS),
        date_format=rng.choice(DATE_FORMATS), upi_handle="ok" + short.lower(),
        min_balance=rng.choice(("250", "500", "1000", "2000", "5000", "10000")),
        cities=tuple(rng.sample(_CITIES, 6)), columns=cols, labels=labels,
        grouping=rng.choice(("indian", "indian", "indian", "western", "none")),
        balance_suffix=rng.choice(("", "", "", " Cr", " CR")),
        orientation="landscape" if rng.random() < 0.2 else "portrait",
        summary_position=rng.choice(("top", "bottom")), zebra=rng.random() < 0.5,
        narration_style=rng.choice(("slash", "hyphen", "transfer")),
        base_font_size=round(rng.uniform(7.6, 9.0), 1),
        meta_generator=rng.choice(_GENERATORS), style=style,
    )


def is_generated(bank_id: str) -> bool:
    return bank_id.startswith(PREFIX) and bank_id[len(PREFIX):].isdigit()
