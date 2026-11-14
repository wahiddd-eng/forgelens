"""Reproduce ADCD-Net's Doc Protocol results with the released checkpoint.

Runs the official ADCD-Net code (``third_party/ADCD-Net``, unedited) on the seven Doc
Protocol test sets and compares the per-image F1 with the published table. Settings and
metric match upstream's ``main.py`` evaluation, but in one process on one GPU (or the CPU),
with:

* a ``--check`` mode that verifies packages, checkpoints, data layout, OCR masks and GPU
  support before any GPU time is spent;
* per-image results, so any number can be recomputed or broken down;
* one CSV per dataset written atomically, so ``--resume`` after a crash or a reboot skips
  the datasets already done;
* images that fail to load recorded and counted instead of ending the run;
* the code version, packages, GPU and checkpoint hashes stored with the results.

Outputs, in ``<out>/adcdnet_<tag>/``:

* ``<dataset>.csv``: one row per image (pixel counts, precision, recall, F1, IoU, error);
* ``summary.csv``, ``summary.md``: one row per dataset with the published F1 beside ours;
* ``summary.json``: the same plus provenance and settings;
* ``masks/<dataset>/`` (with ``--save-masks N``): the first N predicted masks as PNG.

Examples:
    # check everything first (takes seconds)
    python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag dgx --check

    # a 20-image smoke test per set, then the full run
    python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag smoke --limit 20
    python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag dgx --resume
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from forgelens.evaluation import PixelCounts, image_scores, summarise
from forgelens.signals.image import adcdnet
from forgelens.utils import run_info

REPO = Path(__file__).resolve().parents[1]
FIELDS = ["dataset", "image", "height", "width", "tp", "pred", "gt", "precision", "recall",
          "f1", "iou", "error"]
SUMMARY_FIELDS = ["dataset", "short", "n", "n_failed", "n_empty_gt", "f1", "f1_ci_low",
                  "f1_ci_high", "published_f1", "delta", "flagged", "precision", "recall", "iou",
                  "pixel_f1", "pixel_iou", "seconds"]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, help="YAML file whose keys are these options "
                   "(dashes or underscores); command-line options override it")
    g = p.add_argument_group("files")
    g.add_argument("--ckpt", type=Path, help="ADCDNet.pth")
    g.add_argument("--docres", type=Path, help="docres.pkl")
    g.add_argument("--doctamper-root", type=Path,
                   help="folder with DocTamperV1/ and exp_data/ (qt_table.pk, pks/)")
    g.add_argument("--ocr-root", type=Path,
                   help="folder with <set>/char_seg/*.pkl (default <doctamper-root>/DocTamperData)")
    g.add_argument("--pkl-dir", type=Path, help="cross-domain path lists from build_path_pkl.py")
    g.add_argument("--qt-path", type=Path, help="qt_table.pk (default under --doctamper-root)")
    g.add_argument("--upstream", type=Path, default=REPO / "third_party" / "ADCD-Net")
    g = p.add_argument_group("what to run")
    g.add_argument("--datasets", nargs="+", default=["all"],
                   help="FCD SCD Test T-SROIE OSTF TPIC-13 RTM, or in-domain, cross-domain, all")
    g.add_argument("--limit", type=int, help="first N images per set (smoke test; the numbers "
                   "are then not comparable with the paper)")
    g.add_argument("--compression", choices=["protocol", "none"], default="protocol",
                   help="protocol: DocTamper's recorded JPEG qualities; none: QF 100 only")
    g.add_argument("--min-qf", type=int, default=75, help="selects the JPEG record file")
    g.add_argument("--shift-1p", action="store_true",
                   help="shift DocTamper images by one pixel (robustness test)")
    g = p.add_argument_group("how to run")
    g.add_argument("--device", default="cuda", help="cuda, cuda:1 or cpu")
    g.add_argument("--precision", choices=["fp16", "fp32"], default="fp16",
                   help="fp16 autocast as upstream does (GPU only)")
    g.add_argument("--batch-size", type=int, default=4)
    g.add_argument("--workers", type=int, default=4, help="data-loading processes")
    g.add_argument("--save-masks", type=int, default=0, metavar="N",
                   help="save the first N predicted masks of each set as PNG")
    g = p.add_argument_group("output")
    g.add_argument("--out", type=Path, default=REPO / "experiments" / "results")
    g.add_argument("--tag", required=True, help="name of this run, e.g. dgx or 4090")
    g.add_argument("--resume", action="store_true", help="reuse finished per-set CSVs")
    g.add_argument("--check", action="store_true", help="only run the pre-flight checks")
    g.add_argument("--allow-missing-ocr", action="store_true",
                   help="run even without OCR masks (scores will be lower)")
    g.add_argument("--allow-missing-keys", action="store_true",
                   help="run even if the checkpoint lacks some weights")
    return p


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _parser()
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path)
    first, _ = pre.parse_known_args(argv)
    if first.config:
        import yaml

        values = yaml.safe_load(first.config.read_text()) or {}
        known = {a.dest for a in parser._actions}
        defaults = {}
        for key, value in values.items():
            dest = key.replace("-", "_")
            if dest not in known:
                parser.error(f"{first.config}: unknown option {key!r}")
            defaults[dest] = value
        parser.set_defaults(**defaults)
        for action in parser._actions:  # a value from the file satisfies required=True
            if action.dest in defaults:
                action.required = False
    args = parser.parse_args(argv)
    for name in ("ckpt", "docres", "doctamper_root", "ocr_root", "pkl_dir", "qt_path",
                 "upstream", "out"):
        if getattr(args, name) is not None:
            setattr(args, name, Path(getattr(args, name)).expanduser())
    for name in ("ckpt", "docres"):
        if getattr(args, name) is None:
            parser.error(f"--{name} is required")
    try:
        args.datasets = adcdnet.resolve_datasets(
            args.datasets if isinstance(args.datasets, list) else [args.datasets])
    except ValueError as exc:
        parser.error(str(exc))
    if args.device == "cpu":
        args.precision = "fp32"
    return args


def _paths(args) -> adcdnet.Paths:
    return adcdnet.Paths(upstream=args.upstream, ckpt=args.ckpt, docres=args.docres,
                         doctamper_root=args.doctamper_root, ocr_root=args.ocr_root,
                         pkl_dir=args.pkl_dir, qt_path=args.qt_path)


def _settings(args) -> adcdnet.Settings:
    return adcdnet.Settings(min_qf=args.min_qf, compression=args.compression,
                            shift_1p=args.shift_1p)


# ---------------------------------------------------------------- evaluation

def _row(dataset: str, image: str, h: int, w: int, counts: PixelCounts | None,
         error: str = "") -> dict:
    row = {"dataset": dataset, "image": image, "height": h, "width": w, "tp": "", "pred": "",
           "gt": "", "precision": "", "recall": "", "f1": "", "iou": "", "error": error}
    if counts is not None:
        row.update(tp=counts.tp, pred=counts.pred, gt=counts.gt)
        row.update({k: f"{v:.6f}" for k, v in image_scores(counts).items()})
    return row


def evaluate_dataset(name: str, model, args, csv_path: Path) -> float:
    """Run the model on one dataset and write its per-image CSV. Returns seconds taken."""
    import torch
    from torch.utils.data import DataLoader
    from tqdm import tqdm

    dataset = adcdnet.build_dataset(name)
    n = len(dataset) if args.limit is None else min(args.limit, len(dataset))
    loader = DataLoader(adcdnet.Guarded(dataset, range(n)), batch_size=args.batch_size,
                        shuffle=False, num_workers=args.workers, collate_fn=adcdnet.collate,
                        worker_init_fn=adcdnet.worker_init,
                        pin_memory=args.device.startswith("cuda"))
    device = torch.device(args.device)
    use_amp = device.type == "cuda" and args.precision == "fp16"
    mask_dir = args.run_dir / "masks" / name
    saved = 0

    partial = csv_path.with_suffix(".partial.csv")
    start = time.time()
    with open(partial, "w", newline="") as f, torch.inference_mode():
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for padded, failures in tqdm(loader, desc=adcdnet.SHORT_NAMES[name], unit="batch"):
            for item in failures:
                writer.writerow(_row(name, item["img_name"], 0, 0, None, item["error"]))
            if padded is None:
                continue
            img, dct, qt, mask, ocr_mask, names, sizes = padded
            img, dct, qt = img.to(device), dct.to(device), qt.to(device)
            mask, ocr_mask = mask.to(device), ocr_mask.to(device)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
                logits = model(img, dct, qt, mask, ocr_mask, is_train=False)[0]
            pred = logits.argmax(1)
            for i, image_name in enumerate(names):
                if image_name == "padding":
                    continue
                h, w = (int(v) for v in sizes[i])
                p = pred[i, :h, :w]
                y = mask[i, 0, :h, :w]
                counts = PixelCounts(int((p * y).sum()), int(p.sum()), int(y.sum()))
                writer.writerow(_row(name, image_name, h, w, counts))
                if saved < args.save_masks:
                    import cv2

                    mask_dir.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(mask_dir / f"{image_name}.png"),
                                (p.to(torch.uint8) * 255).cpu().numpy())
                    saved += 1
    os.replace(partial, csv_path)  # a CSV without .partial is complete
    return time.time() - start


FLAG_AREA = 0.01  # an image counts as flagged when over 1% of its pixels are predicted tampered


def read_counts(csv_path: Path) -> tuple[list[PixelCounts], int, list[float]]:
    """Pixel counts, number of failed images, and each image's predicted-tampered fraction."""
    counts, failed, areas = [], 0, []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["error"]:
                failed += 1
            else:
                counts.append(PixelCounts(int(row["tp"]), int(row["pred"]), int(row["gt"])))
                areas.append(int(row["pred"]) / max(1, int(row["height"]) * int(row["width"])))
    return counts, failed, areas


