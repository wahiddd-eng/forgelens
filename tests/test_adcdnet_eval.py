"""The ADCD-Net evaluation: metric parity with upstream, the pre-flight checks, the config
file, and (when PyTorch and the upstream dependencies are installed) a full run on a tiny
dataset in DocTamper's format with randomly initialised weights."""

from __future__ import annotations

import csv
import importlib.util
import json
import pickle
from pathlib import Path

import pytest

from forgelens.evaluation import PixelCounts, image_scores, summarise
from forgelens.signals.image import adcdnet

REPO = Path(__file__).resolve().parents[1]
UPSTREAM = REPO / "third_party" / "ADCD-Net"


def _script():
    spec = importlib.util.spec_from_file_location("eval_adcdnet",
                                                  REPO / "scripts" / "eval_adcdnet.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- metrics

def _upstream_f1(tp, pred, gt, eps=1e-8):
    """Trainer.compute_f1 from third_party/ADCD-Net/main.py, for one image."""
    p = tp / (pred + eps)
    r = tp / (gt + eps)
    return 2 * p * r / (p + r + eps), p, r


@pytest.mark.parametrize("counts", [(0, 0, 50), (0, 30, 50), (25, 30, 50), (50, 50, 50),
                                    (1, 1000, 1), (0, 0, 0)])
def test_image_f1_matches_upstream(counts):
    tp, pred, gt = counts
    scores = image_scores(PixelCounts(tp, pred, gt))
    f1, p, r = _upstream_f1(tp, pred, gt)
    assert scores["f1"] == pytest.approx(f1, abs=1e-12)
    assert scores["precision"] == pytest.approx(p, abs=1e-12)
    assert scores["recall"] == pytest.approx(r, abs=1e-12)


def test_summary_separates_mean_and_pooled_scores():
    small_miss = PixelCounts(0, 0, 10)  # a small region, missed
    big_hit = PixelCounts(990, 990, 990)  # a large region, found
    s = summarise([small_miss, big_hit])
    assert s["n"] == 2 and s["n_empty_gt"] == 0
    assert s["f1"] == pytest.approx(0.5, abs=1e-6)  # per-image mean, as published
    assert s["pixel_f1"] == pytest.approx(2 * 0.99 / 1.99, abs=1e-6)  # pooled pixels
    assert s["f1_ci_low"] <= s["f1"] <= s["f1_ci_high"]
    assert summarise([])["f1"] is None


def test_impossible_counts_are_rejected():
    with pytest.raises(ValueError):
        PixelCounts(tp=5, pred=3, gt=10)


def test_published_averages_are_the_means_of_the_published_scores():
    groups = {"in_domain": adcdnet.DOCTAMPER_SETS, "cross_domain": adcdnet.CROSS_DOMAIN_SETS,
              "all": adcdnet.DOC_PROTOCOL}
    for group, names in groups.items():
        mean = sum(adcdnet.PUBLISHED_F1[n] for n in names) / len(names)
        assert mean == pytest.approx(adcdnet.PUBLISHED_AVERAGES[group], abs=6e-4), group


# ---------------------------------------------------------------- names and checks

def test_dataset_names_and_groups():
    assert adcdnet.resolve_datasets(["all"]) == list(adcdnet.DOC_PROTOCOL)
    assert adcdnet.resolve_datasets(["RTM", "test", "fcd", "FCD"]) == [
        "FCD", "TestingSet", "RealTextManipulation_test"]
    assert adcdnet.resolve_datasets(["cross-domain"]) == list(adcdnet.CROSS_DOMAIN_SETS)
    assert adcdnet.resolve_datasets(["T-SROIE_test", "tpic-13"]) == [
        "T-SROIE_test", "Tampered-IC13_test"]
    with pytest.raises(ValueError, match="unknown dataset"):
        adcdnet.resolve_datasets(["DocTamper"])


def test_preflight_lists_every_missing_piece(tmp_path):
    paths = adcdnet.Paths(upstream=tmp_path / "nowhere", ckpt=tmp_path / "ADCDNet.pth",
                          docres=tmp_path / "docres.pkl", doctamper_root=tmp_path / "dt",
                          pkl_dir=tmp_path / "pkl")
    problems, _ = adcdnet.preflight(paths, ["FCD", "OSTF_test"], adcdnet.Settings(), "cpu")
    text = "\n".join(problems)
    for expected in ("upstream code not found", "checkpoint not found: ",
                     "DocRes checkpoint not found", "qt_table.pk", "FCD: no LMDB",
                     "OSTF_test: path list"):
        assert expected in text


def test_preflight_explains_ocr_masks_in_the_wrong_folder(tmp_path):
    root = tmp_path / "dt"
    lmdb_dir = root / "DocTamperV1" / "DocTamperV1-FCD"
    lmdb_dir.mkdir(parents=True)
    (lmdb_dir / "data.mdb").write_bytes(b"")
    (root / "DocTamperData" / "FCD").mkdir(parents=True)
    (root / "DocTamperData" / "FCD" / "000000.pkl").write_bytes(pickle.dumps([]))
    paths = adcdnet.Paths(upstream=UPSTREAM, ckpt=tmp_path / "a", docres=tmp_path / "b",
                          doctamper_root=root)
    settings = adcdnet.Settings(compression="none")
    problems, _ = adcdnet.preflight(paths, ["FCD"], settings, "cpu")
    assert any("move them into char_seg/" in p for p in problems)
    problems, notes = adcdnet.preflight(paths, ["FCD"], settings, "cpu", allow_missing_ocr=True)
    assert not any("OCR" in p for p in problems) and any("OCR" in n for n in notes)


def test_preflight_reports_an_unreadable_lmdb(tmp_path):
    pytest.importorskip("lmdb")
    lmdb_dir = tmp_path / "dt" / "DocTamperV1" / "DocTamperV1-FCD"
    lmdb_dir.mkdir(parents=True)
    (lmdb_dir / "data.mdb").write_bytes(b"half a copy")
    paths = adcdnet.Paths(upstream=UPSTREAM, ckpt=tmp_path / "a", docres=tmp_path / "b",
                          doctamper_root=tmp_path / "dt")
    problems, _ = adcdnet.preflight(paths, ["FCD"], adcdnet.Settings(), "cpu")
    assert any("FCD: cannot open" in p and "copy complete" in p for p in problems)


def test_preflight_rejects_path_lists_from_another_machine(tmp_path):
    (tmp_path / "pkl").mkdir()
    entries = [("/elsewhere/a.jpg", "/elsewhere/a.png", "/elsewhere/ocr/a.jpg")]
    (tmp_path / "pkl" / "OSTF_test.pkl").write_bytes(pickle.dumps(entries))
    paths = adcdnet.Paths(upstream=UPSTREAM, ckpt=tmp_path / "a", docres=tmp_path / "b",
                          qt_path=tmp_path / "qt.pk", pkl_dir=tmp_path / "pkl")
    problems, _ = adcdnet.preflight(paths, ["OSTF_test"], adcdnet.Settings(), "cpu")
    assert any("rebuild it on this machine" in p for p in problems)


def test_config_file_supplies_options_and_the_command_line_wins(tmp_path):
    pytest.importorskip("yaml")
    script = _script()
    config = tmp_path / "run.yaml"
    config.write_text("ckpt: ~/w/ADCDNet.pth\ndocres: ~/w/docres.pkl\ntag: dgx\n"
                      "datasets: [in-domain]\nbatch-size: 8\n")
    args = script.parse_args(["--config", str(config), "--batch-size", "2"])
    assert args.tag == "dgx" and args.batch_size == 2
    assert args.datasets == ["FCD", "SCD", "TestingSet"]
    assert args.ckpt == Path("~/w/ADCDNet.pth").expanduser()
    config.write_text("ckpt: a\ndocres: b\ntag: x\nbatchsize: 8\n")
    with pytest.raises(SystemExit):
        script.parse_args(["--config", str(config)])


def test_check_mode_reports_problems_without_pytorch(tmp_path, capsys):
    script = _script()
    code = script.main(["--ckpt", str(tmp_path / "x.pth"), "--docres", str(tmp_path / "d.pkl"),
                        "--doctamper-root", str(tmp_path), "--datasets", "FCD", "--tag", "t",
                        "--device", "cpu", "--check"])
    assert code == 1
    assert "checkpoint not found" in capsys.readouterr().err


# ---------------------------------------------------------------- full run (needs PyTorch)

def _need_upstream_stack():
    for module in ("torch", "jpeg2dct.numpy", "efficientnet_pytorch", "einops", "lmdb",
                   "albumentations", "cv2"):
        pytest.importorskip(module)
    if not (UPSTREAM / "model" / "model.py").exists():
        pytest.skip("ADCD-Net submodule not checked out")


def _make_doctamper(root: Path, name: str, n: int, broken: int | None = None) -> None:
    """A tiny dataset in DocTamper's LMDB format, with OCR boxes and JPEG records."""
    import cv2
    import lmdb
    import numpy as np

    rng = np.random.default_rng(0)
    lmdb_dir = root / "DocTamperV1" / f"DocTamperV1-{name}"
    lmdb_dir.mkdir(parents=True)
    env = lmdb.open(str(lmdb_dir), map_size=1 << 26)
    with env.begin(write=True) as txn:
        txn.put(b"num-samples", str(n).encode())
        for i in range(n):
            img = np.full((128, 128, 3), 245, np.uint8)
            img[16:112:12, 8:120] = rng.integers(0, 80, (8, 112, 3))  # lines of "text"
            mask = np.zeros((128, 128), np.uint8)
            mask[40:64, 30:90] = 255
            jpeg = cv2.imencode(".jpg", img)[1].tobytes()
            txn.put(f"image-{i:09d}".encode(), b"not an image" if i == broken else jpeg)
            txn.put(f"label-{i:09d}".encode(), cv2.imencode(".png", mask)[1].tobytes())
    env.close()
    char_seg = root / "DocTamperData" / name / "char_seg"
    char_seg.mkdir(parents=True)
    for i in range(n):
        (char_seg / f"{i:06d}.pkl").write_bytes(pickle.dumps([[8, 16, 120, 24], [8, 28, 120, 36]]))
    pks = root / "exp_data" / "pks"
    pks.mkdir(parents=True, exist_ok=True)
    (pks / f"DocTamperV1-{name}_75.pk").write_bytes(pickle.dumps([[90, 80]] * n))


def _make_cross_domain(root: Path, name: str, n: int) -> Path:
    import cv2
    import numpy as np

    folder = root / name
    entries = []
    for sub in ("images", "masks", "ocr"):
        (folder / sub).mkdir(parents=True)
    for i in range(n):
        img = np.full((96, 160, 3), 240, np.uint8)
        img[20:76:10, 10:150] = 30
        mask = np.zeros((96, 160), np.uint8)
        mask[30:50, 40:100] = 255
        paths = (folder / "images" / f"{i}.jpg", folder / "masks" / f"{i}.png",
                 folder / "ocr" / f"{i}.jpg")
        cv2.imwrite(str(paths[0]), img)
        cv2.imwrite(str(paths[1]), mask)
        cv2.imwrite(str(paths[2]), (img < 100).astype(np.uint8) * 255)
        entries.append(tuple(str(p) for p in paths))
    pkl_dir = root / "path_pkl"
    pkl_dir.mkdir(exist_ok=True)
    (pkl_dir / f"{name}.pkl").write_bytes(pickle.dumps(entries))
    return pkl_dir


@pytest.fixture(scope="module")
def fake_setup(tmp_path_factory):
    """Data in upstream's layouts plus checkpoints with random weights."""
    _need_upstream_stack()
    import torch

    root = tmp_path_factory.mktemp("adcd")
    dt = root / "DocTamper"
    _make_doctamper(dt, "FCD", 3, broken=2)
    pkl_dir = _make_cross_domain(root / "cross", "OSTF_test", 2)
    (dt / "exp_data" / "qt_table.pk").write_bytes(pickle.dumps(
        {q: [[1 if q == 100 else min(63, 101 - q)] * 8] * 8 for q in range(1, 101)}))

    paths = adcdnet.Paths(upstream=UPSTREAM, ckpt=root / "ADCDNet.pth",
                          docres=root / "docres.pkl", doctamper_root=dt, pkl_dir=pkl_dir)
    adcdnet.configure(paths, adcdnet.Settings())
    from model.model import ADCDNet
    from model.restormer import get_restormer

    torch.manual_seed(0)
    docres = get_restormer(model_name="full_model", out_channels=96)
    torch.save({"model_state": docres.state_dict()}, paths.docres)
    torch.save({"model": {f"module.{k}": v for k, v in ADCDNet().state_dict().items()}},
               paths.ckpt)
    return root, paths


def _run(paths, out, *extra):
    return _script().main([
        "--ckpt", str(paths.ckpt), "--docres", str(paths.docres),
        "--doctamper-root", str(paths.doctamper_root), "--pkl-dir", str(paths.pkl_dir),
        "--datasets", "FCD", "OSTF", "--device", "cpu", "--batch-size", "2",
        "--workers", "0", "--out", str(out), "--tag", "t", *extra])


def test_full_run_on_tiny_data(fake_setup, tmp_path):
    _, paths = fake_setup
    assert _run(paths, tmp_path, "--save-masks", "1", "--workers", "2") == 0
    run_dir = tmp_path / "adcdnet_t"
    with open(run_dir / "FCD.csv") as f:
        rows = list(csv.DictReader(f))
    assert [r["image"] for r in rows if not r["error"]] == ["000000", "000001"]
    assert [r["image"] for r in rows if r["error"]] == ["000002"]  # broken image recorded
    assert all(int(r["gt"]) == 24 * 60 for r in rows if not r["error"])
    summary = json.loads((run_dir / "summary.json").read_text())
    fcd = summary["datasets"]["FCD"]
    assert fcd["n"] == 2 and fcd["n_failed"] == 1 and 0 <= fcd["f1"] <= 1
    assert summary["datasets"]["OSTF_test"]["n"] == 2
    assert summary["run"]["ckpt_sha256"] == adcdnet.sha256(paths.ckpt)
    assert summary["run"]["model"]["missing_keys"] == []
    assert summary["averages"] == {}  # incomplete groups are not averaged
    assert (run_dir / "masks" / "FCD" / "000000.png").exists()
    assert "| FCD | 2 | 1 |" in (run_dir / "summary.md").read_text()
    assert not list(run_dir.glob("*.partial.csv"))


def test_resume_reuses_finished_sets_and_refuses_a_mismatch(fake_setup, tmp_path, capsys):
    _, paths = fake_setup
    assert _run(paths, tmp_path, "--limit", "1") == 0
    first = (tmp_path / "adcdnet_t" / "FCD.csv").read_text()
    assert _run(paths, tmp_path, "--limit", "1", "--resume") == 0
    assert "reusing FCD.csv" in capsys.readouterr().out
    assert (tmp_path / "adcdnet_t" / "FCD.csv").read_text() == first
    assert "Smoke test" in (tmp_path / "adcdnet_t" / "summary.md").read_text()
    assert _run(paths, tmp_path, "--resume") == 1  # full run cannot reuse a 1-image CSV


def test_checkpoint_missing_weights_is_an_error(fake_setup):
    import torch

    root, paths = fake_setup
    state = torch.load(paths.ckpt, weights_only=True)["model"]
    state.pop(next(iter(state)))
    broken = root / "partial.pth"
    torch.save({"model": state}, broken)
    partial_paths = adcdnet.Paths(upstream=UPSTREAM, ckpt=broken, docres=paths.docres,
                                  doctamper_root=paths.doctamper_root)
    with pytest.raises(RuntimeError, match="1 weights missing"):
        adcdnet.load_model(partial_paths, "cpu")
    _, info = adcdnet.load_model(partial_paths, "cpu", allow_missing_keys=True)
    assert len(info["missing_keys"]) == 1


def test_worker_processes_read_the_lmdb(fake_setup):
    """Data loading in worker processes reopens LMDB per process and gives the same items."""
    import torch
    from torch.utils.data import DataLoader

    dataset = adcdnet.Guarded(adcdnet.build_dataset("FCD"), range(2))
    loaders = [DataLoader(dataset, batch_size=2, num_workers=w, collate_fn=adcdnet.collate,
                          worker_init_fn=adcdnet.worker_init if w else None) for w in (0, 2)]
    (a, _), (b, _) = (next(iter(loader)) for loader in loaders)
    assert torch.equal(a[0], b[0]) and torch.equal(a[3], b[3])

