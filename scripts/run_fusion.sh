#!/usr/bin/env bash
# Fusion on the held-out test set, CPU only (it can run beside a GPU queue):
#   1. template profiles from the training statements (rendered on this machine);
#   2. the rule-based signals on every test statement;
#   3. fusion with each fine-tuned image model whose test-set run exists.
#
#   bash scripts/run_fusion.sh                # ft1, and ft3/ft4 when their runs exist
#
# Results: experiments/results/fusion_test-<model>/summary.md

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
T="${TEST:-$HOME/forgelens-data/synthetic_test}"
D="${DATA:-$HOME/forgelens-data/synthetic_v4}"
R=experiments/results

[[ -f experiments/templates_dgx.json ]] || python scripts/fit_templates.py \
    --genuine "$D/genuine" --out experiments/templates_dgx.json || exit 1
[[ -f $R/signals_test_per_file.csv ]] || python scripts/eval_signals.py \
    --templates experiments/templates_dgx.json --tag test --out $R \
    --genuine "$T/genuine" "$T/genuine_raster" \
    --forged "$T/forged" "$T/forged_raster" "$T/forged_image" > /dev/null || exit 1
for model in ft1 ft3 ft4; do
    pages=("$R"/adcdnet_pages_test-$model*/pages.csv)  # e.g. test-ft1 and test-ft1-digital
    [[ -f ${pages[0]} ]] || { echo "no test-set run of $model yet: skipped"; continue; }
    echo "==> fusion with $model (${#pages[@]} image run(s))"
    python scripts/fuse_signals.py --signals $R/signals_test_per_file.csv \
        --image "${pages[@]}" --tag "test-$model"
    # the released model as a second image signal, when it was run on the test set
    released=("$R"/adcdnet_pages_test-released*/pages.csv)
    ocr=("$R"/ocr_financial_test*.csv)
    extra=()
    [[ -f ${released[0]} ]] && extra+=(--released "${released[@]}")
    [[ -f ${ocr[0]} ]] && extra+=(--ocr "${ocr[@]}")
    if (( ${#extra[@]} )); then
        echo "==> fusion with $model plus${released:+ the released model}${ocr:+ and OCR arithmetic}"
        python scripts/fuse_signals.py --signals $R/signals_test_per_file.csv \
            --image "${pages[@]}" "${extra[@]}" --tag "test-$model-plus"
    fi
done
