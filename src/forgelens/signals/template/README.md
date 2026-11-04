# Template signal

Compares a statement with what the bank it claims to come from normally produces.

`fit_profiles()` learns a profile per bank from genuine statements (use a separate training set, e.g. `scripts/fit_templates.py`). `TemplateMatcher.check()` identifies the bank from the name printed on page 1 and compares:

| Check | Fires when |
| --- | --- |
| `unexpected_font` | A font the bank never uses appears (returned with positions) |
| `table_font`, `table_font_size` | Table figures use a different font or size |
| `masthead` | The bank name is set in a different font, size or position |
| `header_labels` | The table header wording differs |
| `column_positions` | Debit, credit or balance columns end in a different place |
| `date_format`, `amount_format` | Dates or amounts are written differently (e.g. `03-Sep-2025` vs `03/09/2025`, `1,23,456.78` vs `123,456.78`, a missing `Cr`) |
| `page_size` | Page size or orientation differs |
| `creator` | The PDF's "Creator" differs (the "Producer" is ignored, because re-saving changes it) |

It abstains (score 0.5) on image-only PDFs and on banks it has no profile for.

```python
from forgelens.signals.template import TemplateMatcher

matcher = TemplateMatcher.load("experiments/templates_v3.json")
report = matcher.check("statement.pdf")
report.bank_id, report.suspicious, report.score
[f.message for f in report.findings]
```

**Limitation:** a forgery rendered with the bank's exact template looks genuine to this signal (and to every other document-based signal).
