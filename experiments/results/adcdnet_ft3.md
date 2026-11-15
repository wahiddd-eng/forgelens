# ft3: fine-tuning on varied forgeries

15 Nov 2026, SRMIST DGX A100, code cff5ee9 (`scripts/queue_ft3.sh`). ft3 =
`train_ft3/Step6000_Score0.8704.pth` (sha256 5c0501fe11be), trained from the released weights
like ft1 but on the ft1 data plus a second, varied set: forgeries by three inpainting models
(SDXL, SD 2, SD 1.5) at strength 0.45–0.9, and genuine and forged pages saved at JPEG
quality 60–95 instead of always 85.

## AIForge-Doc

| Model | F1 (95% CI) | Pixel F1 | Forged flagged | Authentic flagged |
| --- | --- | ---: | ---: | ---: |
| Released | 0.176 (0.154–0.197) | 0.274 | 12.1% | 2.7% |
| ft1 (SDXL only, JPEG 85) | 0.026 (0.018–0.034) | 0.039 | 19.2% | 9.6% |
| **ft3 (3 models, JPEG 60–95)** | **0.115 (0.096–0.133)** | 0.187 | 13.2% | 4.9% |

## Held-out test set (200 new statements of each kind, rasterised)

| Forgery | ft1 AUC | ft3 AUC | ft1 caught @1% | ft3 caught @1% | ft3 F1 (95% CI) |
| --- | ---: | ---: | ---: | ---: | --- |
| AI inpainting (SDXL) | 0.998 | 0.996 | 96% | 94% | 0.709 (0.675–0.744) |
| Splice | 0.993 | 0.994 | 96% | 95% | 0.715 (0.682–0.748) |
| PDF edit | 0.549 | 0.553 | 2% | 2% | 0.171 (0.136–0.206) |
| Rebuild | 0.536 | 0.551 | 2% | 4% | 0.035 (0.031–0.039) |

## Reading

Varying the forgeries recovers most of what ft1 lost on AIForge-Doc: F1 rises from 0.026 to
0.115 (4.4 times) and false alarms on authentic images halve (9.6% to 4.9%), while detection
on our statements stays about the same (94–95% against 96% at 1% false alarms). It is still
below the released model on AIForge-Doc (0.176): three open inpainting models and our
statement pages are not yet varied enough to cover AIForge's AI tools and document types.
The trend says more variety helps; next candidates are more models, other document types
mixed in (receipts, forms), and the DocTamper share.
