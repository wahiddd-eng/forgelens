"""Check your own bank statement with ForgeLens, and share only the scores.

For people who help measure ForgeLens's false alarms on real statements without handing
their statements over. Run it on your own computer or in your own Google Colab
(``notebooks/self_test.ipynb``): the statement never leaves your machine. It writes one small
JSON file with what the ForgeLens team needs, and nothing else:

* the bank's name (as you type it) and the number of pages;
* each signal's score, whether it could assess the file, and the *names* of any checks that
  fired (e.g. ``running_balance``), never their details;
* no names, account numbers, dates, amounts, transactions or file names.

    python scripts/self_test.py my_statement.pdf --bank "HDFC Bank"
    # password-protected: you are asked for the password (never stored or printed)

Send the JSON file it writes to the team. Open it first if you like: it is short and plain.
"""

from __future__ import annotations

import argparse
import getpass
import json
import secrets
import sys
from pathlib import Path


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("pdf", type=Path)
    p.add_argument("--bank", required=True, help="the bank's name, e.g. 'HDFC Bank'")
    p.add_argument("--how", default="", help="how you got it: net banking, email, app, branch")
    p.add_argument("--no-ocr", action="store_true", help="skip the OCR check (slow on a CPU)")
    p.add_argument("--password", help=argparse.SUPPRESS)  # for tests; normally asked for
    p.add_argument("--out", type=Path, default=Path("."))
    return p.parse_args(argv)


def run(pdf: Path, bank: str, how: str = "", password: str | None = None,
        ocr: bool = True) -> dict:
    """The shareable result for one statement (no content of the statement)."""
    from forgelens.reader import open_pdf
    from forgelens.signals.financial import check_statement
    from forgelens.signals.pdf_structure import analyze_pdf

    with open_pdf(pdf, password) as doc:  # raises PasswordRequired for a wrong password
        pages = doc.page_count
    fin = check_statement(pdf, password)
    struct = analyze_pdf(pdf, password)
    result = {
        "id": secrets.token_hex(4),  # random: lets the team tell results apart, nothing more
        "bank": bank.strip(), "how_obtained": how.strip(), "pages": pages,
        "image_only": bool(struct.abstained),
        "signals": {
            "financial": {"score": round(fin.score, 4), "abstained": fin.abstained,
                          "checks_fired": sorted({f.check for f in fin.findings})},
            "structure": {"score": round(struct.score, 4), "abstained": struct.abstained,
                          "checks_fired": sorted({f.check for f in struct.findings})},
        },
    }
    if ocr:
        try:
            from forgelens.signals.ocr_financial import OcrReader, check_pdf
        except ImportError:
            result["signals"]["ocr_financial"] = {"skipped": "easyocr not installed"}
        else:
            rep = check_pdf(pdf, OcrReader(), password=password)
            result["signals"]["ocr_financial"] = {
                "score": round(rep.score, 4), "abstained": rep.abstained,
                "breaks": rep.breaks, "explained": rep.explained,
                "summary_breaks": rep.summary_breaks}
    try:
        from forgelens.utils import run_info

        result["forgelens"] = (run_info({}).get("git_commit") or "")[:10]
    except Exception:  # noqa: BLE001 - the version is a nicety
        result["forgelens"] = ""
    return result


def main(argv=None) -> int:
    args = parse_args(argv)
    from forgelens.reader import PasswordRequired

    if not args.pdf.exists():
        print(f"{args.pdf} not found", file=sys.stderr)
        return 1
    password = args.password
    for attempt in range(3):
        try:
            result = run(args.pdf, args.bank, args.how, password, not args.no_ocr)
            break
        except PasswordRequired:
            if attempt == 2:
                print("Could not open the file with that password.", file=sys.stderr)
                return 1
            password = getpass.getpass("This statement is password-protected. Password: ")
    out = args.out / f"forgelens_result_{result['id']}.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"\nSaved {out}. Send this file to the ForgeLens team. It contains no details of "
          "your statement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
