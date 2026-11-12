# Results index

Every result set, what produced it, and whether it is still current. Cite only **current**
results. Summaries from v4 on record the git commit, library versions, Ghostscript version
and arguments in their `run` entry; older ones do not.

| Set | Files | Data | Status |
| --- | --- | --- | --- |
| ADCD-Net in-domain | `adcdnet_dgx/summary.md` | Released ADCD-Net checkpoint on the DocTamper FCD, SCD and TestingSet LMDBs (50,000 images), Doc Protocol settings, one A100 on the SRMIST DGX, 12 Nov 2026. Matches the published F1 to three decimals (0.803 / 0.718 / 0.791, mean 0.771). Per-image CSVs and `summary.json` (full provenance) are on the DGX and in the private Hugging Face backup | **Current** |
| v4 | `signals_v4_10banks*`, `robustness_v4_10banks.md` | 10 banks × 30 genuine (seeds 2000–2029, 3 months), 300 PDF edits, 300 rebuilds; each also reprinted and rasterised. Templates fitted on 10 × 12 separate statements (seeds 9000–9011), `experiments/templates_v4.json` | **Current** |
| v3 | `signals_v3_10banks*`, `robustness_v3_10banks.md`, `experiments/templates_v3.json` | Same design as v4 | Superseded by v4: made before the engineering review fixes (labels of naive credit edits, column reading, dates after the dataset window, non-reproducible bytes, order-dependent forgery seeds) |
| v2 | `signals_pdfedit_v2_10banks*`, `robustness_pdfedit_v2_10banks.md` | 10 banks, PDF edits only | Superseded: generated before the bank seed was mixed into each statement's seed, so the same customer appeared at every bank |
| v1 | `signals_pdfedit_v1_himalaya*`, `financial_consistency_pdfedit_v1_himalaya*`, `robustness_pdfedit_v1_himalaya.md` | 1 bank (Himalaya National), PDF edits only | Superseded: single layout |

What changed between v3 and v4 is described in
[`docs/reviews/2026-11-04-engineering-review.md`](../../docs/reviews/2026-11-04-engineering-review.md).
