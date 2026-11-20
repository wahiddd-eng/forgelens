# Phone screenshots and WhatsApp copies

17 Nov 2026, code eabcb5e (`scripts/queue_phone_test.sh`). 500 held-out test statements (100
genuine, 100 each of PDF edits, rebuilds, splices and AI inpaintings), each made into a phone
screenshot (1080 px wide, PNG) and that screenshot sent over WhatsApp (JPEG quality 60–80,
4:2:0). The fusion model fitted on the test set (ft4 + rule-based signals + OCR arithmetic,
`fusion_test-ft4-ocr`) applied unchanged, at the thresholds that flag 1% (5%) of the test
set's genuine statements. Pages re-rendered at 150 DPI.

| Statements | Laundering | n | Image (ft4) | OCR arithmetic | Fused |
| --- | --- | ---: | ---: | ---: | ---: |
| genuine | screenshot | 100 | 2% (7%) | 1% (6%) | **9% (19%)** |
| genuine | whatsapp | 100 | **37% (54%)** | 7% (17%) | **73% (79%)** |
| image_inpaint | screenshot | 100 | 90% (93%) | 46% (59%) | 96% (96%) |
| image_inpaint | whatsapp | 100 | 88% (93%) | 42% (53%) | 99% (99%) |
| image_splice | screenshot | 100 | 93% (96%) | 34% (41%) | 97% (98%) |
| image_splice | whatsapp | 100 | 85% (94%) | 32% (38%) | 99% (99%) |
| pdf_edit | screenshot | 100 | 2% (10%) | 36% (40%) | 44% (53%) |
| pdf_edit | whatsapp | 100 | 36% (54%) | 29% (37%) | 81% (83%) |
| rebuild | screenshot | 100 | 6% (17%) | 7% (13%) | 19% (29%) |
| rebuild | whatsapp | 100 | 36% (55%) | 9% (16%) | 68% (70%) |

Fused AUC: screenshot 0.782, WhatsApp 0.673. The PDF signals and the template abstain on all
of them (no text layer).

## Reading

**Screenshots mostly survive.** The image model alone still catches 90–93% of image forgeries
at 2% false alarms on genuine screenshots, and OCR arithmetic still catches 36% of PDF edits.
The fused model, though, flags 9% of genuine screenshots instead of 1%: its thresholds do not
transfer to a laundering it was not fitted on.

**WhatsApp breaks the image model's calibration.** It flags 37% of genuine WhatsApp copies;
its "catches" on PDF edits and rebuilds (36%) are the same false alarms. The image forgeries
still score higher than genuine copies (85–88% at the threshold), but at a false-alarm rate no
one could use. Likely cause, being tested: the 1080 px JPEG is resampled when the page is
re-rendered at 150 DPI, which smears its 8x8 compression blocks into a pattern the model reads
as tampering. `scripts/queue_phone_native.sh` reads such pages at their own pixels and refits
fusion with phone copies included.

## Read at their own pixels (`--native`), 18 Nov 2026

`scripts/queue_phone_native.sh`, code b4c9b08. Same 1,000 statements; the image model reads
image-only pages without re-rendering them.

| Statements | Laundering | Image, re-rendered | Image, native | Fused (test-set model), re-rendered | Fused, native |
| --- | --- | ---: | ---: | ---: | ---: |
| genuine | screenshot | 2% | 11% | 9% | 18% |
| genuine | whatsapp | 37% | **20%** | 73% | **50%** |
| image forgeries | screenshot | 90–93% | 84% | 96–97% | 90–91% |
| image forgeries | whatsapp | 85–88% | 81% | 99% | 93–94% |

Fused AUC: screenshot 0.782 → 0.771, WhatsApp 0.673 → 0.709. Native reading halves the false
alarms on WhatsApp copies but doubles them on screenshots: resampling the JPEG is part of the
problem, the other part is that ft4 has never seen pages at a phone's resolution (1080 px wide,
about 130 DPI, against 150 DPI in training) or with WhatsApp's compression.

**Fusion refitted with the phone copies** (out-of-fold, 600 genuine statements, one threshold at
1%): 54% of all 1,996 forgeries caught (63% at 5%), against 69% on the test set without phone
copies. Image forgeries on phone copies 63–79%, PDF edits 7–19%, rebuilds 1–8%. Calibrating
the fusion alone does not recover the image model.

