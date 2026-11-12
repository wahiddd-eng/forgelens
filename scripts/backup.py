"""Back up results, logs and checkpoints off the DGX every few minutes while jobs run.

The DGX keeps no backups and reboots weekly. This copies what changed since the last run to
a private Hugging Face repository (the DGX reaches huggingface.co) or to a folder. See
``forgelens.utils.backup`` for the rules: incremental, deletions never mirrored, newest and
best checkpoints kept, private data refused, a Hugging Face repository must be private.

Examples:
    # once: log in to Hugging Face (the token stays in ~/.cache/huggingface)
    huggingface-cli login

    # every 30 minutes until stopped; on Ctrl-C or SIGTERM it does a last backup and exits
    python scripts/backup.py --dest hf:wahiddd-eng/forgelens-dgx-backup --every 30m

    # around one job: back up during it and once more when it ends (see with_backup.sh)
    bash scripts/with_backup.sh python scripts/eval_adcdnet.py --config ... --tag dgx

    # add upstream training output to the default sources
    python scripts/backup.py --dest hf:... --source adcd=~/forgelens-data/exp_out

    # get everything back (e.g. onto the Mac or the home PC)
    python scripts/backup.py restore --dest hf:wahiddd-eng/forgelens-dgx-backup --to ~/restored
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import signal
import sys
import time
import traceback
from pathlib import Path

from forgelens.utils.backup import destination, run_once

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = {
    "results": REPO / "experiments" / "results",
    "logs": REPO / "experiments" / "logs",
    "checkpoints": REPO / "experiments" / "checkpoints",
}
LOG = Path.home() / "forgelens_backup.log"


def interval(text: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smh]?)", text.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"not an interval: {text!r} (e.g. 30m, 1h, 900s)")
    return float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)]


def source(text: str) -> tuple[str, Path]:
    name, sep, path = text.partition("=")
    if not sep or not name or "/" in name:
        raise argparse.ArgumentTypeError(f"use name=path, e.g. adcd=~/exp_out (got {text!r})")
    return name, Path(path).expanduser()


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def report(summary: dict) -> None:
    n, mib = len(summary["uploaded"]), summary["bytes"] / 2**20
    parts = [f"{n} file(s), {mib:.1f} MiB backed up" if n else "nothing new"]
    if summary["removed_old_checkpoints"]:
        parts.append(f"{len(summary['removed_old_checkpoints'])} old checkpoint(s) removed")
    if summary["unsettled"]:
        parts.append(f"{len(summary['unsettled'])} checkpoint(s) still being written")
    log(f"{summary['destination']}: " + "; ".join(parts))
    for item in summary["refused"]:
        log(f"  refused: {item}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__.split("\n\n", 1)[1])
    p.add_argument("command", nargs="?", choices=["run", "restore"], default="run")
    p.add_argument("--dest", required=True, help="hf:<user>/<repo> or dir:<path>")
    p.add_argument("--source", type=source, action="append", default=[],
                   help="extra folder to back up, as name=path (repeatable)")
    p.add_argument("--only", action="store_true", help="back up only the --source folders")
    p.add_argument("--every", type=interval, default=interval("30m"),
                   help="time between backups (default 30m)")
    p.add_argument("--once", action="store_true", help="back up once and exit")
    p.add_argument("--keep", type=int, default=3, help="newest checkpoints kept per folder "
                   "(the best-scoring one is kept as well)")
    p.add_argument("--settle", type=float, default=120,
                   help="skip checkpoints modified in the last N seconds (default 120; "
                   "with_backup.sh uses 0 for its last run, after the job has ended)")
    p.add_argument("--max-gb", type=float, default=10, help="skip larger files")
    p.add_argument("--state-dir", type=Path, default=Path.home() / ".cache" / "forgelens-backup")
    p.add_argument("--to", type=Path, help="restore: where to put the files")
    return p


def restore(args) -> int:
    if args.to is None:
        print("restore needs --to", file=sys.stderr)
        return 2
    dest = destination(args.dest)
    args.to.mkdir(parents=True, exist_ok=True)
    if dest.name.startswith("hf:"):
        from huggingface_hub import snapshot_download

        snapshot_download(dest.repo_id, repo_type=dest.repo_type, local_dir=args.to)
    else:
        shutil.copytree(dest.root, args.to, dirs_exist_ok=True)
    log(f"restored {dest.name} into {args.to}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "restore":
        return restore(args)
    sources = {} if args.only else dict(DEFAULT_SOURCES)
    sources.update(dict(args.source))
    if not sources:
        print("no folders to back up", file=sys.stderr)
        return 2
    dest = destination(args.dest)

    stop = {"requested": False}

    def request_stop(signum, _frame):
        stop["requested"] = True
        log(f"{signal.Signals(signum).name}: one last backup, then exit")

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    log(f"backing up {', '.join(f'{k}={v}' for k, v in sources.items())} to {dest.name}"
        + ("" if args.once else f" every {args.every / 60:g} min"))
    failures = 0
    while True:
        final = args.once or stop["requested"]
        try:
            summary = run_once(sources, dest, args.state_dir, keep=args.keep,
                               settle=args.settle,
                               max_bytes=int(args.max_gb * 2**30))
            report(summary)
            args.state_dir.mkdir(parents=True, exist_ok=True)
            (args.state_dir / "last_backup.json").write_text(json.dumps(summary, indent=1))
            failures = 0
        except Exception as exc:  # noqa: BLE001 - keep backing up; the next run retries
            failures += 1
            log(f"backup FAILED ({failures} in a row): {type(exc).__name__}: {exc}")
            if failures == 1:
                log(traceback.format_exc().rstrip())
            if final:
                return 1
        if final:
            return 0
        deadline = time.time() + args.every
        while time.time() < deadline and not stop["requested"]:
            time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
