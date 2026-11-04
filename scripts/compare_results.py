"""Combine several ``signals_<tag>_summary.json`` files into one robustness table.

Example:
    python scripts/compare_results.py --results experiments/results \
        --tags pdfedit_v1_himalaya pdfedit_v1_himalaya_reprint pdfedit_v1_himalaya_raster \
        --names Original Reprinted Rasterised --out experiments/results/robustness_v1.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SIGNALS = (("financial", "Financial"), ("structure", "PDF structure"), ("either", "Either"))


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
    header = "| Condition | " + " | ".join(n for _, n in SIGNALS) + " | Abstained (fin / struct) |"
    lines = ["# Robustness of rule-based signals to laundering", "",
             "Recall on forgeries (false-positive rate on genuine statements in brackets).", "",
             header, "| --- | --- | --- | --- | --- |"]
    for name, s in zip(names, summaries):
        cells = [f"{_fmt(s['overall'][k]['recall'])} ({_fmt(s['overall'][k]['false_positive_rate'])})"
                 for k, _ in SIGNALS]
        ab = s.get("abstention_rate", {})
        cells.append(f"{_fmt(ab.get('financial'))} / {_fmt(ab.get('structure'))}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    variants = sorted(summaries[0]["flag_rate_by_variant"])
    lines += ["", "Flag rate of the combined signals (either) by forgery type:", "",
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
