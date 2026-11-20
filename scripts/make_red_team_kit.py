#!/usr/bin/env python
"""Build the red-team kit: synthetic statements for outside volunteers to forge.

Every result so far was measured on forgeries our own code made. The red-team (blind) set
asks people who have not seen ForgeLens to forge statements with whatever tools they like.
This script makes:

    <out>/kit/            what volunteers get (zip it and share it)
        statements/RT01.pdf ... RTnn.pdf   fictional statements, 3-month period
        BRIEF.pdf, BRIEF.md                what to do, in one page
        form.csv                           one row per statement they change
    <out>/key/            what stays with us: RTnn -> the generated statement and its JSON

The statements come from the ten hand-made banks with seeds far from the training and test
sets (8000+), so no volunteer file is a statement any model has seen.

    python scripts/make_red_team_kit.py --out ~/forgelens-data/red_team --per-bank 3
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BRIEF = """# Forge a bank statement: brief for volunteers

Thank you for helping. We are testing **ForgeLens**, a final-year project at SRM that tries
to tell edited bank statements from genuine ones. To know whether it works, we need forgeries
made by people other than us, with their own tools and ideas.

**The statements are fictional.** The banks, names, account numbers and transactions were
made up by a program. Nothing here belongs to a real person or bank. Please do not use the
techniques on real documents.

## What to do

1. Pick any of the statements in `statements/` (do as many as you like; 3–5 is great).
2. Change something **the way someone would to get a loan or a visa**: raise a salary credit,
   raise the closing balance, change the account holder's name, remove an inconvenient debit,
   add a deposit, change dates, anything you think would pass.
3. Use **any tool**: a PDF editor (Adobe Acrobat, iLovePDF, Sejda, PDFescape, Smallpdf),
   Photoshop or GIMP on an image of the page, Canva, Word, a phone app, a screenshot that you
   edit, an AI image tool. Try to make it look real.
4. Save the result as a **PDF or an image** named after the statement plus your initials,
   e.g. `RT07_AB.pdf`. If you changed a statement twice in different ways, save two files
   (`RT07_AB_1.pdf`, `RT07_AB_2.pdf`).
5. Fill in **one row of `form.csv`** (or a note in the same format) for each file:
   what you changed, on which page, which tool you used, and roughly how long it took.
6. Send the files and the form back to the person who gave you this kit.

**Please do not** tell us anything that would identify you in the form beyond your initials.
We only need to know what was changed and how, so we can check whether ForgeLens found it.
"""

FORM_FIELDS = ["file", "statement", "what_you_changed", "page", "tool", "minutes",
               "kept_balances_consistent", "notes"]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--per-bank", type=int, default=3)
    p.add_argument("--seed", type=int, default=8000)
    p.add_argument("--months", type=int, default=3)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    from forgelens.generator.banks import BANKS

    kit, key = args.out / "kit", args.out / "key"
    if kit.exists():
        print(f"{kit} exists; remove it first", file=sys.stderr)
        return 1
    (kit / "statements").mkdir(parents=True)
    key.mkdir(parents=True, exist_ok=True)
    mapping = {}
    n = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, bank in enumerate(sorted(BANKS)):
            out = Path(tmp) / bank
            subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_statements.py"),
                            "--bank", bank, "--count", str(args.per_bank),
                            "--seed", str(args.seed + 100 * i), "--months", str(args.months),
                            "--out", str(out)], check=True, capture_output=True)
            for pdf in sorted(out.rglob("*.pdf")):
                n += 1
                rt = f"RT{n:02d}"
                shutil.copy(pdf, kit / "statements" / f"{rt}.pdf")
                shutil.copy(pdf, key / f"{rt}.pdf")
                shutil.copy(pdf.with_suffix(".json"), key / f"{rt}.json")
                mapping[rt] = {"bank_id": bank, "source": pdf.name}
    (key / "key.json").write_text(json.dumps(mapping, indent=1))
    (kit / "BRIEF.md").write_text(BRIEF)
    try:
        import markdown  # noqa: F401
        html_body = __import__("markdown").markdown(BRIEF)
    except ImportError:
        html_body = "".join(f"<p>{line}</p>" for line in BRIEF.splitlines() if line.strip())
    try:
        from weasyprint import HTML

        HTML(string=f"<html><body style='font-family:sans-serif;font-size:10.5pt'>{html_body}"
                    "</body></html>").write_pdf(kit / "BRIEF.pdf")
    except Exception as exc:  # noqa: BLE001
        print(f"BRIEF.pdf not written ({type(exc).__name__}); BRIEF.md is there", file=sys.stderr)
    with open(kit / "form.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FORM_FIELDS)
        w.writerow(["RT07_AB.pdf", "RT07", "raised the salary credit on 3 March from 45,000 to "
                    "95,000", "1", "iLovePDF edit", "10", "no", "example row, delete it"])
    print(f"Kit: {n} statements in {kit}; key (keep private) in {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
