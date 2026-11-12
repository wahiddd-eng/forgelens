"""OCR masks for the cross-domain sets: resume, failures, and path lists that replace the
authors' lists (which hold their own absolute paths)."""

from __future__ import annotations

import importlib.util
import pickle
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
pytest.importorskip("tqdm")

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_ocr_masks",
                                              REPO / "scripts" / "make_ocr_masks.py")
ocr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ocr)


class BoxDetector:
    """Stands in for PaddleOCR: one text box per image."""

    def __init__(self):
        self.calls = 0

    def mask(self, img_path, shape):
        self.calls += 1
        if "broken" in img_path.name:
            raise RuntimeError("detector crashed")
        m = np.zeros(shape, np.uint8)
        m[10:20, 10:40] = 255
        return m


def _make_set(root: Path, name: str, n: int, without_mask: int | None = None) -> Path:
    ds = root / name
    (ds / "images").mkdir(parents=True)
    (ds / "masks").mkdir()
    for i in range(n):
        cv2.imwrite(str(ds / "images" / f"{i}.jpg"), np.full((48, 64, 3), 200, np.uint8))
        if i != without_mask:
            cv2.imwrite(str(ds / "masks" / f"{i}.png"), np.zeros((48, 64), np.uint8))
    return ds


def test_masks_are_made_once_and_resume(tmp_path):
    ds = _make_set(tmp_path, "OSTF_test", 3)
    det = BoxDetector()
    assert ocr.make_masks(ds, det, limit=2) == {"made": 2, "failed": []}
    assert ocr.make_masks(ds, det) == {"made": 1, "failed": []}  # only the remaining image
    assert det.calls == 3
    mask = cv2.imread(str(ds / "ocr" / "0.jpg"), 0)
    assert (mask[12:18, 12:38] != 0).all() and (mask[30:, :] == 0).all()
    assert not list((ds / "ocr").glob(".tmp*"))


def test_a_failing_image_is_reported_and_left_out(tmp_path):
    ds = _make_set(tmp_path, "OSTF_test", 2)
    cv2.imwrite(str(ds / "images" / "broken.jpg"), np.zeros((8, 8, 3), np.uint8))
    cv2.imwrite(str(ds / "masks" / "broken.png"), np.zeros((8, 8), np.uint8))
    result = ocr.make_masks(ds, BoxDetector())
    assert result["made"] == 2 and result["failed"][0].startswith("broken.jpg")
    entries, missing = ocr.path_list(ds)
    assert [Path(e[0]).name for e in entries] == ["0.jpg", "1.jpg"]
    assert missing == ["no OCR mask for broken.jpg"]


def test_path_lists_replace_the_shipped_ones(tmp_path):
    names = ["OSTF_test", "T-SROIE_test"]
    for name in names:
        ocr.make_masks(_make_set(tmp_path, name, 2, without_mask=1), BoxDetector())
    (tmp_path / "path_pkl").mkdir()
    shipped = [("/data/authors/OSTF_test/images/0.jpg", "/x.png", "/y.jpg")]
    (tmp_path / "path_pkl" / "OSTF_test.pkl").write_bytes(pickle.dumps(shipped))
    counts = ocr.write_path_lists(tmp_path, names)
    assert counts == {"OSTF_test": 1, "T-SROIE_test": 1}  # image 1 has no ground-truth mask
    with open(tmp_path / "path_pkl" / "OSTF_test.pkl", "rb") as f:
        entries = pickle.load(f)
    assert all(Path(p).exists() for p in entries[0])
    assert (tmp_path / "path_pkl" / "shipped" / "OSTF_test.pkl").exists()
    ocr.write_path_lists(tmp_path, names)  # again: the shipped copy is kept, not overwritten
    with open(tmp_path / "path_pkl" / "shipped" / "OSTF_test.pkl", "rb") as f:
        assert pickle.load(f) == shipped


def test_lists_only_mode_needs_no_paddle(tmp_path, capsys):
    for name in ocr.CROSS_DOMAIN_SETS:
        _make_set(tmp_path, name, 1)
    assert ocr.main(["--root", str(tmp_path), "--lists-only"]) == 0
    assert "0 of 1 images listed" in capsys.readouterr().out  # no OCR masks yet
