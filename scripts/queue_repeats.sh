#!/usr/bin/env bash
# Repeat runs: the ft4 -> ft6 chain twice more, with seeds 2 and 3, so results can be given as a
# spread over three training runs rather than one. Each seed on its own GPU (two at a time):
#
#   train ft4_s<n> (as ft4: 100 generated banks, 10,000 steps)       ~4.5 h
#   test ft4_s<n> on the rasterised test set (10 banks it never saw)   ~1 h
#   train ft6_s<n> from ft4_s<n> (6,000 steps with phone copies)       ~3 h
#   test ft6_s<n> on the test set and the phone copies                 ~2 h
#
# then a table of all three runs (ft4/ft6 = seed unset, s2, s3). About 10 hours.
#
#   bash scripts/queue_repeats.sh 2>&1 | tee ~/night12.log
#
# Needs queue_ft4.sh and queue_ft6.sh to have run (their data, caches and phone copies).

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
C="${CONFIG:-configs/adcdnet_eval.yaml}"
DATA="$HOME/forgelens-data"
G_DIR="$DATA/synthetic_gen"
T="${TEST:-$DATA/synthetic_test}"
P="$T/phone"
R=experiments/results
SEEDS="${SEEDS:-2 3}"

say() { echo "$(date '+%F %H:%M') $*"; }
job() {
    local name=$1; shift
    say "$name: waiting for a free GPU"
    (
        flock 9
        G=$(bash scripts/free_gpus.sh 1 --wait 2>/dev/null) || exit 99
        say "$name: started on GPU $G"
        export CUDA_VISIBLE_DEVICES=$G
        "$@" > "$HOME/night12_$name.log" 2>&1 &
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
[[ -d $G_DIR/phone_whatsapp/genuine && -f $DATA/page_cache_ft6/index.json ]] \
    || { say "run queue_ft4.sh and queue_ft6.sh first"; exit 1; }

lane() {  # lane <seed>
    local s=$1 a b
    job "train-ft4-s$s" bash scripts/with_backup.sh python scripts/train_adcdnet.py --config "$C" \
        --data "$G_DIR/genuine_raster" "$G_DIR/forged_image" --tag "ft4_s$s" --steps 10000 \
        --seed "$s" --cache "$DATA/page_cache_gen" --resume || return 1
    a=$(best_of "ft4_s$s"); [[ -n $a ]] || return 1
    job "test-ft4-s$s" python scripts/eval_adcdnet_pages.py --config "$C" --ckpt "$a" \
        --tag "test-ft4-s$s" --data "$T/genuine_raster" "$T/forged_image" --resume
    job "train-ft6-s$s" bash scripts/with_backup.sh python scripts/train_adcdnet.py --config "$C" \
        --data "$G_DIR/genuine_raster" "$G_DIR/forged_image" \
               "$G_DIR/phone_screenshot/genuine" "$G_DIR/phone_screenshot/forged_image" \
               "$G_DIR/phone_whatsapp/genuine" "$G_DIR/phone_whatsapp/forged_image" \
        --tag "ft6_s$s" --init "$a" --steps 6000 --warmup 200 --seed "$s" \
        --cache "$DATA/page_cache_ft6" --resume || return 1
    b=$(best_of "ft6_s$s"); [[ -n $b ]] || return 1
    job "test-ft6-s$s" bash -c "python scripts/eval_adcdnet_pages.py --config $C --ckpt $b \
            --tag test-ft6-s$s --data $T/genuine_raster $T/forged_image --resume && \
        python scripts/eval_adcdnet_pages.py --config $C --ckpt $b \
            --tag phone-screenshot-ft6-s$s --data $P/genuine_screenshot $P/forged_screenshot --resume && \
        python scripts/eval_adcdnet_pages.py --config $C --ckpt $b \
            --tag phone-whatsapp-ft6-s$s --data $P/genuine_whatsapp $P/forged_whatsapp --resume"
}

say "queue: repeat runs, seeds $SEEDS"
pids=()
for s in $SEEDS; do
    lane "$s" &
    pids+=($!)
    sleep 180
done
for p in "${pids[@]}"; do wait "$p"; done

say "spread over runs (caught at 1% false alarms, per kind of copy)"
python - "$R" $SEEDS <<'EOF'
import csv, statistics, sys
from pathlib import Path
R, seeds = Path(sys.argv[1]), sys.argv[2:]
runs = {"ft4": [("test-ft4", "raster")] , "ft6": [("test-ft6", "raster"),
        ("phone-screenshot-ft6", "screenshot"), ("phone-whatsapp-ft6", "whatsapp")]}
print("| Model | Copy | Forgery | " + " | ".join(["seed unset"] + [f"seed {s}" for s in seeds])
      + " | Mean ± SD |")
print("| --- | --- | --- | " + " | ".join("---:" for _ in range(len(seeds) + 2)) + " |")
for model, tags in runs.items():
    for base, copy in tags:
        rows = {}
        for i, tag in enumerate([base] + [base.replace(model, f"{model}-s{s}") for s in seeds]):
            f = R / f"adcdnet_pages_{tag}" / "summary.md"
            if not f.exists():
                continue
            for line in f.read_text().splitlines():
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) > 6 and cells[1].startswith("image_"):
                    rows.setdefault(cells[1], [None] * (len(seeds) + 1))[i] = float(cells[6].rstrip("%"))
        for forgery, vals in sorted(rows.items()):
            got = [v for v in vals if v is not None]
            spread = (f"{statistics.mean(got):.1f} ± {statistics.stdev(got):.1f}"
                      if len(got) > 1 else "–")
            print(f"| {model} | {copy} | {forgery} | " + " | ".join(
                "–" if v is None else f"{v:.0f}%" for v in vals) + f" | {spread} |")
EOF
say "ALL DONE"
