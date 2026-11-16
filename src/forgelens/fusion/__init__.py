"""Fusion of the four signals into one score per statement (see ``fuse.py``)."""

from .fuse import Statement, evaluate, join, load_image, load_signals, out_of_fold

__all__ = ["Statement", "evaluate", "join", "load_image", "load_signals", "out_of_fold"]
