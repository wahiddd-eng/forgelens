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
