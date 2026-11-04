"""Learn per-bank template profiles from genuine statements.

Use statements that are NOT in the evaluation set (e.g. a separate seed range).

Example:
    python scripts/generate_statements.py --bank all --count 20 --seed 9000 --out data/synthetic/train_genuine
    python scripts/fit_templates.py --genuine data/synthetic/train_genuine --out experiments/templates.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forgelens.signals.template import TemplateMatcher, fit_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--genuine", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("experiments/templates.json"))
    args = parser.parse_args()

    samples = []
    for json_path in sorted(args.genuine.rglob("*.json")):
        record = json.loads(json_path.read_text())
        pdf = json_path.with_suffix(".pdf")
        if record.get("label") == "genuine" and pdf.exists():
            samples.append((record["bank_id"], pdf))
    profiles = fit_profiles(samples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    TemplateMatcher(profiles).save(args.out)
    for bank, p in sorted(profiles.items()):
        print(f"{bank}: {p['n']} statements, fonts {p['fonts']}")


if __name__ == "__main__":
    main()
