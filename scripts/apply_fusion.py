#!/usr/bin/env python
"""Score new statements with a saved fusion model, at the thresholds it was fitted with.

The model (``model.pkl`` from ``fuse_signals.py``) was fitted on the held-out test set, with
thresholds that flag 1% and 5% of its genuine statements. Applied unchanged to statements
laundered another way (phone screenshots, WhatsApp), it shows whether those thresholds still
hold: the false-alarm rate on the new genuine statements, and the share of each kind of
forgery still caught.

    python scripts/apply_fusion.py --model experiments/results/fusion_test-ft4-ocr/model.pkl \\
        --signals experiments/results/signals_phone_per_file.csv \\
        --image experiments/results/adcdnet_pages_phone-*-ft4/pages.csv \\
        --ocr experiments/results/ocr_financial_phone-*.csv --tag phone-ft4
"""

from __future__ import annotations

import argparse
import pickle
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forgelens.fusion import join, load_image, load_signals  # noqa: E402
from forgelens.fusion.fuse import apply_final, auc, load_ocr  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--signals", type=Path, nargs="+", required=True)
    p.add_argument("--image", type=Path, nargs="+", required=True)
    p.add_argument("--released", type=Path, nargs="*", default=[])
    p.add_argument("--ocr", type=Path, nargs="*", default=[])
    p.add_argument("--tag", required=True)
    p.add_argument("--out", type=Path, default=Path("experiments/results"))
    return p.parse_args(argv)


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def main(argv=None) -> int:
    args = parse_args(argv)
    final = pickle.loads(args.model.read_bytes())
    statements = join(load_signals(args.signals), load_image(args.image),
                      load_image(args.released) if args.released else None,
                      load_ocr(args.ocr) if args.ocr else None)
    statements = [st for st in statements if st.laundering not in ("none", "raster", "reprint")
                  or args.tag.startswith("all")]
    if not statements:
        print("no statements", file=sys.stderr)
        return 1
    fused = apply_final(final, statements)
    th = final["thresholds"]["fused_boosting"]
    names = [s for s in final["signals"]] + ["fused_boosting"]

    def score(name: str, i: int) -> float | None:
        return fused[i] if name == "fused_boosting" else statements[i].scores.get(name)

    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, st in enumerate(statements):
        groups[("genuine" if not st.forged else st.method, st.laundering)].append(i)

    lines = [f"# Fusion applied unchanged: {args.tag}", "",
             f"Model `{args.model.parent.name}` (fitted on {final['trained_on']} test-set "
             "statements), with its own thresholds: those that flagged 1% / 5% of the test set's "
             "genuine statements. Each cell: share flagged at 1% (5%). A single signal that "
             "abstained counts as not flagged.", "",
             "| Statements | Laundering | n | " + " | ".join(names) + " |",
             "| --- | --- | ---: | " + " | ".join("---:" for _ in names) + " |"]
    for (kind, laundering), idx in sorted(groups.items(), key=lambda kv: (kv[0][0] != "genuine", kv[0])):
        cells = []
        for n in names:
            t = th if n == "fused_boosting" else final["thresholds"].get(n) or {}
            if not t:
                cells.append("–")
                continue
            vals = [score(n, i) for i in idx]
            c1 = sum(v is not None and v > t[0.01] for v in vals) / len(idx)
            c5 = sum(v is not None and v > t[0.05] for v in vals) / len(idx)
            cells.append(f"{pct(c1)} ({pct(c5)})")
        lines.append(f"| {kind} | {laundering} | {len(idx)} | " + " | ".join(cells) + " |")
    for laundering in sorted({st.laundering for st in statements}):
        g = [fused[i] for i, st in enumerate(statements) if st.laundering == laundering and not st.forged]
        f = [fused[i] for i, st in enumerate(statements) if st.laundering == laundering and st.forged]
        a = auc(g, f)
        if a is not None:
            lines.append(f"\nFused AUC, {laundering}: {a:.3f} (threshold-free: how well genuine and "
                         "forged are separated, whatever the thresholds).")
    text = "\n".join(lines) + "\n"
    out = args.out / f"fusion_applied_{args.tag}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
