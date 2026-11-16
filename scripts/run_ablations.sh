#!/usr/bin/env bash
# Ablations (H2), CPU only: fusion with each signal left out in turn, and each signal alone
# with the image model, on the held-out test set. Uses the inputs of the "-plus" fusion run
# (image model, released model, OCR arithmetic, rule-based signals).
#
#   bash scripts/run_ablations.sh            # image model ft4
#   MODEL=ft1 bash scripts/run_ablations.sh
#
# Results: experiments/results/ablations_test-<model>.md, and one fusion_ folder per run.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
MODEL="${MODEL:-ft4}"
R=experiments/results
pages=("$R"/adcdnet_pages_test-$MODEL*/pages.csv)
released=("$R"/adcdnet_pages_test-released*/pages.csv)
ocr=("$R"/ocr_financial_test*.csv)
[[ -f ${pages[0]} && -f $R/signals_test_per_file.csv ]] || { echo "run run_fusion.sh first"; exit 1; }
args=(--signals $R/signals_test_per_file.csv --image "${pages[@]}")
[[ -f ${released[0]} ]] && args+=(--released "${released[@]}")
[[ -f ${ocr[0]} ]] && args+=(--ocr "${ocr[@]}")
ALL="image image_released financial structure template ocr_financial"

run() {  # run <tag> <excluded signals...>
    local tag=$1; shift
    if (( $# )); then
        python scripts/fuse_signals.py "${args[@]}" --tag "$tag" --exclude "$@" > /dev/null
    else
        python scripts/fuse_signals.py "${args[@]}" --tag "$tag" > /dev/null
    fi || echo "  $tag failed" >&2
}

tags=("abl-$MODEL-all")
run "abl-$MODEL-all"
for s in $ALL; do  # leave one out
    run "abl-$MODEL-no-$s" $s; tags+=("abl-$MODEL-no-$s")
done
for s in financial structure template ocr_financial; do  # image model plus one signal
    others=$(for o in $ALL; do [[ $o != image && $o != "$s" ]] && echo $o; done)
    # shellcheck disable=SC2086
    run "abl-$MODEL-image+$s" $others; tags+=("abl-$MODEL-image+$s")
done

python - "$R" "$MODEL" "${tags[@]}" <<'PY'
import json, sys
from pathlib import Path
R, model, tags = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
lines = [f"# Ablations: fusion on the held-out test set, image model {model}", "",
         "Gradient boosting, out-of-fold by source statement, one threshold for all inputs. "
         "Caught: share of all forgeries; false alarms fixed at 1% / 5% of genuine statements.", "",
         "| Run | Caught @1% | Caught @5% | AUC |", "| --- | ---: | ---: | ---: |"]
for t in tags:
    f = R / f"fusion_{t}" / "summary.json"
    if not f.exists():
        lines.append(f"| {t} | failed | | |"); continue
    o = json.loads(f.read_text())["overall"]["fused_boosting"]
    name = t.removeprefix(f"abl-{model}-").replace("no-", "without ").replace("image+", "image + ")
    lines.append(f"| {name} | {o['caught@0.01']:.0%} | {o['caught@0.05']:.0%} | {o['auc']:.3f} |")
out = R / f"ablations_test-{model}.md"
out.write_text("\n".join(lines) + "\n")
print("\n".join(lines))
PY
