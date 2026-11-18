#!/usr/bin/env bash
# ft6: ft4 taught phone screenshots and WhatsApp copies.
#
# ft4 flags 11-37% of genuine phone copies at the threshold that flags 1% of rasterised
# statements (experiments/results/phone_laundering.md): it never saw a page at a phone's
# resolution or with WhatsApp's compression. ft6 starts from ft4 and trains 6,000 more steps on
# ft4's own pages (100 generated banks, never the test set) plus screenshot and WhatsApp copies
# of the same statements, genuine and forged (forgery labels and masks carry over).
#
#   1. launder the ft4 training statements into screenshots and WhatsApp copies (CPU)
#   2. train ft6 (one GPU, about 3 hours)
#   3. ft6 on the phone test copies, on the rasterised test set (no loss there?) and on
#      AIForge-Doc, two GPUs at a time
#   4. fusion refitted with the phone statements, as for ft4
#
#   bash scripts/queue_ft6.sh 2>&1 | tee ~/night11.log      # about 5 hours

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
C="${CONFIG:-configs/adcdnet_eval.yaml}"
DATA="$HOME/forgelens-data"
G_DIR="$DATA/synthetic_gen"
T="${TEST:-$DATA/synthetic_test}"
P="$T/phone"
R=experiments/results
CACHE="$DATA/page_cache_ft6"
STEPS="${STEPS:-6000}"

say() { echo "$(date '+%F %H:%M') $*"; }
job() {
    local name=$1; shift
    say "$name: waiting for a free GPU"
    (
        flock 9
        G=$(bash scripts/free_gpus.sh 1 --wait 2>/dev/null) || exit 99
        say "$name: started on GPU $G"
        export CUDA_VISIBLE_DEVICES=$G
        "$@" > "$HOME/night11_$name.log" 2>&1 &
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
[[ -n $ft4 && -d $P/genuine_whatsapp ]] || { say "needs ft4 and queue_phone_test.sh first"; exit 1; }

say "queue: ft6 = ft4 + $STEPS steps with phone copies"
for m in screenshot whatsapp; do
    for src in genuine forged_image; do
        out="$G_DIR/phone_$m/$src"
        [[ -f $out/.complete ]] && continue
        python scripts/launder_pdfs.py --input "$G_DIR/$src" --out "$out" --method $m \
            && touch "$out/.complete" || { say "laundering $src ($m) failed"; exit 1; }
    done
done
say "phone training copies: $(find "$G_DIR"/phone_* -name '*.pdf' | wc -l) PDFs"

if [[ ! -f $CACHE/index.json ]]; then  # ft4's pages, hard-linked (no copying, no re-rendering)
    python - "$DATA/page_cache_gen" "$CACHE" <<'EOF' || exit 1
import json, os, sys
from pathlib import Path
src, target = map(Path, sys.argv[1:])
(target / "pages").mkdir(parents=True, exist_ok=True)
for f in (src / "pages").iterdir():
    if not (target / "pages" / f.name).exists():
        os.link(f, target / "pages" / f.name)
(target / "index.json").write_text((src / "index.json").read_text())
print(f"{len(json.loads((src / 'index.json').read_text()))} pages from ft4's cache")
EOF
fi
job train-ft6 bash scripts/with_backup.sh python scripts/train_adcdnet.py --config "$C" \
    --data "$G_DIR/genuine_raster" "$G_DIR/forged_image" \
           "$G_DIR/phone_screenshot/genuine" "$G_DIR/phone_screenshot/forged_image" \
           "$G_DIR/phone_whatsapp/genuine" "$G_DIR/phone_whatsapp/forged_image" \
    --tag ft6 --init "$ft4" --steps "$STEPS" --warmup 200 --cache "$CACHE" --resume
ft6=$(best_of ft6)
[[ -n $ft6 ]] || { say "no ft6 checkpoint"; exit 1; }
sed "s|^ckpt:.*|ckpt: $PWD/$ft6|" "$C" > configs/adcdnet_ft6.yaml

job phone-ft6 bash -c "python scripts/eval_adcdnet_pages.py --config $C --ckpt $ft6 \
        --tag phone-screenshot-ft6 --data $P/genuine_screenshot $P/forged_screenshot --resume && \
    python scripts/eval_adcdnet_pages.py --config $C --ckpt $ft6 \
        --tag phone-whatsapp-ft6 --data $P/genuine_whatsapp $P/forged_whatsapp --resume" &
a=$!
sleep 150
job test-ft6 bash -c "python scripts/eval_adcdnet_pages.py --config $C --ckpt $ft6 \
        --tag test-ft6 --data $T/genuine_raster $T/forged_raster $T/forged_image --resume && \
    python scripts/eval_adcdnet.py --config configs/adcdnet_ft6.yaml --tag dgx-aiforge-ft6 \
        --datasets aiforge --batch-size 8" &
b=$!
wait $a; wait $b

say "fusion refitted with the phone statements (out-of-fold)"
python scripts/fuse_signals.py --signals $R/signals_test_per_file.csv $R/signals_phone_per_file.csv \
    --image $R/adcdnet_pages_test-ft6/pages.csv $R/adcdnet_pages_phone-*-ft6/pages.csv \
    --ocr $R/ocr_financial_test.csv $R/ocr_financial_phone-*.csv \
    --exclude image_released --tag test-phone-ft6
for t in test-ft6 phone-screenshot-ft6 phone-whatsapp-ft6; do
    echo; cat "$R/adcdnet_pages_$t/summary.md" | head -12
done
tail -n 6 "$R/adcdnet_dgx-aiforge-ft6/summary.md"
say "ALL DONE"
