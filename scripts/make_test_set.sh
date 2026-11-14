#!/usr/bin/env bash
# Build the held-out test set: new statements that no model is trained on, with every kind of
# forgery, for the final comparison of the released and the fine-tuned ADCD-Net.
#
#   bash scripts/make_test_set.sh                     # into ~/forgelens-data/synthetic_test
#   COUNT=30 bash scripts/make_test_set.sh /path/to/folder
#
# Build it on the machine that built the training set (the DGX): the generator renders with
# whatever fonts are installed, so a test set made elsewhere would differ in font as well as
# in forgery, and a model could separate the two by that alone.
#
# Makes, from COUNT (default 20) new statements per bank (seeds from SEED, default 5000;
# the training set uses 2000-2029 and the templates 9000-9011):
#   genuine/, forged/{pdf_edit,rebuild}/, genuine_raster/, forged_raster/,
#   forged_image/splice/, forged_image/inpaint/ (needs a GPU; waits for a free one).
# The folder is marked with .heldout, and train_adcdnet.py refuses to train on it.
# Safe to run again: finished steps are skipped, an interrupted step is redone, and the
# inpainting continues where it stopped.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="${1:-$HOME/forgelens-data/synthetic_test}"
COUNT="${COUNT:-20}"
SEED="${SEED:-5000}"
PY="${PYTHON:-python}"
mkdir -p "$D"
touch "$D/.heldout"
hostname > "$D/.built_on"

step() { echo; echo "==> $(date '+%H:%M') $*"; }
run_step() {  # run_step <folder> <command...>: done once its folder has a .complete marker
    local dir=$1; shift
    if [[ -f $dir/.complete ]]; then echo "  already there"; return 0; fi
    rm -rf "$dir"
    "$@" && touch "$dir/.complete" || { echo "  ! this step failed; run the script again"; return 1; }
}

step "genuine statements ($COUNT per bank, seeds from $SEED)"
run_step "$D/genuine" "$PY" "$REPO/scripts/generate_statements.py" --bank all --count "$COUNT" \
    --seed "$SEED" --out "$D/genuine" || exit 1
step "PDF-edit forgeries"
run_step "$D/forged/pdf_edit" "$PY" "$REPO/scripts/forge_pdf_edits.py" --genuine "$D/genuine" \
    --out "$D/forged/pdf_edit" --seed 1 --masks || exit 1
step "rebuilt forgeries"
run_step "$D/forged/rebuild" "$PY" "$REPO/scripts/forge_rebuild.py" --genuine "$D/genuine" \
    --out "$D/forged/rebuild" --seed 1 --masks || exit 1
step "rasterised versions"
run_step "$D/genuine_raster" "$PY" "$REPO/scripts/launder_pdfs.py" --input "$D/genuine" \
    --out "$D/genuine_raster" --method raster || exit 1
run_step "$D/forged_raster" "$PY" "$REPO/scripts/launder_pdfs.py" --input "$D/forged" \
    --out "$D/forged_raster" --method raster --masks || exit 1
step "spliced forgeries"
run_step "$D/forged_image/splice" "$PY" "$REPO/scripts/forge_image_edits.py" --genuine "$D/genuine" \
    --out "$D/forged_image/splice" --method splice --seed 1 || exit 1

step "AI-inpainted forgeries (waits for a free GPU)"
if [[ -f $D/forged_image/inpaint/.complete ]]; then
    echo "  already there"
else
    G=$(bash "$REPO/scripts/free_gpus.sh" 1 --wait) || exit 1
    echo "  on GPU $G"
    CUDA_VISIBLE_DEVICES=$G "$PY" "$REPO/scripts/forge_image_edits.py" --genuine "$D/genuine" \
        --out "$D/forged_image/inpaint" --method inpaint --seed 1 --preview 6 \
        && touch "$D/forged_image/inpaint/.complete" || { echo "  ! inpainting stopped; run again"; exit 1; }
fi

step "done"
for sub in genuine forged genuine_raster forged_raster forged_image/splice forged_image/inpaint; do
    [[ -d $D/$sub ]] && printf '  %-22s %5d PDFs\n' "$sub" "$(find "$D/$sub" -name '*.pdf' | wc -l)"
done
cat <<EOF

Evaluate a model on it (released, then fine-tuned):
  python scripts/eval_adcdnet_pages.py --config configs/adcdnet_eval.yaml --tag test-released \\
      --data $D/genuine_raster $D/forged_raster $D/forged_image --resume
  python scripts/eval_adcdnet_pages.py --config configs/adcdnet_eval.yaml --tag test-ft1 \\
      --ckpt <best checkpoint in experiments/checkpoints/train_ft1/ckpt> \\
      --data $D/genuine_raster $D/forged_raster $D/forged_image --resume
EOF
