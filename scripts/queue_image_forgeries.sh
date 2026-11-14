#!/usr/bin/env bash
# Overnight queue on two GPUs (the DGX allows at most 2, whichever are free):
#
#   lane A: AI-inpainted forgeries, half 1  ->  released ADCD-Net on the image forgeries
#   lane B: AI-inpainted forgeries, half 2  ->  fine-tune ADCD-Net (once both halves exist)
#
# Before running: the spliced forgeries and an inpainting smoke test (see docs/dgx.md,
# "Image forgeries and fine-tuning"). Run inside tmux:
#
#   bash scripts/queue_image_forgeries.sh 2>&1 | tee ~/night.log
#
# Each job waits for a free GPU. Logs: ~/night_<job>.log. Safe to run again: finished
# forgeries are skipped, and training resumes from its newest checkpoint.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
D="${DATA:-$HOME/forgelens-data/synthetic_v4}"
C="${CONFIG:-configs/adcdnet_eval.yaml}"
STEPS="${STEPS:-10000}"
TAG="${TAG:-ft1}"
MARK="$D/forged_image/inpaint/.half-a-done"

say() { echo "$(date '+%F %H:%M') $*"; }

# job <name> <command...>: wait for a free GPU, run, return the exit status. The pick is
# locked, and held for two minutes after starting, so the two lanes never take the same GPU.
job() {
    local name=$1; shift
    say "$name: waiting for a free GPU"
    (
        flock 9
        G=$(bash scripts/free_gpus.sh 1 --wait 2>/dev/null) || exit 99
        say "$name: started on GPU $G"
        export CUDA_VISIBLE_DEVICES=$G  # this subshell only
        "$@" > "$HOME/night_$name.log" 2>&1 &
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
    python scripts/forge_image_edits.py --genuine "$D/genuine" --out "$D/forged_image/inpaint" \
        --method inpaint --shard "$1"
}

lane_a() {
    job inpaint-a inpaint 0/2; touch "$MARK"  # lane B trains on whatever exists
    job eval-image python scripts/eval_adcdnet_pages.py --config "$C" --tag image-v4 \
        --data "$D/genuine_raster" "$D/forged_image" --save-maps 20 --resume
}

lane_b() {
    job inpaint-b inpaint 1/2 || return 1
    until [[ -f $MARK ]]; do sleep 60; done
    say "both halves of the inpainted set are done"
    job train-$TAG bash scripts/with_backup.sh python scripts/train_adcdnet.py --config "$C" \
        --data "$D/genuine_raster" "$D/forged_image" --tag "$TAG" --steps "$STEPS" --resume
}

mkdir -p "$(dirname "$MARK")" && rm -f "$MARK"
say "queue: data $D, training $STEPS steps as '$TAG'"
lane_a & a=$!
sleep 5
lane_b & b=$!
wait $a; wait $b
say "ALL DONE"
