# Financial signal

Checks whether the numbers printed on a statement add up. It reads the PDF itself through `forgelens.reader`, so it works on forged and real statements, not only on generated ones. Tables that repeat their header on every page and tables whose header is printed only on the first page are both read.

| Check | Fails when |
| --- | --- |
| Running balance | A row's balance ≠ previous balance − debit + credit |
| Row format | A row has both or neither of a debit and a credit, or no balance |
| Opening balance | The summary's opening balance ≠ the opening-balance row |
| Totals | Summary total debits/credits ≠ the sums of the table |
| Counts | Summary debit/credit counts ≠ the rows in the table |
| Closing balance | Summary closing ≠ last row's balance, or ≠ opening + credits − debits |

```python
from forgelens.signals.financial import check_statement

report = check_statement("statement.pdf")                 # or password="..." for a locked file
report.consistent          # True if every check passes
report.score               # 0 = consistent, rising towards 1 with more failures
report.findings[0].message # e.g. "Row 14 (03-04-2025): balance shows ₹1,95,232.74, but ..."
report.features()          # numeric features for the fusion classifier
```

A password-protected file without its password, or a damaged file, gives an abstaining report (`report.abstained`, `report.error`) instead of an exception.

By design it cannot catch forgeries that keep the arithmetic valid (balance-consistent edits, name changes). Those are left to the image, PDF-structure and template signals.

Evaluate with `scripts/eval_signals.py` (all signals together). `scripts/eval_financial.py` is the original single-signal script, kept because the v1 results were made with it.
