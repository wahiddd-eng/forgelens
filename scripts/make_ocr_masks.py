"""Make OCR text masks and path lists for the four Doc Protocol cross-domain test sets.

Same as upstream ADCD-Net's ``seg_char.py`` followed by ``build_path_pkl.py``, which have
hard-coded paths and no resume:

* text regions are detected with PaddleOCR's ``PP-OCRv5_server_det`` and every polygon
  scoring over 0.5 is filled into a binary mask (255 = text);
* each mask is saved in ``<set>/ocr/`` under the image's own file name, as upstream does
  (for .jpg images this JPEG-compresses the mask; ADCD-Net reads it as ``!= 0``, so we keep
  upstream's choice to stay comparable with the published numbers);
* ``path_pkl/<set>.pkl`` lists ``(image, mask, ocr)`` absolute paths for images that have
  all three, as ``build_path_pkl.py`` does. Lists shipped with the download hold the
  authors' paths and are moved to ``path_pkl/shipped/``.

Masks already made are skipped, so an interrupted run continues where it stopped. Run it
with the Python that has PaddleOCR (``scripts/make_ocr_masks.sh`` sets that up); it needs
only OpenCV, NumPy, tqdm and PaddleOCR.
"""

from __future__ import annotations

import argparse
import pickle
import shutil
import sys
import time
from pathlib import Path

CROSS_DOMAIN_SETS = ("Tampered-IC13_test", "OSTF_test", "T-SROIE_test",
                     "RealTextManipulation_test")
MODEL = "PP-OCRv5_server_det"
SCORE = 0.5
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


class PaddleDetector:
    """Upstream's TextDetector, unchanged in what it computes."""

    def __init__(self, device: str = "cpu"):
        from paddleocr import TextDetection

        self.model = TextDetection(model_name=MODEL, device=device)

    def mask(self, img_path: Path, shape: tuple[int, int]):
        import cv2
        import numpy as np

        res = self.model.predict(input=str(img_path), batch_size=1)[0]
        mask = np.zeros(shape, dtype=np.uint8)
        for poly, score in zip(res["dt_polys"], res["dt_scores"], strict=True):
            if score > SCORE:
                cv2.fillPoly(mask, [np.asarray(poly).astype(np.int32)], 1)
        return mask * 255


def images(ds_dir: Path) -> list[Path]:
    return sorted(p for p in (ds_dir / "images").iterdir()
                  if p.suffix.lower() in IMAGE_SUFFIXES)


def make_masks(ds_dir: Path, detector, limit: int | None = None) -> dict:
    """Write ``ocr/<image name>`` for every image that lacks one. Returns counts."""
    import cv2
    from tqdm import tqdm

    ocr_dir = ds_dir / "ocr"
    ocr_dir.mkdir(exist_ok=True)
    todo = [p for p in images(ds_dir) if not (ocr_dir / p.name).exists()]
    if limit is not None:
        todo = todo[:limit]
    failed = []
    for img_path in tqdm(todo, desc=ds_dir.name, unit="img"):
        try:
            img = cv2.imread(str(img_path))
            if img is None:
                raise ValueError("OpenCV cannot read it")
            mask = detector.mask(img_path, img.shape[:2])
            tmp = ocr_dir / f".tmp{img_path.suffix}"  # same suffix: same encoding as upstream
            if not cv2.imwrite(str(tmp), mask):
                raise OSError("could not write the mask")
            tmp.replace(ocr_dir / img_path.name)
        except Exception as exc:  # noqa: BLE001 - logged; the image is left out of the list
            failed.append(f"{img_path.name}: {type(exc).__name__}: {exc}")
    return {"made": len(todo) - len(failed), "failed": failed}


def path_list(ds_dir: Path) -> tuple[list[tuple[str, str, str]], list[str]]:
    """``build_path_pkl.py``: (image, mask, ocr) for images with a mask and an OCR mask."""
    entries, missing = [], []
    for img_path in images(ds_dir):
        mask_path = ds_dir / "masks" / img_path.name.replace(".jpg", ".png")
        ocr_path = ds_dir / "ocr" / img_path.name
        if not mask_path.exists():
            missing.append(f"no mask for {img_path.name}")
        elif not ocr_path.exists():
            missing.append(f"no OCR mask for {img_path.name}")
        else:
            entries.append((str(img_path.resolve()), str(mask_path.resolve()),
                            str(ocr_path.resolve())))
    return entries, missing


def write_path_lists(root: Path, names: list[str]) -> dict[str, int]:
    pkl_dir = root / "path_pkl"
    pkl_dir.mkdir(exist_ok=True)
    shipped = pkl_dir / "shipped"
    counts = {}
    for name in names:
        target = pkl_dir / f"{name}.pkl"
        if target.exists() and not (shipped / target.name).exists():
            with open(target, "rb") as f:
                old = pickle.load(f)  # the dataset's own list, read to compare
            if old and not Path(old[0][0]).exists():  # the authors' paths: keep for reference
                shipped.mkdir(exist_ok=True)
                shutil.move(str(target), shipped / target.name)
        entries, missing = path_list(root / name)
        with open(target, "wb") as f:
            pickle.dump(entries, f)
        counts[name] = len(entries)
        for line in missing[:5]:
            print(f"  {name}: {line}")
        if len(missing) > 5:
            print(f"  {name}: … {len(missing) - 5} more images left out")
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", type=Path, default=Path.home() / "forgelens-data" /
                   "cutted_datasets_fakes", help="folder with the four *_test sets")
    p.add_argument("--datasets", nargs="+", default=list(CROSS_DOMAIN_SETS))
    p.add_argument("--device", default="cpu", help="cpu, or gpu:0 with a GPU Paddle build")
    p.add_argument("--limit", type=int, help="at most N new masks per set (a quick test)")
    p.add_argument("--lists-only", action="store_true", help="only rebuild the path lists")
    args = p.parse_args(argv)

    root = args.root.expanduser()
    missing = [n for n in args.datasets if not (root / n / "images").is_dir()]
    if missing:
        print(f"not found under {root}: {', '.join(missing)}", file=sys.stderr)
        return 1
    status = 0
    if not args.lists_only:
        detector = PaddleDetector(args.device)
        for name in args.datasets:
            start = time.time()
            result = make_masks(root / name, detector, args.limit)
            print(f"{name}: {result['made']} masks made in {time.time() - start:.0f} s")
            for line in result["failed"]:
                print(f"  failed: {line}", file=sys.stderr)
            status |= bool(result["failed"])
    counts = write_path_lists(root, args.datasets)
    for name, n in counts.items():
        total = len(images(root / name))
        print(f"{name}: {n} of {total} images listed in path_pkl/{name}.pkl")
    return status


if __name__ == "__main__":
    sys.exit(main())
