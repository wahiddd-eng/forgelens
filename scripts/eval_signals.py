"""Evaluate the rule-based signals, alone and combined, on genuine and forged statements.

Signals: financial consistency (``financial``), PDF structure (``structure``) and, when a
template-profile file is given, template matching (``template``). ``either`` flags a file
when any of them fires. A signal that cannot read a file (an image-only PDF, an unknown bank,
a damaged file) abstains: the file counts as not flagged by it, and abstentions are reported
separately. Rates come with 95% Wilson intervals.

Localisation is reported for the signals that point at regions (structure, template) as
recall (share of edited values pointed at) and precision (share of pointed-at regions that
were really edited), per forgery method.

Example:
    python scripts/eval_signals.py --genuine data/synthetic/genuine \
        --forged data/synthetic/forged --templates experiments/templates.json \
        --out experiments/results --tag v4
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from forgelens.evaluation import binary_metrics, localisation, localisation_summary
from forgelens.signals.financial import check_statement
from forgelens.signals.pdf_structure import analyze_pdf
from forgelens.signals.template import TemplateMatcher
from forgelens.utils import run_info

NAMES = {"financial": "Financial", "structure": "PDF structure", "template": "Template",
         "either": "Any signal"}
LOCALISING = ("structure", "template")


def _items(folders: list[Path]):
    for folder in folders:
        for json_path in sorted(folder.rglob("*.json")):
            try:
                record = json.loads(json_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            pdf = json_path.with_suffix(".pdf")
            if pdf.exists() and record.get("label") in ("genuine", "forged"):
                yield pdf, record


def _evaluate(pdf: Path, record: dict, matcher: TemplateMatcher | None) -> tuple[dict, dict]:
    """Run every signal on one file; return its CSV row and the regions each one points at."""
    forgery = record.get("forgery") or {}
    laundering = record.get("laundering") or {}
    row = {
        "file": pdf.name,
        "label": record["label"],
        "bank_id": record.get("bank_id", ""),
        "method": forgery.get("method", "genuine"),
        "variant": forgery.get("variant", "genuine"),
        "laundering": laundering.get("method", ""),
        "save_mode": forgery.get("save_mode", ""),
        "font_strategy": forgery.get("font_strategy", ""),
        "error": "",
    }
    located: dict[str, list[dict]] = {}
    try:
        fin = check_statement(pdf)
        struct = analyze_pdf(pdf)
        row.update({
            "financial": bool(fin.findings), "financial_abstained": fin.abstained,
            "financial_score": round(fin.score, 4),
            "financial_checks": ";".join(sorted({f.check for f in fin.findings})),
            "structure": struct.suspicious, "structure_abstained": struct.abstained,
            "structure_score": struct.score,
            "structure_checks": ";".join(sorted({f.check for f in struct.findings})),
        })
        located["structure"] = struct.locations()
        errors = [e for e in (fin.error, struct.error) if e]
        if matcher:
            tpl = matcher.check(pdf)
            row.update({"template": tpl.suspicious, "template_abstained": tpl.abstained,
                        "template_score": tpl.score,
                        "template_checks": ";".join(sorted({f.check for f in tpl.findings}))})
            located["template"] = tpl.locations()
        row["error"] = "; ".join(errors)
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the evaluation
        row["error"] = f"{type(exc).__name__}: {exc}"
        for s in ("financial", "structure") + (("template",) if matcher else ()):
            row.update({s: False, f"{s}_abstained": True, f"{s}_score": 0.5, f"{s}_checks": ""})
        located = {s: [] for s in LOCALISING}
    return row, located


def _group(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return dict(sorted(out.items()))


def _metrics(rows: list[dict], signal: str) -> dict:
    return binary_metrics([r["label"] == "forged" for r in rows], [bool(r[signal]) for r in rows])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--genuine", type=Path, required=True)
    parser.add_argument("--forged", type=Path, required=True)
    parser.add_argument("--templates", type=Path, help="profiles from scripts/fit_templates.py")
    parser.add_argument("--out", type=Path, default=Path("experiments/results"))
    parser.add_argument("--tag", default="v1")
    args = parser.parse_args()

    matcher = TemplateMatcher.load(args.templates) if args.templates else None
    signals = ["financial", "structure"] + (["template"] if matcher else [])
    all_signals = signals + ["either"]

    rows = []
    loc = defaultdict(lambda: {"edits": 0, "edits_found": 0, "locations": 0,
                               "locations_on_edits": 0})  # (signal, method) -> counts
    for pdf, record in _items([args.genuine, args.forged]):
        row, located = _evaluate(pdf, record, matcher)
        row["either"] = any(row[s] for s in signals)
        rows.append(row)
        if record["label"] != "forged":
            continue
        for s, locations in located.items():
            counts = localisation(record.get("edits", []), locations)
            for key in (s, f"{s}|{row['method']}"):
                for k, v in counts.items():
                    loc[key][k] += v
    if not rows:
        raise SystemExit("No statements found")

    errors = [r for r in rows if r["error"]]
    summary = {
        "tag": args.tag,
        "run": run_info(vars(args)),
        "template_profiles": matcher.meta if matcher else None,
        "signals": all_signals,
        "counts": {"genuine": sum(r["label"] == "genuine" for r in rows),
                   "forged": sum(r["label"] == "forged" for r in rows),
                   "errors": len(errors)},
        "overall": {s: _metrics(rows, s) for s in all_signals},
        "flag_rate_by_variant": {
            v: {"n": len(rs), **{s: round(sum(r[s] for r in rs) / len(rs), 4) for s in all_signals}}
            for v, rs in _group(rows, "variant").items()
        },
        "abstention_rate": {
            s: round(sum(r[f"{s}_abstained"] for r in rows) / len(rows), 4) for s in signals
        },
        "by_bank": {
            bank: {
                "n": len(rs),
                **{f"{s}_recall": _metrics(rs, s)["recall"] for s in all_signals},
                **{f"{s}_fpr": _metrics(rs, s)["false_positive_rate"] for s in all_signals},
            }
            for bank, rs in _group(rows, "bank_id").items()
        },
        "localisation": {key: localisation_summary(c) for key, c in sorted(loc.items())
                         if key.split("|")[0] in signals},
        "error_examples": [{"file": r["file"], "error": r["error"]} for r in errors[:20]],
    }

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"signals_{args.tag}"
    fieldnames = list(dict.fromkeys(k for r in rows for k in r))
    with open(f"{stem}_per_file.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    Path(f"{stem}_summary.json").write_text(json.dumps(summary, indent=2))
    text = _markdown(summary, all_signals, signals)
    Path(f"{stem}_summary.md").write_text(text)
    print(text)


def _markdown(summary: dict, all_signals: list[str], signals: list[str]) -> str:
    def pct(x):
        return "n/a" if x is None else f"{x:.3f}"

    def ci(m: dict, key: str) -> str:
        bounds = m.get(f"{key}_ci95")
        return pct(m[key]) + ("" if not bounds else f" [{bounds[0]:.2f}, {bounds[1]:.2f}]")

    run = summary["run"]
    head = " | ".join(NAMES[s] for s in all_signals)
    rule = " | ".join("---" for _ in all_signals)
    counts = summary["counts"]
    dirty = " (uncommitted changes)" if run["git_dirty"] else ""
    versions = (f"Python {run['python']} · PyMuPDF {run['packages']['pymupdf']} · "
                f"WeasyPrint {run['packages']['weasyprint']} · Ghostscript {run['ghostscript']}")
    lines = [f"# Rule-based signals — {summary['tag']}", "",
             (f"Genuine: {counts['genuine']} · Forged: {counts['forged']} · "
              f"Unreadable files: {counts['errors']}"), "",
             f"Code: `{(run['git_commit'] or 'unknown')[:10]}`{dirty} · {versions}", "",
             "95% Wilson intervals in brackets.", "",
             f"| Metric | {head} |", f"| --- | {rule} |"]
    overall = summary["overall"]
    for metric, label in (("recall", "Recall"), ("false_positive_rate", "False-positive rate"),
                          ("precision", "Precision")):
        lines.append(f"| {label} | " + " | ".join(ci(overall[s], metric) for s in all_signals)
                     + " |")
    for metric, label in (("f1", "F1"), ("accuracy", "Accuracy")):
        lines.append(f"| {label} | " + " | ".join(pct(overall[s][metric]) for s in all_signals)
                     + " |")
    lines.append("| Abstained | " + " | ".join(pct(summary["abstention_rate"].get(s))
                                              if s != "either" else "—" for s in all_signals) + " |")
    lines += ["", f"| Variant | n | {head} |", f"| --- | --- | {rule} |"]
    for v, d in summary["flag_rate_by_variant"].items():
        lines.append(f"| {v} | {d['n']} | " + " | ".join(f"{d[s]:.1%}" for s in all_signals) + " |")
    if len(summary["by_bank"]) > 1:
        bank_head = " | ".join(NAMES[s] + " recall" for s in all_signals)
        lines += ["", f"| Bank | n | {bank_head} | Any-signal FPR |",
                  f"| --- | --- | {rule} | --- |"]
        for bank, d in summary["by_bank"].items():
            lines.append(f"| {bank} | {d['n']} | "
                         + " | ".join(pct(d[f"{s}_recall"]) for s in all_signals)
                         + f" | {pct(d['either_fpr'])} |")
    if summary["localisation"]:
        lines += ["", "Localisation (edited values pointed at / pointed-at regions that were edited):",
                  "", "| Signal | Forgeries | Edits | Recall | Regions | Precision |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for key, d in summary["localisation"].items():
            signal, _, method = key.partition("|")
            lines.append(f"| {NAMES[signal]} | {method or 'all'} | {d['edits']} | "
                         f"{ci(d, 'recall')} | {d['locations']} | {ci(d, 'precision')} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
