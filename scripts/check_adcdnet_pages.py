"""Check the statement-page pipeline on images where ADCD-Net is known to work.

The page evaluation (``eval_adcdnet_pages.py``) differs from upstream's DocTamper evaluation in
two ways: pages are cut into 512 px tiles whose predictions are averaged, and the OCR mask
comes from ink blobs instead of an OCR engine. If either is wrong, ADCD-Net would look blind
on our statements for a reason that has nothing to do with the statements. This script runs
the first ``--limit`` DocTamper images of a set three ways and reports the mean per-image F1:

* ``whole``: the whole image in one pass with DocTamper's own character boxes, compressed once
  at quality 100. This is upstream's evaluation with ``--compression none``.
* ``tiles``: the page pipeline (tiles, averaging) with DocTamper's character boxes.
* ``tiles+ink``: the page pipeline exactly as the statement evaluation runs it.

``tiles`` close to ``whole`` means the tiling is right; ``tiles+ink`` close to ``tiles`` means
the ink-blob OCR mask is a fair stand-in.

    python scripts/check_adcdnet_pages.py --config configs/adcdnet_eval.yaml --set TestingSet
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

from forgelens.evaluation import PixelCounts, summarise
from forgelens.signals.image import adcdnet

REPO = Path(__file__).resolve().parents[1]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, required=True,
                   help="the eval_adcdnet.py YAML (ckpt, docres, doctamper_root, ocr_root)")
    p.add_argument("--set", default="TestingSet", choices=adcdnet.DOCTAMPER_SETS)
    p.add_argument("--limit", type=int, default=500, help="first N images of the set")
    p.add_argument("--device", default="cuda")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--out", type=Path, help="write the summary as JSON here too")
    p.add_argument("--upstream", type=Path, default=REPO / "third_party" / "ADCD-Net")
    return p.parse_args(argv)


def counts(prob, gt) -> PixelCounts:
    pred = prob > 0.5
    return PixelCounts(int((pred & (gt == 1)).sum()), int(pred.sum()), int((gt == 1).sum()))


def main(argv=None) -> int:
    args = parse_args(argv)
    import lmdb
    import numpy as np
    import torch
    import yaml
    from tqdm import tqdm

    cfg = {k.replace("-", "_"): v for k, v in yaml.safe_load(args.config.read_text()).items()}
    paths = adcdnet.Paths(upstream=args.upstream, ckpt=cfg["ckpt"], docres=cfg["docres"],
                          doctamper_root=cfg.get("doctamper_root"), ocr_root=cfg.get("ocr_root"),
                          qt_path=cfg.get("qt_path"))
    from forgelens.signals.image.pages import PageDetector, ocr_mask

    precision = "fp32" if args.device == "cpu" else "fp16"
    det = PageDetector(paths, args.device, precision, args.batch_size)
    from ds import bbox_2_mask, load_data  # upstream, importable after PageDetector configured

    env = lmdb.open(str(paths.lmdb_dir(args.set)), readonly=True, lock=False, readahead=False)
    with env.begin() as txn:
        n = min(args.limit, int(txn.get(b"num-samples")))
    ocr_dir = paths.ocr_dir(args.set)
    results = {"whole": [], "tiles": [], "tiles+ink": []}
    missing_ocr = 0
    for i in tqdm(range(n), unit="img"):
        with env.begin() as txn:
            img, gt = load_data(i, txn)
        rgb = np.array(img.convert("RGB"))
        box_file = ocr_dir / f"{i:06d}.pkl"
        if box_file.exists():
            boxes = pickle.loads(box_file.read_bytes())
        else:
            boxes, missing_ocr = [], missing_ocr + 1
        h, w = gt.shape
        upstream_ocr = bbox_2_mask(boxes, h, w).astype(np.uint8)

        item = det._item(rgb, upstream_ocr)  # whole image, one pass, as DtdValDs
        img_t, dct, qt, mask, ocr_t, _, _ = det._pad_collate([item])
        with torch.inference_mode(), torch.autocast(device_type=det.device.type,
                                                    dtype=torch.float16, enabled=det.amp):
            logits = det.model(*[t.to(det.device) for t in (img_t, dct, qt, mask, ocr_t)],
                               is_train=False)[0]
        whole = torch.softmax(logits.float(), dim=1)[0, 1, :h, :w].cpu().numpy()
        results["whole"].append(counts(whole, gt))
        results["tiles"].append(counts(det.predict(rgb, upstream_ocr).prob, gt))
        results["tiles+ink"].append(counts(det.predict(rgb, ocr_mask(rgb)).prob, gt))

    summary = {"set": args.set, "images": n, "missing_ocr": missing_ocr,
               "f1": {k: summarise(v) for k, v in results.items()}}
    print(f"\nDocTamper {args.set}, first {n} images, compressed once at QF 100"
          f"{f', {missing_ocr} without character boxes' if missing_ocr else ''}:")
    print(f"  {'pipeline':<10} {'F1':>6}  95% CI")
    for k, s in summary["f1"].items():
        print(f"  {k:<10} {s['f1']:6.3f}  {s['f1_ci_low']:.3f}-{s['f1_ci_high']:.3f}")
    if args.out:
        args.out.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
