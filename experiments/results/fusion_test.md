# Fusion on the held-out test set (H1)

15 Nov 2026, SRMIST DGX, code eac7794 (`scripts/run_fusion.sh`). The held-out test set: 200 new
genuine statements (seeds 5000–5019, 10 banks), as digital PDFs and rasterised, and 1,196
forgeries of them. Rule-based signals on every file (template profiles fitted on the v4
training statements); image signal = the fine-tuned ADCD-Net's page peak score, run on the
rasterised files (598 digital files have no image score: missing). Fused scores are
out-of-fold, folds grouped by source statement. One threshold for every input, set so that 1%
of all 400 genuine statements are flagged; share of each kind of forgery caught at it:

## With ft1 as the image signal

| Forgery | Laundering | n | Image | Financial | PDF structure | Template | Fused (logistic) | **Fused (boosting)** |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AI inpainting | raster | 200 | 96% | 0% | 0% | 0% | 46% | **100%** |
| Splice | raster | 200 | 97% | 0% | 0% | 0% | 44% | **98%** |
| PDF edit | none | 200 | 0% | 46% | 100% | 100% | 100% | **100%** |
| PDF edit | raster | 200 | 2% | 0% | 0% | 0% | 10% | **13%** |
| Rebuild | none | 198 | 0% | 0% | 0% | 58% | 58% | **58%** |
| Rebuild | raster | 198 | 3% | 0% | 0% | 0% | 4% | **7%** |
| **All forgeries** | | 1,196 | 33% | 8% | 17% | 26% | 44% | **63%** |
| False alarms | | 400 | 1% | 0% | 0% | 0% | 1% | 1% |
| AUC | | | 0.672 | 0.642 | 0.678 | 0.781 | 0.853 | **0.871** |

At 5% false alarms: image 37%, template 26%, fused (boosting) 66%.

## With ft3 as the image signal

Same table within 1–3 points: all forgeries caught 34% (image) and **62%** (fused, boosting) at
1% false alarms, 67% at 5%; AUC 0.871.

## Reading

Fused by gradient boosting, the four signals catch **63%** of all forgeries at 1% false alarms,
against 33% for the fine-tuned image model alone and 26% for the best rule-based signal: H1
holds on this test set. Each forgery kind is caught by the signal that can see it (image
forgeries by the image model, digital PDF edits by PDF structure and template), and fusion
keeps both with one threshold.

The ceiling: PDF edits and rebuilds that were then rasterised (398 of 1,196, a third) leave
neither a PDF trace nor a pixel trace, and no signal catches more than a few per cent of
them. Of the other 798, fusion catches 94%. Logistic regression cannot combine signals that
are present on different inputs as well as boosting does (44%), so boosting is the fusion
model.

Caveats: synthetic statements from the same generator and banks as training; the image
model was not run on the digital test files (it is at chance on PDF edits there, see
`adcdnet_pages_v4.md`, so its column would change little); real statements next.

## With ft4 and the OCR arithmetic signal (17 Nov 2026)

Image model ft4 (the model kept), the released model, and the OCR arithmetic signal after the
misread rules and the size-graded score (code 2902c76). Same 400 genuine and 1,196 forged
statements; one threshold at 1% of all genuine statements.

| Forgery | Laundering | n | Image (ft4) | Image (released) | Financial | PDF structure | Template | OCR arithmetic | Fused (logistic) | Fused (boosting) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| image_inpaint | raster | 200 | 100% | 2% | 0% | 0% | 0% | 47% | 56% | 100% |
| image_splice | raster | 200 | 100% | 2% | 0% | 0% | 0% | 48% | 78% | 100% |
| pdf_edit | none | 200 | 0% | 0% | 46% | 100% | 100% | 0% | 100% | 100% |
| pdf_edit | raster | 200 | 2% | 2% | 0% | 0% | 0% | 46% | 31% | **45%** |
| rebuild | none | 198 | 0% | 0% | 0% | 0% | 58% | 0% | 58% | 58% |
| rebuild | raster | 198 | 3% | 5% | 0% | 0% | 0% | 5% | 4% | 13% |
| **All forgeries** | | 1,196 | 34% | 2% | 8% | 17% | 26% | 24% | 55% | **69%** |
| False alarms | | 400 | 1% | 1% | 0% | 0% | 0% | 1% | 1% | 1% |
| AUC | | | 0.668 | 0.587 | 0.642 | 0.678 | 0.781 | 0.598 | 0.880 | 0.881 |

At 5% false alarms: fused (boosting) 71%, OCR arithmetic alone 25%.

The OCR signal, before the 16 Nov fixes, flagged 49% of genuine rasterised statements and
caught nothing at 1% false alarms; now it catches 24% of all forgeries alone, and 46% of the
rasterised PDF edits, which no other signal sees. Fusion rises from 62% to **69%** at 1% false
alarms. With ft5 instead of ft4: 70% (73% at 5%), the same within noise; ft4 is kept for its
localisation and AIForge-Doc false alarms (`adcdnet_ft5.md`).

What is still missed: rasterised rebuilds (87%), digital rebuilds (42%; only the template
sees them) and the rasterised PDF edits whose balances the forger kept consistent.
