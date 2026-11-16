#!/usr/bin/env python
"""Why the OCR arithmetic check flags genuine statements: every unexplained break, in detail.

Runs the check on a sample of statements at one or more render scales and prints, per
statement, the unexplained breaks (row, page, how far the balance is off, and each cell's
text and OCR confidence), then a summary per folder and scale. Statements are synthetic
test files; nothing is written except the JSON report.

    python scripts/diagnose_ocr_breaks.py --data $T/genuine_raster $T/forged_raster \\
        --per-folder 30 --scale 1 2 --methods genuine pdf_edit
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data", type=Path, nargs="+", required=True)
    p.add_argument("--per-folder", type=int, default=30)
    p.add_argument("--methods", nargs="+", default=["genuine", "pdf_edit"],
                   help="forgery methods to sample (genuine = genuine statements)")
    p.add_argument("--scale", type=float, nargs="+", default=[1.0])
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=Path("experiments/results/ocr_breaks_diagnosis.json"))
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    from forgelens.signals.ocr_financial import OcrReader, check_pdf

    rng = random.Random(args.seed)
    sample = []
    for folder in args.data:
        items = []
        for j in sorted(Path(folder).expanduser().rglob("*.json")):
            try:
                rec = json.loads(j.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            method = (rec.get("forgery") or {}).get("method", "genuine")
            if method in args.methods and j.with_suffix(".pdf").exists():
                items.append((j.with_suffix(".pdf"), rec))
        rng.shuffle(items)
        sample += [(folder.name, p, r) for p, r in items[:args.per_folder]]
    print(f"{len(sample)} statements, scales {args.scale}", flush=True)

    reader = OcrReader()
    out, summary = [], {}
    for scale in args.scale:
        for folder, pdf, rec in sample:
            t = time.time()
            rep = check_pdf(pdf, reader, args.dpi, scale=scale)
            consistent = (rec.get("forgery") or {}).get("balance_consistent")
            entry = {"file": pdf.name, "folder": folder, "scale": scale, "label": rec["label"],
                     "consistent": consistent, "rows": rep.rows, "breaks": rep.breaks,
                     "explained": rep.explained, "summary_breaks": rep.summary_breaks,
                     "unexplained": rep.unexplained, "abstained": rep.abstained,
                     "findings": rep.findings, "details": rep.details,
                     "seconds": round(time.time() - t, 1)}
            out.append(entry)
            key = (folder, scale, rec["label"], consistent)
            summary.setdefault(key, []).append(rep.unexplained)
            if rep.unexplained:
                print(f"\n[{scale}x] {pdf.name} ({rec['label']}, consistent={consistent}): "
                      f"{rep.rows} rows, {rep.breaks} breaks, {rep.explained} explained, "
                      f"{rep.summary_breaks} summary")
                for f in rep.findings:
                    if f.startswith("summary"):
                        print("   ", f)
                for d in rep.details:
                    cells = ", ".join(f"{k}={t!r}@{c}" for k, (t, c) in d["cells"].items())
                    print(f"    row {d['row']} p{d['page']} off {d['delta']}: {cells}")
    print("\n== summary: share flagged, mean unexplained breaks, rows read")
    for (folder, scale, label, cons), u in sorted(summary.items(), key=str):
        print(f"{folder:16} {scale:>4}x {label:8} consistent={cons!s:5} n={len(u):3} "
              f"flagged={sum(x > 0 for x in u) / len(u):5.0%} mean={statistics.mean(u):.2f}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
