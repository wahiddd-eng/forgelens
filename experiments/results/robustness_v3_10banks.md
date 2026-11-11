# Robustness of rule-based signals to laundering

Recall on forgeries (false-positive rate on genuine statements in brackets).

| Condition | Financial | PDF structure | Template | Any signal | Abstained (Financial / PDF structure / Template) |
| --- | --- | --- | --- | --- | --- |
| Original | 0.28 (0.00) | 0.51 (0.00) | 0.76 (0.00) | 0.76 (0.00) | 0.00 / 0.00 / 0.00 |
| Reprinted (Ghostscript) | 0.28 (0.00) | 0.55 (0.00) | 0.75 (0.00) | 0.76 (0.00) | 0.00 / 0.00 / 0.00 |
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

## What this shows

- **Data (v3):** 300 genuine test statements (10 banks × 30, seeds 2000–2029), 300 PDF-edit forgeries and 300 template-rebuilt forgeries (about half `rebuilt_exact`, half `rebuilt_imitation`), each also reprinted and rasterised. Template profiles were learned from a **separate** set of 120 genuine statements (10 banks × 12, seeds 9000–9011): `experiments/templates_v3.json`. The seed now mixes in the bank, so no customer appears at more than one bank (v2 reused the same 30 customers at every bank).
- **Template matching is the strongest single signal** (recall 0.76 vs 0.51 structure and 0.28 financial, no false positives). It catches every PDF-edit forgery (the edit's font is never used by that bank, even when it is the "same" font under another name) and every imitation rebuild (wrong font, text size, masthead or creator).
- **Exact rebuilds (`rebuilt_exact`) defeat every document-based signal.** A forger with the bank's real template leaves nothing in the file to find. This is the honest floor of document-only detection: such forgeries need an external check, such as verifying the statement with the bank or account-aggregator data.
- **Reprinting does not help the forger:** recall is unchanged, and re-saved genuine statements are still not flagged (the producer changes, so it is deliberately not compared).
- **Rasterising still defeats all three rule-based signals**, which all abstain. This is the gap for the image model (ADCD-Net) or OCR.

```bash
python scripts/generate_statements.py --bank all --count 12 --seed 9000 --out data/synthetic/train_genuine
python scripts/fit_templates.py --genuine data/synthetic/train_genuine --out experiments/templates_v3.json
python scripts/generate_statements.py --bank all --count 30 --seed 2000 --out data/synthetic/genuine
python scripts/forge_pdf_edits.py --genuine data/synthetic/genuine --out data/synthetic/forged/pdf_edit --per-statement 1 --seed 0
python scripts/forge_rebuild.py --genuine data/synthetic/genuine --out data/synthetic/forged/rebuild --per-statement 1 --seed 0
# launder genuine (seed 1) and forged (seed 2) with --method reprint and --method raster, then:
python scripts/eval_signals.py --genuine data/synthetic/genuine --forged data/synthetic/forged \
    --templates experiments/templates_v3.json --tag v3_10banks
```
