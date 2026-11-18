#!/usr/bin/env bash
# Follow-up to queue_phone_test.sh: ft4 on the screenshot and WhatsApp copies read at their own
# pixels (--native) instead of re-rendered at 150 DPI, which resamples a 1080 px JPEG and
# smears its 8x8 blocks. Then
#   1. the test-set fusion model applied unchanged, with the native image scores;
#   2. fusion refitted out-of-fold with the phone statements included (what calibrating on
#      such copies would give).
#
#   bash scripts/queue_phone_native.sh 2>&1 | tee ~/night10.log     # about 1-1.5 hours, two GPUs

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
C="${CONFIG:-configs/adcdnet_eval.yaml}"
T="${TEST:-$HOME/forgelens-data/synthetic_test}"
P="$T/phone"
R=experiments/results

say() { echo "$(date '+%F %H:%M') $*"; }
job() {
    local name=$1; shift
    say "$name: waiting for a free GPU"
    (
        flock 9
        G=$(bash scripts/free_gpus.sh 1 --wait 2>/dev/null) || exit 99
        say "$name: started on GPU $G"
        export CUDA_VISIBLE_DEVICES=$G
        "$@" > "$HOME/night10_$name.log" 2>&1 &
        pid=$!
        sleep 120
        flock -u 9
        wait $pid
    ) 9>"$HOME/.forgelens_gpu.lock"
    local rc=$?
    say "$name: finished, exit $rc"
    return $rc
}
ft4=$(ls experiments/checkpoints/train_ft4/ckpt/Step*_Score*.pth | sed 's/.*_Score\(.*\)\.pth/\1 &/' \
      | sort -n | tail -1 | cut -d' ' -f2)
[[ -n $ft4 && -d $P/genuine_whatsapp ]] || { say "run queue_phone_test.sh first"; exit 1; }

say "queue: ft4 on the phone copies at their own pixels"
job image-screenshot-native python scripts/eval_adcdnet_pages.py --config "$C" --ckpt "$ft4" --native \
    --tag phone-screenshot-ft4-native --data "$P/genuine_screenshot" "$P/forged_screenshot" --resume &
a=$!
sleep 150
job image-whatsapp-native python scripts/eval_adcdnet_pages.py --config "$C" --ckpt "$ft4" --native \
    --tag phone-whatsapp-ft4-native --data "$P/genuine_whatsapp" "$P/forged_whatsapp" --resume &
b=$!
wait $a; wait $b

say "1. test-set fusion applied unchanged, native image scores"
python scripts/apply_fusion.py --model $R/fusion_test-ft4-ocr/model.pkl \
    --signals $R/signals_phone_per_file.csv \
    --image $R/adcdnet_pages_phone-*-ft4-native/pages.csv --ocr $R/ocr_financial_phone-*.csv \
    --tag phone-ft4-native
say "2. fusion refitted with the phone statements (out-of-fold)"
python scripts/fuse_signals.py --signals $R/signals_test_per_file.csv $R/signals_phone_per_file.csv \
    --image $R/adcdnet_pages_test-ft4*/pages.csv $R/adcdnet_pages_phone-*-ft4-native/pages.csv \
    --ocr $R/ocr_financial_test.csv $R/ocr_financial_phone-*.csv \
    --exclude image_released --tag test-phone-ft4-native
say "ALL DONE"