# ---------------------------------------------------------------- reporting

def summary_row(name: str, counts: list[PixelCounts], failed: int, seconds: float | None,
                areas: list[float] | None = None) -> dict:
    """``flagged`` is the share of images with over 1% of pixels predicted tampered: the
    detection rate on forged sets and the false-alarm rate on authentic ones."""
    s = summarise(counts)
    if counts and s["n_empty_gt"] == len(counts):  # authentic images: F1 is undefined
        for key in ("f1", "f1_ci_low", "f1_ci_high", "precision", "recall", "iou", "pixel_f1",
                    "pixel_iou"):
            s[key] = None
    published = adcdnet.PUBLISHED_F1.get(name)
    flagged = (sum(a > FLAG_AREA for a in areas) / len(areas)) if areas else None
    return {"dataset": name, "short": adcdnet.SHORT_NAMES[name], "n_failed": failed,
            "published_f1": published, "flagged": flagged,
            "delta": None if s["f1"] is None or published is None else s["f1"] - published,
            "seconds": None if seconds is None else round(seconds, 1), **s}


def averages(rows: dict[str, dict]) -> dict[str, dict]:
    """Doc Protocol averages, only over complete groups."""
    groups = {"in_domain": adcdnet.DOCTAMPER_SETS, "cross_domain": adcdnet.CROSS_DOMAIN_SETS,
              "all": adcdnet.DOC_PROTOCOL}
    out = {}
    for group, names in groups.items():
        if all(n in rows and rows[n]["f1"] is not None for n in names):
            ours = sum(rows[n]["f1"] for n in names) / len(names)
            published = adcdnet.PUBLISHED_AVERAGES[group]
            out[group] = {"f1": ours, "published_f1": published, "delta": ours - published}
    return out


