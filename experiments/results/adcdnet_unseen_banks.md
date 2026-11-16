# Unseen bank layouts: ft2 (trained without two banks) against ft1 (trained on all ten)

15 Nov 2026, SRMIST DGX A100, code b31b90a. ft2 = `train_ft2/Step5000_Score0.8778.pth`
(sha256 f9f2b2f6096b), trained exactly as ft1 but with konark_urban and malabar_coastal left
out of training and validation (`--exclude-banks`). Both models are evaluated on those two
banks only, on the held-out test set (`--banks konark_urban malabar_coastal`: 40 genuine and
40 forged statements of each type, rasterised):

| Forgery | Model | Banks seen in training? | AUC | Caught @5% | Caught @1% | F1 (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | --- |
| AI inpainting | ft1 | yes | 1.000 | 100% | 100% | 0.599 (0.514–0.684) |
| AI inpainting | ft2 | **no** | 0.872 | 68% | 60% | 0.493 (0.405–0.580) |
| Splice | ft1 | yes | 0.999 | 100% | 98% | 0.612 (0.526–0.698) |
| Splice | ft2 | **no** | 0.956 | 88% | 85% | 0.512 (0.423–0.601) |

## Reading

On bank layouts it has never seen, the fine-tuned model still detects most forgeries (AUC
0.87 and 0.96, far above the released model's chance level) but loses a clear share: at 1%
false alarms it catches 60% of AI-inpainted forgeries instead of 100%, and 85% of splices
instead of 98%. By the project's criterion (unseen-bank recall more than 10 points below
seen banks) H4 fails for this model.

The model partly learns what each bank's pages normally look like, so a new layout looks
unusual everywhere and the forgery stands out less. Ten layouts are too few to learn
layout-independent traces. Remedies: more and more varied bank layouts in the generator,
and the varied forgeries of ft3. The samples are small (40 per group, 2 banks), so the
intervals are wide; a leave-one-bank-out run over all ten banks would give a firmer number.
