#!/usr/bin/env python
"""Which forgeries fusion misses, and whether any trace of them is left: the ceiling.

Reads a fusion run's ``statements.csv`` and the forgery labels (the JSON beside each test
PDF), sets the fused score's threshold at 1% (and 5%) of genuine statements, and breaks the
caught share down by what the forger did: method, operation or variant, whether every
balance was kept consistent, and laundering. A rasterised forgery whose balances all agree
leaves no PDF trace and no arithmetic error, so only the image model or the layout could
see it; those groups bound what any signal can catch.

    python scripts/explain_misses.py --run experiments/results/fusion_test-ft4-plus \\
        --data ~/forgelens-data/synthetic_test
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run", type=Path, required=True, help="a fusion_<tag> folder")
    p.add_argument("--data", type=Path, required=True, help="the test set (for the labels)")
    p.add_argument("--score", default="fused_boosting")
    return p.parse_args(argv)


def threshold(genuine: list[float], fpr: float) -> float:
    from forgelens.fusion.fuse import threshold_at
    return threshold_at(genuine, fpr)


def main(argv=None) -> int:
    args = parse_args(argv)
    labels = {}
    for j in args.data.expanduser().rglob("*.json"):
        try:
            rec = json.loads(j.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if rec.get("label") in ("genuine", "forged"):
            labels[j.with_suffix(".pdf").name] = rec
    rows = list(csv.DictReader(open(args.run / "statements.csv", newline="")))
    genuine = [float(r[args.score]) for r in rows if r["label"] == "genuine"]
    t1, t5 = threshold(genuine, 0.01), threshold(genuine, 0.05)

    groups = defaultdict(lambda: [0, 0, 0])  # n, caught @1%, caught @5%
    unlabelled = 0
    for r in rows:
        if r["label"] != "forged":
            continue
        rec = labels.get(Path(r["file"]).name)
        if rec is None:
            unlabelled += 1
            continue
        f = rec.get("forgery") or {}
        what = f.get("operation") or f.get("method")
        consistent = "balances consistent" if f.get("balance_consistent") else "balances broken"
        key = (r["method"], what, consistent, r["laundering"])
        s = float(r[args.score])
        g = groups[key]
        g[0] += 1
        g[1] += s > t1
        g[2] += s > t5

    total = sum(g[0] for g in groups.values())
    lines = [f"# What fusion misses: {args.run.name}", "",
             f"Score `{args.score}`, thresholds at 1% and 5% of {len(genuine)} genuine "
             f"statements. {total} forgeries with labels"
             + (f" ({unlabelled} without)" if unlabelled else "") + ".", "",
             "| Method | Operation | Balances | Laundering | n | Caught @1% | Caught @5% |",
             "| --- | --- | --- | --- | ---: | ---: | ---: |"]
    for key, (n, c1, c5) in sorted(groups.items()):
        lines.append(f"| {' | '.join(key)} | {n} | {c1 / n:.0%} | {c5 / n:.0%} |")
    # the rasterised forgeries with every balance consistent: no PDF trace, no arithmetic error
    blind = [k for k in groups if k[3] != "none" and k[2] == "balances consistent"
             and k[0] in ("pdf_edit", "rebuild")]
    nb = sum(groups[k][0] for k in blind)
    caught = sum(groups[k][1] for k in groups)
    lines += ["", f"All forgeries: {caught / total:.0%} caught at 1%. "
              f"Rasterised PDF edits and rebuilds with consistent balances: {nb} "
              f"({nb / total:.0%}); only pixels or layout could betray them. "
              f"Of the other {total - nb}, fusion catches "
              f"{(caught - sum(groups[k][1] for k in blind)) / max(1, total - nb):.0%} at 1%."]
    text = "\n".join(lines) + "\n"
    (args.run / "misses.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
