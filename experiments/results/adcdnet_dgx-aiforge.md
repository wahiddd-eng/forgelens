# ADCD-Net evaluation

Per-image F1 of the tampered class, as in ADCD-Net (ICCV 2025) Table 1. CI: 95% interval of the mean. Flagged: share of images with over 1% of pixels predicted tampered (false alarms on authentic sets).

| Set | Images | Failed | F1 | 95% CI | Published | Δ | Flagged | Pixel F1 | IoU |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| AIForge | 812 | 0 | 0.176 | 0.154–0.197 | – | – | 0.121 | 0.274 | 0.142 |
| AIForge-authentic | 812 | 0 | – | – | – | – | 0.027 | – | – |

Code 12e53893aa6566bbe954b754dc4bc66b98903329, ADCD-Net 169d04d2d802c1d1e4d934c04c308c3e3f5c4e7a, PyTorch 2.3.0+cu121 on NVIDIA A100-SXM4-40GB; checkpoint sha256 8e98674c0415.

AIForge-Doc v1 test split (812 diffusion-inpainted receipts and forms, Gemini 2.5 Flash Image and Ideogram v2 Edit) and its 812 untouched originals, laid out by `scripts/prepare_aiforge.py`, OCR masks from `scripts/make_ocr_masks.sh`, 13 Nov 2026. No published ADCD-Net score exists for this set. The 1% "flagged" threshold is a fixed choice, not tuned.
