# Fusion

Combines the four signals (financial consistency, PDF structure, template matching, image
forensics) into one score per statement: `fuse.py`, run by `scripts/fuse_signals.py`.

A signal that abstains (cannot read the file) or was not run counts as missing, never as
genuine. Two models are fitted on the signal scores and present/absent flags: logistic
regression and histogram gradient boosting. All fused scores are out-of-fold, with folds
grouped by source statement, and detection is measured with one threshold for every kind
of input, set on all genuine statements together.
