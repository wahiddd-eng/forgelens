"""Generate synthetic genuine bank statements (PDF + ground-truth JSON).

Example:
    python scripts/generate_statements.py --bank himalaya_national --count 100 --seed 0 \
        --months 3 --out data/synthetic/genuine
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forgelens.generator import BANKS, build_statement, get_bank, render_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bank", default="himalaya_national", choices=sorted(BANKS))
    parser.add_argument("--count", type=int, default=10, help="number of statements")
    parser.add_argument("--seed", type=int, default=0, help="seed of the first statement")
    parser.add_argument("--months", type=int, default=3, help="statement period in months (1-12)")
    parser.add_argument("--out", type=Path, default=Path("data/synthetic/genuine"))
    parser.add_argument("--no-pdf", action="store_true", help="write ground-truth JSON only")
    args = parser.parse_args()

    bank = get_bank(args.bank)
    out_dir = args.out / bank.bank_id
    out_dir.mkdir(parents=True, exist_ok=True)

    for seed in range(args.seed, args.seed + args.count):
        statement = build_statement(seed=seed, bank=bank, months=args.months)
        record = statement.ground_truth()
        if not args.no_pdf:
            pdf_path = render_pdf(statement, bank, out_dir / f"{statement.statement_id}.pdf")
            record["pdf"] = pdf_path.name
        (out_dir / f"{statement.statement_id}.json").write_text(json.dumps(record, indent=2))
        print(f"{statement.statement_id}: {len(statement.transactions)} transactions, "
              f"closing balance {statement.closing_balance}")


if __name__ == "__main__":
    main()
