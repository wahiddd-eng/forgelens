# Robustness of rule-based signals to laundering

Recall on forgeries (false-positive rate on genuine statements in brackets).

| Condition | Financial | PDF structure | Either | Abstained (fin / struct) |
| --- | --- | --- | --- | --- |
| Original | 0.58 (0.00) | 1.00 (0.00) | 1.00 (0.00) | 0.00 / 0.00 |
| Reprinted (Ghostscript) | 0.58 (0.00) | 1.00 (0.00) | 1.00 (0.00) | 0.00 / 0.00 |
| Rasterised (150 dpi JPEG) | 0.00 (0.00) | 0.00 (0.00) | 0.00 (0.00) | 1.00 / 1.00 |

Flag rate of the combined signals (either) by forgery type:

| Forgery type | Original | Reprinted (Ghostscript) | Rasterised (150 dpi JPEG) |
| --- | --- | --- | --- |
| closing_balance | 100% | 100% | 0% |
| credit_amount | 100% | 100% | 0% |
| credit_amount_consistent | 100% | 100% | 0% |
| genuine | 0% | 0% | 0% |
| holder_name | 100% | 100% | 0% |

## What this shows

- **Reprinting** (Ghostscript, all fonts embedded, fresh dates) removes the save-history, modification-date, non-embedded-font and content-stream traces. The structure signal still catches every forgery, now only through **font traces**: text in a different font family, or the same font embedded twice under different names. A forger who types with exactly the document's own embedded font, or rebuilds the statement from a template, would leave no such trace.
- **Rasterising** turns pages into images. Both rule-based signals have no text to read and abstain on every file. These forgeries need the image-forensics model (ADCD-Net), or OCR before the financial check.
- Laundering genuine statements caused no false positives: re-saving alone is not treated as forgery.

Data: the same 100 genuine statements and 200 PDF-edit forgeries as `signals_pdfedit_v1_himalaya`, each also reprinted and rasterised.

```bash
python scripts/launder_pdfs.py --input data/synthetic/genuine/himalaya_national --out data/synthetic/genuine_reprint --method reprint --seed 1
python scripts/launder_pdfs.py --input data/synthetic/forged/pdf_edit --out data/synthetic/forged/pdf_edit_reprint --method reprint --seed 2 --masks
python scripts/launder_pdfs.py --input data/synthetic/genuine/himalaya_national --out data/synthetic/genuine_raster --method raster --seed 1
python scripts/launder_pdfs.py --input data/synthetic/forged/pdf_edit --out data/synthetic/forged/pdf_edit_raster --method raster --seed 2 --masks
python scripts/eval_signals.py --genuine data/synthetic/genuine_reprint --forged data/synthetic/forged/pdf_edit_reprint --tag pdfedit_v1_himalaya_reprint
python scripts/eval_signals.py --genuine data/synthetic/genuine_raster --forged data/synthetic/forged/pdf_edit_raster --tag pdfedit_v1_himalaya_raster
python scripts/compare_results.py --tags pdfedit_v1_himalaya pdfedit_v1_himalaya_reprint pdfedit_v1_himalaya_raster \
    --names Original "Reprinted (Ghostscript)" "Rasterised (150 dpi JPEG)" --out experiments/results/robustness_pdfedit_v1_himalaya.md
```
