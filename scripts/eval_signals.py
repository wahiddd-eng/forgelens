"""Evaluate the rule-based signals, alone and combined, on genuine and forged statements.

Signals: financial consistency (``financial``), PDF structure (``structure``) and their
combination (``either``: forged if either signal fires). A signal that cannot read a file
(for example an image-only PDF) abstains: the file counts as not flagged, and abstentions
are reported separately. Also reports how many edited values the structure signal points
at (edit localisation recall).

Example:
    python scripts/eval_signals.py --genuine data/synthetic/genuine/himalaya_national \
        --forged data/synthetic/forged/pdf_edit --out experiments/results --tag pdfedit_v1
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from forgelens.signals.financial import check_statement
from forgelens.signals.pdf_structure import analyze_pdf

SIGNALS = ("financial", "structure", "either")


def _overlaps(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _metrics(rows: list[dict], signal: str) -> dict:
    tp = sum(r["label"] == "forged" and r[signal] for r in rows)
    fp = sum(r["label"] == "genuine" and r[signal] for r in rows)
    fn = sum(r["label"] == "forged" and not r[signal] for r in rows)
    tn = sum(r["label"] == "genuine" and not r[signal] for r in rows)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "accuracy": round((tp + tn) / len(rows), 4),
        "precision": None if precision is None else round(precision, 4),
        "recall": None if recall is None else round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else None,
    }


def _group(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--genuine", type=Path, required=True)
    parser.add_argument("--forged", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("experiments/results"))
    parser.add_argument("--tag", default="v1")
    args = parser.parse_args()

    rows, edits_total, edits_found = [], 0, 0
    for folder in (args.genuine, args.forged):
        for json_path in sorted(folder.rglob("*.json")):
            record = json.loads(json_path.read_text())
            pdf = json_path.with_suffix(".pdf")
            if not pdf.exists() or record.get("label") not in ("genuine", "forged"):
                continue
            fin = check_statement(pdf)
            struct = analyze_pdf(pdf)
            forgery = record.get("forgery") or {}
            row = {
                "file": pdf.name,
                "label": record["label"],
                "bank_id": record.get("bank_id", ""),
                "variant": forgery.get("variant", "genuine"),
                "save_mode": forgery.get("save_mode", ""),
                "font_strategy": forgery.get("font_strategy", ""),
                "financial": bool(fin.findings),
                "structure": struct.suspicious,
                "financial_abstained": fin.parsed_rows == 0,
                "structure_abstained": not struct.text_layer,
                "financial_score": round(fin.score, 4),
                "structure_score": struct.score,
                "financial_checks": ";".join(sorted({f.check for f in fin.findings})),
                "structure_checks": ";".join(sorted({f.check for f in struct.findings})),
            }
            row["either"] = row["financial"] or row["structure"]
            rows.append(row)
            locations = struct.locations()
            for e in record.get("edits", []):
                edits_total += 1
                edits_found += any(loc["page"] == e["page"] and _overlaps(loc["bbox"], e["new_bbox"])
                                   for loc in locations)
    if not rows:
        raise SystemExit("No statements found")

    by_variant = defaultdict(list)
    for r in rows:
        by_variant[r["variant"]].append(r)
    summary = {
        "tag": args.tag,
        "counts": {"genuine": sum(r["label"] == "genuine" for r in rows),
                   "forged": sum(r["label"] == "forged" for r in rows)},
        "overall": {s: _metrics(rows, s) for s in SIGNALS},
        "flag_rate_by_variant": {
            v: {"n": len(rs), **{s: round(sum(r[s] for r in rs) / len(rs), 4) for s in SIGNALS}}
            for v, rs in sorted(by_variant.items())
        },
        "abstention_rate": {
            "financial": round(sum(r["financial_abstained"] for r in rows) / len(rows), 4),
            "structure": round(sum(r["structure_abstained"] for r in rows) / len(rows), 4),
        },
        "by_bank": {
            bank: {
                "n": len(rs),
                **{f"{s}_recall": _metrics(rs, s)["recall"] for s in SIGNALS},
                **{f"{s}_fpr": _metrics(rs, s)["false_positive_rate"] for s in SIGNALS},
            }
            for bank, rs in sorted(_group(rows, "bank_id").items())
        },
        "structure_edit_localisation_recall": (round(edits_found / edits_total, 4)
                                               if edits_total else None),
        "edits_total": edits_total,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"signals_{args.tag}"
    with open(f"{stem}_per_file.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    Path(f"{stem}_summary.json").write_text(json.dumps(summary, indent=2))

    def pct(x):
        return "n/a" if x is None else f"{x:.3f}"

    lines = [
        f"# Rule-based signals — {args.tag}",
        "",
        f"Genuine: {summary['counts']['genuine']} · Forged: {summary['counts']['forged']}",
        "",
        "| Metric | Financial | PDF structure | Either |",
        "| --- | --- | --- | --- |",
    ]
    for metric in ("precision", "recall", "f1", "accuracy", "false_positive_rate"):
        label = metric.replace("_", " ").capitalize()
        lines.append(f"| {label} | " + " | ".join(pct(summary["overall"][s][metric])
                                                   for s in SIGNALS) + " |")
    ab = summary["abstention_rate"]
    lines.append(f"| Abstained (unreadable) | {ab['financial']:.3f} | {ab['structure']:.3f} | — |")
    lines += ["", "| Variant | n | Financial | PDF structure | Either |",
              "| --- | --- | --- | --- | --- |"]
    for v, d in summary["flag_rate_by_variant"].items():
        lines.append(f"| {v} | {d['n']} | " + " | ".join(f"{d[s]:.1%}" for s in SIGNALS) + " |")
    if len(summary["by_bank"]) > 1:
        lines += ["", "| Bank | n | Financial recall | Structure recall | Either recall | Either FPR |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for bank, d in summary["by_bank"].items():
            lines.append(f"| {bank} | {d['n']} | {pct(d['financial_recall'])} | "
                         f"{pct(d['structure_recall'])} | {pct(d['either_recall'])} | "
                         f"{pct(d['either_fpr'])} |")
    if summary["structure_edit_localisation_recall"] is not None:
        recall = summary["structure_edit_localisation_recall"]
        note = f"PDF-structure edit localisation recall: {recall:.1%} of {edits_total} edited values"
        lines += ["", note]
    Path(f"{stem}_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
