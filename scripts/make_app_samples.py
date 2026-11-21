"""Bundle fictional sample statements, examined in advance, with the web app.

    python scripts/make_app_samples.py                       # rule-based checks (any machine)
    python scripts/make_app_samples.py --fusion experiments/results/fusion_final-ft6/model.pkl \\
        --image-config configs/adcdnet_ft6.yaml --templates experiments/templates_v4.json  # DGX

Generates statements of two fictional banks with seeds outside every training and test set,
forges some of them (PDF edits, a phone screenshot), runs ``forgelens.app.engine.Engine`` on
each and writes ``src/forgelens/app/static/samples.json``. Nothing real is involved: the banks,
people and figures are all made up by ForgeLens's generator.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from forgelens.app.engine import Engine, Settings

OUT = REPO / "src" / "forgelens" / "app" / "static" / "samples.json"

SAMPLES = [
    # id, file in the work folder, title, meta, ground truth
    ("konark-genuine", "gen/konark_urban/konark_urban_009302.pdf",
     "Konark Urban Bank, first copy", "Savings account, May to June",
     "Nothing. This is a genuine statement, exactly as the bank's software made it."),
    ("sahyadri-credit", "forged/sahyadri_009301__pdfedit_credit_amount_01.pdf",
     "Sahyadri Bank", "Savings account, February to March",
     ("One credit was raised in a PDF editor and the file saved on top of the original. The "
      "balances after it were left alone, so they no longer add up.")),
    ("konark-consistent", "forged/konark_urban_009302__pdfedit_credit_amount_consistent_01.pdf",
     "Konark Urban Bank, second copy", "The same account and months",
     ("The first copy, with one credit raised in a PDF editor and every balance after it "
      "adjusted, so the arithmetic agrees. Only the way the file was built gives it away.")),
    ("sahyadri-screenshot", "phone/sahyadri_009301__pdfedit_credit_amount_01__screenshot.pdf",
     "Sahyadri Bank, phone screenshot", "The edited Sahyadri statement, captured on a phone",
     ("The same edited Sahyadri statement as above, captured as phone screenshots. A "
      "screenshot has no text layer, so only the checks that read the page image can judge "
      "it.")),
]


def build_files(work: Path) -> None:
    py = sys.executable
    for bank, seed in (("sahyadri", 9301), ("konark_urban", 9302)):
        subprocess.run([py, str(REPO / "scripts" / "generate_statements.py"), "--bank", bank,
                        "--count", "1", "--seed", str(seed), "--months", "2",
                        "--out", str(work / "gen")], check=True, capture_output=True)
    subprocess.run([py, str(REPO / "scripts" / "forge_pdf_edits.py"), "--genuine", str(work / "gen"),
                    "--out", str(work / "forged"), "--per-statement", "2", "--seed", "9303"],
                   check=True, capture_output=True)
    from forgelens.forgery.launder import launder

    src = work / "forged" / "sahyadri_009301__pdfedit_credit_amount_01.pdf"
    record = json.loads(src.with_suffix(".json").read_text())
    (work / "phone").mkdir(exist_ok=True)
    launder(src, record, work / "phone" / f"{src.stem}__screenshot.pdf", method="screenshot",
            seed=9304)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--fusion", type=Path)
    p.add_argument("--templates", type=Path, default=REPO / "experiments" / "templates_v4.json")
    p.add_argument("--image-config", type=Path)
    p.add_argument("--device", default="cpu")
    p.add_argument("--ocr", action="store_true", help="also run OCR arithmetic (needs EasyOCR)")
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args(argv)

    engine = Engine(Settings(fusion_model=args.fusion, templates=args.templates,
                             image_config=args.image_config, ocr=args.ocr, device=args.device))
    work = Path(tempfile.mkdtemp(prefix="forgelens_samples_"))
    try:
        build_files(work)
        samples = []
        for sid, rel, title, meta, truth in SAMPLES:
            pdf = work / rel
            result = engine.analyze(pdf, name=Path(rel).name)
            if "error" in result:
                raise SystemExit(f"{rel}: {result['message']}")
            samples.append({"id": sid, "title": title, "meta": meta, "truth": truth,
                            "result": result})
            print(f"{sid}: {result['verdict']['level']} ({result['kind']}, "
                  f"{len(result['pages'])} pages)")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    caps = engine.capabilities()
    args.out.write_text(json.dumps({"capabilities": caps, "samples": samples},
                                   ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
