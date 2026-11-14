"""Image-level forgeries of generated statements: the edits pixel forensics are meant to see.

A PDF edit or a rebuild is drawn by the same renderer as the rest of the page, so the page
image carries no local trace of the change (ADCD-Net scores chance on them, see
``experiments/results/adcdnet_pages_v4.md``). Forgers who work on a scan or a screenshot
instead change pixels, and leave traces. This module makes such forgeries from genuine
statements, choosing what to change exactly as the PDF-edit forger does (``pdf_edit._plan``:
inflate a credit, with or without fixing every later balance; inflate the closing balance;
change the holder's name), so the labels and claimed values have the same form.

Methods
-------
``splice``
    Paint over the value with the cell background and type the new one, in an image editor:
    the patch is drawn separately and re-saved as JPEG at its own quality before being
    pasted back, as a value cut from another image would be.
``inpaint``
    The same edit finished by a diffusion inpainting model (default: Stable Diffusion XL
    inpainting), as AI photo editors do: the spliced patch is redrawn by the model at
    ``strength`` (1.0 regenerates it from noise, so the digits may come out garbled; lower
    values keep the typed digits and add the model's texture). Only the masked pixels are
    taken from the model's output, so the label stays exact.

Every page is then saved the way ``launder.py`` rasterises statements (PyMuPDF JPEG at the
same resolution and quality, wrapped in a new PDF), so these forgeries are compared with
the rasterised genuine statements and differ from them only where they were edited.
"""

from __future__ import annotations

import copy
import random
from pathlib import Path

import numpy as np

from ..reader import font_key
from .launder import _laundered_at, _pdf_date
from .pdf_edit import _font_index, _plan

METHODS = ("splice", "inpaint")
DEFAULT_MODEL = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1"
NEGATIVE = "blurry, handwriting, distorted, smudged, watermark, colourful"
_FALLBACK_FONTS = {
    (False, False): ("LiberationSans-Regular", "DejaVuSans", "Arial"),
    (True, False): ("LiberationSans-Bold", "DejaVuSans-Bold", "Arial Bold"),
    (False, True): ("LiberationSans-Italic", "DejaVuSans-Oblique", "Arial Italic"),
    (True, True): ("LiberationSans-BoldItalic", "DejaVuSans-BoldOblique", "Arial Bold Italic"),
}


def _font(span_font: str, size_px: float):
    """A PIL font for ``span_font``: the same family if installed, else a sans fallback."""
    from PIL import ImageFont

    family, style = font_key(span_font)
    index = _font_index()
    path = index.get((family, style))
    if path is None:
        bold, italic = "bold" in style, "italic" in style or "oblique" in style
        for name in _FALLBACK_FONTS[(bold, italic)]:
            path = index.get(font_key(name))
            if path:
                break
    size = max(4, round(size_px))
    if path is None:
        return ImageFont.load_default(size=size)
    return ImageFont.truetype(path, size)


def _background(page: np.ndarray, x0: int, x1: int, y: int) -> tuple[int, int, int]:
    """The lighter of the pixels just left and right of a value: the cell background."""
    h, w = page.shape[:2]
    y = min(max(y, 0), h - 1)
    samples = [page[y, min(max(x, 0), w - 1)] for x in (x0 - 3, x1 + 2)]
    return tuple(int(c) for c in max(samples, key=lambda p: int(p.sum())))


def _jpeg_roundtrip(patch: np.ndarray, quality: int) -> np.ndarray:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(patch).save(buf, "JPEG", quality=quality)
    return np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))


