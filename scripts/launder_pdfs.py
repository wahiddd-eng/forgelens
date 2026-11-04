"""Launder genuine or forged statements (reprint with Ghostscript, or rasterise).

Example:
    python scripts/launder_pdfs.py --input data/synthetic/forged/pdf_edit \
        --out data/synthetic/forged/pdf_edit_reprint --method reprint --masks
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from forgelens.forgery import LAUNDER_METHODS, launder, write_masks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True, help="folder of PDF + JSON labels")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--method", choices=LAUNDER_METHODS, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--dpi", type=int, default=150, help="raster resolution")
    parser.add_argument("--masks", action="store_true", help="rewrite masks for forged files")
    args = parser.parse_args()

    import pymupdf

    rng = random.Random(args.seed)
    made = 0
    for json_path in sorted(args.input.rglob("*.json")):
        record = json.loads(json_path.read_text())
        pdf = json_path.with_suffix(".pdf")
        if not pdf.exists() or record.get("label") not in ("genuine", "forged"):
            continue
        out_pdf = args.out / f"{record['statement_id']}__{args.method}.pdf"
        label = launder(pdf, record, out_pdf, method=args.method, seed=rng.randrange(2**31),
                        dpi=args.dpi)
        if args.masks and label.get("edits"):
            with pymupdf.open(out_pdf) as doc:
                size = (doc[0].rect.width, doc[0].rect.height)
            masks = write_masks(label, size, args.out / out_pdf.stem, dpi=args.dpi)
            label["masks"] = {"dpi": args.dpi, "files": [m.name for m in masks]}
        out_pdf.with_suffix(".json").write_text(json.dumps(label, indent=2))
        made += 1
    print(f"Laundered {made} files with '{args.method}' into {args.out}")


if __name__ == "__main__":
    main()
