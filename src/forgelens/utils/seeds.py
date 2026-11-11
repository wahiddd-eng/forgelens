"""Seeds that depend only on what they are for, not on the order things are processed in."""

from __future__ import annotations

import hashlib


def stable_seed(*parts: object) -> int:
    """Return a seed in [0, 2**31) derived from ``parts``.

    Scripts used to draw each item's seed from one random sequence, so adding or removing a
    single statement changed every forgery after it. A seed built from the run seed and the
    item's identity (for example ``stable_seed(0, "sahyadri_000012", 1)``) stays the same
    whatever else is in the folder.
    """
    text = ":".join(str(p) for p in parts)
    return int(hashlib.sha256(text.encode()).hexdigest()[:15], 16) % 2**31
