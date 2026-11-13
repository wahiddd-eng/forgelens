# Scripts

Command-line entry points. Each one's `--help` and module docstring give the details.

| Script | What it does |
| --- | --- |
| `generate_statements.py` | Synthetic genuine statements with labels and field layouts |
| `forge_pdf_edits.py`, `forge_rebuild.py` | Forged statements: object-level PDF edits and full rebuilds |
| `launder_pdfs.py` | Reprint or rasterise statements to hide editing traces |
| `fit_templates.py` | Fit per-bank template profiles |
| `eval_signals.py`, `eval_financial.py`, `compare_results.py` | Evaluate the rule-based signals |
| `eval_adcdnet.py` | Reproduce ADCD-Net's Doc Protocol results with the released checkpoint |
| `setup_dgx.sh` | Build the ADCD-Net environment on the DGX (or any Linux GPU machine) without sudo |
| `free_gpus.sh` | Pick up to 2 free GPUs on the shared DGX for `CUDA_VISIBLE_DEVICES` |
| `backup.py`, `with_backup.sh` | Periodic incremental backups of results, logs and checkpoints off the DGX |
| `download_data.sh` | Download the Phase 1 datasets and checkpoints into `~/forgelens-data` |
| `make_ocr_masks.sh` | OCR masks and path lists for the four cross-domain test sets (PaddleOCR, own environment) |
| `prepare_aiforge.py` | Lay out the AIForge-Doc test split (forged and authentic) for ADCD-Net |
| `make_synthetic_set.sh` | Build the v4 synthetic statement set in one folder, after checking PDFs can be rendered |
| `eval_adcdnet_pages.py` | ADCD-Net on rendered statement pages: detection AUC and localisation F1 |
