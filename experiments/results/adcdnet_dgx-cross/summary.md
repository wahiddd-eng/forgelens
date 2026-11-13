# ADCD-Net Doc Protocol reproduction

Per-image F1 of the tampered class, as in ADCD-Net (ICCV 2025) Table 1. CI: 95% interval of the mean.

| Set | Images | Failed | F1 | 95% CI | Published | Δ | Pixel F1 | IoU |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| T-SROIE | 1579 | 0 | 0.623 | 0.606–0.640 | 0.623 | +0.000 | 0.638 | 0.532 |
| OSTF | 3046 | 0 | 0.441 | 0.428–0.453 | 0.441 | -0.000 | 0.474 | 0.355 |
| TPIC-13 | 589 | 0 | 0.579 | 0.551–0.607 | 0.579 | +0.000 | 0.590 | 0.487 |
| RTM | 3444 | 0 | 0.158 | 0.149–0.168 | 0.159 | -0.001 | 0.152 | 0.120 |
| Avg. cross-domain | | | 0.450 | | 0.450 | +0.000 | | |

Code 7a75d98b8e0f6c322c99d73efdbad1152eb5104e, ADCD-Net 169d04d2d802c1d1e4d934c04c308c3e3f5c4e7a, PyTorch 2.3.0+cu121 on NVIDIA A100-SXM4-40GB; checkpoint sha256 8e98674c0415.

OCR masks for these sets were made with `scripts/make_ocr_masks.sh` (PaddleOCR 3.3 / PP-OCRv5_server_det, CPU without oneDNN), as upstream's `seg_char.py` does.
