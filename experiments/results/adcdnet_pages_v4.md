# ADCD-Net on rendered bank-statement pages (v4)

Released ADCD-Net checkpoint on the v4 synthetic statements (`scripts/make_synthetic_set.sh`
on the SRMIST DGX, 14 Nov 2026): 300 genuine statements, 300 PDF edits, 299 rebuilds, and
their rasterised versions (no reprinted versions: no Ghostscript on the DGX). Pages are
rendered at a fixed resolution, cut into 512 px tiles, and the tiles' probabilities averaged
(`scripts/eval_adcdnet_pages.py`). Detection compares forged statements with genuine ones of
the same laundering setting: ROC AUC, and the share of forgeries caught when 5% / 1% of
genuine statements may be flagged. Peak: mean of the 500 most suspicious pixels on the worst
page. Area: share of a page predicted tampered. F1: predicted tampered pixels against the
edited regions, per statement (95% CI).

## 150 DPI

| Laundering | Forgery | Genuine | Forged | AUC (peak) | Caught @5% | Caught @1% | AUC (area) | F1 | 95% CI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| none | pdf_edit | 300 | 300 | 0.501 | 5% | 1% | 0.503 | 0.022 | 0.017–0.027 |
| none | rebuild | 300 | 299 | 0.490 | 4% | 1% | 0.500 | 0.081 | 0.072–0.089 |
| raster | pdf_edit | 300 | 300 | 0.503 | 7% | 2% | 0.501 | 0.034 | 0.029–0.039 |
| raster | rebuild | 300 | 299 | 0.504 | 7% | 4% | 0.493 | 0.130 | 0.126–0.135 |

## 100 DPI

| Laundering | Forgery | Genuine | Forged | AUC (peak) | Caught @5% | Caught @1% | AUC (area) | F1 | 95% CI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| none | pdf_edit | 300 | 300 | 0.495 | 0% | 0% | 0.498 | 0.029 | 0.022–0.035 |
| none | rebuild | 300 | 299 | 0.528 | 4% | 4% | 0.520 | 0.082 | 0.070–0.093 |
| raster | pdf_edit | 300 | 300 | 0.498 | 5% | 1% | 0.497 | 0.016 | 0.012–0.019 |
| raster | rebuild | 300 | 299 | 0.523 | 4% | 1% | 0.513 | 0.044 | 0.039–0.049 |

## 200 DPI

| Laundering | Forgery | Genuine | Forged | AUC (peak) | Caught @5% | Caught @1% | AUC (area) | F1 | 95% CI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| none | pdf_edit | 300 | 300 | 0.503 | 6% | 1% | 0.499 | 0.029 | 0.024–0.034 |
| none | rebuild | 300 | 299 | 0.537 | 12% | 7% | 0.497 | 0.095 | 0.088–0.103 |
| raster | pdf_edit | 300 | 300 | 0.500 | 5% | 1% | 0.500 | 0.046 | 0.039–0.052 |
| raster | rebuild | 300 | 299 | 0.471 | 6% | 2% | 0.480 | 0.165 | 0.160–0.171 |

Code a5eec02a0f1bbca3a3621a5bae06e1657002d8df, ADCD-Net 169d04d2d802c1d1e4d934c04c308c3e3f5c4e7a,
PyTorch 2.3.0+cu121 on NVIDIA A100-SXM4-40GB; checkpoint sha256 8e98674c0415.

## Reading

Every AUC is between 0.47 and 0.54, and the catch rates are at or barely above the
false-alarm rate they were set to (the best, 12% at 5% for unlaundered rebuilds at 200 DPI,
is not repeated at other resolutions): the released checkpoint cannot tell our forged
statements from genuine ones at any resolution, before or after rasterising. The F1 values are not evidence of localisation: the
model marks a similar amount of genuine statements, and rebuilds score higher only because
they change much larger regions, so random marks overlap them more.

This is the expected outcome for these forgeries. ADCD-Net looks for local traces of
tampering in a raster image (compression and resampling mismatches between the edited region
and the rest). A PDF edit or a rebuild is rendered by the same engine as the rest of the page,
and rasterising treats the whole page alike, so the page has no such mismatch. Clean digital
forgeries need the document-level signals (PDF structure, fonts, arithmetic, layout), and
pixel forensics need training on forgeries that do leave pixel traces (AI inpainting, pasted
crops, print-and-scan).

Before relying on this, `scripts/check_adcdnet_pages.py` checks that the tiling and the
ink-blob OCR masks reproduce ADCD-Net's DocTamper scores; its result is recorded below once run.
