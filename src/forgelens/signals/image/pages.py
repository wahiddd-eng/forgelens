"""Run ADCD-Net on whole statement pages.

ADCD-Net was trained on 512 x 512 crops of document images, and the Doc Protocol shrinks each
test image to at most 512 pixels on its longest side. A statement page shrunk that far has
unreadable text, so here a page is rendered at a fixed resolution, cut into overlapping 512 x
512 tiles, each tile is prepared exactly as upstream prepares a DocTamper image (single JPEG
compression at quality 100, DCT coefficients, the quality-100 quantisation table, an OCR
mask), and the tiles' tampering probabilities are averaged back into one page map.

The OCR mask marks characters. Instead of running an OCR engine on every page, characters
are found as connected blobs of ink and boxed, then each box is enlarged by 10% as upstream
does with DocTamper's character boxes (``bbox_2_mask``). On clean rendered statements this
finds the same characters an OCR engine would, and it works the same on rasterised pages.

Ground-truth masks come from the forgery labels: each edit records the PDF-point box it
changed (``mask_bbox``) and its page.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

TILE = 512
STRIDE = 384  # tiles overlap by a quarter, so no character sits only on a tile edge


def render_pages(pdf: str | Path, dpi: int = 150, password: str | None = None) -> list[np.ndarray]:
    """Every page of ``pdf`` as an RGB uint8 array."""
    from forgelens.reader import open_pdf

    pages = []
    with open_pdf(pdf, password) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width,
                                                                     pix.n)
            pages.append(img[:, :, :3].copy())
    return pages


def edit_mask(edits: list[dict], page: int, shape: tuple[int, int], dpi: int) -> np.ndarray:
    """0/1 mask of the regions edited on ``page`` (labels give boxes in PDF points)."""
    mask = np.zeros(shape, np.uint8)
    scale = dpi / 72.0
    h, w = shape
    for e in edits:
        if e.get("page") != page or not e.get("mask_bbox"):
            continue
        x0, y0, x1, y1 = (v * scale for v in e["mask_bbox"])
        x0, y0 = max(0, int(np.floor(x0))), max(0, int(np.floor(y0)))
        x1, y1 = min(w, int(np.ceil(x1))), min(h, int(np.ceil(y1)))
        mask[y0:y1, x0:x1] = 1
    return mask


def char_boxes(rgb: np.ndarray, ink: int = 160) -> list[tuple[int, int, int, int]]:
    """Boxes (x0, y0, x1, y1) of character-sized blobs of ink.

    Blobs much larger than a character (table rules, logos, filled boxes) and specks are
    left out; touching characters stay one box, as an OCR engine's word pieces would.
    """
    import cv2

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    dark = (gray < ink).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    h, w = gray.shape
    max_h, max_w = max(48, 0.03 * h), max(240, 0.15 * w)  # floors for small images
    boxes = []
    for x, y, bw, bh, area in stats[1:]:
        if area < 4 or bh > max_h or bw > max_w:
            continue
        if bw > 12 * bh:  # a horizontal rule, not a run of text
            continue
        boxes.append((int(x), int(y), int(x + bw), int(y + bh)))
    return boxes


def ocr_mask(rgb: np.ndarray, expand_ratio: float = 0.1) -> np.ndarray:
    """Upstream's ``bbox_2_mask`` applied to :func:`char_boxes`."""
    h, w = rgb.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    for x0, y0, x1, y1 in char_boxes(rgb):
        bw, bh = x1 - x0, y1 - y0
        x0 = int(max(0, x0 - bw * expand_ratio))
        y0 = int(max(0, y0 - bh * expand_ratio))
        x1 = int(min(w, x1 + bw * expand_ratio))
        y1 = int(min(h, y1 + bh * expand_ratio))
        mask[y0:y1, x0:x1] = 1
    return mask


def tile_origins(length: int, tile: int = TILE, stride: int = STRIDE) -> list[int]:
    """Start offsets that cover ``length`` with tiles, the last one flush with the end."""
    if length <= tile:
        return [0]
    starts = list(range(0, length - tile, stride))
    starts.append(length - tile)
    return starts


@dataclass
class PageResult:
    prob: np.ndarray  # H x W tampering probability
    tiles: int