def _fmt(value) -> str:
    return "–" if value is None else f"{value:.3f}"


def markdown(rows: dict[str, dict], avgs: dict, partial: bool, run: dict) -> str:
    lines = ["# ADCD-Net evaluation", ""]
    if partial:
        lines += ["**Smoke test on a subset (`--limit`): not comparable with the paper.**", ""]
    lines += [("Per-image F1 of the tampered class, as in ADCD-Net (ICCV 2025) Table 1. "
               "CI: 95% interval of the mean. Flagged: share of images with over 1% of "
               "pixels predicted tampered (false alarms on authentic sets)."), "",
              "| Set | Images | Failed | F1 | 95% CI | Published | Δ | Flagged | Pixel F1 | IoU |",
              "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
    for r in rows.values():
        ci = (f"{r['f1_ci_low']:.3f}–{r['f1_ci_high']:.3f}" if r["f1"] is not None else "–")
        delta = "–" if r["delta"] is None else f"{r['delta']:+.3f}"
        lines.append(f"| {r['short']} | {r['n']} | {r['n_failed']} | {_fmt(r['f1'])} | {ci} | "
                     f"{_fmt(r['published_f1'])} | {delta} | {_fmt(r.get('flagged'))} | "
                     f"{_fmt(r['pixel_f1'])} | {_fmt(r['iou'])} |")
    labels = {"in_domain": "Avg. in-domain", "cross_domain": "Avg. cross-domain",
              "all": "Avg. all"}
    for group, a in avgs.items():
        lines.append(f"| {labels[group]} | | | {a['f1']:.3f} | | {a['published_f1']:.3f} | "
                     f"{a['delta']:+.3f} | | | |")
    env = run.get("environment", {})
    dirty = " (with uncommitted changes)" if run.get("git_dirty") else ""
    lines += ["", (f"Code {run.get('git_commit')}{dirty}, ADCD-Net {run.get('upstream_commit')}, "
                   f"PyTorch {env.get('torch')} on {env.get('gpu') or 'CPU'}; "
                   f"checkpoint sha256 {str(run.get('ckpt_sha256'))[:12]}."), ""]
    return "\n".join(lines)


def write_summary(run_dir: Path, rows: dict[str, dict], args, run: dict) -> None:
    avgs = averages(rows)
    partial = args.limit is not None
    with open(run_dir / "summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in rows.values():
            writer.writerow({k: (f"{v:.6f}" if isinstance(v, float) else v)
                             for k, v in r.items()})
    (run_dir / "summary.md").write_text(markdown(rows, avgs, partial, run))
    (run_dir / "summary.json").write_text(json.dumps(
        {"run": run, "partial": partial, "datasets": rows, "averages": avgs}, indent=2))


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths, settings = _paths(args), _settings(args)
    problems, notes = adcdnet.preflight(paths, args.datasets, settings, args.device,
                                        args.allow_missing_ocr)
    for note in notes:
        print(f"  - {note}")
    if problems:
        print("\nCannot run:", file=sys.stderr)
        for problem in problems:
            print(f"  ✗ {problem}", file=sys.stderr)
        return 1
    print(f"Pre-flight checks passed for {', '.join(args.datasets)}.")
    if args.check:
        return 0

    import torch

    args.run_dir = args.out / f"adcdnet_{args.tag}"
    args.run_dir.mkdir(parents=True, exist_ok=True)
    adcdnet.configure(paths, settings)
    torch.backends.cudnn.benchmark = False  # padded sizes vary; keep runs deterministic
    model, model_info = adcdnet.load_model(paths, args.device, args.allow_missing_keys)
    if model_info["unexpected_keys"]:
        print(f"Note: {len(model_info['unexpected_keys'])} unused weights in the checkpoint")

    run = run_info(vars(args))
    run.update(upstream_commit=adcdnet.upstream_commit(paths.upstream),
               ckpt_sha256=adcdnet.sha256(paths.ckpt), docres_sha256=adcdnet.sha256(paths.docres),
               environment=adcdnet.environment(), model=model_info,
               settings=vars(settings) | {"batch_size": args.batch_size,
                                          "precision": args.precision, "limit": args.limit})

    rows: dict[str, dict] = {}
    for name in args.datasets:
        csv_path = args.run_dir / f"{name}.csv"
        seconds = None
        if args.resume and csv_path.exists():
            expected = len(adcdnet.build_dataset(name))
            if args.limit is not None:
                expected = min(expected, args.limit)
            with open(csv_path) as f:
                found = sum(1 for _ in f) - 1
            if found != expected:
                print(f"{csv_path.name} has {found} images but this run needs {expected} "
                      "(different --limit?); use another --tag or delete it", file=sys.stderr)
                return 1
            print(f"{adcdnet.SHORT_NAMES[name]}: reusing {csv_path.name}")
        else:
            seconds = evaluate_dataset(name, model, args, csv_path)
        counts, failed, areas = read_counts(csv_path)
        rows[name] = summary_row(name, counts, failed, seconds, areas)
        if failed:
            print(f"Warning: {failed} {adcdnet.SHORT_NAMES[name]} images failed to load; "
                  f"see the error column of {csv_path.name}", file=sys.stderr)
        write_summary(args.run_dir, rows, args, run)  # keep the summary current after each set

    print()
    print(markdown(rows, averages(rows), args.limit is not None, run))
    print(f"Results in {args.run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
