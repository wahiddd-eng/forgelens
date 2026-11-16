# ft4: trained only on generated bank layouts

15–16 Nov 2026, SRMIST DGX A100, code eac7794 (`scripts/queue_ft4.sh`). ft4 =
`train_ft4/Step8000_Score0.8657.pth` (sha256 8cee779fdd20), trained from the released weights
for 10,000 steps on 100 generated fictional banks (`generator/random_banks.py`, 4 statements
each; 396 of 400 rendered and read back, 4 failed) with ft3's varied forgeries (splices, and
inpainting by SDXL, SD 2 and SD 1.5 at strength 0.45–0.9; pages at JPEG quality 60–95), mixed
with DocTamper as for ft1. **None of the 10 hand-made banks was in training.**

## Held-out test set (the 10 hand-made banks, 200 new statements of each kind, rasterised)

| Forgery | ft1 AUC (saw these banks) | ft4 AUC (never saw them) | ft1 caught @1% | ft4 caught @1% | ft4 F1 (95% CI) |
| --- | ---: | ---: | ---: | ---: | --- |
| AI inpainting (SDXL) | 0.998 | **1.000** | 96% | **100%** | 0.791 (0.761–0.821) |
| Splice | 0.993 | **0.999** | 96% | **99%** | 0.789 (0.759–0.819) |

At 5% false alarms ft4 catches 100% of both. Area AUC 0.816 (inpaint) and 0.830 (splice).

## AIForge-Doc

| Model | F1 (95% CI) | Pixel F1 | Forged flagged | Authentic flagged |
| --- | --- | ---: | ---: | ---: |
| Released | 0.176 (0.154–0.197) | 0.274 | 12.1% | 2.7% |
| ft1 | 0.026 (0.018–0.034) | 0.039 | 19.2% | 9.6% |
| ft3 | 0.115 (0.096–0.133) | 0.187 | 13.2% | 4.9% |
| ft4 | 0.076 (0.062–0.091) | 0.135 | 4.4% | 1.6% |

## Reading

H4 holds for ft4. ft2, trained on 8 of the 10 hand-made banks, caught only 60% (inpaint) and
85% (splice) on the 2 it had not seen (`adcdnet_unseen_banks.md`). ft4 has seen none of the 10
and catches 100% and 99%, more than ft1, which trained on all of them. With 100 varied
layouts the model learns traces of the edit itself, not the look of particular banks.
Localisation is also better: F1 0.79 against 0.71 for ft1 and ft3.

AIForge-Doc stays the weak spot. ft4 raises the fewest false alarms of any model (1.6% of
authentic images) but also flags few forgeries (4.4%), and its F1 (0.076, CI 0.062–0.091) is
below ft3's (0.115, 0.096–0.133) although both saw the same kinds of forgery. The difference
is the training statements: ft3 trained on the hand-made banks, ft4 on generated ones, and
fewer of them. Why that matters for AIForge-Doc is not yet known. The final model (ft5,
`scripts/queue_ft5.sh`) is trained on both sets together.

Fusion with ft4 needs one more run: test-ft4 covered the rasterised genuine statements but
not the rasterised PDF edits and rebuilds, so a fusion model could read the label off whether
an image score exists. `fuse_signals.py` now refuses such uneven coverage, and
`queue_ft5.sh` first runs ft4 on the missing folders.
