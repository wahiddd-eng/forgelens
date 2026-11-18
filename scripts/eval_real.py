"""False alarms on real, genuine bank statements: every signal and the fused verdict.

Real statements are genuine (as far as anyone knows), so the question is how many of them
ForgeLens would wrongly flag, at the thresholds set on the synthetic test set (1% and 5% of
synthetic genuine statements flagged). Run through ``scripts/eval_real.sh``, which checks the
folder is private, never saves page pictures, and deletes the statements afterwards.

The folder holds the PDFs (named S001.pdf, S002.pdf, ... so that names carry no account
numbers) and ``statements.tsv``: one line per file, ``file<TAB>bank<TAB>password`` (password
empty for unprotected files). Only aggregate numbers, bank names and file IDs leave the
folder: the summary written to ``--summary`` (Markdown) and its ``.json`` twin.

    python scripts/eval_real.py --folder ~/real_statements \\
        --fusion experiments/results/fusion_test-ft3-real/model.pkl \\
        --config configs/adcdnet_ft3.yaml --summary experiments/results/real_<date>.md
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--folder", type=Path, required=True)
    p.add_argument("--fusion", type=Path, required=True,
                   help="model.pkl from fuse_signals.py, fitted without the template signal")
    p.add_argument("--config", type=Path,
                   help="eval_adcdnet.py YAML of the image model (omit to skip the image signal)")
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--device", default="cuda")
    p.add_argument("--diagnostics", type=Path,
                   help="also write per-statement diagnostics here (how each file is built and "
                        "parsed, which checks fired; no text, dates or amounts)")
    return p.parse_args(argv)


def read_list(folder: Path) -> list[tuple[Path, str, str | None]]:
    listing = folder / "statements.tsv"
    if not listing.exists():
        raise SystemExit(f"{listing} is missing: one line per PDF, file<TAB>bank<TAB>password")
    out = []
    with open(listing, newline="") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if not row or row[0].startswith("#") or row[0].lower() == "file":
                continue
            name, bank = row[0].strip(), (row[1].strip() if len(row) > 1 else "")
            password = row[2] if len(row) > 2 and row[2] != "" else None
            pdf = folder / name
            if not pdf.exists():
                raise SystemExit(f"{name} is listed but not in the folder")
            out.append((pdf, bank or "unknown", password))
    unlisted = {p.name for p in folder.glob("*.pdf")} - {p.name for p, _, _ in out}
    if unlisted:
        raise SystemExit(f"PDFs not in statements.tsv: {', '.join(sorted(unlisted))}")
    return out


def wilson(k: int, n: int) -> tuple[float, float]:
    import math

    if n == 0:
        return (0.0, 1.0)
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main(argv=None) -> int:
    args = parse_args(argv)
    from forgelens.fusion import Statement
    from forgelens.reader import PasswordRequired
    from forgelens.signals.financial import check_statement
    from forgelens.signals.pdf_structure import analyze_pdf

    files = read_list(args.folder)
    final = pickle.loads(args.fusion.read_bytes())
    if "template" in final["signals"]:
        raise SystemExit("This fusion model uses the template signal, which knows only our "
                         "fictional banks: fit one with fuse_signals.py --exclude template")

    detector = None
    if args.config and "image" in final["signals"]:
        import yaml

        from forgelens.signals.image import adcdnet
        from forgelens.signals.image.pages import PageDetector

        cfg = {k.replace("-", "_"): v for k, v in yaml.safe_load(args.config.read_text()).items()}
        paths = adcdnet.Paths(upstream=REPO / "third_party" / "ADCD-Net", ckpt=cfg["ckpt"],
                              docres=cfg["docres"], doctamper_root=cfg.get("doctamper_root"),
                              qt_path=cfg.get("qt_path"))
        detector = PageDetector(paths, args.device, "fp16" if args.device != "cpu" else "fp32")

    ocr = None
    if "ocr_financial" in final["signals"]:
        from forgelens.signals.ocr_financial import OcrReader

        ocr = OcrReader(gpu=args.device != "cpu")

    rows, statements, diagnostics = [], [], {}
    for pdf, bank, password in files:
        fin = struct = rep = None
        row = {"id": pdf.stem, "bank": bank, "error": "", "checks": ""}
        st = Statement(pdf.name, "genuine", "real", "none", bank, pdf.stem)
        try:
            fin = check_statement(pdf, password)
            struct = analyze_pdf(pdf, password)
            if struct.error:  # the signals report a locked or damaged file instead of raising
                raise PasswordRequired(struct.error) if "password" in struct.error.lower() \
                    else ValueError(struct.error)
            st.scores["financial"] = None if fin.abstained else fin.score
            st.scores["structure"] = None if struct.abstained else struct.score
            row["checks"] = ";".join(sorted({f.check for f in fin.findings}
                                            | {f.check for f in struct.findings}))
            row["image_only"] = struct.abstained
            if ocr is not None:
                from forgelens.signals.ocr_financial import check_pdf

                rep = check_pdf(pdf, ocr, args.dpi, password)
                st.scores["ocr_financial"] = None if rep.abstained else rep.score
            if detector is not None:
                from forgelens.signals.image.pages import page_scores, render_pages_native

                peaks, areas = [], []
                for rgb, _ in render_pages_native(pdf, dpi=args.dpi, password=password):
                    s = page_scores(detector.predict(rgb).prob)
                    peaks.append(s["peak"])
                    areas.append(s["area"])
                st.scores["image"], st.image_area = max(peaks), max(areas)
        except PasswordRequired:
            row["error"] = "password missing or wrong"
        except Exception:  # noqa: BLE001 - one bad file must not stop the run
            row["error"] = "unreadable"  # (no message: it could quote the file's contents)
        st.scores.setdefault("template", None)
        if args.diagnostics and not row["error"]:
            from forgelens.evaluation.real_diagnostics import diagnose

            try:
                diagnostics[pdf.stem] = {"bank": bank, **diagnose(
                    pdf, password, fin, struct, rep, st.scores.get("image"))}
            except Exception as exc:  # noqa: BLE001
                diagnostics[pdf.stem] = {"bank": bank, "error": type(exc).__name__}
        rows.append(row)
        statements.append(st)
        print(f"  {pdf.stem}: {'error: ' + row['error'] if row['error'] else 'done'}",
              flush=True)

    summary = summarise(rows, statements, final, detector is not None)
    if args.diagnostics:
        for r in rows:
            if r["id"] in diagnostics:
                diagnostics[r["id"]]["fused"] = r.get("fused")
                diagnostics[r["id"]]["scores"] = {
                    k: v for k, v in statements[rows.index(r)].scores.items() if v is not None}
        args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
        args.diagnostics.write_text(json.dumps(diagnostics, indent=1, default=str))
        print(f"Diagnostics: {args.diagnostics}")
    summary["fusion_model"] = str(args.fusion)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=list))
    names = [n for n in final["signals"] if n != "template"] + ["fused_boosting"]
    args.summary.write_text(markdown(summary, names))
    print(markdown(summary, names))
    return 0


def for_fusion(st, row: dict):
    """The statement as the fusion model saw such statements in training: on the test set the
    image model and OCR arithmetic were run only on image-only (rasterised) statements, so a
    statement with a text layer is fused without them. Their own scores still count below,
    as single signals."""
    import copy

    if row.get("image_only"):
        return st
    st = copy.deepcopy(st)
    for s in ("image", "image_released", "ocr_financial"):
        if s in st.scores:
            st.scores[s] = None
    st.image_area = None
    return st


def summarise(rows: list[dict], statements: list, final: dict, image_signal: bool) -> dict:
    """False-alarm counts per signal and for the fused verdict, at the thresholds the fusion
    model was saved with. ``rows``: id, bank, error, checks (and image_only) per statement;
    ``statements``: their scores (``fusion.Statement``)."""
    from forgelens.fusion.fuse import apply_final

    ok = [i for i, r in enumerate(rows) if not r["error"]]
    fused = apply_final(final, [for_fusion(statements[i], rows[i]) for i in ok]) if ok else []
    for i, f in zip(ok, fused, strict=True):
        rows[i]["fused"] = f
    names = [s for s in final["signals"] if s != "template"] + ["fused_boosting"]
    summary = {"statements": len(rows), "read": len(ok),
               "errors": Counter(r["error"] for r in rows if r["error"]),
               "banks": Counter(r["bank"] for r in rows),
               "image_only": sum(bool(r.get("image_only")) for r in rows),
               "image_signal": image_signal, "flagged": {}, "by_bank": defaultdict(dict),
               "checks_fired": Counter(c for r in rows for c in r["checks"].split(";") if c)}
    for fpr in (0.01, 0.05):
        for name in names:
            t = final["thresholds"].get(name, {}).get(fpr)
            if t is None:
                continue
            flagged = []
            for i in ok:
                v = rows[i]["fused"] if name == "fused_boosting" else statements[i].scores.get(name)
                if v is not None and v > t:
                    flagged.append(i)
            assessed = [i for i in ok if name == "fused_boosting"
                        or statements[i].scores.get(name) is not None]
            lo, hi = wilson(len(flagged), len(assessed))
            summary["flagged"][f"{name}@{fpr:g}"] = {
                "flagged": len(flagged), "assessed": len(assessed), "ci95": [lo, hi],
                "ids": [rows[i]["id"] for i in flagged]}
            if name == "fused_boosting":
                for bank in summary["banks"]:
                    b = [i for i in assessed if rows[i]["bank"] == bank]
                    summary["by_bank"][bank][f"{fpr:g}"] = [sum(i in flagged for i in b), len(b)]

    return summary


def markdown(s: dict, names: list[str]) -> str:
    label = {"image": "Image (ADCD-Net)", "image_released": "Image (released)",
             "ocr_financial": "OCR arithmetic", "financial": "Financial",
             "structure": "PDF structure",
             "fused_boosting": "**ForgeLens (fused)**"}
    lines = ["# ForgeLens on real bank statements", "",
             (f"{s['statements']} genuine statements from {len(s['banks'])} banks "
             f"({', '.join(f'{b} {n}' for b, n in sorted(s['banks'].items()))}); "
             f"{s['read']} read, {s['image_only']} image-only (scans or photos). Thresholds as "
             "set on the synthetic test set. Every statement here is genuine, so every flag is "
             "a false alarm."), "",
             "| Signal | Threshold | Flagged | Assessed | False-alarm rate (95% CI) | Flagged IDs |",
             "| --- | --- | ---: | ---: | --- | --- |"]
    for key, v in s["flagged"].items():
        name, fpr = key.split("@")
        rate = v["flagged"] / v["assessed"] if v["assessed"] else 0
        lines.append(f"| {label.get(name, name)} | {float(fpr):.0%} synthetic | {v['flagged']} | "
                     f"{v['assessed']} | {rate:.1%} ({v['ci95'][0]:.1%}–{v['ci95'][1]:.1%}) | "
                     f"{', '.join(v['ids']) or '–'} |")
    if s["checks_fired"]:
        lines += ["", "Checks that fired: " + ", ".join(
            f"{c} ({n})" for c, n in s["checks_fired"].most_common()) + "."]
    if s["errors"]:
        lines += ["", "Not read: " + ", ".join(f"{e} ({n})" for e, n in s["errors"].items()) + "."]
    lines += ["", "Fused flags by bank at 1% (flagged / assessed): " + ", ".join(
        f"{b} {v.get('0.01', [0, 0])[0]}/{v.get('0.01', [0, 0])[1]}"
        for b, v in sorted(s["by_bank"].items())) + "."]
    if not s["image_signal"]:
        lines += ["", "The image signal was not run (no GPU or no --config)."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
