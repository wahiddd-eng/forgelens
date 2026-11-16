#!/usr/bin/env bash
# Fifth queue: the final image model ft5, and the ft4 test run fusion still needs.
#
# ft3 (varied forgeries on the 10 hand-made banks) did best on AIForge-Doc; ft4 (100 generated
# banks) did best on banks it had never seen. ft5 is trained, from the released weights, on
# both training sets together: every page in ~/forgelens-data/page_cache (ft1 and ft3 data)
# and page_cache_gen (ft4 data), merged into page_cache_ft5 with hard links (no copying, no
# re-rendering; each index.json stays separate). The held-out test set is never in either.
#
#   1. ft4 on the rasterised PDF edits and rebuilds of the test set (test-ft4 covered only
#      the image-level forgeries; fusion refuses uneven coverage, since the present/absent
#      flag would give the label away)
#   2. train ft5 (12,000 steps)
#   3. ft5 on the test set, then AIForge-Doc and DocTamper, two GPUs at a time
#   4. fusion with every model (CPU)
#
# Uses one GPU while another job of ours (the OCR run) may hold a second, then two.
#
#   bash scripts/queue_ft5.sh 2>&1 | tee ~/night6.log
#
# Logs: ~/night6_<job>.log. Safe to run again: finished work is skipped or resumed.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
C="${CONFIG:-configs/adcdnet_eval.yaml}"
DATA="$HOME/forgelens-data"
D="$DATA/synthetic_v4"
G_DIR="$DATA/synthetic_gen"
T="${TEST:-$DATA/synthetic_test}"
CACHE="$DATA/page_cache_ft5"
STEPS="${STEPS:-12000}"

say() { echo "$(date '+%F %H:%M') $*"; }
job() {  # wait for a free GPU (locked pick, held 2 min after starting), run, report
    local name=$1; shift
    say "$name: waiting for a free GPU"
    (
        flock 9
        G=$(bash scripts/free_gpus.sh 1 --wait 2>/dev/null) || exit 99
        say "$name: started on GPU $G"
        export CUDA_VISIBLE_DEVICES=$G
        "$@" > "$HOME/night6_$name.log" 2>&1 &
        pid=$!
        sleep 120
        flock -u 9
        wait $pid
    ) 9>"$HOME/.forgelens_gpu.lock"
    local rc=$?
    say "$name: finished, exit $rc"
    return $rc
}
best_of() {  # best_of <tag>: the checkpoint with the highest validation score
    ls experiments/checkpoints/train_$1/ckpt/Step*_Score*.pth 2>/dev/null \
        | sed 's/.*_Score\(.*\)\.pth/\1 &/' | sort -n | tail -1 | cut -d' ' -f2
}

say "queue: ft4 on rasterised test forgeries, then ft5 ($STEPS steps) on ft3 + ft4 data"

# 1. ft4 on the rest of the test set
ft4=$(best_of ft4)
if [[ -n $ft4 ]]; then
    job test-ft4-raster python scripts/eval_adcdnet_pages.py --config "$C" --ckpt "$ft4" \
        --tag test-ft4-raster --data "$T/genuine_raster" "$T/forged_raster" --resume
else
    say "no ft4 checkpoint: skipping its raster run"
fi

# 2. merged page cache and ft5
if [[ ! -f $CACHE/index.json ]]; then
    say "merging page caches into $CACHE"
    python - "$DATA/page_cache" "$DATA/page_cache_gen" "$CACHE" <<'EOF' || exit 1
import json, os, sys
from pathlib import Path
*sources, target = map(Path, sys.argv[1:])
(target / "pages").mkdir(parents=True, exist_ok=True)
index = {}
for src in sources:
    for e in json.loads((src / "index.json").read_text()):
        index.setdefault(e["key"], e)
    for f in (src / "pages").iterdir():
        dst = target / "pages" / f.name
        if not dst.exists():
            os.link(f, dst)  # hard link: same file, no copy; pages are never rewritten
(target / "index.json").write_text(json.dumps(list(index.values())))
print(f"{len(index)} pages from {len(sources)} caches")
EOF
fi
job train-ft5 bash scripts/with_backup.sh python scripts/train_adcdnet.py --config "$C" \
    --data "$D/genuine_raster" "$D/genuine_raster_mixq" "$D/forged_image" "$D/forged_image_v2" \
           "$G_DIR/genuine_raster" "$G_DIR/forged_image" \
    --tag ft5 --steps "$STEPS" --cache "$CACHE" --resume
ft5=$(best_of ft5)
[[ -n $ft5 ]] || { say "no ft5 checkpoint"; exit 1; }
sed "s|^ckpt:.*|ckpt: $PWD/$ft5|" "$C" > configs/adcdnet_ft5.yaml

# 3. ft5 evaluations, two at a time
job test-ft5 python scripts/eval_adcdnet_pages.py --config "$C" --ckpt "$ft5" \
    --tag test-ft5 --data "$T/genuine_raster" "$T/forged_raster" "$T/forged_image" \
    --save-maps 20 --resume &
a=$!
sleep 150
( job aiforge-ft5 python scripts/eval_adcdnet.py --config configs/adcdnet_ft5.yaml \
      --tag dgx-aiforge-ft5 --datasets aiforge --batch-size 8
  job indomain-ft5 python scripts/eval_adcdnet.py --config configs/adcdnet_ft5.yaml \
      --tag dgx-ft5 --datasets in-domain --batch-size 8 --resume ) &
b=$!
wait $a; wait $b

# 4. fusion
say "fusion (CPU)"
bash scripts/run_fusion.sh > "$HOME/night6_fusion.log" 2>&1
say "ALL DONE"
