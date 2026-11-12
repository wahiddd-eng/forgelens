# ADCD-Net Doc Protocol reproduction

Per-image F1 of the tampered class, as in ADCD-Net (ICCV 2025) Table 1. CI: 95% interval of the mean.

| Set | Images | Failed | F1 | 95% CI | Published | Δ | Pixel F1 | IoU |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| FCD | 2000 | 0 | 0.803 | 0.791–0.815 | 0.803 | +0.000 | 0.814 | 0.738 |
| SCD | 18000 | 0 | 0.718 | 0.714–0.722 | 0.718 | -0.000 | 0.776 | 0.629 |
| Test | 30000 | 0 | 0.791 | 0.787–0.794 | 0.791 | -0.000 | 0.908 | 0.737 |
| Avg. in-domain | | | 0.771 | | 0.771 | -0.000 | | |

Code 0ba4786d2d701d922396a7feccd34f527ec3be01, ADCD-Net 169d04d2d802c1d1e4d934c04c308c3e3f5c4e7a, PyTorch 2.3.0+cu121 on NVIDIA A100-SXM4-40GB; checkpoint sha256 8e98674c0415.
