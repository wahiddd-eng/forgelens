"""Fuse the rule-based and image signals per statement, and compare with each signal alone.

    # rule-based signals on the test set (CPU)
    python scripts/eval_signals.py --templates experiments/templates_dgx.json --tag test \\
        --genuine $T/genuine $T/genuine_raster --forged $T/forged $T/forged_raster $T/forged_image
    # fuse with the image model's pages.csv (one or more runs of the same model)
    python scripts/fuse_signals.py --signals experiments/results/signals_test_per_file.csv \\
        --image experiments/results/adcdnet_pages_test-ft1/pages.csv --tag test-ft1

Writes ``<out>/fusion_<tag>/``: ``statements.csv`` (every statement's scores, fused ones
out-of-fold), ``summary.json``, ``summary.md``, and ``model.pkl`` (the boosting model fitted on
all statements, with the thresholds for 1% and 5% false alarms, for ``eval_real.py``).
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
from pathlib import Path

from forgelens.fusion import evaluate, join, load_image, load_signals, out_of_fold
from forgelens.fusion.fuse import FUSED, SINGLE, fit_final, load_ocr
from forgelens.utils import run_info

NAMES = {"image": "Image (ADCD-Net)", "image_released": "Image (released)",
         "ocr_financial": "OCR arithmetic", "financial": "Financial", "structure": "PDF structure",
         "template": "Template", "fused_logistic": "Fused (logistic)",
         "fused_boosting": "Fused (boosting)"}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--signals", type=Path, nargs="+", required=True,
                   help="per-file CSV(s) from eval_signals.py")
    p.add_argument("--image", type=Path, nargs="*", default=[],
                   help="pages.csv file(s) from eval_adcdnet_pages.py, all from one model")
    p.add_argument("--released", type=Path, nargs="*", default=[],
                   help="pages.csv of the released ADCD-Net on the same files (a second image "
                        "signal)")
    p.add_argument("--ocr", type=Path, nargs="*", default=[],
                   help="CSV(s) from eval_ocr_financial.py (arithmetic read from page images)")
    p.add_argument("--tag", required=True)
    p.add_argument("--out", type=Path, default=Path("experiments/results"))
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--exclude", nargs="+", default=[], choices=SINGLE,
                   help="leave these signals out (e.g. template, which only knows our "
                        "fictional banks, for a model to apply to real statements)")
    return p.parse_args(argv)


def pct(x) -> str:
    return "–" if x is None else f"{100 * x:.0f}%"


def markdown(result: dict, args, missing_image: int) -> str:
    names = result["signals"]
    c = result["counts"]
    head = " | ".join(NAMES[n] for n in names)
    lines = [f"# Fusion: {args.tag}", "",
             (f"{c['genuine']} genuine statements "
             f"({', '.join(f'{v} {k}' for k, v in sorted(c['genuine_by_laundering'].items()))}) "
             f"and {c['forged']} forged. One threshold for every input, set so that 1% of all "
             "genuine statements are flagged; the table gives the share of each kind of forgery "
             "caught at it. Fused scores are out-of-fold (folds grouped by source statement). "
             "A signal that abstains or was not run counts as no evidence (score 0.5)."), ""]
    if missing_image:
        lines += [f"The image model was not run on {missing_image} statements (missing there).", ""]
    lines += [f"| Forgery | Laundering | n | {head} |",
              "| --- | --- | ---: | " + " | ".join("---:" for _ in names) + " |"]
    for kind, row in sorted(result["by_kind"].items()):
        method, laundering = kind.split("|")
        lines.append(f"| {method} | {laundering} | {row['n']} | "
                     + " | ".join(pct(row.get(f"{n}@0.01")) for n in names) + " |")
    o = result["overall"]
    lines.append("| **All forgeries** | | " + str(c["forged"]) + " | "
                 + " | ".join(f"**{pct(o[n]['caught@0.01'])}**" for n in names) + " |")
    lines.append("| False alarms | | " + str(c["genuine"]) + " | "
                 + " | ".join(pct(o[n]["false_alarms@0.01"]) for n in names) + " |")
    lines.append("| AUC | | | " + " | ".join(
        "–" if o[n]["auc"] is None else f"{o[n]['auc']:.3f}" for n in names) + " |")
    lines += ["", "At 5% false alarms, all forgeries: " + ", ".join(
        f"{NAMES[n]} {pct(o[n]['caught@0.05'])}" for n in names) + "."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    args = parse_args(argv)
    statements = join(load_signals(args.signals), load_image(args.image),
                      load_image(args.released) if args.released else None,
                      load_ocr(args.ocr) if args.ocr else None)
    for st in statements:
        for s in args.exclude:
            st.scores[s] = None
        if "image" in args.exclude:
            st.image_area = None
    if not statements or all(st.forged for st in statements) or not any(st.forged for st in statements):
        print("Need genuine and forged statements", file=sys.stderr)
        return 1
    fused = out_of_fold(statements, args.folds)
    result = evaluate(statements, fused)
    result["run"] = run_info(vars(args))
    missing_image = sum(st.scores.get("image") is None for st in statements)

    out = args.out / f"fusion_{args.tag}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "statements.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "label", "method", "laundering", "bank_id", *SINGLE,
                    "image_area", *FUSED])
        for i, st in enumerate(statements):
            w.writerow([st.file, st.label, st.method, st.laundering, st.bank,
                        *("" if st.scores.get(s) is None else st.scores[s] for s in SINGLE),
                        "" if st.image_area is None else st.image_area,
                        *(round(fused[f][i], 5) for f in FUSED)])
    (out / "summary.json").write_text(json.dumps(result, indent=2, default=str))
    final = fit_final(statements, fused)
    with open(out / "model.pkl", "wb") as fh:  # for eval_real.py
        pickle.dump(final, fh)
    text = markdown(result, args, missing_image)
    (out / "summary.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
