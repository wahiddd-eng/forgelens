# Results index

Every result set, what produced it, and whether it is still current. Cite only **current**
results. Summaries from v4 on record the git commit, library versions, Ghostscript version
and arguments in their `run` entry; older ones do not.

| Set | Files | Data | Status |
| --- | --- | --- | --- |
| ADCD-Net in-domain | `adcdnet_dgx.md` | Released ADCD-Net checkpoint on the DocTamper FCD, SCD and TestingSet LMDBs (50,000 images), Doc Protocol settings, one A100 on the SRMIST DGX, 12 Nov 2026. Matches the published F1 to three decimals (0.803 / 0.718 / 0.791, mean 0.771). Per-image CSVs and `summary.json` (full provenance) are on the DGX and in the private Hugging Face backup | **Current** |
| ADCD-Net cross-domain | `adcdnet_dgx-cross.md` | Released checkpoint on T-SROIE, OSTF, Tampered-IC13 and RealTextManipulation test sets (8,658 images) with our PaddleOCR masks, 13 Nov 2026. Matches the published F1 (0.623 / 0.441 / 0.579 / 0.158 vs 0.159; mean 0.450) | **Current** |
| ADCD-Net on AIForge-Doc | `adcdnet_dgx-aiforge.md` | Released checkpoint on AIForge-Doc v1's 812 AI-inpainted test images and 812 authentic originals, 13 Nov 2026. F1 0.176 (0.154–0.197); flags 12.1% of forged and 2.7% of authentic images at the 1% area threshold. New result: no published score | **Current** |
| ADCD-Net on statement pages | `adcdnet_pages_v4.md` | Released checkpoint on the v4 synthetic statements (genuine, PDF edits, rebuilds, each also rasterised) rendered at 100, 150 and 200 DPI, 512 px tiles, 14 Nov 2026. AUC 0.47–0.54 everywhere: the base model cannot tell these forgeries from genuine statements. Pipeline check on 500 DocTamper images matches upstream (F1 0.940; 0.932 on 2 x 2 mosaics) | **Current** |
| ADCD-Net fine-tuned on image-level forgeries | `adcdnet_ft1.md` | Released model on spliced and AI-inpainted statements (AUC 0.49–0.53), and fine-tuning run ft1 (10,000 steps, 14 Nov 2026): validation AUC 0.999, F1 0.88 on held-out statements, DocTamper FCD F1 0.78. Test-set results in `adcdnet_ft1_test.md` | Superseded in part |
| ft1 on the held-out test set, AIForge-Doc and DocTamper | `adcdnet_ft1_test.md` | New statements: AUC 0.998 (inpaint) and 0.993 (splice), 96% caught at 1% false alarms; PDF edits and rebuilds at chance. AIForge-Doc F1 fell to 0.026 (from 0.176); DocTamper mean 0.750 (from 0.771). 15 Nov 2026 | **Current** |
| Unseen bank layouts (ft2 vs ft1) | `adcdnet_unseen_banks.md` | ft2, trained without konark_urban and malabar_coastal, on those banks: AUC 0.872 (inpaint) and 0.956 (splice), against 1.000 and 0.999 for ft1; caught at 1%: 60% and 85% against 100% and 98%. H4 fails for this model. 15 Nov 2026 | **Current**; see ft4 |
| ft3: varied forgeries | `adcdnet_ft3.md` | Three inpainting models and JPEG 60–95: AIForge-Doc F1 0.115 (ft1 0.026, released 0.176), authentic false alarms 4.9% (ft1 9.6%); test set still 94–95% caught at 1%. 15 Nov 2026 | **Current** |
| ft4: unseen bank layouts (H4); the image model kept | `adcdnet_ft4.md` | Trained only on 100 generated banks; on the 10 hand-made banks, which it never saw: AUC 1.000 (inpaint) and 0.999 (splice), 100% and 99% caught at 1% false alarms (ft1, which saw them: 96%). H4 holds. AIForge-Doc F1 0.076, authentic false alarms 1.6%. DocTamper mean F1 0.731 (published 0.771); cross-domain mean 0.438 (published 0.450; T-SROIE +0.094). 16–17 Nov 2026 | **Current** |
| ft5: ft3 + ft4 data | `adcdnet_ft5.md` | Test set 100% caught at 1% (inpaint and splice), F1 0.72; AIForge-Doc F1 0.049 (ft4 0.076, ft3 0.115, released 0.176). Combining the training sets did not help; ft4 stays the image model. 16 Nov 2026 | **Current** |
| Ablations (H2) and misses | `ablations_test.md` | Without the image model 50%, without template 60%, without OCR 61% (all: 69%); financial, PDF structure and the released model add nothing on this test set. 26% of forgeries (consistent, then rasterised) leave no trace; of the rest fusion catches 89%. 17 Nov 2026 | **Current** |
| Fusion on the held-out test set (H1) | `fusion_test.md` | Signals fused by gradient boosting. With ft4, the released model and OCR arithmetic (17 Nov): **69%** of all 1,196 forgeries caught at 1% false alarms (71% at 5%), against 34% for the image model alone; rasterised PDF edits 45% (were 2–10%). First run with ft1 (15 Nov): 63%. 15–17 Nov 2026 | **Current** |
| v4 | `signals_v4_10banks*`, `robustness_v4_10banks.md` | 10 banks × 30 genuine (seeds 2000–2029, 3 months), 300 PDF edits, 300 rebuilds; each also reprinted and rasterised. Templates fitted on 10 × 12 separate statements (seeds 9000–9011), `experiments/templates_v4.json` | **Current** |
| v3 | `signals_v3_10banks*`, `robustness_v3_10banks.md`, `experiments/templates_v3.json` | Same design as v4 | Superseded by v4: made before the engineering review fixes (labels of naive credit edits, column reading, dates after the dataset window, non-reproducible bytes, order-dependent forgery seeds) |
| v2 | `signals_pdfedit_v2_10banks*`, `robustness_pdfedit_v2_10banks.md` | 10 banks, PDF edits only | Superseded: generated before the bank seed was mixed into each statement's seed, so the same customer appeared at every bank |
| v1 | `signals_pdfedit_v1_himalaya*`, `financial_consistency_pdfedit_v1_himalaya*`, `robustness_pdfedit_v1_himalaya.md` | 1 bank (Himalaya National), PDF edits only | Superseded: single layout |

What changed between v3 and v4 is described in
[`docs/reviews/2026-11-04-engineering-review.md`](../../docs/reviews/2026-11-04-engineering-review.md).

ADCD-Net runs write their full output (per-image CSVs, `summary.json`) to
`adcdnet_<tag>/` on the machine that ran them; those folders are git-ignored. The tables
from them are copied to `adcdnet_<tag>.md` here.
