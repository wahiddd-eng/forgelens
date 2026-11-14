#!/usr/bin/env bash
# Run a job with backups every 30 minutes, plus one more as soon as it ends (even if it fails).
#
#   export FORGELENS_BACKUP=hf:wahiddd-eng/forgelens-dgx-backup      # once, in ~/.bashrc
#   bash scripts/with_backup.sh python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag dgx
#
# Settings: FORGELENS_BACKUP (destination, required), BACKUP_EVERY (default 30m),
# BACKUP_ARGS (extra options for scripts/backup.py, e.g. "--source adcd=~/forgelens-data/exp_out").
# The job's exit status is passed through.

set -uo pipefail

if [[ $# -eq 0 ]]; then
    echo "usage: bash scripts/with_backup.sh <command> [args...]" >&2
    exit 2
fi
: "${FORGELENS_BACKUP:?set FORGELENS_BACKUP, e.g. hf:<user>/forgelens-dgx-backup}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck disable=SC2086
python "$here/backup.py" --dest "$FORGELENS_BACKUP" --every "${BACKUP_EVERY:-30m}" \
    ${BACKUP_ARGS:-} &
backup_pid=$!

finish() {
    local status=$?
    kill -TERM "$backup_pid" 2>/dev/null
    wait "$backup_pid" 2>/dev/null
    # The job has ended, so its checkpoints are complete: back up everything now.
    # shellcheck disable=SC2086
    python "$here/backup.py" --dest "$FORGELENS_BACKUP" --once --settle 0 ${BACKUP_ARGS:-} \
        || echo "final backup failed; see ~/forgelens_backup.log" >&2
    exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM HUP          # Ctrl-C or a closed session still runs finish

"$@"
