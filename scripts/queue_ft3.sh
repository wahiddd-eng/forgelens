#!/usr/bin/env bash
# Third overnight queue on two GPUs: more varied training forgeries, and ft3 trained on them.
#
# ft1 learned our forgeries (SDXL retouching, one JPEG setting) rather than AI editing in
# general: on AIForge-Doc its F1 fell from 0.176 to 0.026. ft3 is trained, from the released
# weights, on the ft1 data plus a second set that varies what ft1 always saw the same way:
#   - three inpainting models (SDXL, SD 2, SD 1.5) instead of SDXL alone, strength up to 0.9;
#   - page JPEG quality 60-95 instead of always 85, for genuine and forged pages alike
#     (so quality itself says nothing about forgery).
#
#   lane A: varied genuine and spliced pages (CPU) -> inpainting, half 1 -> train ft3
#           -> ft3 on the held-out test set
#   lane B: inpainting, half 2 -> (once ft3 is trained) ft3 on AIForge-Doc and DocTamper
#
#   bash scripts/queue_ft3.sh 2>&1 | tee ~/night3.log
#
# Logs: ~/night3_<job>.log. Safe to run again: finished work is skipped or resumed.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
C="${CONFIG:-configs/adcdnet_eval.yaml}"
D="${DATA:-$HOME/forgelens-data/synthetic_v4}"
T="${TEST:-$HOME/forgelens-data/synthetic_test}"
STEPS="${STEPS:-10000}"
Q="60 70 80 90 95"
MODELS="diffusers/stable-diffusion-xl-1.0-inpainting-0.1 stabilityai/stable-diffusion-2-inpainting stable-diffusion-v1-5/stable-diffusion-inpainting"
V2="$D/forged_image_v2"
HALF_A="$V2/inpaint/.half-a-done"
TRAINED="$HOME/forgelens-runs-ft3.done"

say() { echo "$(date '+%F %H:%M') $*"; }
job() {  # wait for a free GPU (locked pick, held 2 min after starting), run, report
    local name=$1; shift
    say "$name: waiting for a free GPU"
    (
        flock 9
        G=$(bash scripts/free_gpus.sh 1 --wait 2>/dev/null) || exit 99
        say "$name: started on GPU $G"
        export CUDA_VISIBLE_DEVICES=$G
        "$@" > "$HOME/night3_$name.log" 2>&1 &
        pid=$!
        sleep 120
        flock -u 9
        wait $pid
    ) 9>"$HOME/.forgelens_gpu.lock"
    local rc=$?
    say "$name: finished, exit $rc"
    return $rc
}

inpaint() {  # inpaint <shard>
    # shellcheck disable=SC2086
    python scripts/forge_image_edits.py --genuine "$D/genuine" --out "$V2/inpaint" \
        --method inpaint --shard "$1" --seed 2 --tag _v2 --model $MODELS \
        --strength 0.45 0.6 0.75 0.9 --jpeg-quality $Q --preview 6
}

lane_a() {
    say "varied genuine pages and splices (CPU)"
    # shellcheck disable=SC2086
    python scripts/launder_pdfs.py --input "$D/genuine" --out "$D/genuine_raster_mixq" \
        --method raster --jpeg-quality $Q --tag _mixq > "$HOME/night3_mixq.log" 2>&1 \
        || { say "genuine_raster_mixq failed: see ~/night3_mixq.log"; }
    # shellcheck disable=SC2086
    python scripts/forge_image_edits.py --genuine "$D/genuine" --out "$V2/splice" \
        --method splice --seed 2 --tag _v2 --jpeg-quality $Q > "$HOME/night3_splice.log" 2>&1 \
        || { say "splice v2 failed: see ~/night3_splice.log"; }
    job inpaint-a inpaint 0/2; touch "$HALF_A"
    until [[ -f $V2/inpaint/.half-b-done ]]; do sleep 60; done
    say "both halves of the varied inpainted set are done"
    job train-ft3 bash scripts/with_backup.sh python scripts/train_adcdnet.py --config "$C" \
        --data "$D/genuine_raster" "$D/genuine_raster_mixq" "$D/forged_image" "$V2" \
        --tag ft3 --steps "$STEPS" --resume
    best=$(ls experiments/checkpoints/train_ft3/ckpt/Step*_Score*.pth 2>/dev/null \
           | sed 's/.*_Score\(.*\)\.pth/\1 &/' | sort -n | tail -1 | cut -d' ' -f2)
    [[ -n $best ]] || { say "no ft3 checkpoint"; touch "$TRAINED.failed"; return 1; }
    sed "s|^ckpt:.*|ckpt: $PWD/$best|" "$C" > configs/adcdnet_ft3.yaml
    touch "$TRAINED"
    job test-ft3 python scripts/eval_adcdnet_pages.py --config "$C" --ckpt "$best" \
        --tag test-ft3 --data "$T/genuine_raster" "$T/forged_raster" "$T/forged_image" \
        --save-maps 20 --resume
}

lane_b() {
    mkdir -p "$V2/inpaint"
    job inpaint-b inpaint 1/2; touch "$V2/inpaint/.half-b-done"
    until [[ -f $TRAINED && -f configs/adcdnet_ft3.yaml || -f $TRAINED.failed ]]; do sleep 120; done
    [[ -f $TRAINED.failed ]] && return 1
    job aiforge-ft3 python scripts/eval_adcdnet.py --config configs/adcdnet_ft3.yaml \
        --tag dgx-aiforge-ft3 --datasets aiforge --batch-size 8
    job indomain-ft3 python scripts/eval_adcdnet.py --config configs/adcdnet_ft3.yaml \
        --tag dgx-ft3 --datasets in-domain --batch-size 8 --resume
}

mkdir -p "$V2/inpaint"
rm -f "$TRAINED" "$TRAINED.failed" "$HALF_A" "$V2/inpaint/.half-b-done" configs/adcdnet_ft3.yaml
say "queue: varied forgeries into $V2, then ft3 ($STEPS steps)"
lane_a & a=$!
sleep 5
lane_b & b=$!
wait $a; wait $b
say "ALL DONE"
