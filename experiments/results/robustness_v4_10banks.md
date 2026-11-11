# Robustness of rule-based signals to laundering

Recall on forgeries (false-positive rate on genuine statements in brackets).

| Condition | Financial | PDF structure | Template | Any signal | Abstained (Financial / PDF structure / Template) |
| --- | --- | --- | --- | --- | --- |
| Original | 0.24 (0.00) | 0.51 (0.00) | 0.76 (0.00) | 0.76 (0.00) | 0.00 / 0.00 / 0.00 |
| Reprinted (Ghostscript) | 0.24 (0.00) | 0.55 (0.00) | 0.76 (0.00) | 0.76 (0.00) | 0.00 / 0.00 / 0.00 |
| Rasterised (150 dpi JPEG) | 0.00 (0.00) | 0.00 (0.00) | 0.00 (0.00) | 0.00 (0.00) | 1.00 / 1.00 / 1.00 |

Flag rate of any signal by forgery type:

| Forgery type | Original | Reprinted (Ghostscript) | Rasterised (150 dpi JPEG) |
| --- | --- | --- | --- |
| closing_balance | 100% | 100% | 0% |
| credit_amount | 100% | 100% | 0% |
| credit_amount_consistent | 100% | 100% | 0% |
| genuine | 0% | 0% | 0% |
| holder_name | 100% | 100% | 0% |
| rebuilt_exact | 0% | 0% | 0% |
| rebuilt_imitation | 100% | 100% | 0% |
