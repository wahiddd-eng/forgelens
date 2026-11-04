"""Record how a result was produced, so every number can be traced to code and set-up."""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

_PACKAGES = ("forgelens", "pymupdf", "weasyprint", "fonttools", "faker", "jinja2")


def _git(*args: str) -> str | None:
    root = Path(__file__).resolve().parents[3]
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                             timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def _version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _ghostscript() -> str | None:
    from ..forgery.launder import ghostscript

    gs = ghostscript()
    if gs is None:
        return None
    try:
        return subprocess.run([gs, "--version"], capture_output=True, text=True, timeout=10,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def run_info(args: dict | None = None) -> dict:
    """Return the code version, environment and arguments of the current run."""
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit,
        "git_dirty": None if status is None else bool(status),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {p: _version(p) for p in _PACKAGES},
        "ghostscript": _ghostscript(),
        "command": " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]),
        "args": {k: str(v) for k, v in (args or {}).items()},
    }
