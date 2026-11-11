# Image signal

ADCD-Net (ICCV 2025), run from the official code in `third_party/ADCD-Net` without editing
it.

- `adcdnet.py` points upstream's `cfg` module at our paths, checks a run's prerequisites
  (`preflight`), loads the checkpoint (a missing weight is an error, not a log line) and
  builds upstream's evaluation datasets.
- `scripts/eval_adcdnet.py` uses it to reproduce the Doc Protocol table.

Still to come: the page-image wrapper that runs ADCD-Net on one statement page, and
fine-tuning on bank-statement pages.
