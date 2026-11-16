# ft5: ft3 and ft4 training data together

16 Nov 2026, SRMIST DGX A100, code aa410e1 (`scripts/queue_ft5.sh`). ft5 =
`train_ft5/Step8000_Score0.8797.pth` (sha256 dbf227bb9b3c), trained from the released weights
for 12,000 steps on every page of the ft3 cache (10 hand-made banks, varied forgeries) and the
ft4 cache (100 generated banks): 11,439 pages, mixed with DocTamper as before.

## Held-out test set (200 new statements of each kind, rasterised)

| Forgery | ft1 | ft3 | ft4 | **ft5** caught @1% | ft5 AUC | ft5 F1 (95% CI) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| AI inpainting | 96% | 94% | 100% | **100%** | 1.000 | 0.724 (0.690–0.758) |
| Splice | 96% | 95% | 99% | **100%** | 0.997 | 0.725 (0.690–0.759) |
| PDF edit | 2% | 2% | – | 2% | 0.526 | 0.138 |
| Rebuild | 2% | 4% | – | 4% | 0.540 | 0.029 |

## AIForge-Doc

| Model | F1 (95% CI) | Pixel F1 | Forged flagged | Authentic flagged |
| --- | --- | ---: | ---: | ---: |
| Released | 0.176 (0.154–0.197) | 0.274 | 12.1% | 2.7% |
| ft1 | 0.026 (0.018–0.034) | 0.039 | 19.2% | 9.6% |
| ft3 | 0.115 (0.096–0.133) | 0.187 | 13.2% | 4.9% |
| ft4 | 0.076 (0.062–0.091) | 0.135 | 4.4% | 1.6% |
| ft5 | 0.049 (0.037–0.060) | 0.092 | 7.0% | 4.2% |

## Reading

On our statements ft5 is as good as ft4 (100% caught at 1% false alarms) but localises
less well (F1 0.72 against 0.79). On AIForge-Doc it is worse than both ft3 and ft4: combining
the two training sets did not combine their strengths. Every fine-tuned model is below the
released one on AIForge-Doc; fine-tuning on our statements trades away part of the general
AI-editing detection, and no mix of our data tried so far recovers it. This is reported as a
limitation. **ft4 is kept as the image model**: the same detection on our statements, the best
localisation, and the fewest false alarms on authentic AIForge-Doc images (1.6%).
