# ForgeLens

ForgeLens is a research system for detecting forged and AI-edited Indian bank statements. It combines image forensics, PDF structure and metadata analysis, running-balance financial consistency checks, and bank template matching into an explainable authenticity score using an XGBoost fusion classifier, exposed through a FastAPI and React dashboard. The project also generates a synthetic benchmark of genuine and forged statements.

## Team and guide

- **Syed Wahid Sajad** (RA2311026011016)
- **Dhruv Bhoye** (RA2311026011059)
- **Guide:** Dr. N. Gopinath
- **Department:** CINTEL, SRM Institute of Science and Technology

## Four signals

1. **Image forensics:** fine-tuning and inference with the ADCD-Net base model.
2. **PDF structure and metadata:** inspection of metadata, fonts, object streams, and incremental saves.
3. **Financial consistency:** running balance, opening/closing balance, and transaction-total checks.
4. **Bank template matching:** layout, font, and field-position comparison.

The signals are combined by an XGBoost fusion classifier to produce an explainable authenticity score.

## Base paper

K. Wong, J. Zhou, H. Wu, Y.-W. Si and J. Zhou, “ADCD-Net: Robust Document Image Forgery Localization via Adaptive DCT Feature and Hierarchical Content Disentanglement,” IEEE/CVF ICCV 2025, pp. 19280–19289.

## Folder structure

See the README in each top-level directory for its purpose. Source code uses a `src/` layout; generated data, experiment artifacts, application code, scripts, tests, documentation, and third-party integrations are kept separate.

## Setup

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Data and privacy

Real bank statements and personal data must never be committed. Public dataset releases must use invented bank names and no real logos. Every real statement used for testing must be collected with consent.

## Roadmap

- **Phase 0 — Setup and 0th review:** 4–15 Nov 2026
- **Phase 1 — Base model reproduction:** 16 Nov – 20 Dec 2026
- **Phase 2 — Dataset generation:** 16 Nov 2026 – 10 Jan 2027
- **Phase 3 — Signal modules:** 1–31 Jan 2027
- **Phase 4 — Fusion and evaluation:** 1–28 Feb 2027
- **Phase 5 — Dashboard:** 15 Feb – 15 Mar 2027
- **Phase 6 — Paper:** 1–31 Mar 2027 (submit by 31 Mar 2027)
