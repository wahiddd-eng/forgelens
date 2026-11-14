"""Image-level forgeries (splice, inpaint) and ADCD-Net fine-tuning, on generated statements."""

from __future__ import annotations

import json
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")
pytest.importorskip("weasyprint")

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def statements(tmp_path_factory):
    root = tmp_path_factory.mktemp("img")
    py = sys.executable
    subprocess.run([py, str(REPO / "scripts" / "generate_statements.py"), "--bank", "sahyadri",
                    "--count", "3", "--seed", "2000", "--months", "1", "--out",
                    str(root / "genuine")], check=True, capture_output=True)
    subprocess.run([py, str(REPO / "scripts" / "launder_pdfs.py"), "--input", str(root / "genuine"),
                    "--out", str(root / "genuine_raster"), "--method", "raster"],
                   check=True, capture_output=True)
    return root


def _load(path):
    from forgelens.signals.image.pages import render_pages

    return render_pages(path, dpi=150)


def test_splice_changes_only_the_edited_regions(statements, tmp_path):
    from forgelens.signals.image.pages import edit_mask

    script = REPO / "scripts" / "forge_image_edits.py"
    subprocess.run([sys.executable, str(script), "--genuine", str(statements / "genuine"),
                    "--out", str(tmp_path / "splice"), "--method", "splice", "--masks"],
                   check=True, capture_output=True)
    labels = sorted((tmp_path / "splice").glob("*.json"))
    assert len(labels) == 3
    for label_path in labels:
        label = json.loads(label_path.read_text())
        assert label["label"] == "forged" and label["forgery"]["method"] == "image_splice"
        assert label["laundering"]["method"] == "raster" and label["edits"]
        source = label["source_statement_id"]
        genuine = _load(statements / "genuine_raster" / f"{source}__raster.pdf")
        forged = _load(label_path.with_suffix(".pdf"))
        assert len(genuine) == len(forged)
        for page, (g, f) in enumerate(zip(genuine, forged, strict=True)):
            mask = edit_mask(label["edits"], page, g.shape[:2], 150).astype(bool)
            # JPEG works in 8 x 8 blocks (16 x 16 with chroma subsampling): grow the mask
            # to whole blocks, and outside that the pages must be identical.
            import cv2

            near = cv2.dilate(mask.astype(np.uint8), np.ones((33, 33), np.uint8)).astype(bool)
            diff = np.abs(g.astype(int) - f.astype(int)).max(axis=2)
            assert diff[~near].max() == 0, f"{label_path.name} p{page}: changed outside edits"
            if mask.any():
                assert diff[mask].mean() > 5, f"{label_path.name} p{page}: edit not visible"


def test_inpaint_takes_only_masked_pixels_from_the_model(statements, tmp_path):
    from forgelens.forgery.image_edit import forge_image

    calls = []

    def fake_inpainter(crops, masks, prompts, strength, seed):
        calls.append((len(crops), strength))
        assert all(c.shape[:2] == m.shape for c, m in zip(crops, masks, strict=True))
        assert all('"' in p for p in prompts)
        return [np.zeros_like(c) for c in crops]  # paints everything black

    record_path = next((statements / "genuine").rglob("sahyadri_*.json"))
    record = json.loads(record_path.read_text())
    out = tmp_path / "x.pdf"
    label = forge_image(record_path.with_suffix(".pdf"), record, out, operation="holder_name",
                        method="inpaint", inpainter=fake_inpainter, strength=0.8, seed=1)
    assert calls == [(1, 0.8)] and label["forgery"]["inpaint_strength"] == 0.8
    page = _load(out)[0]
    x0, y0, x1, y1 = (round(v * 150 / 72) for v in label["edits"][0]["mask_bbox"])
    assert page[y0 + 2:y1 - 2, x0 + 2:x1 - 2].mean() < 40  # the model's (black) pixels
    assert page[y1 + 20:y1 + 40, x0:x1].mean() > 200  # untouched page around it


# ---------------------------------------------------------------- fine-tuning (needs PyTorch)

def _fake_doctamper(root: Path, name: str, n: int, size: int = 320) -> None:
    import cv2
    import lmdb

    rng = np.random.default_rng(0)
    d = root / "DocTamperV1" / f"DocTamperV1-{name}"
    d.mkdir(parents=True)
    env = lmdb.open(str(d), map_size=1 << 27)
    with env.begin(write=True) as txn:
        txn.put(b"num-samples", str(n).encode())
        for i in range(n):
            img = np.full((size, size, 3), 245, np.uint8)
            img[16:size - 16:12, 8:size - 8] = rng.integers(0, 80, (len(range(16, size - 16, 12)),
                                                                     size - 16, 3))
            mask = np.zeros((size, size), np.uint8)
            mask[40:120, 30:200] = 255
            txn.put(f"image-{i:09d}".encode(), cv2.imencode(".jpg", img)[1].tobytes())
            txn.put(f"label-{i:09d}".encode(), cv2.imencode(".png", mask)[1].tobytes())
    env.close()
    seg = root / "DocTamperData" / name / "char_seg"
    seg.mkdir(parents=True)
    for i in range(n):
        (seg / f"{i:06d}.pkl").write_bytes(pickle.dumps([[8, 16, 200, 24], [8, 28, 200, 36]]))
    pks = root / "exp_data" / "pks"
    pks.mkdir(parents=True, exist_ok=True)
    (pks / f"DocTamperV1-{name}_75.pk").write_bytes(pickle.dumps([[90, 80]] * n))


