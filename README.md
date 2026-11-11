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

See the README in each top-level directory for its purpose. Source code uses a `src/` layout:

| Package | What it does |
| --- | --- |
| `forgelens.generator` | Fictional banks and synthetic genuine statements (PDF + ground truth) |
| `forgelens.forgery` | Labelled forgeries: PDF edits, template rebuilds, laundering (reprint, raster) |
| `forgelens.reader` | Reads what a PDF prints (cells, fonts, table, summary); shared by everything else |
| `forgelens.signals` | Financial-consistency, PDF-structure and template-matching signals |
| `forgelens.evaluation` | Metrics with 95% confidence intervals, localisation precision and recall |
| `forgelens.utils` | Stable seeds and run provenance (code version and environment of each result) |

## Setup

The core package (generator, forgeries, rule-based signals) needs Python 3.10+, the Pango
library for WeasyPrint, Ghostscript for laundering, and the free fonts the fictional banks
use. With other fonts installed the statements still render, but with substitutes, so they
differ from other machines (the generator warns, and records the fonts it used).

**macOS (Apple silicon or Intel):**

```bash
brew install pango ghostscript
brew install --cask font-liberation font-carlito font-dejavu
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
git submodule update --init --recursive
```

**Ubuntu:**

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 ghostscript fonts-liberation \
    fonts-crosextra-carlito fonts-dejavu-core fonts-dejavu-extra
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The image-forensics and fusion work (Phases 1, 3, 4) also needs `pip install -e ".[ml]"`,
with PyTorch installed first from pytorch.org in the CUDA build that matches the GPU
(CUDA 12.8+ for the RTX 5060 Ti). `requirements.txt` installs everything.

## Reproduce the results

Each step writes labels next to its PDFs; every summary records the git commit, library
versions and arguments that produced it.

```bash
D=data/synthetic/v4
python scripts/generate_statements.py --bank all --count 30 --seed 2000 --out $D/genuine
python scripts/generate_statements.py --bank all --count 12 --seed 9000 --out $D/train
python scripts/forge_pdf_edits.py --genuine $D/genuine --out $D/forged/pdf_edit --masks
python scripts/forge_rebuild.py --genuine $D/genuine --out $D/forged/rebuild --masks
for m in reprint raster; do
  python scripts/launder_pdfs.py --input $D/genuine --out $D/genuine_$m --method $m
  python scripts/launder_pdfs.py --input $D/forged --out $D/forged_$m --method $m --masks
done
python scripts/fit_templates.py --genuine $D/train --out experiments/templates_v4.json
python scripts/eval_signals.py --genuine $D/genuine --forged $D/forged \
    --templates experiments/templates_v4.json --tag v4_10banks
```

Run the evaluation again on `genuine_reprint`/`forged_reprint` and `genuine_raster`/
`forged_raster`, then combine with `scripts/compare_results.py`. Fit and evaluate the
template profiles on the same machine: they depend on the installed fonts.
`experiments/results/README.md` lists every result set and which ones are superseded.

### ADCD-Net base model (Phase 1)

`scripts/eval_adcdnet.py` runs the official ADCD-Net code (`third_party/ADCD-Net`,
unedited) with the released checkpoint on the seven Doc Protocol test sets and compares
the per-image F1 with the published table. Its packages are in `requirements-adcdnet.txt`
(install PyTorch first). Copy `configs/adcdnet_eval.example.yaml` to
`configs/adcdnet_eval.yaml`, set the paths, then:

```bash
git submodule update --init
python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag dgx --check
python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag smoke --limit 20
python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag dgx --resume
```

`--check` verifies packages, checkpoints, the data layout, OCR masks and GPU support in
seconds. Results go to `experiments/results/adcdnet_<tag>/`: a CSV per test set (one row
per image), and `summary.md`/`.json` with the published scores beside ours and the code,
package, GPU and checkpoint versions. `--resume` skips the sets already finished, so a run
interrupted by a reboot loses at most one set.

## Tests

```bash
ruff check .
pytest -ra
```

The suite renders and forges real PDFs, including an end-to-end run of the scripts on a tiny
dataset (`tests/test_pipeline_smoke.py`), and takes about two minutes. Tests that need
Ghostscript are skipped when it is not installed.

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
