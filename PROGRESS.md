# ForgeLens Progress Log

**Project:** ForgeLens — Multi-Signal Detection of AI-Forged Bank Statements
**Team:** Syed Wahid Sajad (RA2311026011016), Dhruv Bhoye (RA2311026011059)
**Guide:** Dr. N. Gopinath, Department of Computational Intelligence (CINTEL), SRM Institute of Science and Technology

---

## Milestones

| Phase | Dates | Owner | Status |
| --- | --- | --- | --- |
| Phase 0 — Setup and 0th review | 4–15 Nov 2026 | Both | In progress |
| Phase 1 — Base model reproduction (ADCD-Net) | 16 Nov – 20 Dec 2026 | Dhruv | In progress (started early, 12 Nov): all seven Doc Protocol results reproduced (13 Nov) |
| Phase 2 — Dataset generation | 16 Nov 2026 – 10 Jan 2027 | Wahid | In progress (started early): generator with 10 bank layouts, PDF-edit and rebuild forgeries |
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
| Page-image wrapper in `src/forgelens/signals/image/` | Phase 1 | Dhruv | Runs ADCD-Net on any single page image; needed in Phase 3 |
| ADCD-Net on rendered synthetic statement pages | Phase 1 | Both | Especially the reprinted and rasterised forgeries, where all PDF signals abstain |
| Fine-tuning on bank-statement pages | Phase 1 | Dhruv | Ask the DocTamper authors first whether training alongside our data counts as "integration with other datasets"; use their mask thresholds 8 and 160 |
| Consent form and collection log for real statements | Phase 2 | Wahid | Target 100 statements (minimum 50) from at least 8 banks; kept only on local encrypted storage |
| PyTorch 2.7+ with CUDA 12.8+ environment for the RTX 5060 Ti | Phase 1 | Dhruv | Optional now that the DGX is set up; for debugging at home |

---

## Dataset access

Passwords are shared privately between team members and are **never** written in this repository.

