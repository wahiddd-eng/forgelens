# Rule-based signals — v4_10banks_reprint

Genuine: 300 · Forged: 600 · Unreadable files: 0

Code: `71f1bfcd13` · Python 3.13.18 · PyMuPDF 2.1 · WeasyPrint 70.0 · Ghostscript 10.02.1

95% Wilson intervals in brackets.

| Metric | Financial | PDF structure | Template | Any signal |
| --- | --- | --- | --- | --- |
| Recall | 0.237 [0.20, 0.27] | 0.552 [0.51, 0.59] | 0.762 [0.73, 0.79] | 0.763 [0.73, 0.80] |
| False-positive rate | 0.000 [0.00, 0.01] | 0.000 [0.00, 0.01] | 0.000 [0.00, 0.01] | 0.000 [0.00, 0.01] |
| Precision | 1.000 [0.97, 1.00] | 1.000 [0.99, 1.00] | 1.000 [0.99, 1.00] | 1.000 [0.99, 1.00] |
| F1 | 0.383 | 0.711 | 0.865 | 0.866 |
| Accuracy | 0.491 | 0.701 | 0.841 | 0.842 |
| Abstained | 0.000 | 0.000 | 0.000 | — |

| Variant | n | Financial | PDF structure | Template | Any signal |
| --- | --- | --- | --- | --- | --- |
| closing_balance | 64 | 100.0% | 100.0% | 100.0% | 100.0% |
| credit_amount | 78 | 100.0% | 100.0% | 100.0% | 100.0% |
| credit_amount_consistent | 110 | 0.0% | 100.0% | 100.0% | 100.0% |
| genuine | 300 | 0.0% | 0.0% | 0.0% | 0.0% |
| holder_name | 48 | 0.0% | 100.0% | 97.9% | 100.0% |
| rebuilt_exact | 142 | 0.0% | 0.0% | 0.0% | 0.0% |
| rebuilt_imitation | 158 | 0.0% | 19.6% | 100.0% | 100.0% |

| Bank | n | Financial recall | PDF structure recall | Template recall | Any signal recall | Any-signal FPR |
| --- | --- | --- | --- | --- | --- | --- |
| bayview_international | 90 | 0.200 | 0.517 | 0.767 | 0.767 | 0.000 |
| deccan_cooperative | 90 | 0.333 | 0.500 | 0.633 | 0.633 | 0.000 |
| ganga_mercantile | 90 | 0.233 | 0.583 | 0.750 | 0.750 | 0.000 |
| himalaya_national | 90 | 0.183 | 0.550 | 0.800 | 0.800 | 0.000 |
| konark_urban | 90 | 0.217 | 0.583 | 0.783 | 0.783 | 0.000 |
| malabar_coastal | 90 | 0.167 | 0.550 | 0.883 | 0.883 | 0.000 |
| narmada_gramin | 90 | 0.250 | 0.533 | 0.733 | 0.733 | 0.000 |
| sahyadri | 90 | 0.250 | 0.550 | 0.783 | 0.800 | 0.000 |
| tapti_valley | 90 | 0.283 | 0.600 | 0.700 | 0.700 | 0.000 |
| vindhya_state | 90 | 0.250 | 0.550 | 0.783 | 0.783 | 0.000 |

Localisation (edited values pointed at / pointed-at regions that were edited):

| Signal | Forgeries | Edits | Recall | Regions | Precision |
| --- | --- | --- | --- | --- | --- |
| PDF structure | all | 36590 | 0.199 [0.19, 0.20] | 7306 | 0.995 [0.99, 1.00] |
| PDF structure | pdf_edit | 7281 | 0.998 [1.00, 1.00] | 7267 | 1.000 [1.00, 1.00] |
| PDF structure | rebuild | 29309 | 0.000 [0.00, 0.00] | 39 | 0.000 [0.00, 0.09] |
| Template | all | 36590 | 0.609 [0.60, 0.61] | 113180 | 0.197 [0.19, 0.20] |
| Template | pdf_edit | 7281 | 0.998 [1.00, 1.00] | 7267 | 1.000 [1.00, 1.00] |
| Template | rebuild | 29309 | 0.512 [0.51, 0.52] | 105913 | 0.142 [0.14, 0.14] |
