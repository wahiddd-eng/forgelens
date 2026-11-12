"""Periodic, incremental backups of experiment outputs from the shared DGX.

The DGX keeps no backups and reboots weekly, so results, logs and checkpoints are copied
off it while jobs run. Design rules:

* **Incremental.** A manifest per destination records each file's size and mtime; only new or
  changed files are sent.
* **Never mirror deletions.** A file deleted locally (by accident or a bad ``rm``) stays in
  the backup. The one exception is checkpoint retention, below.
* **Checkpoint retention.** Per folder, the newest ``keep`` checkpoints plus the best one (by
  the ``Score`` in upstream ADCD-Net's file names, ``Step1000_Score0.7912.pth``) are kept;
  older ones that were backed up are removed from the backup to save space.
* **No half-written checkpoints.** A checkpoint changed in the last ``settle`` seconds is left
  for the next run. Logs and CSVs are copied as they are, so a growing training log is backed
  up while the job runs.
* **No private data.** Anything under a folder named ``data`` or starting with ``real``, and
  every PDF, is refused: real bank statements never leave the machine they were collected on.
* **A Hugging Face destination must be private**; it is checked before every upload.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

CHECKPOINT_SUFFIXES = {".pth", ".pt", ".ckpt", ".safetensors"}
SCORE_RE = re.compile(r"score[_-]?(\d+(?:\.\d+)?)", re.IGNORECASE)
SKIP_SUFFIXES = {".partial", ".tmp", ".lock", ".swp"}


@dataclass(frozen=True)
class Entry:
    rel: str  # path in the backup: "<source name>/<path inside the source>"
    path: Path
    size: int
    mtime: float

    @property
    def key(self) -> list:
        return [self.size, round(self.mtime, 3)]


@dataclass
class Selection:
    files: list[Entry] = field(default_factory=list)
    unsettled: list[str] = field(default_factory=list)  # checkpoints still being written
    refused: list[str] = field(default_factory=list)  # private data or too large
    pruned_checkpoints: set[str] = field(default_factory=set)  # older than retention


def is_checkpoint(path: Path) -> bool:
    return path.suffix.lower() in CHECKPOINT_SUFFIXES


def _private(rel_parts: tuple[str, ...], path: Path) -> bool:
    if path.suffix.lower() == ".pdf":
        return True
    return any(p.lower() == "data" or p.lower().startswith("real") for p in rel_parts[:-1])


def _score(path: Path) -> float | None:
    m = SCORE_RE.search(path.stem)
    return float(m.group(1)) if m else None


def select(sources: dict[str, Path], keep: int = 3, settle: float = 120,
           max_bytes: int = 10 << 30, now: float | None = None) -> Selection:
    """Choose the files to back up from each ``name -> folder`` source."""
    now = time.time() if now is None else now
    sel = Selection()
    checkpoints: dict[Path, list[Entry]] = {}
    for name, root in sources.items():
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            inner = path.relative_to(root)
            rel = f"{name}/{inner.as_posix()}"
            if any(s in SKIP_SUFFIXES for s in path.suffixes) or path.name.startswith("."):
                continue
            if _private(inner.parts, path):
                sel.refused.append(f"{rel} (looks like private data)")
                continue
            st = path.stat()
            if st.st_size > max_bytes:
                sel.refused.append(f"{rel} ({st.st_size / 2**30:.1f} GB, over the size limit)")
                continue
            entry = Entry(rel, path, st.st_size, st.st_mtime)
            if not is_checkpoint(path):
                sel.files.append(entry)
            elif now - st.st_mtime < settle:
                sel.unsettled.append(rel)
            else:
                checkpoints.setdefault(path.parent, []).append(entry)
    for group in checkpoints.values():
        newest = sorted(group, key=lambda e: e.mtime, reverse=True)
        kept = {e.rel for e in newest[:keep]}
        scored = [e for e in group if _score(e.path) is not None]
        if scored:
            kept.add(max(scored, key=lambda e: _score(e.path)).rel)
        for e in group:
            if e.rel in kept:
                sel.files.append(e)
            else:
                sel.pruned_checkpoints.add(e.rel)
    return sel


# ---------------------------------------------------------------- destinations

class DirDestination:
    """A folder: another disk, a mounted drive, or a synced folder."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.name = f"dir:{self.root}"

    def check(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def apply(self, add: list[Entry], delete: list[str], message: str) -> None:
        for e in add:
            target = self.root / e.rel
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".backup-tmp")
            shutil.copy2(e.path, tmp)
            os.replace(tmp, target)
        for rel in delete:
            (self.root / rel).unlink(missing_ok=True)


