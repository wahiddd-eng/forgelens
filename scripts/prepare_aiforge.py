"""Lay out the AIForge-Doc v1 test split like the Doc Protocol cross-domain sets.

ADCD-Net's general loader reads ``<root>/<set>/{images,masks,ocr}`` through a path list, so
this makes two sets beside the cross-domain ones, with links instead of copies:

* ``AIForge_test``: the 812 AI-inpainted test images and their masks (255 = tampered);
* ``AIForge_authentic``: the 812 untouched originals, with all-black masks, to measure how
  often ADCD-Net flags a genuine document.

Then ``scripts/make_ocr_masks.sh --datasets AIForge_test AIForge_authentic`` makes their OCR
masks and path lists, and ``scripts/eval_adcdnet.py --datasets aiforge`` evaluates them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def link(src: Path, dst: Path) -> None:
    if dst.is_symlink() or dst.exists():
        return
    dst.symlink_to(src.resolve())


def prepare(src: Path, dst: Path) -> dict[str, int]:
    import cv2
    import numpy as np

    test = src / "TestingSet"
    forged = dst / "AIForge_test"
    authentic = dst / "AIForge_authentic"
    for d in (forged / "images", forged / "masks", authentic / "images", authentic / "masks"):
        d.mkdir(parents=True, exist_ok=True)

    images = sorted(p for p in (test / "images").iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    unmatched = 0
    for img in images:
        mask = test / "masks" / img.name
        if not mask.exists():
            unmatched += 1
            continue
        link(img, forged / "images" / img.name)
        # make_ocr_masks.py and upstream look for <name>.png beside a .jpg image
        link(mask, forged / "masks" / (img.stem + ".png"))

    originals = sorted(p for p in (test / "authentic").iterdir()
                       if p.suffix.lower() in IMAGE_SUFFIXES)
    unreadable = 0
    for img in originals:
        link(img, authentic / "images" / img.name)
        target = authentic / "masks" / (img.stem + ".png")
        if target.exists():
            continue
        pixels = cv2.imread(str(img), cv2.IMREAD_UNCHANGED)
        if pixels is None:
            unreadable += 1
            continue
        cv2.imwrite(str(target), np.zeros(pixels.shape[:2], np.uint8))
    return {"forged": len(images) - unmatched, "forged_without_mask": unmatched,
            "authentic": len(originals) - unreadable, "authentic_unreadable": unreadable}


def main(argv: list[str] | None = None) -> int:
    data = Path.home() / "forgelens-data"
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--src", type=Path, default=data / "AIForge-Doc-v1")
    p.add_argument("--dst", type=Path, default=data / "cutted_datasets_fakes")
    args = p.parse_args(argv)
    if not (args.src / "TestingSet" / "images").is_dir():
        print(f"no TestingSet/images under {args.src}", file=sys.stderr)
        return 1
    counts = prepare(args.src.expanduser(), args.dst.expanduser())
    print(f"AIForge_test: {counts['forged']} forged images with masks"
          + (f" ({counts['forged_without_mask']} without a mask left out)"
             if counts["forged_without_mask"] else ""))
    print(f"AIForge_authentic: {counts['authentic']} authentic images"
          + (f" ({counts['authentic_unreadable']} unreadable left out)"
             if counts["authentic_unreadable"] else ""))
    print("Next: bash scripts/make_ocr_masks.sh --datasets AIForge_test AIForge_authentic")
    return 0


if __name__ == "__main__":
    sys.exit(main())
