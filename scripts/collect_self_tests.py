"""Summarise the result files that friends send back from ``self_test.py`` / the Colab notebook.

Each file holds one genuine statement's signal scores (no statement content). This gives the
same false-alarm summary as ``eval_real.py``, for the signals the self-test runs (financial,
PDF structure, OCR arithmetic), at the thresholds of a fusion model fitted on the synthetic
test set with those signals only:

    python scripts/fuse_signals.py --signals experiments/results/signals_test_per_file.csv \\
        --ocr experiments/results/ocr_financial_test.csv --exclude template --tag test-selftest
    python scripts/collect_self_tests.py results_from_friends/*.json \\
        --fusion experiments/results/fusion_test-selftest/model.pkl \\
        --summary experiments/results/real_selftest_<date>.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("results", type=Path, nargs="+")
    p.add_argument("--fusion", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    args = p.parse_args(argv)

    from forgelens.fusion import Statement

    spec = importlib.util.spec_from_file_location("eval_real", REPO / "scripts" / "eval_real.py")
    eval_real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eval_real)

    final = pickle.loads(args.fusion.read_bytes())
    unusable = [s for s in final["signals"] if s not in ("financial", "structure", "ocr_financial")]
    if unusable:
        raise SystemExit(f"The fusion model uses {', '.join(unusable)}, which the self-test does "
                         "not run: fit one with --exclude template image image_released")
    rows, statements, seen = [], [], set()
    for path in args.results:
        r = json.loads(path.read_text())
        if r.get("id") in seen:
            continue  # the same result sent twice
        seen.add(r.get("id"))
        sig = r.get("signals", {})
        st = Statement(path.name, "genuine", "real", "none", r.get("bank", "unknown"), r["id"])
        for name in ("financial", "structure", "ocr_financial"):
            s = sig.get(name) or {}
            st.scores[name] = None if s.get("abstained", True) or "score" not in s else s["score"]
        checks = set()
        for name in ("financial", "structure"):
            checks |= set((sig.get(name) or {}).get("checks_fired", []))
        rows.append({"id": r["id"], "bank": r.get("bank", "unknown"), "error": "",
                     "checks": ";".join(sorted(checks)), "image_only": r.get("image_only")})
        statements.append(st)
    summary = eval_real.summarise(rows, statements, final, image_signal=False)
    summary["source"] = "self-test results"
    names = [n for n in final["signals"]] + ["fused_boosting"]
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=list))
    text = eval_real.markdown(summary, names)
    args.summary.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
