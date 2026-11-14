"""Fine-tune ADCD-Net on statement pages, mixed with DocTamper.

Pieces used by ``scripts/train_adcdnet.py``:

* :func:`build_page_cache` renders every page of the given statements once (PNG), with its
  ground-truth mask from the labels and ink-blob character boxes (``pages.char_boxes``), and
  splits them by source statement into training and validation, so a genuine statement and
  the forgeries made from it never sit on both sides.
* :class:`PageCrops` serves training crops from those pages exactly as upstream's
  ``TrainDs`` serves DocTamper images (grid-aligned and non-aligned crops, the same
  augmentation, 1 to 3 JPEG compressions), with a set share of crops that contain an edit.
* :class:`Mixed` draws each sample from DocTamper or from the pages, so the model keeps what
  it knows while it learns statements.
* :class:`Losses` is upstream's training objective (``main.py``), unchanged.
* :func:`validate_pages` and :func:`validate_doctamper` score a model during training.
"""

from __future__ import annotations

import json
import random
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .pages import char_boxes, edit_mask, page_scores, render_pages

# ---------------------------------------------------------------- page cache

def _source(record: dict) -> str:
    """The genuine statement a file was made from (for the train/validation split)."""
    sid = record.get("source_statement_id") or record.get("laundered_from") \
        or record["statement_id"]
    return sid.split("__")[0]


def bank_of(entry: dict) -> str:
    """The bank of a cached page (its source id is ``<bank_id>_<seed>``)."""
    return entry.get("bank") or entry["source"].rsplit("_", 1)[0]


def held_out(path: Path) -> bool:
    """True inside a folder marked with a ``.heldout`` file (a test set: never trained on)."""
    return any((d / ".heldout").exists() for d in Path(path).resolve().parents)


