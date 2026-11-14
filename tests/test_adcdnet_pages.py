"""ADCD-Net on statement pages: tiling, OCR and ground-truth masks, the detection statistics,
and (with PyTorch and the upstream dependencies) a run over real generated statements with a
randomly initialised model."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from forgelens.signals.image.pages import (
    TILE,
    char_boxes,
    edit_mask,
    ocr_mask,
    page_scores,
    tile_origins,
)

REPO = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("eval_adcdnet_pages",
                                                  REPO / "scripts" / "eval_adcdnet_pages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tiles_cover_the_page_and_stay_inside_it():
    for length in (300, 512, 513, 1240, 1754):
        starts = tile_origins(length)
        covered = np.zeros(max(length, TILE), bool)
        for s in starts:
            covered[s:s + TILE] = True
        assert covered[:length].all() and starts[-1] + TILE == max(length, TILE)


def test_edit_mask_converts_pdf_points_to_pixels():
    edits = [{"page": 1, "mask_bbox": [72, 144, 144, 162]}, {"page": 0, "mask_bbox": [0, 0, 9, 9]}]
    m = edit_mask(edits, 1, (400, 400), dpi=150)
    ys, xs = m.nonzero()
    assert (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) == (150, 300, 300, 338)


def test_ocr_mask_boxes_characters_and_skips_rules():
    img = np.full((200, 400, 3), 255, np.uint8)
    cv2.putText(img, "1,23,456.00", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    img[120:122, 10:390] = 0  # a table rule
    boxes = char_boxes(img)
    assert len(boxes) >= 8 and all(y1 < 100 for _, _, _, y1 in boxes)
    m = ocr_mask(img)
    assert m[40:60, 30:200].mean() > 0.3 and m[118:124].sum() == 0


def test_page_scores_see_a_small_edit_that_area_misses():
    prob = np.zeros((1000, 1000), np.float32)
    prob[500:510, 500:540] = 0.9  # 400 px, 0.04% of the page
    s = page_scores(prob)
    assert s["area"] == pytest.approx(0.0004) and s["peak"] > 0.7


def test_auc_and_catch_rates():
    script = _script()
    assert script.auc([0.1, 0.2, 0.3], [0.4, 0.5]) == 1.0
    assert script.auc([0.5, 0.5], [0.5]) == 0.5
    assert script.auc([0.9], [0.1, 0.2]) == 0.0
    genuine = [i / 100 for i in range(100)]  # 0.00 … 0.99
    assert script.caught_at(genuine, [0.955, 0.5], 0.05) == 0.5  # flags 0.95-0.99: 5 of 100
    assert script.caught_at(genuine, [0.975, 0.995], 0.01) == 0.5  # flags only 0.99


# ---------------------------------------------------------------- full run (needs PyTorch)

@pytest.fixture(scope="module")
def statement_set(tmp_path_factory):
    pytest.importorskip("weasyprint")
    root = tmp_path_factory.mktemp("pages")
    run = [sys.executable]
    subprocess.run([*run, str(REPO / "scripts" / "generate_statements.py"), "--bank", "sahyadri",
                    "--count", "2", "--seed", "2000", "--months", "1", "--out",
                    str(root / "genuine")], check=True, capture_output=True)
    subprocess.run([*run, str(REPO / "scripts" / "forge_pdf_edits.py"), "--genuine",
                    str(root / "genuine"), "--out", str(root / "forged"), "--per-statement", "1"],
                   check=True, capture_output=True)
    for label in ("genuine", "forged"):
        subprocess.run([*run, str(REPO / "scripts" / "launder_pdfs.py"), "--input",
                        str(root / label), "--out", str(root / f"{label}_raster"), "--method",
                        "raster", "--dpi", "100"], check=True, capture_output=True)
    return root


def test_full_run_on_generated_statements(statement_set, tmp_path):
    for module in ("torch", "jpeg2dct.numpy", "efficientnet_pytorch", "einops", "lmdb"):
        pytest.importorskip(module)
    if not (REPO / "third_party" / "ADCD-Net" / "model" / "model.py").exists():
        pytest.skip("ADCD-Net submodule not checked out")
    import pickle

    import torch

    from forgelens.signals.image import adcdnet

    weights = tmp_path / "w"
    weights.mkdir()
    (weights / "qt.pk").write_bytes(pickle.dumps(
        {q: [[1 if q == 100 else min(63, 101 - q)] * 8] * 8 for q in range(1, 101)}))
    paths = adcdnet.Paths(upstream=REPO / "third_party" / "ADCD-Net", ckpt=weights / "a.pth",
                          docres=weights / "d.pkl", qt_path=weights / "qt.pk")
    adcdnet.configure(paths, adcdnet.Settings())
    from model.model import ADCDNet
    from model.restormer import get_restormer

    torch.manual_seed(0)
    torch.save({"model_state": get_restormer(model_name="full_model",
                                             out_channels=96).state_dict()}, paths.docres)
    torch.save({"model": ADCDNet().state_dict()}, paths.ckpt)
    config = tmp_path / "c.yaml"
    config.write_text(f"ckpt: {paths.ckpt}\ndocres: {paths.docres}\nqt_path: {paths.qt_path}\n")

    script = _script()
    args = ["--config", str(config), "--data", str(statement_set), "--tag", "t", "--out",
            str(tmp_path), "--device", "cpu", "--dpi", "50", "--batch-size", "1", "--limit", "1",
            "--save-maps", "1"]
    assert script.main(args) == 0
    run_dir = tmp_path / "adcdnet_pages_t"
    with open(run_dir / "pages.csv") as f:
        rows = list(csv.DictReader(f))
    assert {r["laundering"] for r in rows} == {"none", "raster"}
    assert {(r["label"], r["laundering"]) for r in rows} == {
        ("genuine", "none"), ("forged", "none"), ("genuine", "raster"), ("forged", "raster")}
    assert not [r for r in rows if r["error"]]
    assert any(int(r["gt"]) > 0 for r in rows if r["label"] == "forged")
    assert all(int(r["gt"]) == 0 for r in rows if r["label"] == "genuine")
    summary = json.loads((run_dir / "summary.json").read_text())
    assert {(g["laundering"], g["method"]) for g in summary["groups"]} == {
        ("none", "pdf_edit"), ("raster", "pdf_edit")}
    assert list((run_dir / "maps").glob("*.jpg"))
    n = len(rows)
    assert script.main([*args, "--resume"]) == 0  # nothing new to do
    with open(run_dir / "pages.csv") as f:
        assert len(list(csv.DictReader(f))) == n
