"""Generate synthetic genuine bank statements (PDF + ground-truth JSON).

Example:
    python scripts/generate_statements.py --bank himalaya_national --count 100 --seed 0 \
        --months 3 --out data/synthetic/genuine

    # 40 procedurally generated banks (gen_0000 ... gen_0039), 10 statements each
    python scripts/generate_statements.py --bank generated --generated 0 40 --count 10 \
        --seed 3000 --out data/synthetic/genuine_gen
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forgelens.generator import (
    BANKS,
    LayoutError,
    build_statement,
    get_bank,
    locate_fields,
    render_pdf,
)
from forgelens.utils import run_info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bank", default="himalaya_national",
                        help="bank id (a hand-made bank or a generated one such as gen_0007), "
                             "'all' for every hand-made bank, or 'generated' for the range "
                             "given by --generated")
    parser.add_argument("--generated", type=int, nargs=2, metavar=("FIRST", "COUNT"),
                        default=(0, 40), help="generated banks to use with --bank generated")
    parser.add_argument("--count", type=int, default=10, help="number of statements")
    parser.add_argument("--seed", type=int, default=0, help="seed of the first statement")
    parser.add_argument("--months", type=int, default=3, help="statement period in months (1-12)")
    parser.add_argument("--out", type=Path, default=Path("data/synthetic/genuine"))
    parser.add_argument("--no-pdf", action="store_true", help="write ground-truth JSON only")
    args = parser.parse_args()

    if args.bank == "all":
        banks = list(BANKS.values())
    elif args.bank == "generated":
        first, count = args.generated
        banks = [get_bank(f"gen_{i:04d}") for i in range(first, first + count)]
    else:
        try:
            banks = [get_bank(args.bank)]
        except KeyError as exc:
            parser.error(str(exc))
    manifest = {"run": run_info(vars(args)), "banks": {}}
    failed = 0
    for bank in banks:
        made, errors, fonts = generate(bank, args)
        manifest["banks"][bank.bank_id] = {"statements": made, "failed": errors,
                                           "expected_font": bank.primary_font, "fonts": fonts}
        failed += len(errors)
    args.out.mkdir(parents=True, exist_ok=True)
    # The manifest records the fonts each bank was rendered with: statements made on machines
    # with different fonts are not interchangeable (see the README).
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if failed:
        raise SystemExit(f"{failed} statement(s) failed; see manifest.json")


def generate(bank, args) -> tuple[int, list[dict], list[str]]:
    """Generate one bank's statements; return (made, failures, fonts used)."""
    out_dir = args.out / bank.bank_id
    out_dir.mkdir(parents=True, exist_ok=True)
    made, errors, fonts = 0, [], set()
    for seed in range(args.seed, args.seed + args.count):
        statement = build_statement(seed=seed, bank=bank, months=args.months)
        record = statement.ground_truth()
        pdf_path = out_dir / f"{statement.statement_id}.pdf"
        if not args.no_pdf:
            try:
                render_pdf(statement, bank, pdf_path)  # warns (once per bank) if a font is missing
                record["pdf"] = pdf_path.name
                record["layout"] = locate_fields(pdf_path, statement, bank)
            except LayoutError as exc:
                pdf_path.unlink(missing_ok=True)
                errors.append({"statement_id": statement.statement_id, "error": str(exc)})
                print(f"FAILED {statement.statement_id}: {exc}")
                continue
            fonts.update(record["layout"]["fonts"])
        (out_dir / f"{statement.statement_id}.json").write_text(json.dumps(record, indent=2))
        made += 1
        print(f"{statement.statement_id}: {len(statement.transactions)} transactions, "
              f"closing balance {statement.closing_balance}")
    return made, errors, sorted(fonts)


if __name__ == "__main__":
    main()
