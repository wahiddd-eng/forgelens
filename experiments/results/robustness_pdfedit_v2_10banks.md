# Robustness of rule-based signals to laundering

Recall on forgeries (false-positive rate on genuine statements in brackets).

| Condition | Financial | PDF structure | Either | Abstained (fin / struct) |
| --- | --- | --- | --- | --- |
| Original | 0.52 (0.00) | 1.00 (0.00) | 1.00 (0.00) | 0.00 / 0.00 |
| Reprinted (Ghostscript) | 0.52 (0.00) | 1.00 (0.00) | 1.00 (0.00) | 0.00 / 0.00 |
| Rasterised (150 dpi JPEG) | 0.00 (0.00) | 0.00 (0.00) | 0.00 (0.00) | 1.00 / 1.00 |

Flag rate of the combined signals (either) by forgery type:

| Forgery type | Original | Reprinted (Ghostscript) | Rasterised (150 dpi JPEG) |
| --- | --- | --- | --- |
| closing_balance | 100% | 100% | 0% |
| credit_amount | 100% | 100% | 0% |
| credit_amount_consistent | 100% | 100% | 0% |
| genuine | 0% | 0% | 0% |
| holder_name | 100% | 100% | 0% |

## What changed from v1

- **10 fictional bank layouts instead of 1** (3 templates: classic table, ledger grid, modern band), varying column order and labels, date formats (`03-09-2025`, `03/09/25`, `03-Sep-2025`, `03 Sep 2025`, `03.09.2025`), digit grouping (Indian, western, none), `Cr` suffixes, fonts (DejaVu Sans/Serif/Condensed, Liberation Sans/Serif, Carlito), portrait and landscape pages, summaries above or below the table, and narration styles.
- **Data:** 300 genuine statements (30 per bank, seeds 2000–2029) and 600 PDF-edit forgeries (2 per statement), each also reprinted and rasterised. About half of the forgeries use the bank's own font ("matched"), half Helvetica ("fallback").
- **Findings are unchanged across layouts:** no false positives on any bank; the financial check catches every arithmetic-breaking edit and none of the arithmetic-preserving ones; the structure signal catches every text-layer forgery, also after reprinting, through font traces; rasterising defeats both rule-based signals. Per-bank tables are in `signals_pdfedit_v2_10banks*_summary.md`.

```bash
python scripts/generate_statements.py --bank all --count 30 --seed 2000 --months 3 --out data/synthetic/genuine
python scripts/forge_pdf_edits.py --genuine data/synthetic/genuine --out data/synthetic/forged/pdf_edit --per-statement 2 --seed 0
# launder both folders with --method reprint (seed 1 genuine, 2 forged) and --method raster, then:
python scripts/eval_signals.py --genuine data/synthetic/genuine --forged data/synthetic/forged/pdf_edit --tag pdfedit_v2_10banks
```
