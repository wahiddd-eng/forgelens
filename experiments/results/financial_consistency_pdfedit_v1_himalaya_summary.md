# Financial-consistency signal — pdfedit_v1_himalaya

Genuine: 100 · Forged: 200

| Metric | Value |
| --- | --- |
| Accuracy | 0.720 |
| Precision | 1.000 |
| Recall | 0.580 |
| F1 | 0.734 |
| False-positive rate | 0.000 |

| Variant | Statements | Flagged | Flag rate |
| --- | --- | --- | --- |
| closing_balance | 51 | 51 | 100.0% |
| credit_amount | 65 | 65 | 100.0% |
| credit_amount_consistent | 57 | 0 | 0.0% |
| genuine | 100 | 0 | 0.0% |
| holder_name | 27 | 0 | 0.0% |

## How this was produced

- Data: 100 genuine statements (Himalaya National Bank layout, seeds 1000–1099, 3 months each) and 200 PDF-edit forgeries (2 per genuine statement, seed 0).
- Prediction: "forged" when any financial-consistency check fails.
- Caveats: one synthetic layout only; the genuine statements come from the same generator, so the 0% false-positive rate must be confirmed on consented real statements.

```bash
python scripts/generate_statements.py --count 100 --seed 1000 --months 3 --out data/synthetic/genuine
python scripts/forge_pdf_edits.py --genuine data/synthetic/genuine/himalaya_national \
    --out data/synthetic/forged/pdf_edit --per-statement 2 --seed 0
python scripts/eval_financial.py --genuine data/synthetic/genuine/himalaya_national \
    --forged data/synthetic/forged/pdf_edit --out experiments/results --tag pdfedit_v1_himalaya
```
