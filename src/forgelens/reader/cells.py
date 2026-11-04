"""Printed text cells with position and style, and font-name normalisation."""

from __future__ import annotations

import re
from dataclasses import dataclass

STYLE_WORDS = ("bold", "italic", "oblique", "book", "regular", "roman", "medium", "light")


@dataclass
class Cell:
    """A printed text span with its position and style (PDF points, top-left origin)."""

    page: int
    text: str
    bbox: tuple[float, float, float, float]
    origin: tuple[float, float]
    size: float
    font: str
    color: int

    @property
    def baseline(self) -> float:
        return self.origin[1]

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "text": self.text,
            "bbox": [round(v, 3) for v in self.bbox],
            "origin": [round(v, 3) for v in self.origin],
            "size": round(self.size, 3),
            "font": self.font,
            "color": self.color,
        }


def font_key(name: str) -> tuple[str, str]:
    """Return (family, style) from a font name, ignoring subset tags and spelling.

    ``ABCDEF+LiberationSans-BoldItalic`` and ``Liberation Sans Bold Italic`` both give
    ``("liberationsans", "bolditalic")``; ``DejaVu Sans Condensed`` and
    ``DejaVu-Sans-Semi-Condensed`` are the same family.
    """
    name = name.split("+", 1)[-1].lower()
    letters = re.sub(r"[^a-z]", "", name)
    style = "".join(w for w in ("bold", "italic", "oblique") if w in letters) or "regular"
    family = letters
    for w in STYLE_WORDS:
        family = family.replace(w, "")
    family = family.removesuffix("mt").removesuffix("ps").replace("semicondensed", "condensed")
    return family, style


class _ResolvingDict(dict):
    def __init__(self, resolve):
        super().__init__()
        self._resolve = resolve

    def __missing__(self, key):
        value = self._resolve(key)
        self[key] = value
        return value


def full_font_names(doc, page_no: int) -> dict[str, str]:
    """Map shortened span font names to the page's full font names.

    Text extraction reports at most about 24 characters of a font name
    (``Liberation-Serif-Bold-It``); the page's font list has the full name.
    """
    names = [f[3].split("+", 1)[-1] for f in doc.get_page_fonts(page_no)]
    lookup = {n: n for n in names}

    def resolve(short: str) -> str:
        if short in lookup:
            return lookup[short]
        matches = [n for n in names if n.startswith(short)]
        return matches[0] if len(matches) == 1 else short

    return _ResolvingDict(resolve)


def read_cells(doc, gap: float = 3.0) -> list[Cell]:
    """Return text cells with positions, splitting runs where characters are ``gap`` apart.

    PDF text extractors join neighbouring table cells into one run when they share a font
    and sit on the same line. A gap wider than a normal letter spacing marks a new cell.
    """
    out = []
    for page_no, page in enumerate(doc):
        fonts = full_font_names(doc, page_no)
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                for s in line["spans"]:
                    groups, current = [], []
                    for ch in s["chars"]:
                        if current and ch["bbox"][0] - current[-1]["bbox"][2] > max(
                                gap, 0.35 * s["size"]):
                            groups.append(current)
                            current = []
                        current.append(ch)
                    if current:
                        groups.append(current)
                    for g in groups:
                        stripped = "".join(ch["c"] for ch in g).strip()
                        if not stripped:
                            continue
                        visible = [ch for ch in g if ch["c"].strip()]
                        x0 = min(ch["bbox"][0] for ch in visible)
                        x1 = max(ch["bbox"][2] for ch in visible)
                        bbox = (x0, s["bbox"][1], x1, s["bbox"][3])
                        origin = (visible[0]["origin"][0], visible[0]["origin"][1])
                        out.append(Cell(page_no, stripped, bbox, origin, s["size"],
                                        fonts[s["font"]], s["color"]))
    return out
