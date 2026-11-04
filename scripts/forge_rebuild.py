"""Create template-rebuilt forgeries from generated genuine statements.

Example:
    python scripts/forge_rebuild.py --genuine data/synthetic/genuine \
        --out data/synthetic/forged/rebuild --per-statement 1 --seed 0 --masks
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from forgelens.forgery import REBUILD_VARIANTS, rebuild, write_masks
from forgelens.generator import LayoutError
from forgelens.utils import stable_seed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--genuine", type=Path, required=True, help="folder of genuine PDF+JSON")
    parser.add_argument("--out", type=Path, default=Path("data/synthetic/forged/rebuild"))
    parser.add_argument("--per-statement", type=int, default=1)
    parser.add_argument("--variants", nargs="+", default=list(REBUILD_VARIANTS),
                        choices=REBUILD_VARIANTS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--masks", action="store_true")
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()

    made, failed = 0, 0
    for json_path in sorted(args.genuine.rglob("*.json")):
        record = json.loads(json_path.read_text())
        if record.get("label") != "genuine":
            continue
        for k in range(args.per_statement):
            seed = stable_seed(args.seed, record["statement_id"], k)
            variant = random.Random(seed).choice(args.variants)
            stem = f"{record['statement_id']}__{variant}_{k:02d}"
            out_pdf = args.out / f"{stem}.pdf"
            try:
                label = rebuild(record, out_pdf, variant=variant, seed=seed)
            except (ValueError, LayoutError) as exc:  # no credits, or layout not readable
                out_pdf.unlink(missing_ok=True)
                print(f"skip {stem}: {exc}")
                failed += 1
                continue
            if args.masks and label["edits"]:
                import pymupdf

                with pymupdf.open(out_pdf) as doc:
                    size = (doc[0].rect.width, doc[0].rect.height)
                masks = write_masks(label, size, args.out / stem, dpi=args.dpi)
                label["masks"] = {"dpi": args.dpi, "files": [m.name for m in masks]}
            (args.out / f"{stem}.json").write_text(json.dumps(label, indent=2))
            made += 1
    print(f"Created {made} rebuilt forgeries in {args.out}"
          + (f"; skipped {failed}" if failed else ""))


if __name__ == "__main__":
    main()
