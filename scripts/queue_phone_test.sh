#!/usr/bin/env bash
# Phone laundering: are statements still caught after a screenshot, or a screenshot sent
# over WhatsApp? Lenders' staff often receive statements that way, and the test set has
# neither.
#
# From the held-out test set (never trained on), 500 statements per laundering: 100 genuine
# (10 per bank), 100 each of PDF edits, rebuilds, splices and AI inpaintings, each made into
#   screenshot  1080 px wide PNG, as a phone screenshot of the page;
#   whatsapp    that screenshot recompressed as WhatsApp does (JPEG quality 60-80).
# Then ft4 and the OCR arithmetic on them (two GPUs, one per laundering), the rule-based
# signals (CPU), and the fusion model fitted on the test set, applied unchanged at its own
# thresholds: do its 1% false alarms and its catch rates hold?
#
#   bash scripts/queue_phone_test.sh 2>&1 | tee ~/night9.log      # about 1.5 hours
#
# Results: experiments/results/fusion_applied_phone-ft4.md (and per-signal runs).

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
C="${CONFIG:-configs/adcdnet_eval.yaml}"
T="${TEST:-$HOME/forgelens-data/synthetic_test}"
P="$T/phone"
R=experiments/results

say() { echo "$(date '+%F %H:%M') $*"; }
job() {  # wait for a free GPU (locked pick, held 2 min after starting), run, report
    local name=$1; shift
    say "$name: waiting for a free GPU"
    (
        flock 9
        G=$(bash scripts/free_gpus.sh 1 --wait 2>/dev/null) || exit 99
        say "$name: started on GPU $G"
        export CUDA_VISIBLE_DEVICES=$G
        "$@" > "$HOME/night9_$name.log" 2>&1 &
        pid=$!
        sleep 120
        flock -u 9
        wait $pid
    ) 9>"$HOME/.forgelens_gpu.lock"
    local rc=$?
    say "$name: finished, exit $rc"
    return $rc
}
best_of() {
    ls experiments/checkpoints/train_$1/ckpt/Step*_Score*.pth 2>/dev/null \
        | sed 's/.*_Score\(.*\)\.pth/\1 &/' | sort -n | tail -1 | cut -d' ' -f2
}
ft4=$(best_of ft4)
[[ -n $ft4 ]] || { say "no ft4 checkpoint"; exit 1; }
[[ -f $R/signals_test_per_file.csv ]] || { say "run scripts/run_fusion.sh first"; exit 1; }

say "queue: phone laundering of the test set (screenshot, whatsapp)"
for m in screenshot whatsapp; do
    [[ -f $P/genuine_$m/.complete ]] || { python scripts/launder_pdfs.py --input "$T/genuine" \
        --out "$P/genuine_$m" --method $m --per-folder 10 && touch "$P/genuine_$m/.complete"; } || exit 1
    [[ -f $P/forged_$m/digital/.complete ]] || { python scripts/launder_pdfs.py --input "$T/forged" \
        --out "$P/forged_$m/digital" --method $m --per-folder 100 \
        && touch "$P/forged_$m/digital/.complete"; } || exit 1
    [[ -f $P/forged_$m/image/.complete ]] || { python scripts/launder_pdfs.py --input "$T/forged_image" \
        --out "$P/forged_$m/image" --method $m --per-folder 100 \
        && touch "$P/forged_$m/image/.complete"; } || exit 1
done
say "laundered: $(find "$P" -name '*.pdf' | wc -l) PDFs"

lane() {  # lane <method>: image model, then OCR arithmetic, on one GPU
    local m=$1
    job "image-$m" python scripts/eval_adcdnet_pages.py --config "$C" --ckpt "$ft4" \
        --tag "phone-$m-ft4" --data "$P/genuine_$m" "$P/forged_$m" --resume
    job "ocr-$m" python scripts/eval_ocr_financial.py --tag "phone-$m" \
        --data "$P/genuine_$m" "$P/forged_$m" --resume
}
lane screenshot &
a=$!
sleep 150
lane whatsapp &
b=$!

say "rule-based signals (CPU)"
python scripts/eval_signals.py --templates experiments/templates_dgx.json --tag phone --out $R \
    --genuine "$P/genuine_screenshot" "$P/genuine_whatsapp" \
    --forged "$P/forged_screenshot" "$P/forged_whatsapp" > "$HOME/night9_signals.log" 2>&1 \
    || say "signals failed: see ~/night9_signals.log"
say "fusion model for applying: test set, ft4 + OCR (no released model)"
python scripts/fuse_signals.py --signals $R/signals_test_per_file.csv \
    --image $R/adcdnet_pages_test-ft4*/pages.csv --ocr $R/ocr_financial_test.csv \
    --exclude image_released --tag test-ft4-ocr > "$HOME/night9_fusion.log" 2>&1 \
    || say "fusion failed: see ~/night9_fusion.log"
wait $a; wait $b

say "applying it to the phone statements"
python scripts/apply_fusion.py --model $R/fusion_test-ft4-ocr/model.pkl \
    --signals $R/signals_phone_per_file.csv \
    --image $R/adcdnet_pages_phone-*-ft4/pages.csv --ocr $R/ocr_financial_phone-*.csv \
    --tag phone-ft4
say "ALL DONE"