Next: ft6, ft4 trained further on screenshot and WhatsApp copies of its own training
statements (`scripts/queue_ft6.sh`).

## ft6: phone copies in training (18–19 Nov 2026)

`scripts/queue_ft6.sh`, code 0387a94. ft6 = ft4 + 6,000 steps on ft4's own training statements
plus their screenshot and WhatsApp copies (`train_ft6/Step2000_Score0.8636.pth`, sha256
041189989ec2). Pages re-rendered at 150 DPI. Thresholds per laundering (genuine statements of
the same kind):

| Laundering | Forgery | ft6 AUC | ft6 caught @1% | ft6 caught @5% | F1 |
| --- | --- | ---: | ---: | ---: | ---: |
| raster (test set) | AI inpainting | 1.000 | 100% | 100% | 0.726 |
| raster (test set) | splice | 0.999 | 99% | 100% | 0.709 |
| screenshot | AI inpainting | 0.991 | **96%** | 97% | 0.700 |
| screenshot | splice | 0.988 | **95%** | 95% | 0.649 |
| whatsapp | AI inpainting | 0.945 | **73%** | 80% | 0.558 |
| whatsapp | splice | 0.927 | **75%** | 83% | 0.524 |
| any phone copy | PDF edit, rebuild | 0.48–0.56 | 1–10% | 3–14% | – |

AIForge-Doc: F1 0.072 (ft4 0.076), authentic images flagged 3.9% (ft4 1.6%).

Fusion refitted with phone copies (out-of-fold, one threshold for all 600 genuine): 58% of all
1,996 forgeries at 1% false alarms (ft4: 54%), 67% at 5% (ft4: 63%).

**Reading.** On the rasterised test set ft6 detects as well as ft4 (localisation F1 0.71–0.73
against 0.79). On phone copies, with a threshold set for that kind of copy, it catches 95–96% of
image forgeries in screenshots and 73–75% in WhatsApp copies. WhatsApp compression still
costs a quarter of them. One threshold for every kind of copy wastes this: the per-kind
thresholds need the system to know what kind of copy it has, which the file itself shows (an
image-only page, its pixel width, PNG or JPEG).

## Threshold per kind of copy (20 Nov 2026)

`fuse_signals.py` with the copy kind read from each file (`fusion/copy_kind.py`), image model
ft6, test set plus phone copies (600 genuine, 1,996 forged), tag `test-phone-ft6-kinds`, code
b6fd100. One threshold for all genuine statements against one per kind (digital, scan,
screenshot, phone JPEG), each flagging 1% of that kind's genuine statements:

| Forgery | Copy | n | One threshold | Threshold per kind |
| --- | --- | ---: | ---: | ---: |
| image_inpaint | raster | 200 | 96% | 99% |
| image_inpaint | screenshot | 100 | 89% | 94% |
| image_inpaint | whatsapp | 100 | 79% | 73% |
| image_splice | raster | 200 | 100% | 100% |
| image_splice | screenshot | 100 | 97% | 99% |
| image_splice | whatsapp | 100 | 85% | 80% |
| pdf_edit | none | 200 | 100% | 100% |
| pdf_edit | raster | 200 | 23% | 42% |
| pdf_edit | screenshot | 100 | 17% | 35% |
| pdf_edit | whatsapp | 100 | 13% | 3% |
| rebuild | none | 198 | 58% | 58% |
| rebuild | raster | 198 | 4% | 6% |
| rebuild | screenshot | 100 | 9% | 13% |
| rebuild | whatsapp | 100 | 4% | 1% |
| **All forgeries** | | 1,996 | 58% | **60%** (65% at 5%) |

With one threshold, the 1% of genuine statements it flags are mostly WhatsApp copies, so
WhatsApp forgeries look better caught than they are; per kind, every kind of copy gets the
same 1% false-alarm rate. That costs WhatsApp copies a few points (73–80% of image forgeries)
and gains everywhere else, most on rasterised and screenshot PDF edits (42% and 35%, from 23%
and 17%), which OCR arithmetic catches once the threshold is not spent on WhatsApp noise.
Per-kind thresholds are the honest setting and the default from here.
