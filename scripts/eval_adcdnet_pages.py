"""Evaluate ADCD-Net on rendered bank-statement pages.

Runs the released ADCD-Net checkpoint over every page of every statement in the given folders
(PDF + JSON label pairs, searched recursively), tile by tile (see
``forgelens.signals.image.pages``), and reports, for each laundering setting (none, reprint,
raster) and forgery method:

* detection: how well a statement's score separates forged from genuine statements of the same
  laundering setting: ROC AUC, and the share of forgeries caught when 5% or 1% of genuine
  statements may be flagged (thresholds taken from the genuine scores). Two scores: ``peak``
  (mean of the 500 most suspicious pixels on the worst page) and ``area`` (largest share of a
  page predicted tampered);
* localisation: per-statement F1 of the predicted tampered pixels against the edited regions,
  pooled over the statement's pages, with a 95% interval.

Outputs in ``<out>/adcdnet_pages_<tag>/``: ``pages.csv`` (one row per page, appended as it
goes, so ``--resume`` continues after an interruption), ``groups.csv``, ``summary.md`` and
``summary.json``, plus ``maps/`` with heat maps of the first ``--save-maps`` forged pages.

Example (the data folders as made by the README's v4 commands):
    python scripts/eval_adcdnet_pages.py --config configs/adcdnet_eval.yaml --tag v4 \\
        --data ~/forgelens-data/synthetic_v4 --resume
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

from forgelens.evaluation import PixelCounts, summarise
from forgelens.signals.image import adcdnet
from forgelens.utils import run_info

REPO = Path(__file__).resolve().parents[1]
PAGE_FIELDS = ["file", "label", "method", "laundering", "bank_id", "page", "height", "width",
               "tiles", "tp", "pred", "gt", "area", "peak", "error"]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, required=True,
                   help="the eval_adcdnet.py YAML (ckpt, docres, doctamper_root)")
    p.add_argument("--data", type=Path, nargs="+", required=True,
                   help="folders with statement PDFs and their JSON labels")
    p.add_argument("--tag", required=True)
    p.add_argument("--out", type=Path, default=REPO / "experiments" / "results")
    p.add_argument("--dpi", type=int, default=150, help="page rendering resolution")
    p.add_argument("--device", default="cuda")
    p.add_argument("--precision", choices=["fp16", "fp32"], default="fp16")
    p.add_argument("--batch-size", type=int, default=16, help="tiles per forward pass")
    p.add_argument("--limit", type=int, help="at most N statements per group (smoke test)")
    p.add_argument("--save-maps", type=int, default=0, metavar="N",
                   help="save heat maps of the first N forged pages that have edits")
    p.add_argument("--resume", action="store_true", help="skip pages already in pages.csv")
    p.add_argument("--upstream", type=Path, default=REPO / "third_party" / "ADCD-Net")
    args = p.parse_args(argv)
    if args.device == "cpu":
        args.precision = "fp32"
    return args


def load_paths(args) -> adcdnet.Paths:
    import yaml

    cfg = {k.replace("-", "_"): v for k, v in yaml.safe_load(args.config.read_text()).items()}
    return adcdnet.Paths(upstream=args.upstream, ckpt=cfg["ckpt"], docres=cfg["docres"],
                         doctamper_root=cfg.get("doctamper_root"), qt_path=cfg.get("qt_path"))


def statements(folders: list[Path], limit: int | None):
    """(pdf, record, group) for labelled statements, at most ``limit`` per group."""
    seen: dict[tuple, int] = defaultdict(int)
    for folder in folders:
        for json_path in sorted(folder.expanduser().rglob("*.json")):
            try:
                record = json.loads(json_path.read_text())
            except (OSError, ValueError):
                continue
            pdf = json_path.with_suffix(".pdf")
            if record.get("label") not in ("genuine", "forged") or not pdf.exists():
                continue
            group = (record["label"], (record.get("forgery") or {}).get("method", "genuine"),
                     (record.get("laundering") or {}).get("method", "none"))
            if limit is not None and seen[group] >= limit:
                continue
            seen[group] += 1
            yield pdf, record, group


# ---------------------------------------------------------------- statistics

def auc(neg: list[float], pos: list[float]) -> float | None:
    """ROC AUC (probability a forged score exceeds a genuine one, ties counted half)."""
    if not neg or not pos:
        return None
    ranked = sorted([(s, 0) for s in neg] + [(s, 1) for s in pos])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        mid = (i + j + 1) / 2  # average 1-based rank of the tie block
        rank_sum += mid * sum(1 for k in range(i, j) if ranked[k][1] == 1)
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def caught_at(neg: list[float], pos: list[float], fpr: float) -> float | None:
    """Share of ``pos`` above the threshold that flags at most ``fpr`` of ``neg``."""
    if not neg or not pos:
        return None
    allowed = math.floor(fpr * len(neg))
    threshold = sorted(neg, reverse=True)[allowed] if allowed < len(neg) else -math.inf
    return sum(s > threshold for s in pos) / len(pos)


def summarise_groups(rows: list[dict]) -> list[dict]:
    """One line per (laundering, forgery method), compared with genuine of the same laundering."""
    by_stmt: dict[str, dict] = {}
    for r in rows:
        if r["error"]:
            continue
        s = by_stmt.setdefault(r["file"], {"label": r["label"], "method": r["method"],
                                           "laundering": r["laundering"], "tp": 0, "pred": 0,
                                           "gt": 0, "area": 0.0, "peak": 0.0, "pages": 0})
        s["pages"] += 1
        for k in ("tp", "pred", "gt"):
            s[k] += int(r[k])
        s["area"] = max(s["area"], float(r["area"]))
        s["peak"] = max(s["peak"], float(r["peak"]))
    out = []
    for laundering in sorted({s["laundering"] for s in by_stmt.values()}):
        genuine = [s for s in by_stmt.values()
                   if s["laundering"] == laundering and s["label"] == "genuine"]
        methods = sorted({s["method"] for s in by_stmt.values()
                          if s["laundering"] == laundering and s["label"] == "forged"})
        for method in methods:
            forged = [s for s in by_stmt.values() if s["laundering"] == laundering
                      and s["label"] == "forged" and s["method"] == method]
            line = {"laundering": laundering, "method": method, "genuine": len(genuine),
                    "forged": len(forged)}
            for score in ("peak", "area"):
                neg = [s[score] for s in genuine]
                pos = [s[score] for s in forged]
                line[f"auc_{score}"] = auc(neg, pos)
                line[f"caught5_{score}"] = caught_at(neg, pos, 0.05)
                line[f"caught1_{score}"] = caught_at(neg, pos, 0.01)
            loc = summarise([PixelCounts(s["tp"], s["pred"], s["gt"]) for s in forged
                             if s["gt"] > 0])
            line.update(f1=loc["f1"], f1_ci_low=loc["f1_ci_low"], f1_ci_high=loc["f1_ci_high"],
                        pixel_f1=loc["pixel_f1"],
                        genuine_flagged_area=(sum(s["area"] > 0.01 for s in genuine)
                                              / len(genuine)) if genuine else None)
            out.append(line)
    return out


def _f(v, pct=False) -> str:
    if v is None:
        return "–"
    return f"{100 * v:.0f}%" if pct else f"{v:.3f}"


def markdown(lines: list[dict], run: dict, partial: bool) -> str:
    md = ["# ADCD-Net on rendered bank-statement pages", ""]
    if partial:
        md += ["**Smoke test on a subset (`--limit`).**", ""]
    intro = (f"Released checkpoint, pages rendered at {run['settings']['dpi']} DPI and cut "
             "into 512 px tiles. Detection compares forged statements with genuine ones of the "
             "same laundering setting: ROC AUC, and the share of forgeries caught when 5% / 1% "
             "of genuine statements may be flagged. Peak: mean of the 500 most suspicious "
             "pixels on the worst page. F1: predicted tampered pixels against the edited "
             "regions, per statement (95% CI).")
    header = ("| Laundering | Forgery | Genuine | Forged | AUC (peak) | Caught @5% | Caught @1% "
              "| AUC (area) | F1 | 95% CI |")
    md += [intro, "", header,
           "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for x in lines:
        ci = (f"{x['f1_ci_low']:.3f}–{x['f1_ci_high']:.3f}" if x["f1"] is not None else "–")
        md.append(f"| {x['laundering']} | {x['method']} | {x['genuine']} | {x['forged']} | "
                  f"{_f(x['auc_peak'])} | {_f(x['caught5_peak'], True)} | "
                  f"{_f(x['caught1_peak'], True)} | {_f(x['auc_area'])} | {_f(x['f1'])} | {ci} |")
    env = run.get("environment", {})
    footer = (f"Code {run.get('git_commit')}, ADCD-Net {run.get('upstream_commit')}, PyTorch "
              f"{env.get('torch')} on {env.get('gpu') or 'CPU'}; checkpoint sha256 "
              f"{str(run.get('ckpt_sha256'))[:12]}.")
    md += ["", footer, ""]
    return "\n".join(md)


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    args = parse_args(argv)
    paths = load_paths(args)
    problems, notes = adcdnet.preflight(paths, [], adcdnet.Settings(), args.device)
    for n in notes:
        print(f"  - {n}")
    if problems:
        print("Cannot run:", *[f"  ✗ {p}" for p in problems], sep="\n", file=sys.stderr)
        return 1
    items = list(statements(args.data, args.limit))
    if not items:
        print("no labelled statements (PDF + JSON) found in --data", file=sys.stderr)
        return 1
    counts = defaultdict(int)
    for _, _, g in items:
        counts[g] += 1
    for g, n in sorted(counts.items()):
        print(f"  {n:5d}  {' / '.join(g)}")

    from forgelens.signals.image.pages import (
        PageDetector,
        edit_mask,
        ocr_mask,
        page_scores,
        render_pages,
    )

    run_dir = args.out / f"adcdnet_pages_{args.tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pages_csv = run_dir / "pages.csv"
    done: set[tuple[str, int]] = set()
    if args.resume and pages_csv.exists():
        with open(pages_csv, newline="") as f:
            done = {(r["file"], int(r["page"])) for r in csv.DictReader(f)}
        print(f"resuming: {len(done)} pages already done")
    elif pages_csv.exists():
        pages_csv.unlink()

    detector = PageDetector(paths, args.device, args.precision, args.batch_size)
    run = run_info(vars(args))
    run.update(upstream_commit=adcdnet.upstream_commit(paths.upstream),
               ckpt_sha256=adcdnet.sha256(paths.ckpt), environment=adcdnet.environment(),
               settings={"dpi": args.dpi, "tile": 512, "stride": 384,
                         "precision": args.precision, "limit": args.limit})

    from tqdm import tqdm

    maps_saved = 0
    new_file = not pages_csv.exists()
    start = time.time()
    with open(pages_csv, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PAGE_FIELDS)
        if new_file:
            writer.writeheader()
        for pdf, record, (label, method, laundering) in tqdm(items, unit="stmt"):
            base = {"file": str(pdf), "label": label, "method": method,
                    "laundering": laundering, "bank_id": record.get("bank_id", "")}
            try:
                pages = render_pages(pdf, args.dpi)
            except Exception as exc:  # noqa: BLE001 - recorded, the run continues
                writer.writerow({**base, "page": -1, "error": f"{type(exc).__name__}: {exc}"})
                continue
            for page_no, rgb in enumerate(pages):
                if (str(pdf), page_no) in done:
                    continue
                gt = edit_mask(record.get("edits") or [], page_no, rgb.shape[:2], args.dpi)
                result = detector.predict(rgb, ocr_mask(rgb))
                pred = result.prob > 0.5
                c = PixelCounts(int((pred & (gt > 0)).sum()), int(pred.sum()), int(gt.sum()))
                writer.writerow({**base, "page": page_no, "height": rgb.shape[0],
                                 "width": rgb.shape[1], "tiles": result.tiles, "tp": c.tp,
                                 "pred": c.pred, "gt": c.gt,
                                 **{k: f"{v:.6f}" for k, v in page_scores(result.prob).items()},
                                 "error": ""})
                if maps_saved < args.save_maps and c.gt:
                    import cv2

                    maps = run_dir / "maps"
                    maps.mkdir(exist_ok=True)
                    heat = cv2.applyColorMap((result.prob * 255).astype("uint8"),
                                             cv2.COLORMAP_JET)
                    overlay = cv2.addWeighted(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), 0.6, heat,
                                              0.4, 0)
                    ys, xs = (gt > 0).nonzero()
                    cv2.rectangle(overlay, (int(xs.min()), int(ys.min())),
                                  (int(xs.max()), int(ys.max())), (0, 255, 0), 2)
                    cv2.imwrite(str(maps / f"{pdf.stem}_p{page_no}.jpg"), overlay)
                    maps_saved += 1
            f.flush()

    with open(pages_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    lines = summarise_groups(rows)
    run["seconds"] = round(time.time() - start, 1)
    with open(run_dir / "groups.csv", "w", newline="") as f:
        if lines:
            w = csv.DictWriter(f, fieldnames=list(lines[0]))
            w.writeheader()
            w.writerows(lines)
    (run_dir / "summary.json").write_text(json.dumps({"run": run, "groups": lines}, indent=2))
    md = markdown(lines, run, args.limit is not None)
    (run_dir / "summary.md").write_text(md)
    errors = sum(1 for r in rows if r["error"])
    print()
    print(md)
    if errors:
        print(f"Warning: {errors} statements could not be rendered; see the error column of "
              f"{pages_csv.name}", file=sys.stderr)
    print(f"Results in {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
