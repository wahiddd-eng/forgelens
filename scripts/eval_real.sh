#!/usr/bin/env bash
# Run ForgeLens on real bank statements on the DGX, then delete them.
#
# Real statements may be on the DGX only in a private folder whose name starts with "real"
# (the Hugging Face backup refuses such folders), only for the length of this run. This
# script refuses any other folder, keeps every output that could show a statement inside that
# folder, saves no page pictures, writes only aggregate numbers to the repository, and
# deletes the folder when it ends, whether the run succeeds or not.
#
#   mkdir -m 700 ~/real_statements                # then copy the PDFs in from the Mac
#   bash scripts/eval_real.sh                      # ~/real_statements, ft4, delete after
#   KEEP=1 bash scripts/eval_real.sh               # keep the folder (e.g. to fix a password)
#
# The folder holds S001.pdf, S002.pdf, ... and statements.tsv (file<TAB>bank<TAB>password).
# Result: experiments/results/real_<date>.md (counts, bank names and file IDs only).

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
R="${1:-$HOME/real_statements}"
MODEL="${MODEL:-ft4}"
DATE=$(date +%Y%m%d-%H%M)

die() { echo "eval_real: $*" >&2; exit 1; }
[[ -d $R ]] || die "$R does not exist"
R=$(cd "$R" && pwd)
[[ $(basename "$R") == real* ]] || die "the folder's name must start with 'real' (the backup skips those)"
[[ $R != "$PWD"* ]] || die "keep real statements outside the repository"
perm=$(stat -c %a "$R")
[[ $perm == 700 ]] || die "$R is readable by others (mode $perm): run chmod 700 $R"
[[ -f $R/statements.tsv ]] || die "$R/statements.tsv is missing (file<TAB>bank<TAB>password per line)"
chmod 600 "$R"/* 2>/dev/null

cleanup() {
    if [[ ${KEEP:-0} == 1 ]]; then
        echo "KEEP=1: $R is NOT deleted. Delete it yourself: rm -rf $R"
    else
        rm -rf "$R" && echo "deleted $R"
    fi
}
trap cleanup EXIT

# The fusion model for real statements: trained on the test set without the template signal
# (which knows only our fictional banks), with the image model's scores.
# Plus the OCR arithmetic signal when it was run on the test set (eval_ocr_financial.py).
F=experiments/results/fusion_test-$MODEL-real/model.pkl
ocr=(experiments/results/ocr_financial_test*.csv)
if [[ ! -f $F ]]; then
    echo "==> fitting the fusion model for real statements (CPU, about a minute)"
    extra=()
    [[ -f ${ocr[0]} ]] && extra+=(--ocr "${ocr[@]}")
    python scripts/fuse_signals.py --signals experiments/results/signals_test_per_file.csv \
        --image experiments/results/adcdnet_pages_test-$MODEL*/pages.csv "${extra[@]}" \
        --tag "test-$MODEL-real" --exclude template image_released > /dev/null \
        || die "fusion fit failed"
fi

CONFIG=configs/adcdnet_$MODEL.yaml
[[ -f $CONFIG ]] || die "$CONFIG is missing (made by the queue that trained $MODEL)"
G=$(bash scripts/free_gpus.sh 1 --wait) || die "no GPU"
echo "==> ForgeLens on $(ls "$R"/*.pdf 2>/dev/null | wc -l) statements, image model $MODEL on GPU $G"
CUDA_VISIBLE_DEVICES=$G python scripts/eval_real.py --folder "$R" --fusion "$F" \
    --config "$CONFIG" --summary "experiments/results/real_$DATE.md" \
    --diagnostics "experiments/results/real_${DATE}_diagnostics.json" \
    --profiles-out "experiments/results/bank_profiles_${DATE}.json"
