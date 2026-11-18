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
