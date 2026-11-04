"""Template-rebuilt forgeries: the forger regenerates the whole statement.

Instead of editing a PDF, the forger re-creates the statement from a template with better
numbers, so there is no edited file to find. Two variants:

``rebuilt_exact``
    Rendered with the bank's real template, fonts and settings: an insider or perfect-copy
    forgery. Nothing about the file differs from a genuine statement; only external checks
    (asking the bank) can catch it. It sets the floor for every document-based signal.
``rebuilt_imitation``
    Rendered from an imitation of the template: a different font, a slightly different text
    size and often a different "Creator" in the metadata, as when a forger rebuilds the
    layout in an office or HTML tool.

The content change is the same for both: every salary credit (or, without salary, the
incoming transfers, else the largest credit) is inflated and every later balance, the totals
and the closing balance are recomputed, so the arithmetic is fully consistent. Optionally the
account holder's name is replaced too.

Labels use the same edit fields as PDF edits. ``old_bbox`` is None because the rebuilt file
is a new document: the original values were never drawn in it. For imitations the label
also records the fonts the PDF really embeds, since a requested imitation font that is not
installed can fall back to the bank's own font.
"""

from __future__ import annotations

import copy
import random
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from faker import Faker

from ..generator.banks import CALIBRI, DEJAVU, DEJAVU_SERIF, SANS, SERIF, get_bank
from ..generator.layout import locate_fields
from ..generator.models import Statement
from ..generator.money import format_amount, to_money
from ..generator.render import render_pdf
from ..reader import font_key

VARIANTS = ("rebuilt_exact", "rebuilt_imitation")
_FONT_STACKS = (SANS, SERIF, CALIBRI, DEJAVU, DEJAVU_SERIF,
                "'Nimbus Sans', Helvetica, sans-serif", "FreeSerif, 'Times New Roman', serif")
_CREATORS = ("PDF Converter 3.1", "HTML to PDF", "Statement Editor", "Document Writer 7",
             "PDF Printer")


def _inflate(statement: Statement, rng: random.Random) -> list[int]:
    """Inflate income rows in place, recompute balances, and return the changed row indices."""
    rows = statement.transactions
    targets = [i for i, t in enumerate(rows) if t.category == "salary"]
    if not targets:
        targets = [i for i, t in enumerate(rows) if t.category == "transfer_in"]
    if not targets:
        credits = [i for i, t in enumerate(rows) if t.credit > 0]
        targets = [max(credits, key=lambda i: rows[i].credit)] if credits else []
    if not targets:
        raise ValueError("statement has no credit rows to inflate")
    factor = Decimal(str(round(rng.uniform(1.4, 2.5), 2)))
    for i in targets:
        old = rows[i].credit
        new = old * factor
        if old == old.to_integral_value():
            new = (new / 100).to_integral_value() * 100
        rows[i].credit = to_money(new)
    balance = statement.opening_balance
    for t in rows:
        balance = balance - t.debit + t.credit
        t.balance = balance
    return targets


def rebuild(record: dict, out_pdf: str | Path, *, variant: str, seed: int = 0,
            change_name: bool | None = None) -> dict:
    """Render a rebuilt forgery of the genuine ``record`` and return its label record."""
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant '{variant}'. Choose from {', '.join(VARIANTS)}")
    rng = random.Random(seed)
    bank = get_bank(record["bank_id"])
    original = Statement.from_ground_truth(record)
    forged = Statement.from_ground_truth(record)
    changed_rows = _inflate(forged, rng)
    if change_name is None:
        change_name = rng.random() < 0.3
    if change_name:
        fake = Faker("en_IN")
        fake.seed_instance(seed)
        new_name = fake.name().upper()
        while new_name == original.customer.name:
            new_name = fake.name().upper()
        forged.customer.name = new_name

    imitation = {}
    if variant == "rebuilt_imitation":
        font = rng.choice([f for f in _FONT_STACKS if f != bank.font_family])
        size = round(bank.base_font_size + rng.choice([-0.8, -0.5, -0.3, 0.3, 0.5, 0.8]), 1)
        creator = rng.choice(_CREATORS) if rng.random() < 0.6 else ""
        imitation = {"font_family": font, "base_font_size": size, "meta_generator": creator}
        bank = replace(bank, **imitation)

    out_pdf = Path(out_pdf)
    forged.statement_id = out_pdf.stem
    render_pdf(forged, bank, out_pdf, check_fonts=variant == "rebuilt_exact")
    layout = locate_fields(out_pdf, forged, bank)
    if imitation:
        families = {font_key(f)[0] for f in layout["fonts"]}
        genuine = record.get("layout", {}).get("fonts")
        imitation["rendered_fonts"] = layout["fonts"]
        imitation["font_changed"] = (None if genuine is None
                                     else families != {font_key(f)[0] for f in genuine})

    def amt(v: Decimal) -> str:
        return format_amount(v, bank.grouping)

    def bal(v: Decimal) -> str:
        return format_amount(v, bank.grouping, bank.balance_suffix)

    edits = []
    for i, (old, new) in enumerate(zip(original.transactions, forged.transactions)):
        row = layout["rows"][i]
        if old.credit != new.credit:
            edits.append({"field": "credit", "row": i, "page": row["page"],
                          "old": amt(old.credit), "new": row["amount"]["text"],
                          "old_bbox": None, "new_bbox": row["amount"]["bbox"],
                          "mask_bbox": row["amount"]["bbox"]})
        if old.balance != new.balance:
            edits.append({"field": "balance", "row": i, "page": row["page"],
                          "old": bal(old.balance), "new": row["balance"]["text"],
                          "old_bbox": None, "new_bbox": row["balance"]["bbox"],
                          "mask_bbox": row["balance"]["bbox"]})
    fields = layout["fields"]
    for key, old_text, changed in (
            ("summary_total_credits", amt(original.total_credits),
             original.total_credits != forged.total_credits),
            ("summary_closing", bal(original.closing_balance),
             original.closing_balance != forged.closing_balance)):
        if key in fields and changed:
            f = fields[key]
            edits.append({"field": key, "row": None, "page": f["page"], "old": old_text,
                          "new": f["text"], "old_bbox": None, "new_bbox": f["bbox"],
                          "mask_bbox": f["bbox"]})
    if change_name:
        f = fields["customer_name"]
        edits.append({"field": "customer_name", "row": None, "page": f["page"],
                      "old": original.customer.name, "new": f["text"], "old_bbox": None,
                      "new_bbox": f["bbox"], "mask_bbox": f["bbox"]})

    label = copy.deepcopy(forged.ground_truth())
    label.update({
        "label": "forged",
        "pdf": out_pdf.name,
        "source_statement_id": record["statement_id"],
        "forgery": {
            "method": "rebuild",
            "operation": "income_inflation" + ("+holder_name" if change_name else ""),
            "variant": variant,
            "balance_consistent": True,
            "seed": seed,
            "inflated_rows": changed_rows,
            "imitation": imitation or None,
        },
        "edits": edits,
    })
    return label
