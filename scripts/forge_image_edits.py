"""Create image-edited forgeries (spliced or AI-inpainted) from generated genuine statements.

Reads every genuine ``<id>.json`` (with its ``<id>.pdf``) and writes rasterised forged PDFs
with their labels (see ``forgelens.forgery.image_edit``). Compare them with the rasterised
genuine statements (``launder_pdfs.py --method raster``, same DPI and JPEG quality).

    # spliced edits, CPU only
    python scripts/forge_image_edits.py --genuine ~/forgelens-data/synthetic_v4/genuine \\
        --out ~/forgelens-data/synthetic_v4/forged_image/splice --method splice

    # AI inpainting on a GPU, the work split over two GPUs (run once per shard)
    CUDA_VISIBLE_DEVICES=3 python scripts/forge_image_edits.py --genuine ... \\
        --out ~/forgelens-data/synthetic_v4/forged_image/inpaint --method inpaint --shard 0/2

Safe to run again: forgeries already written are skipped.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import zlib
from pathlib import Path

from forgelens.forgery import write_masks
from forgelens.forgery.image_edit import DEFAULT_MODEL, METHODS, forge_image
from forgelens.utils import stable_seed

# Same mix as the PDF-edit forgeries (scripts/forge_pdf_edits.py).
VARIANTS = (
    ("credit_amount", False, 0.30),
    ("credit_amount", True, 0.35),
    ("closing_balance", False, 0.20),
    ("holder_name", False, 0.15),
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--genuine", type=Path, required=True, help="folder of genuine PDF + JSON")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--method", choices=METHODS, required=True)
    p.add_argument("--per-statement", type=int, default=1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--dpi", type=int, default=150, help="as launder_pdfs.py --method raster")
    p.add_argument("--jpeg-quality", type=int, default=85, help="as launder_pdfs.py")
    p.add_argument("--masks", action="store_true", help="also write PNG masks")
    p.add_argument("--limit", type=int, help="at most N genuine statements (smoke test)")
    p.add_argument("--shard", default="0/1", help="i/n: do every n-th statement, from the i-th")
    p.add_argument("--preview", type=int, default=0, metavar="N",
                   help="save before/after pictures of the first N forgeries in <out>/preview")
    g = p.add_argument_group("inpainting")
    g.add_argument("--model", default=DEFAULT_MODEL, help="diffusers inpainting model")
    g.add_argument("--strength", type=float, nargs="+", default=[0.6, 0.8, 1.0],
                   help="chosen per forgery from these (1.0 regenerates the value entirely)")
    g.add_argument("--steps", type=int, default=30)
    g.add_argument("--device", default="cuda")
    return p.parse_args(argv)


def save_preview(genuine_pdf: Path, label: dict, forged_pdf: Path, out: Path) -> None:
    """Genuine | forged | forged with the edited region tinted, around the first edit."""
    import cv2
    import numpy as np

    from forgelens.signals.image.pages import edit_mask, render_pages

    e = label["edits"][0]
    page = e["page"]
    g = render_pages(genuine_pdf, dpi=150)[page]
    f = render_pages(forged_pdf, dpi=150)[page]
    m = edit_mask(label["edits"], page, f.shape[:2], 150).astype(bool)
    x0, y0, x1, y1 = (round(v * 150 / 72) for v in e["mask_bbox"])
    ys = slice(max(0, y0 - 60), min(f.shape[0], y1 + 60))
    xs = slice(max(0, x0 - 200), min(f.shape[1], x1 + 60))
    tint = f.copy()
    tint[m] = (0.6 * tint[m] + 0.4 * np.array([255, 0, 0])).astype(np.uint8)
    strip = np.concatenate([g[ys, xs], f[ys, xs], tint[ys, xs]], axis=1)
    strip = cv2.resize(strip, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.cvtColor(strip, cv2.COLOR_RGB2BGR))


def main(argv=None) -> int:
    args = parse_args(argv)
    shard, shards = (int(v) for v in args.shard.split("/"))
    records = []
    for json_path in sorted(args.genuine.rglob("*.json")):
        record = json.loads(json_path.read_text())
        if record.get("label") == "genuine" and "layout" in record \
                and json_path.with_suffix(".pdf").exists():
            records.append((json_path.with_suffix(".pdf"), record))
    if not records:
        print(f"No genuine statements with layouts in {args.genuine}", file=sys.stderr)
        return 1
    records = records[:args.limit] if args.limit else records
    # Shard by a hash of the id, so the split does not depend on what else is in the folder.
    records = [r for r in records
               if zlib.crc32(r[1]["statement_id"].encode()) % shards == shard]

    inpainter = None
    if args.method == "inpaint":
        from forgelens.forgery.image_edit import DiffusionInpainter

        print(f"loading {args.model} …", flush=True)
        inpainter = DiffusionInpainter(args.model, args.device, steps=args.steps)

    args.out.mkdir(parents=True, exist_ok=True)
    made = skipped = failed = 0
    start = time.time()
    for n, (pdf, record) in enumerate(records, 1):
        for k in range(args.per_statement):
            seed = stable_seed(args.seed, record["statement_id"], args.method, k)
            rng = random.Random(seed)
            operation, consistent, _ = rng.choices(VARIANTS, weights=[v[2] for v in VARIANTS])[0]
            variant = operation + ("_consistent" if consistent else "")
            stem = f"{record['statement_id']}__img{args.method}_{variant}_{k:02d}"
            out_pdf = args.out / f"{stem}.pdf"
            if out_pdf.exists() and out_pdf.with_suffix(".json").exists():
                skipped += 1
                continue
            strength = rng.choice(args.strength)
            try:
                label = forge_image(pdf, record, out_pdf, operation=operation,
                                    consistent=consistent, method=args.method, seed=seed,
                                    dpi=args.dpi, jpeg_quality=args.jpeg_quality,
                                    inpainter=inpainter, strength=strength)
            except ValueError as exc:  # e.g. a statement without credits
                print(f"skip {stem}: {exc}")
                failed += 1
                continue
            if args.masks:
                masks = write_masks(label, record["layout"]["page_size"], args.out / stem,
                                    dpi=args.dpi)
                label["masks"] = {"dpi": args.dpi, "files": [m.name for m in masks]}
            out_pdf.with_suffix(".json").write_text(json.dumps(label, indent=2))
            made += 1
            if made <= args.preview:
                save_preview(pdf, label, out_pdf, args.out / "preview" / f"{stem}.jpg")
        if n % 10 == 0 or n == len(records):
            rate = (time.time() - start) / max(made, 1)
            print(f"{n}/{len(records)} statements, {made} made, {skipped} already there, "
                  f"{failed} skipped, {rate:.1f}s each", flush=True)
    print(f"Created {made} {args.method} forgeries in {args.out}"
          + (f"; {skipped} already there" if skipped else "")
          + (f"; skipped {failed}" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
