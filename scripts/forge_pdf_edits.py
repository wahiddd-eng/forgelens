"""Create PDF-edit forgeries from generated genuine statements.

Reads every ``<id>.json`` (with its ``<id>.pdf``) in the genuine folder and writes forged
PDFs, their label JSON files and, optionally, per-page PNG masks.

Example:
    python scripts/forge_pdf_edits.py --genuine data/synthetic/genuine/himalaya_national \
        --out data/synthetic/forged/pdf_edit --per-statement 2 --seed 0 --masks --dpi 150
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from forgelens.forgery import forge, write_masks
from forgelens.utils import stable_seed

# (operation, balance_consistent, weight). Balance-consistent forgeries are kept common so
# that detectors cannot rely on arithmetic checks alone.
VARIANTS = (
    ("credit_amount", False, 0.30),
    ("credit_amount", True, 0.35),
    ("closing_balance", False, 0.20),
    ("holder_name", False, 0.15),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--genuine", type=Path, required=True, help="folder of genuine PDF+JSON")
    parser.add_argument("--out", type=Path, default=Path("data/synthetic/forged/pdf_edit"))
    parser.add_argument("--per-statement", type=int, default=1, help="forgeries per genuine file")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--masks", action="store_true", help="also write PNG masks")
    parser.add_argument("--dpi", type=int, default=150, help="mask resolution")
    args = parser.parse_args()

    records = sorted(args.genuine.rglob("*.json"))
    if not records:
        raise SystemExit(f"No genuine JSON files found in {args.genuine}")

    made, failed = 0, 0
    for json_path in records:
        record = json.loads(json_path.read_text())
        if record.get("label") != "genuine":
            continue
        pdf_path = json_path.with_suffix(".pdf")
        if "layout" not in record or not pdf_path.exists():
            print(f"skip {json_path.name}: missing PDF or layout")
            continue
        for k in range(args.per_statement):
            # Each forgery's choices depend only on the run seed and its own identity, so
            # adding or removing other statements does not change it.
            seed = stable_seed(args.seed, record["statement_id"], k)
            rng = random.Random(seed)
            operation, consistent, _ = rng.choices(VARIANTS, weights=[v[2] for v in VARIANTS])[0]
            variant = operation + ("_consistent" if consistent else "")
            stem = f"{record['statement_id']}__pdfedit_{variant}_{k:02d}"
            out_pdf = args.out / f"{stem}.pdf"
            try:
                label = forge(pdf_path, record, out_pdf, operation=operation,
                              consistent=consistent, seed=seed)
            except ValueError as exc:  # e.g. a statement without credits to inflate
                print(f"skip {stem}: {exc}")
                failed += 1
                continue
            if args.masks:
                masks = write_masks(label, record["layout"]["page_size"], args.out / stem,
                                    dpi=args.dpi)
                label["masks"] = {"dpi": args.dpi, "files": [m.name for m in masks]}
            (args.out / f"{stem}.json").write_text(json.dumps(label, indent=2))
            made += 1
            print(f"{stem}: {len(label['edits'])} edit(s), {label['forgery']['save_mode']}, "
                  f"{label['forgery']['font_strategy']} font")
    print(f"Created {made} forgeries in {args.out}" + (f"; skipped {failed}" if failed else ""))


if __name__ == "__main__":
    main()
