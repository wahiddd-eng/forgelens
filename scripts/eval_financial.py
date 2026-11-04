"""Evaluate the financial-consistency signal on genuine and forged statements.

A statement is predicted "forged" when any consistency check fails. Writes a per-file CSV,
a summary JSON and a Markdown table to the output folder.

Example:
    python scripts/eval_financial.py --genuine data/synthetic/genuine/himalaya_national \
        --forged data/synthetic/forged/pdf_edit --out experiments/results --tag v1
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from forgelens.signals.financial import check_statement


def _items(folder: Path):
    for json_path in sorted(folder.glob("*.json")):
        record = json.loads(json_path.read_text())
        pdf = json_path.with_suffix(".pdf")
        if pdf.exists() and record.get("label") in ("genuine", "forged"):
            yield pdf, record


def _rate(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--genuine", type=Path, required=True)
    parser.add_argument("--forged", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("experiments/results"))
    parser.add_argument("--tag", default="v1")
    args = parser.parse_args()

    rows = []
    for folder in (args.genuine, args.forged):
        for pdf, record in _items(folder):
            report = check_statement(pdf)
            forgery = record.get("forgery") or {}
            rows.append({
                "file": pdf.name,
                "label": record["label"],
                "variant": forgery.get("variant", "genuine"),
                "balance_consistent": forgery.get("balance_consistent", True),
                "predicted": "consistent" if report.consistent else "inconsistent",
                "score": round(report.score, 4),
                "parsed_rows": report.parsed_rows,
                "n_findings": len(report.findings),
                "failed_checks": ";".join(sorted({f.check for f in report.findings})),
            })
    if not rows:
        raise SystemExit("No statements found")

    tp = sum(r["label"] == "forged" and r["predicted"] == "inconsistent" for r in rows)
    fp = sum(r["label"] == "genuine" and r["predicted"] == "inconsistent" for r in rows)
    fn = sum(r["label"] == "forged" and r["predicted"] == "consistent" for r in rows)
    tn = sum(r["label"] == "genuine" and r["predicted"] == "consistent" for r in rows)
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = (round(2 * precision * recall / (precision + recall), 4)
          if precision and recall else 0.0)

    per_variant = defaultdict(lambda: [0, 0])
    for r in rows:
        per_variant[r["variant"]][0] += 1
        per_variant[r["variant"]][1] += r["predicted"] == "inconsistent"

    summary = {
        "signal": "financial_consistency",
        "tag": args.tag,
        "counts": {"genuine": fp + tn, "forged": tp + fn},
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "accuracy": _rate(tp + tn, len(rows)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": _rate(fp, fp + tn),
        "flagged_rate_by_variant": {
            v: {"n": n, "flagged": k, "rate": _rate(k, n)} for v, (n, k) in sorted(per_variant.items())
        },
    }

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"financial_consistency_{args.tag}"
    with open(f"{stem}_per_file.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    Path(f"{stem}_summary.json").write_text(json.dumps(summary, indent=2))

    lines = [
        f"# Financial-consistency signal — {args.tag}",
        "",
        f"Genuine: {fp + tn} · Forged: {tp + fn}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Accuracy | {summary['accuracy']:.3f} |",
        f"| Precision | {precision:.3f} |" if precision is not None else "| Precision | n/a |",
        f"| Recall | {recall:.3f} |" if recall is not None else "| Recall | n/a |",
        f"| F1 | {f1:.3f} |",
        f"| False-positive rate | {summary['false_positive_rate']:.3f} |",
        "",
        "| Variant | Statements | Flagged | Flag rate |",
        "| --- | --- | --- | --- |",
    ]
    for v, d in summary["flagged_rate_by_variant"].items():
        lines.append(f"| {v} | {d['n']} | {d['flagged']} | {d['rate']:.1%} |")
    Path(f"{stem}_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
