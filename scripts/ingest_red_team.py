#!/usr/bin/env python
"""Turn the files volunteers send back into a labelled blind test set.

    python scripts/ingest_red_team.py --returned ~/red_team_returned --form form.csv \\
        --key ~/forgelens-data/red_team/key --out ~/forgelens-data/red_team/blind

Writes ``<out>/genuine`` (the untouched kit statements, with their ground-truth JSON) and
``<out>/forged`` (each returned file, as a PDF, with a label recording the statement it came
from, what the volunteer says they changed and the tool). Returned images (PNG, JPEG) are
wrapped into one-page PDFs and labelled as such. The folders then go through the same
evaluation as the test set (eval_signals.py, eval_adcdnet_pages.py, eval_ocr_financial.py,
apply_fusion.py), with the thresholds fitted on the test set.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".heic"}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--returned", type=Path, required=True, help="folder of returned files")
    p.add_argument("--form", type=Path, nargs="+", required=True, help="filled-in form.csv files")
    p.add_argument("--key", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args(argv)


def _image_to_pdf(src: Path, dst: Path) -> None:
    import pymupdf

    with pymupdf.open() as doc:
        img = pymupdf.open(src)
        rect = img[0].rect
        page = doc.new_page(width=595, height=595 * rect.height / rect.width)
        page.insert_image(page.rect, filename=str(src))
        doc.save(dst)


def main(argv=None) -> int:
    args = parse_args(argv)
    key = json.loads((args.key / "key.json").read_text())
    rows = {}
    for form in args.form:
        with open(form, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if r.get("file") and "example row" not in (r.get("notes") or ""):
                    rows[r["file"].strip()] = r
    gen, forged = args.out / "genuine", args.out / "forged"
    gen.mkdir(parents=True, exist_ok=True)
    forged.mkdir(parents=True, exist_ok=True)
    for rt in key:
        shutil.copy(args.key / f"{rt}.pdf", gen / f"{rt}.pdf")
        rec = json.loads((args.key / f"{rt}.json").read_text())
        rec["red_team_id"] = rt
        (gen / f"{rt}.json").write_text(json.dumps(rec, indent=1))

    made, unmatched = 0, []
    for f in sorted(args.returned.iterdir()):
        m = re.match(r"(RT\d{2})", f.name, re.I)
        if not m or f.suffix.lower() not in IMAGE_EXT | {".pdf"}:
            continue
        rt = m.group(1).upper()
        if rt not in key:
            unmatched.append(f.name)
            continue
        out = forged / f"{f.stem}__red_team.pdf"
        if f.suffix.lower() == ".pdf":
            shutil.copy(f, out)
            laundering = "none"
        else:
            _image_to_pdf(f, out)
            laundering = "image_returned"
        base = json.loads((args.key / f"{rt}.json").read_text())
        row = rows.get(f.name, {})
        label = {
            "statement_id": f.stem, "label": "forged", "bank_id": key[rt]["bank_id"],
            "red_team_id": rt,
            "forgery": {"method": "red_team", "operation": row.get("what_you_changed", ""),
                        "tool": row.get("tool", ""), "page": row.get("page", ""),
                        "minutes": row.get("minutes", ""),
                        "balance_consistent": (row.get("kept_balances_consistent", "")
                                               .strip().lower() in ("yes", "y", "true")),
                        "source": base.get("statement_id")},
            "laundering": {"method": laundering},
            "edits": [],  # volunteers do not mark regions; pixel F1 is not measured
        }
        if not row:
            label["forgery"]["note"] = "no form row for this file"
        out.with_suffix(".json").write_text(json.dumps(label, indent=1))
        made += 1
    print(f"{len(key)} genuine and {made} forged statements in {args.out}"
          + (f"; not matched to a kit statement: {', '.join(unmatched)}" if unmatched else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
