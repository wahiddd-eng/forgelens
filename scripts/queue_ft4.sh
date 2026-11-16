#!/usr/bin/env bash
# Fourth queue on two GPUs: many generated bank layouts, and ft4 trained on them alone.
#
# ft2 lost a large share of its accuracy on bank layouts it had not seen
# (experiments/results/adcdnet_unseen_banks.md): ten layouts are too few. ft4 is trained, from
# the released weights, only on statements of procedurally generated banks (gen_0000 ...,
# src/forgelens/generator/random_banks.py), with the varied forgeries of ft3 (three
# inpainting models, JPEG quality 60-95). It is then tested on the held-out test set, whose
# ten hand-made banks it has never seen: the unseen-layout test, on 200 statements.
#
#   lane A: generated statements, rasterised and spliced (CPU) -> inpainting, half 1
#           -> train ft4 -> ft4 on the held-out test set (hand-made banks, unseen)
#   lane B: inpainting, half 2 -> (once ft4 is trained) ft4 on AIForge-Doc
#
#   bash scripts/queue_ft4.sh 2>&1 | tee ~/night4.log
#
# Logs: ~/night4_<job>.log. Safe to run again: finished work is skipped or resumed.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
C="${CONFIG:-configs/adcdnet_eval.yaml}"
G_DIR="${GEN:-$HOME/forgelens-data/synthetic_gen}"
T="${TEST:-$HOME/forgelens-data/synthetic_test}"
BANKS_FIRST="${BANKS_FIRST:-0}"
BANKS_COUNT="${BANKS_COUNT:-100}"
PER_BANK="${PER_BANK:-4}"
STEPS="${STEPS:-10000}"
Q="60 70 80 85 90 95"
MODELS="diffusers/stable-diffusion-xl-1.0-inpainting-0.1 sd2-community/stable-diffusion-2-inpainting stable-diffusion-v1-5/stable-diffusion-inpainting"
READY="$G_DIR/.genuine-ready"
TRAINED="$G_DIR/.ft4-trained"

say() { echo "$(date '+%F %H:%M') $*"; }
job() {  # wait for a free GPU (locked pick, held 2 min after starting), run, report
    local name=$1; shift
    say "$name: waiting for a free GPU"
    (
        flock 9
        G=$(bash scripts/free_gpus.sh 1 --wait 2>/dev/null) || exit 99
        say "$name: started on GPU $G"
        export CUDA_VISIBLE_DEVICES=$G
        "$@" > "$HOME/night4_$name.log" 2>&1 &
        pid=$!
        sleep 120
        flock -u 9
        wait $pid
    ) 9>"$HOME/.forgelens_gpu.lock"
    local rc=$?
    say "$name: finished, exit $rc"
    return $rc
}
cpu() {  # cpu <name> <command...>: a CPU step, logged like the GPU jobs
    local name=$1; shift
    say "$name (CPU)"
    "$@" > "$HOME/night4_$name.log" 2>&1 || { say "$name failed: see ~/night4_$name.log"; return 1; }
}

inpaint() {  # inpaint <shard>
    # shellcheck disable=SC2086
    python scripts/forge_image_edits.py --genuine "$G_DIR/genuine" \
        --out "$G_DIR/forged_image/inpaint" --method inpaint --shard "$1" --seed 4 \
        --model $MODELS --strength 0.45 0.6 0.75 0.9 --jpeg-quality $Q --preview 6
}

lane_a() {
    if [[ ! -f $READY ]]; then
        cpu genuine python scripts/generate_statements.py --bank generated \
            --generated "$BANKS_FIRST" "$BANKS_COUNT" --count "$PER_BANK" --seed 6000 --months 2 \
            --out "$G_DIR/genuine"  # a few layouts may fail to read back; they are skipped
        # shellcheck disable=SC2086
        cpu raster python scripts/launder_pdfs.py --input "$G_DIR/genuine" \
            --out "$G_DIR/genuine_raster" --method raster --jpeg-quality $Q || return 1
        touch "$READY"
    fi
    # shellcheck disable=SC2086
    cpu splice python scripts/forge_image_edits.py --genuine "$G_DIR/genuine" \
        --out "$G_DIR/forged_image/splice" --method splice --seed 4 --jpeg-quality $Q
    job inpaint-a inpaint 0/2
    until [[ -f $G_DIR/forged_image/inpaint/.half-b-done ]]; do sleep 60; done
    job train-ft4 bash scripts/with_backup.sh python scripts/train_adcdnet.py --config "$C" \
        --data "$G_DIR/genuine_raster" "$G_DIR/forged_image" --tag ft4 --steps "$STEPS" \
        --cache "$HOME/forgelens-data/page_cache_gen" --resume
    best=$(ls experiments/checkpoints/train_ft4/ckpt/Step*_Score*.pth 2>/dev/null \
           | sed 's/.*_Score\(.*\)\.pth/\1 &/' | sort -n | tail -1 | cut -d' ' -f2)
    [[ -n $best ]] || { say "no ft4 checkpoint"; touch "$TRAINED.failed"; return 1; }
    sed "s|^ckpt:.*|ckpt: $PWD/$best|" "$C" > configs/adcdnet_ft4.yaml
    touch "$TRAINED"
    job test-ft4 python scripts/eval_adcdnet_pages.py --config "$C" --ckpt "$best" \
        --tag test-ft4 --data "$T/genuine_raster" "$T/forged_image" --save-maps 20 --resume
}

lane_b() {
    until [[ -f $READY ]]; do sleep 30; done
    mkdir -p "$G_DIR/forged_image/inpaint"
    job inpaint-b inpaint 1/2; touch "$G_DIR/forged_image/inpaint/.half-b-done"
    until [[ -f $TRAINED || -f $TRAINED.failed ]]; do sleep 120; done
    [[ -f $TRAINED.failed ]] && return 1
    job aiforge-ft4 python scripts/eval_adcdnet.py --config configs/adcdnet_ft4.yaml \
        --tag dgx-aiforge-ft4 --datasets aiforge --batch-size 8
}

mkdir -p "$G_DIR"
rm -f "$TRAINED" "$TRAINED.failed" "$G_DIR/forged_image/inpaint/.half-b-done" configs/adcdnet_ft4.yaml
say "queue: $BANKS_COUNT generated banks x $PER_BANK statements into $G_DIR, then ft4 ($STEPS steps)"
lane_a & a=$!
sleep 5
lane_b & b=$!
wait $a; wait $b
say "ALL DONE"
