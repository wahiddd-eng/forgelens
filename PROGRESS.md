# ForgeLens Progress Log

**Project:** ForgeLens — Multi-Signal Detection of AI-Forged Bank Statements
**Team:** Syed Wahid Sajad (RA2311026011016), Dhruv Bhoye (RA2311026011059)
**Guide:** Dr. N. Gopinath, Department of Computational Intelligence (CINTEL), SRM Institute of Science and Technology

---

## Milestones

| Phase | Dates | Owner | Status |
| --- | --- | --- | --- |
| Phase 0 — Setup and 0th review | 4–15 Nov 2026 | Both | In progress |
| Phase 1 — Base model reproduction (ADCD-Net) | 16 Nov – 20 Dec 2026 | Dhruv | Not started |
| Phase 2 — Dataset generation | 16 Nov 2026 – 10 Jan 2027 | Wahid | Not started |
| Phase 3 — Signal modules | 1–31 Jan 2027 | Both | Not started |
| Phase 4 — Fusion and evaluation | 1–28 Feb 2027 | Both | Not started |
| Phase 5 — Dashboard | 15 Feb – 15 Mar 2027 | Dhruv | Not started |
| Phase 6 — Paper (submit by 31 Mar 2027) | 1–31 Mar 2027 | Wahid | Not started |
| Phase 7 — Report and final review | 1–30 Apr 2027 | Both | Not started |

Review dates are not yet announced. Add them here when SRM publishes the review calendar.

---

## Backlog

Agreed but not yet started. Move an item into a weekly entry when work begins.

| Item | Phase | Owner | Notes |
| --- | --- | --- | --- |
| Single-GPU ADCD-Net config (`gpus = '0'`, reduced `val_bs`) | Phase 1 | Dhruv | Keep upstream `cfg.py` untouched; override from our own config |
| ADCD-Net evaluation script saving CSV results to `experiments/results/` | Phase 1 | Dhruv | Doc Protocol: TestingSet, FCD, SCD + T-SROIE, Tampered-IC13, RTM, OSTF |
| Page-image wrapper in `src/forgelens/signals/image/` | Phase 1 | Dhruv | Runs ADCD-Net on any single page image; needed in Phase 3 |
| PyTorch 2.7+ with CUDA 12.8+ environment for the RTX 5060 Ti | Phase 1 | Dhruv | Upstream pins PyTorch 2.3.0+cu121, which does not support RTX 50-series GPUs |
| Evaluate with the released checkpoint, do not retrain | Phase 1 | Dhruv | Upstream training used 4× RTX 4090 for ~27 hours |

---

## Dataset access

Passwords are shared privately between team members and are **never** written in this repository.

| Dataset | Source | Requested | Status | Licence / terms |
| --- | --- | --- | --- | --- |
| DocTamper | [qcf-568/DocTamper](https://github.com/qcf-568/DocTamper) | 4 Nov 2026 (email from SRM account) | Granted 4 Nov 2026 | Non-commercial only; no redistribution; no integration with other datasets |
| TFR benchmark | [qcf-568/TextShield](https://github.com/qcf-568/TextShield) | 4 Nov 2026 (email) | Granted 4 Nov 2026 | Same terms as DocTamper |
| AIForge-Doc v1 | [Scam-AI/AIForge-Doc-v1](https://huggingface.co/datasets/Scam-AI/AIForge-Doc-v1) | 4 Nov 2026 (Hugging Face form) | Form submitted | CC BY-NC-SA 4.0 (non-commercial) |
| Omni-273k, MIML, OSTF, DanceText | qcf-568 repositories | Offered by the authors | Passwords received; not yet needed | Same terms as DocTamper |

**Rules that follow from these licences:**

- Files from these datasets stay in `data/external/` (git-ignored) and are never uploaded or shared.
- They may be used for research training and evaluation in this project and the paper, **not** in the startup product.
- The public ForgeLens benchmark must not contain any images from these datasets.

**Author's notes for DocTamper (from Chenfan Qu, 4 Nov 2026):**

- Read all the good first issues in the DocTamper repo, both open and closed.
- The unzipped data is in `.mdb` (LMDB) files. Visualise samples with `python vizlmdb.py --input DocTamperV1-FCD --i 0` ([vizlmdb.py](https://github.com/qcf-568/DocTamper/blob/main/vizlmdb.py)).
- Reuse the data loader in lines 43–107 of [models/eval_dtd.py](https://github.com/qcf-568/DocTamper/blob/main/models/eval_dtd.py).
- MIML is for training only; mix it 1:1 with tamperCOCO and use cross-entropy loss with `ignore_index=100` (mask thresholds 8 and 160).

---

## How to update

- Add a new weekly entry at the **top** of the weekly log every Monday.
- Both members fill in their own lines.
- Record numbers under **Results** so every figure in the paper can be traced back to this log.
- Update the Milestones status when a phase starts or finishes.

---

## Weekly log

## Week 1 · 4 Nov – 10 Nov 2026

**Phase:** Phase 0 — Setup and 0th review

**Done:**

- Project topic changed from bank statement processing automation to AI-forged bank statement detection (ForgeLens).
- Base paper selected: ADCD-Net (Wong et al., ICCV 2025).
- 0th review deck prepared: 13 slides, including a 15-paper literature survey (2023–2026) and a Base Paper slide.
- Project roadmap drafted (phases, team split, paper and startup tracks, risks).
- GitHub repository set up: folder structure, README, CI workflow, issue and PR templates.
- ADCD-Net official repository verified and added as a submodule at `third_party/ADCD-Net`, pinned to commit `169d04d2d802c1d1e4d934c04c308c3e3f5c4e7a` (MIT licence).
- Dataset access: DocTamper and TFR granted; AIForge-Doc form submitted.

**Results / numbers:** None yet.

**Blockers:** None. The 0th review date is still to be confirmed.

**Next week:**

- Wahid: present the 0th review; start the synthetic statement generator (first bank layout with correct running balances); draft the output-format (JSON) spec.
- Dhruv: set up PyTorch with CUDA 12.8+ on the RTX 5060 Ti; download DocTamper and TFR to `data/external/`; read the DocTamper good first issues; run ADCD-Net on the DocTamper test sets.

**Guide feedback:** To be added after the 0th review.

---

## Entry template

Copy this block to the top of the weekly log each week.

```markdown
## Week N · <start date> – <end date>

**Phase:**

**Done:**
- Wahid:
- Dhruv:

**Results / numbers:**

**Blockers:**

**Next week:**
- Wahid:
- Dhruv:

**Guide feedback:**
```
