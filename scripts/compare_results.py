"""Combine several ``signals_<tag>_summary.json`` files into one robustness table.

Example:
    python scripts/compare_results.py --results experiments/results \
        --tags v3 v3_reprint v3_raster --names Original Reprinted Rasterised \
        --out experiments/results/robustness_v3.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

NAMES = {"financial": "Financial", "structure": "PDF structure", "template": "Template",
         "either": "Any signal"}


def _fmt(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("experiments/results"))
    parser.add_argument("--tags", nargs="+", required=True)
    parser.add_argument("--names", nargs="+", help="display names, one per tag")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    names = args.names or args.tags
    if len(names) != len(args.tags):
        raise SystemExit("--names must have one entry per tag")

    summaries = [json.loads((args.results / f"signals_{t}_summary.json").read_text())
                 for t in args.tags]
    signals = summaries[0].get("signals", ["financial", "structure", "either"])
    base = [s for s in signals if s != "either"]
    lines = ["# Robustness of rule-based signals to laundering", "",
             "Recall on forgeries (false-positive rate on genuine statements in brackets).", "",
             "| Condition | " + " | ".join(NAMES[s] for s in signals) + " | Abstained ("
             + " / ".join(NAMES[s] for s in base) + ") |",
             "| --- | " + " | ".join("---" for _ in signals) + " | --- |"]
    for name, s in zip(names, summaries):
        cells = [f"{_fmt(s['overall'][k]['recall'])} ({_fmt(s['overall'][k]['false_positive_rate'])})"
                 for k in signals]
        ab = s.get("abstention_rate", {})
        cells.append(" / ".join(_fmt(ab.get(k)) for k in base))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    variants = sorted(summaries[0]["flag_rate_by_variant"])
    lines += ["", "Flag rate of any signal by forgery type:", "",
              "| Forgery type | " + " | ".join(names) + " |",
              "| --- | " + " | ".join("---" for _ in names) + " |"]
    for v in variants:
        rates = [s["flag_rate_by_variant"].get(v, {}).get("either") for s in summaries]
        lines.append(f"| {v} | " + " | ".join("n/a" if r is None else f"{r:.0%}" for r in rates)
                     + " |")
    args.out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
