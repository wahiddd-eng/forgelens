# Rule-based signals — v4_10banks_raster

Genuine: 300 · Forged: 600 · Unreadable files: 0

Code: `71f1bfcd13` · Python 3.13.18 · PyMuPDF 2.1 · WeasyPrint 70.0 · Ghostscript 10.02.1

95% Wilson intervals in brackets.

| Metric | Financial | PDF structure | Template | Any signal |
| --- | --- | --- | --- | --- |
| Recall | 0.000 [0.00, 0.01] | 0.000 [0.00, 0.01] | 0.000 [0.00, 0.01] | 0.000 [0.00, 0.01] |
| False-positive rate | 0.000 [0.00, 0.01] | 0.000 [0.00, 0.01] | 0.000 [0.00, 0.01] | 0.000 [0.00, 0.01] |
| Precision | n/a | n/a | n/a | n/a |
| F1 | 0.000 | 0.000 | 0.000 | 0.000 |
| Accuracy | 0.333 | 0.333 | 0.333 | 0.333 |
| Abstained | 1.000 | 1.000 | 1.000 | — |

| Variant | n | Financial | PDF structure | Template | Any signal |
| --- | --- | --- | --- | --- | --- |
| closing_balance | 64 | 0.0% | 0.0% | 0.0% | 0.0% |
| credit_amount | 78 | 0.0% | 0.0% | 0.0% | 0.0% |
| credit_amount_consistent | 110 | 0.0% | 0.0% | 0.0% | 0.0% |
| genuine | 300 | 0.0% | 0.0% | 0.0% | 0.0% |
| holder_name | 48 | 0.0% | 0.0% | 0.0% | 0.0% |
| rebuilt_exact | 142 | 0.0% | 0.0% | 0.0% | 0.0% |
| rebuilt_imitation | 158 | 0.0% | 0.0% | 0.0% | 0.0% |

| Bank | n | Financial recall | PDF structure recall | Template recall | Any signal recall | Any-signal FPR |
| --- | --- | --- | --- | --- | --- | --- |
| bayview_international | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| deccan_cooperative | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| ganga_mercantile | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| himalaya_national | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| konark_urban | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| malabar_coastal | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| narmada_gramin | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| sahyadri | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| tapti_valley | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| vindhya_state | 90 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

Localisation (edited values pointed at / pointed-at regions that were edited):

| Signal | Forgeries | Edits | Recall | Regions | Precision |
| --- | --- | --- | --- | --- | --- |
| PDF structure | all | 36590 | 0.000 [0.00, 0.00] | 0 | n/a |
| PDF structure | pdf_edit | 7281 | 0.000 [0.00, 0.00] | 0 | n/a |
| PDF structure | rebuild | 29309 | 0.000 [0.00, 0.00] | 0 | n/a |
| Template | all | 36590 | 0.000 [0.00, 0.00] | 0 | n/a |
| Template | pdf_edit | 7281 | 0.000 [0.00, 0.00] | 0 | n/a |
| Template | rebuild | 29309 | 0.000 [0.00, 0.00] | 0 | n/a |
