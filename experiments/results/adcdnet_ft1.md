# ADCD-Net on image-level statement forgeries, and the first fine-tuning run (ft1)

14 Nov 2026, SRMIST DGX A100, code f7485d2 (training: `scripts/queue_image_forgeries.sh`).

## Released checkpoint on spliced and AI-inpainted statements

The v4 synthetic statements with values changed in the image: retyped on a patch re-saved
at its own JPEG quality (`image_splice`), or that patch retouched by SDXL inpainting at
strength 0.45–0.75 (`image_inpaint`); every page then rasterised exactly as the genuine
statements are (150 DPI, JPEG quality 85). Compared with the 300 rasterised genuine
statements (`scripts/eval_adcdnet_pages.py --tag image-v4`, 150 DPI):

| Forgery | Genuine | Forged | AUC (peak) | Caught @5% | Caught @1% | F1 | 95% CI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| image_inpaint | 300 | 286 | 0.487 | 4% | 1% | 0.001 | 0.001–0.001 |
| image_splice | 300 | 300 | 0.529 | 4% | 1% | 0.006 | 0.005–0.007 |

The released model is at chance even on forgeries that do change pixels. (14 of the 300
inpainting jobs produced no forgery and are absent.)

## Fine-tuning run ft1

Released weights fine-tuned for 10,000 steps (batch 8 x 2 accumulation, 256 px crops, lr
5e-5 cosine, 30% of crops from DocTamper's training set) on the rasterised genuine
statements and both image-level forgery types, one A100, 4 h 40 min. Validation every
1,000 steps on 300 pages of held-out source statements (20% of statements, split by source,
so no genuine statement or its forgeries is on both sides): `val_f1` mean per-page F1 on
edited pages, `val_auc` edited against clean pages by peak score, `val_clean_area` share of
clean pages predicted tampered; `fcd_f1` the first 300 DocTamper FCD images (Doc Protocol).

| Step | Val F1 | Val AUC | Clean area flagged | FCD F1 |
| ---: | ---: | ---: | ---: | ---: |
| 0 (released) | 0.007 | 0.468 | 5.03% | 0.798 |
| 1,000 | 0.783 | 0.993 | 0.07% | 0.733 |
| 2,000 | 0.783 | 0.989 | 0.08% | 0.756 |
| 3,000 | 0.778 | 0.995 | 0.05% | 0.768 |
| 4,000 | 0.787 | 0.995 | 0.05% | 0.784 |
| 5,000 | 0.839 | 0.997 | 0.05% | 0.757 |
| 6,000 | 0.856 | 0.995 | 0.03% | 0.772 |
| 7,000 | 0.880 | 0.997 | 0.02% | 0.770 |
| 8,000 | 0.840 | 0.998 | 0.04% | 0.777 |
| 9,000 | 0.869 | 0.999 | 0.02% | 0.779 |
| 10,000 | 0.879 | 0.999 | 0.02% | 0.779 |

## Reading

Fine-tuning turns a model that cannot see these forgeries (AUC 0.47) into one that
separates them almost perfectly on held-out statements (AUC 0.999, F1 0.88), while
flagging 100 times less of a genuine page and keeping most of its DocTamper skill (FCD F1
0.78 against 0.80).

These are validation numbers and optimistic: the held-out statements come from the same
generator, the same 10 bank layouts, the same fonts and the same two forgery methods as the
training data. What they do not yet show: whether it still works on new statements
(`scripts/make_test_set.sh`), on banks it has not seen (`--exclude-banks`), on forgeries
it was not trained on (PDF edits, AIForge-Doc), and on real statements. Those are the next
runs.
