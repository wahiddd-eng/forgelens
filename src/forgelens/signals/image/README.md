# Image signal

ADCD-Net (ICCV 2025), run from the official code in `third_party/ADCD-Net` without editing
it.

- `adcdnet.py` points upstream's `cfg` module at our paths, checks a run's prerequisites
  (`preflight`), loads the checkpoint (a missing weight is an error, not a log line) and
  builds upstream's evaluation datasets.
- `scripts/eval_adcdnet.py` uses it to reproduce the Doc Protocol table.

- `pages.py` runs ADCD-Net on whole statement pages: render at a fixed DPI, cut into
  overlapping 512 px tiles prepared exactly as upstream prepares DocTamper images, average the
  tile probabilities into a page map. The OCR mask comes from character-sized blobs of ink,
  and ground-truth masks from the forgery labels' edited boxes.
- `scripts/eval_adcdnet_pages.py` measures it on the synthetic statement set: detection
  (ROC AUC, forgeries caught at 5% / 1% false alarms) and localisation (F1).

Still to come: fine-tuning on bank-statement pages.
