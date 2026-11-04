# Rule-based signals — pdfedit_v1_himalaya

Genuine: 100 · Forged: 200

| Metric | Financial | PDF structure | Either |
| --- | --- | --- | --- |
| Precision | 1.000 | 1.000 | 1.000 |
| Recall | 0.580 | 1.000 | 1.000 |
| F1 | 0.734 | 1.000 | 1.000 |
| Accuracy | 0.720 | 1.000 | 1.000 |
| False positive rate | 0.000 | 0.000 | 0.000 |

| Variant | n | Financial | PDF structure | Either |
| --- | --- | --- | --- | --- |
| closing_balance | 51 | 100.0% | 100.0% | 100.0% |
| credit_amount | 65 | 100.0% | 100.0% | 100.0% |
| credit_amount_consistent | 57 | 0.0% | 100.0% | 100.0% |
| genuine | 100 | 0.0% | 0.0% | 0.0% |
| holder_name | 27 | 0.0% | 100.0% | 100.0% |

PDF-structure edit localisation recall: 100.0% of 4014 edited values

## How to read this

- **Same data as `financial_consistency_pdfedit_v1_himalaya`:** 100 genuine statements (seeds 1000–1099) and 200 PDF-edit forgeries (seed 0).
- **Why the PDF-structure signal scores 100%:** every forgery here was made with one tool (PyMuPDF), which leaves consistent traces: an appended update section, an extra font copy or a non-embedded Helvetica, extra content streams and a later modification date. Real forgers use many different tools, and "printing" an edited statement to a fresh PDF removes most of these traces. Treat this as an upper bound, not a real-world estimate.
- **Next to make it harder:** add laundered forgeries (re-rendered to a clean PDF), image-level edits and AI inpainting, then re-run this evaluation.

```bash
python scripts/eval_signals.py --genuine data/synthetic/genuine/himalaya_national \
    --forged data/synthetic/forged/pdf_edit --out experiments/results --tag pdfedit_v1_himalaya
```
