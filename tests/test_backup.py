"""Backups off the DGX: what is chosen, incremental runs, checkpoint retention, deletions not
mirrored, private data refused, the Hugging Face destination's privacy check, and the job
wrapper's final backup."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from forgelens.utils.backup import DirDestination, HfDestination, destination, run_once, select

REPO = Path(__file__).resolve().parents[1]
OLD = time.time() - 3600  # an hour ago: settled


def _write(path: Path, text: str = "x", mtime: float | None = OLD) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def tree(tmp_path):
    results = tmp_path / "results"
    _write(results / "adcdnet_dgx" / "FCD.csv", "a,b\n1,2\n")
    _write(results / "adcdnet_dgx" / "SCD.partial.csv")  # unfinished set
    _write(results / "adcdnet_dgx" / "summary.json", "{}")
    ckpt = tmp_path / "exp" / "run1" / "ckpt"
    for i, score in enumerate([0.70, 0.79, 0.75, 0.74, 0.73]):  # best is the 2nd oldest
        _write(ckpt / f"Step{(i + 1) * 1000}_Score{score:.4f}.pth", f"w{i}", OLD + i)
    return tmp_path, {"results": results, "adcd": tmp_path / "exp"}


def test_selection_keeps_newest_and_best_checkpoints(tree):
    _, sources = tree
    sel = select(sources, keep=2)
    names = sorted(Path(e.rel).name for e in sel.files)
    assert names == ["FCD.csv", "Step2000_Score0.7900.pth", "Step4000_Score0.7400.pth",
                     "Step5000_Score0.7300.pth", "summary.json"]
    assert {Path(r).name for r in sel.pruned_checkpoints} == {
        "Step1000_Score0.7000.pth", "Step3000_Score0.7500.pth"}


def test_checkpoints_still_being_written_wait(tree):
    root, sources = tree
    _write(root / "exp" / "run1" / "ckpt" / "Step6000_Score0.8000.pth", "new", mtime=None)
    _write(root / "results" / "adcdnet_dgx" / "train.log", "growing", mtime=None)
    sel = select(sources, keep=2, settle=120)
    assert [Path(r).name for r in sel.unsettled] == ["Step6000_Score0.8000.pth"]
    assert "train.log" in {Path(e.rel).name for e in sel.files}  # logs go while they grow


def test_private_data_is_refused(tmp_path):
    src = tmp_path / "exp"
    _write(src / "data" / "real" / "hdfc_2025.pdf")
    _write(src / "real_statements" / "notes.txt")
    _write(src / "figures" / "page.pdf")
    _write(src / "ok.csv")
    sel = select({"exp": src})
    assert [e.rel for e in sel.files] == ["exp/ok.csv"]
    assert len(sel.refused) == 3


def test_runs_are_incremental_and_never_mirror_deletions(tree, tmp_path):
    root, sources = tree
    dest = DirDestination(tmp_path / "backup")
    first = run_once(sources, dest, tmp_path / "state", keep=2)
    assert len(first["uploaded"]) == 5 and first["removed_old_checkpoints"] == []
    assert run_once(sources, dest, tmp_path / "state", keep=2)["uploaded"] == []

    fcd = root / "results" / "adcdnet_dgx" / "FCD.csv"
    _write(fcd, "a,b\n1,2\n3,4\n", OLD + 100)
    assert run_once(sources, dest, tmp_path / "state", keep=2)["uploaded"] == [
        "results/adcdnet_dgx/FCD.csv"]
    assert (tmp_path / "backup" / "results/adcdnet_dgx/FCD.csv").read_text().endswith("3,4\n")

    fcd.unlink()  # an accidental delete on the DGX
    run_once(sources, dest, tmp_path / "state", keep=2)
    assert (tmp_path / "backup" / "results/adcdnet_dgx/FCD.csv").exists()


def test_old_checkpoints_leave_the_backup_when_newer_ones_arrive(tree, tmp_path):
    root, sources = tree
    dest = DirDestination(tmp_path / "backup")
    state = tmp_path / "state"
    run_once(sources, dest, state, keep=2)
    ckpt = root / "exp" / "run1" / "ckpt"
    _write(ckpt / "Step6000_Score0.7200.pth", "w5", OLD + 10)
    summary = run_once(sources, dest, state, keep=2)
    assert summary["uploaded"] == ["adcd/run1/ckpt/Step6000_Score0.7200.pth"]
    assert summary["removed_old_checkpoints"] == ["adcd/run1/ckpt/Step4000_Score0.7400.pth"]
    kept = sorted(p.name for p in (tmp_path / "backup" / "adcd/run1/ckpt").iterdir())
    assert kept == ["Step2000_Score0.7900.pth", "Step5000_Score0.7300.pth",
                    "Step6000_Score0.7200.pth"]


def test_failed_upload_is_retried_next_time(tree, tmp_path):
    _, sources = tree

    class Flaky(DirDestination):
        fail = True

        def apply(self, add, delete, message):
            if Flaky.fail:
                raise OSError("network down")
            super().apply(add, delete, message)

    dest = Flaky(tmp_path / "backup")
    with pytest.raises(OSError):
        run_once(sources, dest, tmp_path / "state")
    Flaky.fail = False
    assert len(run_once(sources, dest, tmp_path / "state")["uploaded"]) == 6


class FakeHfApi:
    def __init__(self, private=True):
        self.private, self.commits, self.squashes = private, [], 0

    def create_repo(self, repo_id, repo_type, private, exist_ok):
        assert private and exist_ok

    def repo_info(self, repo_id, repo_type):
        return type("Info", (), {"private": self.private})()

    def create_commit(self, repo_id, operations, commit_message, repo_type):
        self.commits.append([type(op).__name__ + ":" + op.path_in_repo for op in operations])

    def super_squash_history(self, repo_id, repo_type, commit_message):
        self.squashes += 1


def test_hugging_face_backup_is_one_commit_per_run_and_squashes_after_pruning(tree, tmp_path):
    pytest.importorskip("huggingface_hub")
    root, sources = tree
    api = FakeHfApi()
    dest = HfDestination("me/forgelens-dgx-backup", api=api)
    run_once(sources, dest, tmp_path / "state", keep=2)
    assert len(api.commits) == 1 and len(api.commits[0]) == 5 and api.squashes == 0
    _write(root / "exp" / "run1" / "ckpt" / "Step6000_Score0.7200.pth", "w5", OLD + 10)
    run_once(sources, dest, tmp_path / "state", keep=2)
    assert api.commits[1] == ["CommitOperationAdd:adcd/run1/ckpt/Step6000_Score0.7200.pth",
                              "CommitOperationDelete:adcd/run1/ckpt/Step4000_Score0.7400.pth"]
    assert api.squashes == 1


def test_public_hugging_face_repo_is_refused(tree, tmp_path):
    _, sources = tree
    dest = HfDestination("me/oops-public", api=FakeHfApi(private=False))
    with pytest.raises(RuntimeError, match="PUBLIC"):
        run_once(sources, dest, tmp_path / "state")
    assert not list((tmp_path / "state").glob("manifest-*"))  # nothing recorded as done


def test_destination_spec():
    assert destination("dir:/tmp/b").name == "dir:/tmp/b"
    assert destination("/mnt/usb/b").name == "dir:/mnt/usb/b"


# ---------------------------------------------------------------- the scripts

def test_loop_does_a_last_backup_when_stopped(tmp_path):
    src = tmp_path / "results"
    _write(src / "a.csv")
    env = {**os.environ, "HOME": str(tmp_path)}
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "scripts" / "backup.py"), "--dest", f"dir:{tmp_path / 'b'}",
         "--only", "--source", f"results={src}", "--every", "1h",
         "--state-dir", str(tmp_path / "state")], env=env, stdout=subprocess.PIPE, text=True)
    deadline = time.time() + 30
    while not (tmp_path / "b" / "results" / "a.csv").exists() and time.time() < deadline:
        time.sleep(0.2)
    _write(src / "b.csv")  # written after the first backup, before the stop
    proc.send_signal(signal.SIGTERM)
    out, _ = proc.communicate(timeout=30)
    assert proc.returncode == 0, out
    assert (tmp_path / "b" / "results" / "b.csv").exists()
    assert "one last backup" in out
    assert json.loads((tmp_path / "state" / "last_backup.json").read_text())["uploaded"] == [
        "results/b.csv"]


@pytest.mark.parametrize("job_seconds", [0, 3])  # 0: ends before the backup loop is ready
def test_job_wrapper_backs_up_what_the_job_wrote_and_keeps_its_exit_status(tmp_path,
                                                                            job_seconds):
    results = tmp_path / "results"
    results.mkdir()
    ckpt = tmp_path / "ckpt"
    job = (f"sleep {job_seconds}; mkdir -p {ckpt}; echo w > {ckpt}/Step1_Score0.5.pth; "
           f"echo done > {results}/final.csv; exit 3")
    env = {**os.environ, "HOME": str(tmp_path), "FORGELENS_BACKUP": f"dir:{tmp_path / 'b'}",
           "BACKUP_ARGS": f"--only --source results={results} --source ckpt={ckpt} "
                          f"--state-dir {tmp_path / 'state'}"}
    proc = subprocess.run(["bash", str(REPO / "scripts" / "with_backup.sh"), "bash", "-c", job],
                          env=env, capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert (tmp_path / "b" / "results" / "final.csv").exists()
    # written a moment before the job ended, but the job is over, so it is complete
    assert (tmp_path / "b" / "ckpt" / "Step1_Score0.5.pth").exists()
