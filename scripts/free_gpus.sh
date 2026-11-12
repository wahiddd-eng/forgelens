#!/usr/bin/env bash
# Print up to N free GPUs (comma-separated, least used first) for CUDA_VISIBLE_DEVICES.
#
# On the shared DGX we may use at most 2 GPUs, whichever are free, so pick them when a job
# starts instead of fixing numbers in ~/.bashrc:
#
#   export CUDA_VISIBLE_DEVICES=$(bash scripts/free_gpus.sh 2) || exit 1
#   bash scripts/free_gpus.sh 2 --wait     # wait until 2 are free, checking every minute
#   bash scripts/free_gpus.sh 1 --min 1    # accept fewer: at least 1, at most 1
#
# A GPU counts as free when under MAX_MEM_MIB (default 1000) MiB is in use and its
# utilisation is under MAX_UTIL (default 10) %. Exits 1 if fewer than --min are free.

set -euo pipefail

want="${1:-2}"
shift || true
need="$want"
wait=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --wait) wait=1 ;;
        --min) need="$2"; shift ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
    shift
done
if (( want > 2 )); then
    echo "the DGX allows at most 2 GPUs per project" >&2
    exit 2
fi
max_mem="${MAX_MEM_MIB:-1000}"
max_util="${MAX_UTIL:-10}"

free_list() {
    nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits |
        awk -F', *' -v m="$max_mem" -v u="$max_util" '$2 < m && $3 < u {print $2, $1}' |
        sort -n | awk '{print $2}' | head -n "$want" | paste -sd, -
}

while true; do
    gpus="$(free_list)"
    count=$(( ${#gpus} ? $(tr -cd , <<<"$gpus" | wc -c) + 1 : 0 ))
    if (( count >= need )); then
        echo "$gpus"
        echo "using GPU(s) $gpus" >&2
        exit 0
    fi
    if (( ! wait )); then
        echo "only $count free GPU(s), need $need; try --wait or --min 1" >&2
        nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader >&2
        exit 1
    fi
    echo "$(date +%H:%M) only $count free GPU(s), waiting..." >&2
    sleep 60
done
