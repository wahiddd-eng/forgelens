# Fine-tuned ADCD-Net (ft1) on the held-out test set, AIForge-Doc and DocTamper

15 Nov 2026, SRMIST DGX A100, code f08cc0f (`scripts/queue_test_eval.sh`). ft1 =
`train_ft1/Step7000_Score0.8796.pth` (sha256 49ba822c070f), the best validation checkpoint of
the run in `adcdnet_ft1.md`.

## Held-out test set

200 new statements (20 per bank, seeds 5000–5019, never trained on; `scripts/make_test_set.sh`),
each forged four ways, all rasterised (150 DPI, JPEG 85). AUC of forged against the 200
rasterised genuine statements, page peak score, and the share caught when 1% of genuine
statements may be flagged:

| Forgery | Released AUC | ft1 AUC | Released caught @1% | ft1 caught @1% | ft1 F1 (95% CI) |
| --- | ---: | ---: | ---: | ---: | --- |
| AI inpainting (SDXL) | 0.494 | **0.998** | 0% | **96%** | 0.765 (0.735–0.794) |
| Splice | 0.530 | **0.993** | 0% | **96%** | 0.761 (0.730–0.792) |
| PDF edit | 0.499 | 0.549 | 2% | 2% | 0.160 (0.126–0.194) |
| Rebuild (198) | 0.519 | 0.536 | 3% | 2% | 0.021 (0.018–0.024) |

ft1 keeps its validation performance on statements it has never seen: the gain is not
memorisation of the training statements. Forgeries without pixel traces (PDF edits,
rebuilds) stay at chance, as expected: those are the PDF signals' to catch.

## AIForge-Doc (diffusion edits of receipts and forms by other AI tools)

| Model | F1 (95% CI) | Forged flagged | Authentic flagged |
| --- | --- | ---: | ---: |
| Released | 0.176 (0.154–0.197) | 12.1% | 2.7% |
| ft1 | 0.026 (0.018–0.034) | 19.2% | 9.6% |

Fine-tuning made AIForge-Doc worse: lower F1 and four times the false alarms on authentic
images. ft1 learned the traces of our forgeries (SDXL retouching and spliced patches on
statement pages), not AI editing in general. H5 holds on our statements and fails on
AIForge-Doc. Next: train on more varied forgeries (several inpainting models, compression
settings, document types).

## DocTamper (Doc Protocol, in-domain)

| Set | Images | ft1 F1 | Released F1 |
| --- | ---: | ---: | ---: |
| FCD | 2,000 | 0.781 | 0.803 |
| SCD | 18,000 | 0.695 | 0.718 |
| TestingSet | 30,000 | 0.775 | 0.791 |
| Mean | | 0.750 | 0.771 |

A small loss (0.02) of DocTamper skill, from 30% DocTamper crops in training.