def build_page_cache(folders: list[Path], cache: Path, dpi: int = 150,
                     val_fraction: float = 0.1, log=print) -> list[dict]:
    """Render the statements under ``folders`` into ``cache``; return the page index.

    Reuses pages already in the cache, so it is cheap to call again with more folders.
    """
    import cv2

    cache.mkdir(parents=True, exist_ok=True)
    index_file = cache / "index.json"
    index = {e["key"]: e for e in json.loads(index_file.read_text())} \
        if index_file.exists() else {}
    for f in folders:
        if held_out(Path(f).expanduser() / "x") or any(Path(f).expanduser().rglob(".heldout")):
            raise ValueError(f"{f} is (or contains) a held-out test set: never train on it")
    files = sorted({p for f in folders for p in Path(f).expanduser().rglob("*.json")})
    added = 0
    for n, json_path in enumerate(files, 1):
        pdf = json_path.with_suffix(".pdf")
        try:
            record = json.loads(json_path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if record.get("label") not in ("genuine", "forged") or not pdf.exists():
            continue
        sid = record["statement_id"]
        if f"{sid}#0" in index:
            continue
        source = _source(record)
        split = "val" if zlib.crc32(source.encode()) % 1000 < val_fraction * 1000 else "train"
        edits = record.get("edits", []) if record["label"] == "forged" else []
        for page_no, rgb in enumerate(render_pages(pdf, dpi=dpi)):
            key = f"{sid}#{page_no}"
            mask = edit_mask(edits, page_no, rgb.shape[:2], dpi)
            stem = cache / "pages" / f"{sid}_p{page_no}"
            stem.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(f"{stem}.png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            cv2.imwrite(f"{stem}_mask.png", mask * 255)
            np.save(f"{stem}_boxes.npy", np.array(char_boxes(rgb), np.int32).reshape(-1, 4))
            index[key] = {"key": key, "stem": str(stem.relative_to(cache)), "split": split,
                          "label": record["label"], "edited": bool(mask.any()),
                          "method": record.get("forgery", {}).get("method", "genuine"),
                          "laundering": record.get("laundering", {}).get("method", "none"),
                          "source": source, "bank": record.get("bank_id", "")}
            added += 1
        if n % 200 == 0:
            log(f"  cache: {n}/{len(files)} label files read, {added} pages added")
            index_file.write_text(json.dumps(list(index.values())))
    index_file.write_text(json.dumps(list(index.values())))
    log(f"  cache: {len(index)} pages ({added} new) in {cache}")
    return list(index.values())


# ---------------------------------------------------------------- training data

class PageCrops:
    """Upstream-style training crops from cached statement pages."""

    def __init__(self, cache: Path, entries: list[dict], length: int, edited_share: float = 0.6,
                 min_qf: int = 75):
        import cfg
        from ds import get_align_aug, get_non_align_aug, img_totsr, load_qt, mask_totsr

        self.cache = Path(cache)
        self.edited = [e for e in entries if e["edited"]]
        self.clean = [e for e in entries if not e["edited"]]
        if not self.edited or not self.clean:
            raise ValueError(f"need pages with and without edits; got {len(self.edited)} "
                             f"edited and {len(self.clean)} clean")
        self.length, self.edited_share, self.min_qf = length, edited_share, min_qf
        self.qts = load_qt(cfg.qt_path)
        self.align_aug, self.non_align_aug = get_align_aug(), get_non_align_aug()
        self.img_totsr, self.mask_totsr = img_totsr, mask_totsr

    def __len__(self):
        return self.length

    def __getitem__(self, _):
        from copy import deepcopy

        import cv2
        from ds import bbox_2_mask, multi_jpeg
        from PIL import Image

        pool = self.edited if random.random() < self.edited_share else self.clean
        entry = random.choice(pool)
        stem = self.cache / entry["stem"]
        img = cv2.cvtColor(cv2.imread(f"{stem}.png"), cv2.COLOR_BGR2RGB)
        mask = (cv2.imread(f"{stem}_mask.png", cv2.IMREAD_GRAYSCALE) > 0).astype(np.uint8)
        boxes = [tuple(int(v) for v in b) for b in np.load(f"{stem}_boxes.npy")]
        is_align = random.random() > 0.5
        aug = (self.align_aug if is_align else self.non_align_aug)(image=img, mask=mask,
                                                                   bboxes=boxes)
        img, mask, boxes = aug["image"], aug["mask"], aug["bboxes"]
        h, w = mask.shape
        ocr = bbox_2_mask(boxes, h, w)
        dct, img, qfs = multi_jpeg(deepcopy(Image.fromarray(img)), num_jpeg=random.randint(1, 3),
                                   min_qf=self.min_qf, upper_bound=100)
        return {"img": self.img_totsr(img), "dct": np.clip(np.abs(dct), 0, 20),
                "qt": self.qts[qfs[-1]], "mask": self.mask_totsr(image=mask.copy())["image"].long(),
                "ocr_mask": self.mask_totsr(image=ocr.copy())["image"].long(),
                "img_name": entry["key"], "min_qf": self.min_qf, "is_align": is_align}


class Mixed:
    """Each sample from ``doctamper`` with probability ``doctamper_share``, else ``pages``."""

    def __init__(self, pages, doctamper=None, doctamper_share: float = 0.3):
        self.pages, self.doctamper = pages, doctamper
        self.share = doctamper_share if doctamper is not None else 0.0
        self.length = len(pages)

    def __len__(self):
        return self.length

    def __getitem__(self, i):
        item = self.doctamper[i] if random.random() < self.share else self.pages[i]
        item["min_qf"] = int(item["min_qf"])
        return item


def worker_init(worker_id: int) -> None:
    """Fresh random state per worker, and reopen DocTamper's LMDB after the fork."""
    import lmdb
    import torch

    info = torch.utils.data.get_worker_info()
    seed = (torch.initial_seed() + worker_id) % 2**32
    random.seed(seed)
    np.random.seed(seed)
    dt = getattr(info.dataset, "doctamper", None)
    if dt is not None and hasattr(dt, "lmdb"):
        path = dt.lmdb.path()
        dt.lmdb.close()
        dt.lmdb = lmdb.open(path, max_readers=64, readonly=True, lock=False, readahead=False,
                            meminit=False)


# ---------------------------------------------------------------- objective

class Losses:
    """Upstream ADCD-Net's training loss (``main.py``), with its weights from ``cfg``."""

    def __init__(self):
        import cfg
        from loss.lovasz_loss import LovaszLoss
        from loss.soft_ce_loss import SoftCrossEntropyLoss
        from torch import nn

        self.cfg = cfg
        self.loc_ce = SoftCrossEntropyLoss(smooth_factor=0.1, reduction="mean", ignore_index=None)
        self.loc_lovasz = LovaszLoss(mode="multiclass", per_image=True)
        self.rec_l1 = nn.L1Loss()
        self.align_ce = nn.CrossEntropyLoss()

    def __call__(self, outputs, img, mask, is_align) -> dict:
        import torch

        cfg = self.cfg
        logits, norm_feats, align_logits, (rec, norm_dct), focal_losses = outputs
        parts = {
            "ce": cfg.ce_w * self.loc_ce(logits.float(), mask),
            "iou": self.loc_lovasz(logits.float(), mask),
            "rec": cfg.rec_w * (self.rec_l1(rec[:, :3], img) + self.rec_l1(rec[:, -1], norm_dct)),
            "align_ce": self.align_ce(align_logits, is_align.long()),
            "focal": torch.stack([cfg.focal_w * (fl.sum() / (fl != 0).sum().clamp_min(1))
                                  for fl in focal_losses]).sum(),
            "norm": cfg.norm_w * torch.stack([f.norm(dim=1).mean() for f in norm_feats]).mean(),
        }
        parts["total"] = sum(parts.values())
        return parts


# ---------------------------------------------------------------- validation

@dataclass
class PageValidation:
    f1: float  # mean per-page F1 on edited pages (the checkpoint score)
    auc: float | None  # edited pages against clean pages, by page peak score
    clean_area: float  # mean share of a clean page predicted tampered (false alarms)
    pages: int


def validate_pages(model, cache: Path, entries: list[dict], device: str, limit: int = 300,
                   batch: int = 16) -> PageValidation:
    """Whole-page predictions on validation pages (the same pages every time)."""
    import cv2

    from .pages import PageDetector

    edited = [e for e in entries if e["edited"]][:limit // 2]
    clean = [e for e in entries if not e["edited"]][:limit - len(edited)]
    det = PageDetector.from_model(model, device, "fp16", batch)
    f1s, peaks_e, peaks_c, areas_c = [], [], [], []
    was_training = model.training
    model.eval()
    for e in edited + clean:
        stem = Path(cache) / e["stem"]
        rgb = cv2.cvtColor(cv2.imread(f"{stem}.png"), cv2.COLOR_BGR2RGB)
        from .pages import ocr_mask

        prob = det.predict(rgb, ocr_mask(rgb)).prob
        s = page_scores(prob)
        if e["edited"]:
            gt = cv2.imread(f"{stem}_mask.png", cv2.IMREAD_GRAYSCALE) > 0
            pred = prob > 0.5
            tp = float((pred & gt).sum())
            p, r = tp / (pred.sum() + 1e-8), tp / (gt.sum() + 1e-8)
            f1s.append(2 * p * r / (p + r + 1e-8))
            peaks_e.append(s["peak"])
        else:
            peaks_c.append(s["peak"])
            areas_c.append(s["area"])
    if was_training:
        model.train()
    auc = None
    if peaks_e and peaks_c:
        wins = sum((pe > pc) + 0.5 * (pe == pc) for pe in peaks_e for pc in peaks_c)
        auc = wins / (len(peaks_e) * len(peaks_c))
    return PageValidation(f1=float(np.mean(f1s)) if f1s else 0.0, auc=auc,
                          clean_area=float(np.mean(areas_c)) if areas_c else 0.0,
                          pages=len(edited) + len(clean))


def validate_doctamper(model, name: str, device: str, limit: int = 300, batch: int = 8) -> float:
    """Mean per-image F1 on the first ``limit`` images of a DocTamper set (Doc Protocol)."""
    import torch
    from ds import DtdValDs, pad_collate

    ds = DtdValDs(name)
    loader = torch.utils.data.DataLoader(torch.utils.data.Subset(ds, range(min(limit, len(ds)))),
                                         batch_size=batch, collate_fn=pad_collate)
    was_training = model.training
    model.eval()
    f1s = []
    with torch.inference_mode():
        for img, dct, qt, mask, ocr, _names, sizes in loader:
            with torch.autocast(device_type="cuda", dtype=torch.float16,
                                enabled=device.startswith("cuda")):
                logits = model(img.to(device), dct.to(device), qt.to(device), mask.to(device),
                               ocr.to(device), is_train=False)[0]
            pred = logits.argmax(1).cpu()
            for p, y, (h, w) in zip(pred, mask, sizes, strict=True):
                p, y = p[:h, :w], y.squeeze(0)[:h, :w]
                tp = float((p * y).sum())
                pr, rc = tp / (float(p.sum()) + 1e-8), tp / (float(y.sum()) + 1e-8)
                f1s.append(2 * pr * rc / (pr + rc + 1e-8))
    if was_training:
        model.train()
    return float(np.mean(f1s)) if f1s else 0.0