def splice(page: np.ndarray, edit: dict, scale: float, rng: random.Random) -> tuple[list, dict]:
    """Retype ``edit`` on ``page`` (in place). Returns the changed box in pixels and details."""
    from PIL import Image, ImageDraw

    span = edit["span"]
    color = ((span["color"] >> 16) & 255, (span["color"] >> 8) & 255, span["color"] & 255)
    font = _font(span["font"], span["size"] * scale)
    x0, y0, x1, y1 = (v * scale for v in span["bbox"])
    width = font.getlength(edit["new"])
    nx0 = x1 - width if edit["align"] == "right" else x0
    margin = 2 + rng.randint(0, 3)
    h, w = page.shape[:2]
    bx0 = max(0, int(min(x0, nx0)) - margin)
    by0 = max(0, int(y0) - margin)
    bx1 = min(w, int(np.ceil(max(x1, nx0 + width))) + margin)
    by1 = min(h, int(np.ceil(y1)) + margin)
    bg = _background(page, int(x0), int(x1), int((y0 + y1) / 2))

    patch = Image.new("RGB", (bx1 - bx0, by1 - by0), bg)
    draw = ImageDraw.Draw(patch)
    draw.text((nx0 - bx0, span["origin"][1] * scale - by0), edit["new"], font=font, fill=color,
              anchor="ls")
    patch = np.array(patch)
    quality = rng.randint(55, 92)
    patch = _jpeg_roundtrip(patch, quality)
    page[by0:by1, bx0:bx1] = patch
    return [bx0, by0, bx1, by1], {"patch_jpeg_quality": quality, "font": font.getname()[0]}


class DiffusionInpainter:
    """A diffusers inpainting pipeline. Call with lists of crops, masks and prompts."""

    def __init__(self, model: str = DEFAULT_MODEL, device: str = "cuda", steps: int = 30,
                 guidance: float = 7.0, size: int = 1024):
        import torch
        from diffusers import AutoPipelineForInpainting

        dtype = torch.float16 if device.startswith("cuda") else torch.float32
        try:
            pipe = AutoPipelineForInpainting.from_pretrained(model, torch_dtype=dtype,
                                                             variant="fp16")
        except (OSError, ValueError):  # no fp16 weights published
            pipe = AutoPipelineForInpainting.from_pretrained(model, torch_dtype=dtype)
        self.pipe = pipe.to(device)
        self.pipe.set_progress_bar_config(disable=True)
        self.model, self.device, self.steps, self.guidance, self.size = (model, device, steps,
                                                                         guidance, size)

    def __call__(self, crops: list[np.ndarray], masks: list[np.ndarray], prompts: list[str],
                 strength: float, seed: int) -> list[np.ndarray]:
        import torch
        from PIL import Image

        s = self.size
        images = [Image.fromarray(c).resize((s, s), Image.LANCZOS) for c in crops]
        mask_images = [Image.fromarray(m * 255).resize((s, s), Image.NEAREST) for m in masks]
        generator = torch.Generator(self.device).manual_seed(seed)
        out = self.pipe(prompt=prompts, negative_prompt=[NEGATIVE] * len(prompts), image=images,
                        mask_image=mask_images, strength=strength, height=s, width=s,
                        num_inference_steps=self.steps, guidance_scale=self.guidance,
                        generator=generator).images
        return [np.array(o.convert("RGB").resize(c.shape[1::-1], Image.LANCZOS))
                for o, c in zip(out, crops, strict=True)]


