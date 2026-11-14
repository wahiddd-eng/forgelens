#!/usr/bin/env bash
# Second overnight queue on two GPUs, after the first fine-tuning run (ft1):
#
#   lane A: build the held-out test set -> released ADCD-Net on it -> train ft2 with two
#           banks left out (for the unseen-bank test)
#   lane B: ft1 on AIForge-Doc and on DocTamper (in-domain) -> ft1 on the test set, once built
#
#   bash scripts/queue_test_eval.sh 2>&1 | tee ~/night2.log
#
# Logs: ~/night2_<job>.log. Safe to run again (finished work is skipped or resumed).

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
C="${CONFIG:-configs/adcdnet_eval.yaml}"
T="${TEST:-$HOME/forgelens-data/synthetic_test}"
D="${DATA:-$HOME/forgelens-data/synthetic_v4}"
HELD_OUT_BANKS="${HELD_OUT_BANKS:-konark_urban malabar_coastal}"
TESTDATA="$T/genuine_raster $T/forged_raster $T/forged_image"

say() { echo "$(date '+%F %H:%M') $*"; }
job() {  # as in queue_image_forgeries.sh: wait for a free GPU (locked pick), run, report
    local name=$1; shift
    say "$name: waiting for a free GPU"
    (
        flock 9
        G=$(bash scripts/free_gpus.sh 1 --wait 2>/dev/null) || exit 99
        say "$name: started on GPU $G"
        export CUDA_VISIBLE_DEVICES=$G
        "$@" > "$HOME/night2_$name.log" 2>&1 &
        pid=$!
        sleep 120
        flock -u 9
        wait $pid
    ) 9>"$HOME/.forgelens_gpu.lock"
    local rc=$?
    say "$name: finished, exit $rc"
    return $rc
}

# The best ft1 checkpoint (highest validation F1) and a config that points at it.
BEST=$(ls experiments/checkpoints/train_ft1/ckpt/Step*_Score*.pth 2>/dev/null \
       | sed 's/.*_Score\(.*\)\.pth/\1 &/' | sort -n | tail -1 | cut -d' ' -f2)
[[ -n $BEST ]] || { say "no ft1 checkpoint found"; exit 1; }
sed "s|^ckpt:.*|ckpt: $PWD/$BEST|" "$C" > configs/adcdnet_ft1.yaml
mkdir -p "$T" && rm -f "$T/.failed"
say "queue: ft1 = $BEST; test set $T; ft2 leaves out $HELD_OUT_BANKS"

lane_a() {
    job testset bash scripts/make_test_set.sh "$T" || { touch "$T/.failed"; return 1; }
    job test-released python scripts/eval_adcdnet_pages.py --config "$C" --tag test-released \
        --data $TESTDATA --save-maps 20 --resume
    job train-ft2 bash scripts/with_backup.sh python scripts/train_adcdnet.py --config "$C" \
        --data "$D/genuine_raster" "$D/forged_image" --tag ft2 --steps 10000 \
        --exclude-banks $HELD_OUT_BANKS --resume
}

lane_b() {
    job aiforge-ft1 python scripts/eval_adcdnet.py --config configs/adcdnet_ft1.yaml \
        --tag dgx-aiforge-ft1 --datasets aiforge --batch-size 8
    job indomain-ft1 python scripts/eval_adcdnet.py --config configs/adcdnet_ft1.yaml \
        --tag dgx-ft1 --datasets in-domain --batch-size 8 --resume
    until [[ -f $T/forged_image/inpaint/.complete || -f $T/.failed ]]; do sleep 120; done
    [[ -f $T/.failed ]] && { say "test set failed: see ~/night2_testset.log"; return 1; }
    job test-ft1 python scripts/eval_adcdnet_pages.py --config "$C" --ckpt "$BEST" \
        --tag test-ft1 --data $TESTDATA --save-maps 20 --resume
}

lane_a & a=$!
sleep 5
lane_b & b=$!
wait $a; wait $b
say "ALL DONE"
