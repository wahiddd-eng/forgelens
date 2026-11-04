"""Forgery generators for the ForgeLens dataset."""

from .pdf_edit import FONT_STRATEGIES, OPERATIONS, SAVE_MODES, forge, write_masks

__all__ = ["FONT_STRATEGIES", "OPERATIONS", "SAVE_MODES", "forge", "write_masks"]
