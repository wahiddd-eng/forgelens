# Notebooks

Exploratory analyses and reproducible research notebooks.

## Self-test kit for real statements

`self_test.ipynb`: for friends and family who help measure ForgeLens's false alarms on real
bank statements without sharing them. Open it in Google Colab (File → Upload notebook, or
from GitHub), run the cells in order: it runs ForgeLens on their own statement in their own
Colab and downloads a small JSON file with scores only (no name, account number, date,
amount, transaction or file name). They send that file to the team.

Collect the files in a folder (outside the repository) and summarise them:

```bash
python scripts/fuse_signals.py --signals experiments/results/signals_test_per_file.csv \
    --ocr experiments/results/ocr_financial_test.csv --exclude template image image_released \
    --tag test-selftest
python scripts/collect_self_tests.py ~/selftest_results/*.json \
    --fusion experiments/results/fusion_test-selftest/model.pkl \
    --summary experiments/results/real_selftest_<date>.md
```

The same check from a terminal: `python scripts/self_test.py statement.pdf --bank "HDFC Bank"`.
