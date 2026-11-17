# Ablations (H2) and what fusion misses: held-out test set

17 Nov 2026, code ce6af17 (`scripts/run_ablations.sh`, `scripts/explain_misses.py`). Image model
ft4; gradient boosting, out-of-fold by source statement; one threshold at 1% (5%) of the 400
genuine statements; 1,196 forgeries.

## Leaving signals out, and the image model with one other signal

| Run | Caught @1% | Caught @5% | AUC |
| --- | ---: | ---: | ---: |
| All signals | **69%** | 71% | 0.881 |
| without image model (ft4) | 50% | 57% | 0.850 |
| without template | 60% | 62% | 0.807 |
| without OCR arithmetic | 61% | 65% | 0.866 |
| without released image model | 69% | 71% | 0.882 |
| without financial (PDF text) | 69% | 71% | 0.881 |
| without PDF structure | 69% | 72% | 0.881 |
| image + template | 62% | 65% | 0.864 |
| image + PDF structure | 52% | 56% | 0.786 |
| image + financial | 43% | 47% | 0.712 |
| image + OCR arithmetic | 42% | 45% | 0.712 |

Three signals carry the result: the image model (−19 points without it), the template
(−9) and OCR arithmetic (−8). On this test set the financial and PDF-structure signals and the
released image model add nothing beyond them: every digital PDF edit they catch the template
also catches. That holds only because the template was fitted on the same 10 banks as the
test statements. On statements from banks without a fitted template (every real statement so
far), the template abstains and PDF structure is what catches digital edits
(`scripts/eval_real.sh` fuses without the template for that reason). H2 holds in part: no
single signal comes close to fusion (best pair 62%, alone 34%), but two of the six are
redundant on this test set.

## What is missed (fused, 1% false alarms)

| Method | Operation | Balances | Laundering | n | Caught @1% | Caught @5% |
| --- | --- | --- | --- | ---: | ---: | ---: |
| image_inpaint / image_splice | all | all | raster | 400 | 99–100% | 100% |
| pdf_edit | all | all | none | 200 | 100% | 100% |
| pdf_edit | closing_balance | broken | raster | 38 | 97% | 100% |
| pdf_edit | credit_amount | broken | raster | 55 | 78% | 82% |
| pdf_edit | credit_amount | consistent | raster | 75 | 12% | 17% |
| pdf_edit | holder_name | consistent | raster | 32 | 3% | 6% |
| rebuild | income_inflation | consistent | none | 147 | 61% | 61% |
| rebuild | income_inflation + holder_name | consistent | none | 51 | 49% | 49% |
| rebuild | income_inflation | consistent | raster | 147 | 14% | 19% |
| rebuild | income_inflation + holder_name | consistent | raster | 51 | 10% | 20% |

**The ceiling.** 305 forgeries (26%) are PDF edits or rebuilds whose balances all agree, then
rasterised: no PDF trace, no arithmetic error, no pixel tampering (the page was rendered whole).
Only a layout or typography difference could betray them, and fusion catches about 12% of
them. Of the other 891 forgeries, fusion catches **89%** at 1% false alarms. The largest
detectable group still missed is the digital rebuild (40–50% missed), seen only by the
template; a rebuild imitates the layout closely enough that the template often accepts it.
