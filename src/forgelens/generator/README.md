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

## Adding a bank layout

1. Add a new HTML template in `templates/` (copy `classic_table.html.j2` and change the layout).
2. Add a `BankProfile` in `banks.py` with an invented name and IFSC prefix, and register it in `BANKS`.
3. Run `pytest` — the balance and rendering tests run for every seed.

Target for Phase 2: 8–10 layouts that differ in column order, date format, fonts, page structure and narration style.