class HfDestination:
    """A private Hugging Face repository; one commit per backup run."""

    def __init__(self, repo_id: str, api=None, repo_type: str = "model"):
        if api is None:
            from huggingface_hub import HfApi

            api = HfApi()
        self.api, self.repo_id, self.repo_type = api, repo_id, repo_type
        self.name = f"hf:{repo_id}"

    def check(self) -> None:
        self.api.create_repo(self.repo_id, repo_type=self.repo_type, private=True, exist_ok=True)
        info = self.api.repo_info(self.repo_id, repo_type=self.repo_type)
        if not getattr(info, "private", False):
            raise RuntimeError(f"{self.repo_id} is PUBLIC; make it private on huggingface.co "
                               "before backing up to it")

    def apply(self, add: list[Entry], delete: list[str], message: str) -> None:
        from huggingface_hub import CommitOperationAdd, CommitOperationDelete

        ops = [CommitOperationAdd(path_in_repo=e.rel, path_or_fileobj=str(e.path)) for e in add]
        ops += [CommitOperationDelete(path_in_repo=rel) for rel in delete]
        self.api.create_commit(self.repo_id, ops, commit_message=message,
                               repo_type=self.repo_type)
        if delete:  # deleted files stay in the history and keep using storage until squashed
            self.api.super_squash_history(self.repo_id, repo_type=self.repo_type,
                                          commit_message=f"squash: {message}")


def destination(spec: str):
    """``hf:<user>/<repo>`` or ``dir:<path>`` (a bare path also means a folder)."""
    kind, _, target = spec.partition(":")
    if kind == "hf" and target:
        return HfDestination(target)
    if kind == "dir" and target:
        return DirDestination(target)
    return DirDestination(spec)


# ---------------------------------------------------------------- one backup run

def state_path(state_dir: Path, dest_name: str) -> Path:
    digest = hashlib.sha256(dest_name.encode()).hexdigest()[:16]
    return Path(state_dir).expanduser() / f"manifest-{digest}.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"destination": None, "files": {}}


def run_once(sources: dict[str, Path], dest, state_dir: Path, keep: int = 3,
             settle: float = 120, max_bytes: int = 10 << 30, now: float | None = None) -> dict:
    """Back up what changed since the last successful run. Returns a summary."""
    manifest_path = state_path(state_dir, dest.name)
    manifest = _load(manifest_path)
    done: dict[str, list] = manifest.get("files", {})
    sel = select(sources, keep=keep, settle=settle, max_bytes=max_bytes, now=now)
    add = [e for e in sel.files if done.get(e.rel) != e.key]
    delete = sorted(rel for rel in sel.pruned_checkpoints if rel in done)
    summary = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "destination": dest.name,
               "uploaded": [e.rel for e in add], "removed_old_checkpoints": delete,
               "bytes": sum(e.size for e in add), "unsettled": sel.unsettled,
               "refused": sel.refused, "unchanged": len(sel.files) - len(add)}
    if not add and not delete:
        return summary
    dest.check()
    dest.apply(add, delete, f"backup {summary['time']}: {len(add)} files, "
                            f"{summary['bytes'] / 2**20:.1f} MiB")
    for e in add:
        done[e.rel] = e.key
    for rel in delete:
        done.pop(rel, None)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"destination": dest.name, "files": done}, indent=1))
    os.replace(tmp, manifest_path)  # only after the upload succeeded
    return summary
