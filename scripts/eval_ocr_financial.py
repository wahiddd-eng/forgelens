"""Run the OCR arithmetic signal on labelled statements, for fusion (``fuse_signals.py --ocr``).

Every statement's pages are rendered, read by OCR and checked (``signals/ocr_financial.py``).
Meant for the rasterised files, where the PDF financial signal abstains; it runs on any PDF.
One CSV row per statement; safe to stop and start again (``--resume``).

    python scripts/eval_ocr_financial.py --tag test --resume \\
        --data $T/genuine_raster $T/forged_raster $T/forged_image
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

FIELDS = ["file", "label", "method", "laundering", "bank_id", "pages", "rows", "breaks",
          "explained", "summary_breaks", "score", "abstained", "error", "seconds"]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data", type=Path, nargs="+", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--out", type=Path, default=Path("experiments/results"))
    p.add_argument("--dpi", type=int, default=150, help="as the rasterised files were saved")
    p.add_argument("--limit", type=int, help="at most N statements (smoke test)")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--cpu", action="store_true", help="run the OCR on the CPU")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    from forgelens.signals.ocr_financial import OcrReader, check_pdf

    items = []
    for folder in args.data:
        for j in sorted(Path(folder).expanduser().rglob("*.json")):
            try:
                rec = json.loads(j.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if rec.get("label") in ("genuine", "forged") and j.with_suffix(".pdf").exists():
                items.append((j.with_suffix(".pdf"), rec))
    items = items[:args.limit] if args.limit else items
    out = args.out / f"ocr_financial_{args.tag}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.resume and out.exists():
        with open(out, newline="") as fh:
            done = {r["file"] for r in csv.DictReader(fh)}
    else:
        with open(out, "w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=FIELDS).writeheader()
    todo = [(p, r) for p, r in items if p.name not in done]
    print(f"{len(items)} statements, {len(todo)} to do", flush=True)
    if not todo:
        return 0
    reader = OcrReader(gpu=False if args.cpu else None)
    start = time.time()
    with open(out, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        for n, (pdf, rec) in enumerate(todo, 1):
            t = time.time()
            rep = check_pdf(pdf, reader, args.dpi)
            writer.writerow({
                "file": pdf.name, "label": rec["label"],
                "method": (rec.get("forgery") or {}).get("method", "genuine"),
                "laundering": (rec.get("laundering") or {}).get("method", "none"),
                "bank_id": rec.get("bank_id", ""), "pages": rep.pages, "rows": rep.rows,
                "breaks": rep.breaks, "explained": rep.explained,
                "summary_breaks": rep.summary_breaks, "score": round(rep.score, 4),
                "abstained": rep.abstained, "error": rep.error or "",
                "seconds": round(time.time() - t, 1)})
            fh.flush()
            if n % 20 == 0 or n == len(todo):
                rate = (time.time() - start) / n
                print(f"{n}/{len(todo)} statements, {rate:.1f}s each, "
                      f"~{rate * (len(todo) - n) / 60:.0f} min left", flush=True)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