| Dataset | Source | Requested | Status | Licence / terms |
| --- | --- | --- | --- | --- |
| DocTamper | [qcf-568/DocTamper](https://github.com/qcf-568/DocTamper) | 4 Nov 2026 (email from SRM account) | Granted 4 Nov 2026 | Non-commercial only; no redistribution; no integration with other datasets |
| TFR benchmark | [qcf-568/TextShield](https://github.com/qcf-568/TextShield) | 4 Nov 2026 (email) | Granted 4 Nov 2026 | Same terms as DocTamper |
| AIForge-Doc v1 | [Scam-AI/AIForge-Doc-v1](https://huggingface.co/datasets/Scam-AI/AIForge-Doc-v1) | 4 Nov 2026 (Hugging Face form) | Granted 5 Nov 2026; downloaded to the DGX 12 Nov (9.4 GB) | CC BY-NC-SA 4.0 (non-commercial) |
| Doc Protocol cross-domain sets | [Jason37437/Doc-Protocol-Data](https://huggingface.co/datasets/Jason37437/Doc-Protocol-Data) | Public | Downloaded to the DGX 12 Nov | Terms of each source dataset |
| Omni-273k, MIML, OSTF, DanceText | qcf-568 repositories | Offered by the authors | Passwords received; not yet needed | Same terms as DocTamper |

DocTamper was downloaded to the DGX on 12 Nov from the Kaggle copy (`dinmkeljiame/doctamper`, all four LMDB splits, 23 GB). The authors' terms above still apply to it, whatever licence the Kaggle page shows.

**Rules that follow from these licences:**

- Files from these datasets stay in `data/external/` or `~/forgelens-data/` on the DGX (never in git) and are never uploaded or shared.
- They may be used for research training and evaluation in this project and the paper, **not** in the startup product.
- The public ForgeLens benchmark must not contain any images from these datasets.

**Author's notes for DocTamper (from Chenfan Qu, 4 Nov 2026):**

- Read all the good first issues in the DocTamper repo, both open and closed.
- The unzipped data is in `.mdb` (LMDB) files. Visualise samples with `python vizlmdb.py --input DocTamperV1-FCD --i 0` ([vizlmdb.py](https://github.com/qcf-568/DocTamper/blob/main/vizlmdb.py)).
- Reuse the data loader in lines 43–107 of [models/eval_dtd.py](https://github.com/qcf-568/DocTamper/blob/main/models/eval_dtd.py).
- MIML is for training only; mix it 1:1 with tamperCOCO and use cross-entropy loss with `ignore_index=100` (mask thresholds 8 and 160).

---

## Compute

| Resource | Details | Status |
| --- | --- | --- |
| SRMIST DGX A100 (Centre for AI) | Account `srmist32` at 172.16.0.32, campus Wi-Fi from one registered laptop. Up to 2 A100 40 GB GPUs, whichever are free; 500 GB; about 400 GPU-hours, 16 Nov 2026 – 15 Feb 2027 | Approved 11 Nov 2026; environment set up 12 Nov (`docs/dgx.md`) |
| Backups | Results, logs and checkpoints sent every 30 min to a private Hugging Face repository (`scripts/backup.py`) | Working since 12 Nov |
| Home PC | RTX 5060 Ti 16 GB, in Kashmir | Optional; needs PyTorch 2.7+ |

Renew the DGX allocation at least 4 days before each 20-day period ends; a new form is needed after 3 months. The DGX keeps no backups and reboots weekly.

---

## How to update

- Add a new weekly entry at the **top** of the weekly log every Monday.
- Both members fill in their own lines.
- Record numbers under **Results** so every figure in the paper can be traced back to this log.
- Update the Milestones status when a phase starts or finishes.

---

## Weekly log

## Week 2 · 11 Nov – 17 Nov 2026

**Phase:** Phase 0 — Setup and 0th review; Phase 1 started early

**Done:**

- Engineering review of the repository (`docs/reviews/2026-11-04-engineering-review.md`) and all its fixes; rule-based signal results re-run as v4 (`experiments/results/README.md`).
- DGX A100 GPU request form submitted with Dr. Gopinath's details; approved 11 Nov 2026 (up to 2 GPUs, whichever are free).
- DGX environment built without sudo (`scripts/setup_dgx.sh`): Python 3.10.14, PyTorch 2.3.0 + CUDA 12.1, jpeg2dct with a bundled libjpeg-turbo.
- Phase 1 data downloaded to the DGX (`scripts/download_data.sh`): DocTamper (4 splits), ADCD-Net checkpoint, DocRes checkpoint and OCR masks, the four cross-domain sets, AIForge-Doc v1.
- ADCD-Net Doc Protocol evaluation script (`scripts/eval_adcdnet.py`) with pre-flight checks, resume, per-image CSVs and provenance.
- Automatic backups to a private Hugging Face repository (`scripts/backup.py`, `scripts/with_backup.sh`) and GPU picking for the shared DGX (`scripts/free_gpus.sh`).
- ADCD-Net in-domain results reproduced on the DGX (below).
- OCR masks for the four cross-domain sets made on the DGX CPUs overnight (`scripts/make_ocr_masks.sh`, 8,638 masks, no failures).

**Results / numbers:**

ADCD-Net, released checkpoint, Doc Protocol, 12 Nov 2026, one A100 (`experiments/results/adcdnet_dgx.md`). Per-image F1, 95% CI of the mean:

| Set | Images | F1 | 95% CI | Published |
| --- | ---: | ---: | --- | ---: |
| FCD | 2,000 | 0.803 | 0.791–0.815 | 0.803 |
| SCD | 18,000 | 0.718 | 0.714–0.722 | 0.718 |
| TestingSet | 30,000 | 0.791 | 0.787–0.794 | 0.791 |
| Mean (in-domain) | | 0.771 | | 0.771 |

No image failed. Code `0ba4786`, ADCD-Net `169d04d`, checkpoint sha256 `8e98674c0415…`.

Cross-domain sets, 13 Nov 2026, same checkpoint, OCR masks made with `scripts/make_ocr_masks.sh` (`experiments/results/adcdnet_dgx-cross.md`):

| Set | Images | F1 | 95% CI | Published |
| --- | ---: | ---: | --- | ---: |
| T-SROIE | 1,579 | 0.623 | 0.606–0.640 | 0.623 |
| OSTF | 3,046 | 0.441 | 0.428–0.453 | 0.441 |
| Tampered-IC13 | 589 | 0.579 | 0.551–0.607 | 0.579 |
| RealTextManipulation | 3,444 | 0.158 | 0.149–0.168 | 0.159 |
| Mean (cross-domain) | | 0.450 | | 0.450 |

All seven Doc Protocol scores now match the paper (overall mean 0.588). No image failed. Code `7a75d98`.

ADCD-Net on AI-made edits, 13 Nov 2026, same checkpoint, AIForge-Doc v1 test split (`experiments/results/adcdnet_dgx-aiforge.md`). No published score exists:

| Set | Images | F1 | 95% CI | Flagged (>1% of pixels) |
| --- | ---: | ---: | --- | ---: |
| AIForge-Doc, AI-inpainted | 812 | 0.176 | 0.154–0.197 | 12.1% |
| AIForge-Doc, authentic originals | 812 | – | – | 2.7% (false alarms) |

The base model mostly misses diffusion inpainting: F1 0.176 against 0.771 on DocTamper, close to its weakest Doc Protocol set (RTM, 0.158).

**Blockers:** None. Asked the DocTamper authors on 13 Nov (reply to the original thread) whether fine-tuning on DocTamper together with our own synthetic data counts as "integration with other datasets", and whether the resulting weights may be published; awaiting their answer before any joint training.

**Next week:**

- Wahid: draft the consent form and collection log and start collecting real statements; send Dr. Gopinath an update.
- Dhruv: start the page-image wrapper; add TFR to the download script and evaluate it.

**Guide feedback:** To be added.

---

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
