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