def _crop_window(box: list[int], shape: tuple[int, int], minimum: int = 320) -> list[int]:
    """A square window around ``box`` with context on every side, inside the page."""
    h, w = shape
    side = min(max(minimum, box[2] - box[0] + 96, box[3] - box[1] + 96), h, w)
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    x0 = min(max(0, cx - side // 2), w - side)
    y0 = min(max(0, cy - side // 2), h - side)
    return [x0, y0, x0 + side, y0 + side]


def inpaint(page: np.ndarray, boxes: list[list[int]], texts: list[str], inpainter,
            strength: float, seed: int, batch: int = 8) -> None:
    """Redraw each box of ``page`` (in place) with ``inpainter``, keeping pixels outside it."""
    jobs = []
    for box, text in zip(boxes, texts, strict=True):
        win = _crop_window(box, page.shape[:2])
        crop = page[win[1]:win[3], win[0]:win[2]].copy()
        mask = np.zeros(crop.shape[:2], np.uint8)
        mask[box[1] - win[1]:box[3] - win[1], box[0] - win[0]:box[2] - win[0]] = 1
        prompt = (f"scan of a printed bank statement, the amount \"{text}\" in small black "
                  "sans-serif print on a plain background, crisp")
        jobs.append((win, crop, mask, prompt))
    for i in range(0, len(jobs), batch):
        chunk = jobs[i:i + batch]
        outs = inpainter([j[1] for j in chunk], [j[2] for j in chunk], [j[3] for j in chunk],
                         strength, seed + i)
        for (win, crop, mask, _), out in zip(chunk, outs, strict=True):
            region = page[win[1]:win[3], win[0]:win[2]]
            region[mask == 1] = out[mask == 1]


def _save_raster_pdf(pages: list[np.ndarray], page_size: tuple[float, float], out: Path,
                     quality: int, stamp: str) -> None:
    """Wrap page images in a new PDF exactly as ``launder._raster`` does."""
    import pymupdf

    with pymupdf.open() as new:
        for img in pages:
            h, w = img.shape[:2]
            pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, np.ascontiguousarray(img).tobytes(), 0)
            target = new.new_page(width=page_size[0], height=page_size[1])
            target.insert_image(target.rect, stream=pix.tobytes("jpeg", jpg_quality=quality))
        new.set_metadata({"creationDate": stamp, "modDate": stamp, "producer": "",
                          "creator": "", "title": "", "author": ""})
        new.save(out, garbage=3, deflate=True)


def forge_image(genuine_pdf: str | Path, record: dict, out_pdf: str | Path, *, operation: str,
                consistent: bool = False, method: str = "splice", seed: int = 0, dpi: int = 150,
                jpeg_quality: int = 85, inpainter=None, strength: float = 0.75) -> dict:
    """Write an image-edited, rasterised forgery of ``genuine_pdf``; return its label record."""
    from ..signals.image.pages import render_pages

    if method not in METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from {', '.join(METHODS)}")
    if method == "inpaint" and inpainter is None:
        raise ValueError("method 'inpaint' needs an inpainter (DiffusionInpainter)")
    if "layout" not in record:
        raise ValueError("record has no 'layout'; regenerate it with the current generator")
    rng = random.Random(seed)
    claimed, edits = _plan(record, operation, consistent, rng, seed)
    scale = dpi / 72.0
    pages = render_pages(genuine_pdf, dpi=dpi)

    done = []
    for page_no in sorted({e["span"]["page"] for e in edits}):
        page_edits = [e for e in edits if e["span"]["page"] == page_no]
        boxes = []
        for e in page_edits:
            box, details = splice(pages[page_no], e, scale, rng)
            boxes.append(box)
            done.append((e, box, details))
        if method == "inpaint":
            inpaint(pages[page_no], boxes, [e["new"] for e in page_edits], inpainter, strength,
                    seed)

    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    when = _laundered_at(record, rng)
    work = out_pdf.with_name(out_pdf.stem + ".partial.pdf")
    _save_raster_pdf(pages, tuple(record["layout"]["page_size"]), work, jpeg_quality,
                     _pdf_date(when))
    work.replace(out_pdf)

    variant = operation + ("_consistent" if consistent else "")
    claimed = copy.deepcopy(claimed)
    claimed.pop("layout", None)
    claimed.update({
        "statement_id": out_pdf.stem,
        "label": "forged",
        "pdf": out_pdf.name,
        "source_statement_id": record["statement_id"],
        "forgery": {
            "method": f"image_{method}",
            "operation": operation,
            "variant": variant,
            "balance_consistent": operation == "holder_name" or consistent,
            "seed": seed,
            "inpaint_model": getattr(inpainter, "model", None) if method == "inpaint" else None,
            "inpaint_strength": strength if method == "inpaint" else None,
        },
        "edits": [
            {
                "field": e["field"],
                "row": e["row"],
                "page": e["span"]["page"],
                "old": e["old"],
                "new": e["new"],
                "old_bbox": e["span"]["bbox"],
                "mask_bbox": [round(v / scale, 3) for v in box],
                **details,
            }
            for e, box, details in done
        ],
        "laundering": {
            "method": "raster",
            "seed": seed,
            "laundered_at": when.isoformat(),
            "dpi": dpi,
            "jpeg_quality": jpeg_quality,
            "tool": "pymupdf",
        },
    })
    return claimed
