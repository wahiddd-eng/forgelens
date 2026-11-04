# Generator

Synthetic **genuine** bank statements for the ForgeLens dataset. Every bank, merchant, employer and lender is fictional, and each PDF says so in its footer note.

## What it produces

For each seed: a multi-page PDF statement and a ground-truth JSON file with the customer, account summary and every transaction row. Forgery scripts (Phase 2, next step) compare forged copies against this JSON to label exactly what was changed.

- Indian-style transactions: salary (NEFT), UPI debits and credits, rent, EMI (ACH), bill payments (BBPS), ATM withdrawals, card (POS) payments, IMPS transfers, cheque deposits, quarterly interest and SMS charges.
- Running balances are computed row by row with exact decimal arithmetic, so every row, the summary box and the closing balance always agree.
- Amounts use Indian digit grouping (`12,34,567.50`).
- The same seed always produces the same statement.

## Usage

```bash
# macOS: WeasyPrint needs Pango
brew install pango

python scripts/generate_statements.py --bank himalaya_national --count 100 --seed 0 --months 3 \
    --out data/synthetic/genuine
```

```python
from forgelens.generator import build_statement, get_bank, render_pdf

bank = get_bank("himalaya_national")
statement = build_statement(seed=42, bank=bank, months=3)
render_pdf(statement, bank, "statement.pdf")
record = statement.ground_truth()  # dict saved as JSON next to the PDF
```

## Files

| File | Purpose |
| --- | --- |
| `banks.py` | Fictional bank profiles (name, IFSC prefix, colours, font, template) |
| `transactions.py` | Customer and transaction generation, running balances |
| `models.py` | `Customer`, `Transaction`, `Statement` and the ground-truth record |
| `money.py` | Decimal rounding and Indian number formatting |
| `render.py` | HTML (Jinja2) and PDF (WeasyPrint) rendering |
| `templates/` | One HTML layout per bank style |

## Bank layouts

All ten banks are fictional; every statement carries a footer note saying so.

| Bank | Template | Columns | Date | Numbers | Font | Page | Summary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Himalaya National Bank | classic table | date, narration, ref, value date, Dr, Cr, balance | 03-09-2025 | 1,23,456.78 | DejaVu Sans | portrait | top |
| Deccan Co-operative Bank | ledger grid | date, particulars, cheque, Dr, Cr, balance | 03/09/2025 | 1,23,456.78 Cr | Liberation Serif | portrait | bottom |
| Sahyadri Bank | modern band | date, value date, description, ref, Dr, Cr, balance | 03-Sep-2025 | 1,23,456.78 | Carlito | portrait | top |
| Konark Urban Bank | classic table | date, details, ref, value date, Dr, Cr, balance | 03/09/25 | 1,23,456.78 | Liberation Sans | landscape | top |
| Narmada Gramin Bank | ledger grid | S.No., date, description, Dr, Cr, balance | 03.09.2025 | 123456.78 | DejaVu Sans Condensed | portrait | bottom |
| Bayview International Bank | modern band | date, description, ref, Dr, Cr, balance | 03 Sep 2025 | 123,456.78 | Liberation Sans | portrait | top |
| Vindhya State Bank | classic table | S.No., date, description, ref, Dr, Cr, balance | 03-09-2025 | 1,23,456.78 Cr | DejaVu Sans | portrait | top |
| Ganga Mercantile Bank | ledger grid | date, value date, particulars, cheque, Dr, Cr, balance | 03-09-2025 | 1,23,456.78 | DejaVu Serif | portrait | bottom |
| Tapti Valley Bank | modern band | date, narration, ref, value date, Dr, Cr, balance | 03/09/2025 | 1,23,456.78 | DejaVu Sans | landscape | top |
| Malabar Coastal Bank | classic table | date, remarks, Dr, Cr, balance | 03-Sep-25 | 1,23,456.78 CR | Liberation Serif | portrait | bottom |

Fonts use stacks that resolve on Linux (DejaVu, Liberation, Carlito) and fall back to Arial / Times / Calibri on macOS and Windows, so PDFs made on different machines differ slightly.

Generate every bank at once with `--bank all`.

## Adding a bank layout

1. Add a `BankProfile` to `BANK_LIST` in `banks.py` with an invented name and IFSC prefix. Choose a template, column order, labels, date format, grouping, suffix, font, orientation and summary position.
2. For a new look, add a template in `templates/` built from the macros in `_macros.j2` (numeric cells must stay right-aligned).
3. Run `pytest` — `tests/test_banks.py` checks every bank: rendering, exact read-back, both signals on genuine statements, and every forgery type.