class PageDetector:
    """ADCD-Net over tiles of a page. Build once, then call :meth:`predict` per page."""

    def __init__(self, paths, device: str = "cuda", precision: str = "fp16", batch: int = 16,
                 allow_missing_keys: bool = False):
        import torch

        from . import adcdnet

        adcdnet.configure(paths, adcdnet.Settings())
        self.model, self.info = adcdnet.load_model(paths, device, allow_missing_keys)
        from ds import img_totsr, load_qt, mask_totsr, multi_jpeg, pad_collate  # upstream

        self._img_totsr, self._mask_totsr = img_totsr, mask_totsr
        self._multi_jpeg, self._pad_collate = multi_jpeg, pad_collate
        import cfg

        self._qt = load_qt(cfg.qt_path)[100]  # what DtdValDs uses
        self.device = torch.device(device)
        self.amp = self.device.type == "cuda" and precision == "fp16"
        self.batch = batch

    @classmethod
    def from_model(cls, model, device: str = "cuda", precision: str = "fp16",
                   batch: int = 16) -> PageDetector:
        """Wrap a model that is already built and configured (e.g. one being trained)."""
        import cfg
        import torch
        from ds import img_totsr, load_qt, mask_totsr, multi_jpeg, pad_collate  # upstream

        self = cls.__new__(cls)
        self.model, self.info = model, {}
        self._img_totsr, self._mask_totsr = img_totsr, mask_totsr
        self._multi_jpeg, self._pad_collate = multi_jpeg, pad_collate
        self._qt = load_qt(cfg.qt_path)[100]
        self.device = torch.device(device)
        self.amp = self.device.type == "cuda" and precision == "fp16"
        self.batch = batch
        return self

    def _item(self, tile_rgb: np.ndarray, tile_ocr: np.ndarray) -> dict:
        from copy import deepcopy

        from PIL import Image

        img = Image.fromarray(tile_rgb)
        dct, img, _ = self._multi_jpeg(deepcopy(img), num_jpeg=-1, min_qf=-1, upper_bound=-1,
                                       jpeg_record=[100])
        empty = np.zeros(tile_ocr.shape, np.uint8)
        return {"img": self._img_totsr(img), "dct": np.clip(np.abs(dct), 0, 20),
                "qt": self._qt, "mask": self._mask_totsr(image=empty)["image"].long(),
                "ocr_mask": self._mask_totsr(image=tile_ocr.copy())["image"].long(),
                "img_name": "tile"}

    def predict(self, rgb: np.ndarray, ocr: np.ndarray | None = None) -> PageResult:
        import torch

        h, w = rgb.shape[:2]
        if ocr is None:
            ocr = ocr_mask(rgb)
        # Pad small pages with white so every tile is full size, as in training.
        ph, pw = max(h, TILE), max(w, TILE)
        if (ph, pw) != (h, w):
            canvas = np.full((ph, pw, 3), 255, np.uint8)
            canvas[:h, :w] = rgb
            ocr_canvas = np.zeros((ph, pw), np.uint8)
            ocr_canvas[:h, :w] = ocr
            rgb, ocr = canvas, ocr_canvas
        total = np.zeros((ph, pw), np.float32)
        count = np.zeros((ph, pw), np.float32)
        origins = [(y, x) for y in tile_origins(ph) for x in tile_origins(pw)]
        with torch.inference_mode():
            for i in range(0, len(origins), self.batch):
                chunk = origins[i:i + self.batch]
                items = [self._item(rgb[y:y + TILE, x:x + TILE], ocr[y:y + TILE, x:x + TILE])
                         for y, x in chunk]
                img, dct, qt, mask, ocr_t, _, _ = self._pad_collate(items)
                args = [t.to(self.device) for t in (img, dct, qt, mask, ocr_t)]
                with torch.autocast(device_type=self.device.type, dtype=torch.float16,
                                    enabled=self.amp):
                    logits = self.model(*args, is_train=False)[0]
                prob = torch.softmax(logits.float(), dim=1)[:, 1, :TILE, :TILE].cpu().numpy()
                for (y, x), p in zip(chunk, prob, strict=True):
                    total[y:y + TILE, x:x + TILE] += p
                    count[y:y + TILE, x:x + TILE] += 1
        return PageResult(prob=(total / np.maximum(count, 1))[:h, :w], tiles=len(origins))


def page_scores(prob: np.ndarray, top: int = 500) -> dict[str, float]:
    """Statement-level evidence from one page's probability map.

    ``area``: share of pixels predicted tampered (probability over 0.5);
    ``peak``: mean of the ``top`` highest probabilities, which a single edited amount of a
    few hundred pixels can raise even when it is a tiny share of the page.
    """
    flat = prob.ravel()
    k = min(top, flat.size)
    peak = float(np.partition(flat, flat.size - k)[-k:].mean())
    return {"area": float((prob > 0.5).mean()), "peak": peak}