def test_training_runs_end_to_end_on_cpu(statements, tmp_path, monkeypatch):
    for module in ("torch", "jpeg2dct.numpy", "efficientnet_pytorch", "einops", "lmdb",
                   "albumentations"):
        pytest.importorskip(module)
    upstream = REPO / "third_party" / "ADCD-Net"
    if not (upstream / "model" / "model.py").exists():
        pytest.skip("ADCD-Net submodule not checked out")
    import importlib.util

    import torch

    from forgelens.signals.image import adcdnet

    # Upstream's focal loss calls .cuda() itself (training is GPU-only there).
    monkeypatch.setattr(torch.Tensor, "cuda", lambda self, *a, **k: self)
    subprocess.run([sys.executable, str(REPO / "scripts" / "forge_image_edits.py"), "--genuine",
                    str(statements / "genuine"), "--out", str(tmp_path / "data" / "splice"),
                    "--method", "splice"], check=True, capture_output=True)
    dt = tmp_path / "DocTamper"
    _fake_doctamper(dt, "TrainingSet", 4)
    _fake_doctamper(dt, "FCD", 2)
    (dt / "exp_data" / "qt_table.pk").write_bytes(pickle.dumps(
        {q: [[1 if q == 100 else min(63, 101 - q)] * 8] * 8 for q in range(1, 101)}))
    paths = adcdnet.Paths(upstream=upstream, ckpt=tmp_path / "a.pth", docres=tmp_path / "d.pkl",
                          doctamper_root=dt)
    adcdnet.configure(paths, adcdnet.Settings())
    from model.model import ADCDNet
    from model.restormer import get_restormer

    torch.manual_seed(0)
    torch.save({"model_state": get_restormer(model_name="full_model",
                                             out_channels=96).state_dict()}, paths.docres)
    torch.save({"model": ADCDNet().state_dict()}, paths.ckpt)
    config = tmp_path / "c.yaml"
    config.write_text(f"ckpt: {paths.ckpt}\ndocres: {paths.docres}\ndoctamper_root: {dt}\n")

    spec = importlib.util.spec_from_file_location("train_adcdnet",
                                                  REPO / "scripts" / "train_adcdnet.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    data = [str(statements / "genuine_raster"), str(tmp_path / "data")]
    args = ["--config", str(config), "--data", *data, "--tag", "t", "--out",
            str(tmp_path / "runs"), "--cache", str(tmp_path / "runs" / "page_cache"), "--device", "cpu", "--steps", "2", "--batch-size", "2", "--crop", "96",
            "--accum", "1", "--workers", "0", "--val-every", "2", "--val-pages", "2",
            "--val-doctamper", "2", "--log-every", "1", "--warmup", "1", "--dpi", "60",
            "--val-batch", "1"]
    assert script.main(args) == 0
    run = tmp_path / "runs" / "train_t"
    log = [json.loads(line) for line in (run / "log.jsonl").read_text().splitlines()]
    assert [e["step"] for e in log if e["kind"] == "train"] == [1, 2]
    vals = [e for e in log if e["kind"] == "val"]
    assert [v["step"] for v in vals] == [0, 2] and all("fcd_f1" in v for v in vals)
    assert all(np.isfinite(e["total"]) for e in log if e["kind"] == "train")
    ckpts = list((run / "ckpt").glob("Step2_Score*.pth"))
    assert len(ckpts) == 1
    index = json.loads((tmp_path / "runs" / "page_cache" / "index.json").read_text())
    by_source: dict[str, set] = {}
    for e in index:
        by_source.setdefault(e["source"], set()).add(e["split"])
    assert all(len(s) == 1 for s in by_source.values())  # a statement's pages stay together
    # the fine-tuned checkpoint loads like the released one
    model, _ = adcdnet.load_model(adcdnet.Paths(upstream=upstream, ckpt=ckpts[0],
                                                docres=paths.docres, doctamper_root=dt), "cpu")
    assert model is not None
    assert script.main([*args, "--resume"]) == 0  # already at the last step: nothing to do


def test_page_cache_refuses_a_held_out_test_set(statements, tmp_path):
    from forgelens.signals.image.training import bank_of, build_page_cache

    test_set = tmp_path / "synthetic_test"
    (test_set / "genuine").mkdir(parents=True)
    (test_set / ".heldout").touch()
    for folder in (test_set, test_set / "genuine"):
        with pytest.raises(ValueError, match="held-out"):
            build_page_cache([folder], tmp_path / "cache", dpi=30)
    index = build_page_cache([statements / "genuine_raster"], tmp_path / "cache", dpi=30,
                             log=lambda _: None)
    assert index and {bank_of(e) for e in index} == {"sahyadri"}
    assert bank_of({"source": "bayview_international_002000"}) == "bayview_international"
