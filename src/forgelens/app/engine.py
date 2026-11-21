"""ForgeLens on one statement: every available signal, the fused verdict and its evidence.

The web app (``forgelens.app.server``) calls :meth:`Engine.analyze` once per upload. The file is
read from a temporary path the server deletes afterwards; nothing here writes it anywhere or
logs its contents.

What runs depends on what the machine has:

* always: the kind of copy, the financial (PDF text) and PDF-structure checks;
* with template profiles (``scripts/fit_templates.py``): template matching;
* with EasyOCR: OCR arithmetic on the page images;
* with an image-model config (``configs/adcdnet_ft6.yaml``) and a GPU: ADCD-Net, with a heat
  map per page;
* with a fusion model (``model.pkl`` from ``scripts/fuse_signals.py``): the fused verdict at the
  thresholds for this kind of copy. Without one, the verdict says which signals found evidence.
"""

from __future__ import annotations

import base64
import io
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]

KIND_LABEL = {
    "digital": "Bank PDF with a text layer",
    "scan": "Scan or image-only PDF",
    "screenshot": "Phone screenshot",
    "phone_jpeg": "Phone or messenger copy (JPEG)",
}
SIGNAL_NAME = {
    "financial": "Arithmetic in the text",
    "structure": "PDF structure",
    "template": "Bank layout",
    "ocr_financial": "Arithmetic on the page image",
    "image": "Image forensics (ADCD-Net)",
}
SIGNAL_WHAT = {
    "financial": "Re-adds every row: each balance must follow from the one before, and the "
                 "summary must match the table.",
    "structure": "Reads how the file was built: fonts, saves and edits a PDF editor leaves behind.",
    "template": "Compares the layout with what this bank's genuine statements look like.",
    "ocr_financial": "Reads the figures from the page image and re-adds them, for scans and "
                     "screenshots that have no text layer.",
    "image": "A neural network looks for pixels that were retouched, pasted or regenerated.",
}
CHECK_TITLE = {
    # financial
    "running_balance": "A balance does not follow from the row before",
    "closing_balance": "Closing balance does not match the table",
    "opening_balance": "Opening balance does not match the table",
    "totals": "Totals do not match the rows",
    "counts": "Transaction count does not match the rows",
    "row_format": "A row has both a debit and a credit",
    # structure
    "incremental_update": "The file was edited and saved again",
    "modified_after_signing": "Changed after it was digitally signed",
    "signature_broken": "The digital signature no longer matches",
    "modified_after_creation": "Modified after it was created",
    "non_embedded_font": "Text in a font the file does not carry",
    "duplicate_font": "The same font added twice",
    "extra_content_streams": "A page has extra drawing layers",
    "font_anomaly": "Text in a font the rest of the document does not use",
    # template
    "page_size": "Page size differs from this bank's",
    "creator": "Made by different software than this bank uses",
    "header_labels": "Table headings differ from this bank's",
    "column_positions": "Columns are not where this bank puts them",
    "table_font": "Table figures in a different font",
    "table_font_size": "Table figures in a different size",
    "date_format": "Dates written differently from this bank's",
    "amount_format": "Amounts written differently from this bank's",
    "masthead": "The bank's name is set differently",
    "unexpected_font": "Text in a font this bank does not use",
    # OCR
    "ocr_break": "A balance on the page image does not add up",
    "ocr_summary": "The summary on the page image does not match the table",
}
PREVIEW_DPI = 110


@dataclass
class Settings:
    fusion_model: Path | None = None
    templates: Path | None = None
    image_config: Path | None = None
    profiles: Path | None = None
    ocr: bool = True
    device: str = "cuda"
    dpi: int = 150


def _jpeg(arr: np.ndarray) -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "JPEG", quality=85, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _heat_png(prob: np.ndarray, size: tuple[int, int]) -> str:
    """The probability map as a translucent violet layer (alpha = probability)."""
    from PIL import Image

    p = np.clip(prob, 0, 1)
    p = np.where(p < 0.25, 0, (p - 0.25) / 0.75)  # keep faint noise off the page
    rgba = np.zeros((*p.shape, 4), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = 122, 63, 242  # --uv
    rgba[..., 3] = (p * 210).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA").resize(size, Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def for_fusion(scores: dict, kind: str) -> dict:
    """As the fusion model saw statements in training: image and OCR scores only for copies
    without a text layer (see scripts/eval_real.py)."""
    if kind != "digital":
        return scores
    return {k: (None if k in ("image", "image_released", "ocr_financial") else v)
            for k, v in scores.items()}


class Engine:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.final = None
        if settings.fusion_model and Path(settings.fusion_model).exists():
            self.final = pickle.loads(Path(settings.fusion_model).read_bytes())
        self.matcher = None
        if settings.templates and Path(settings.templates).exists():
            from forgelens.signals.template import TemplateMatcher

            self.matcher = TemplateMatcher.load(settings.templates)
        self.profiles = None
        if settings.profiles and Path(settings.profiles).exists():
            from forgelens.signals.pdf_structure.profiles import BankProfiles

            self.profiles = BankProfiles.load(settings.profiles)
        self.ocr = None
        if settings.ocr:
            try:
                from forgelens.signals.ocr_financial import OcrReader

                self.ocr = OcrReader(gpu=settings.device != "cpu")
            except Exception:  # noqa: BLE001 - EasyOCR not installed: the signal is skipped
                self.ocr = None
        self.detector = None
        self.image_model = None
        if settings.image_config and Path(settings.image_config).exists():
            import yaml

            from forgelens.signals.image import adcdnet
            from forgelens.signals.image.pages import PageDetector

            cfg = {k.replace("-", "_"): v
                   for k, v in yaml.safe_load(Path(settings.image_config).read_text()).items()}
            paths = adcdnet.Paths(upstream=ROOT / "third_party" / "ADCD-Net", ckpt=cfg["ckpt"],
                                  docres=cfg["docres"], doctamper_root=cfg.get("doctamper_root"),
                                  qt_path=cfg.get("qt_path"))
            self.detector = PageDetector(paths, settings.device,
                                         "fp16" if settings.device != "cpu" else "fp32")
            self.image_model = Path(settings.image_config).stem.removeprefix("adcdnet_")

    def banks(self) -> list[str]:
        """Banks this server knows something about: bank-layout profiles and bank profiles."""
        names = set()
        if self.matcher is not None:
            names |= {p.get("bank_name", k) for k, p in self.matcher.profiles.items()}
        if self.profiles is not None:
            names |= {b for b, _ in self.profiles.seen}
        return sorted(names, key=str.lower)

    def _template_id(self, bank: str | None) -> str | None:
        if not bank or self.matcher is None:
            return None
        b = bank.strip().lower()
        for k, p in self.matcher.profiles.items():
            if b in (k.lower(), str(p.get("bank_name", "")).lower()):
                return k
        return None

    def capabilities(self) -> dict:
        return {
            "fusion": self.final is not None,
            "fusion_trained_on": self.final.get("trained_on") if self.final else None,
            "per_kind_thresholds": bool(self.final and self.final.get("thresholds_by_kind")),
            "template": self.matcher is not None,
            "ocr": self.ocr is not None,
            "image": self.detector is not None,
            "image_model": self.image_model,
            "bank_profiles": self.profiles is not None,
            "banks": self.banks(),
        }

    # ------------------------------------------------------------------ analysis
    def analyze(self, pdf: Path, password: str | None = None, bank: str | None = None,
                name: str | None = None) -> dict:
        from forgelens.fusion.copy_kind import copy_kind
        from forgelens.reader import open_pdf
        from forgelens.signals.financial.checker import check_statement
        from forgelens.signals.image.pages import render_pages, render_pages_native
        from forgelens.signals.pdf_structure.analyzer import analyze_pdf

        t0 = time.perf_counter()
        struct = analyze_pdf(pdf, password)
        if struct.error and "password" in struct.error.lower():
            return {"error": "password", "message": "This PDF is locked. Enter its password and "
                    "examine it again."}
        if struct.error:
            return {"error": "unreadable", "message": "This file could not be read as a PDF or "
                    "an image."}
        kind = copy_kind(pdf, password)
        with open_pdf(pdf, password) as doc:
            sizes = [(p.rect.width, p.rect.height) for p in doc]
            producer = (doc.metadata or {}).get("producer", "")
        fin = check_statement(pdf, password)

        signals, boxes = [], {i: [] for i in range(len(sizes))}

        def add_boxes(sig: str, locations: list[dict], label: str) -> None:
            for loc in locations:
                if loc.get("bbox") is not None and loc.get("page") in boxes:
                    boxes[loc["page"]].append({"bbox": [round(v, 1) for v in loc["bbox"]],
                                               "signal": sig, "label": label})

        # financial
        signals.append(self._signal(
            "financial", None if fin.abstained else fin.score, fin.abstained,
            [{"check": f.check, "title": CHECK_TITLE.get(f.check, f.check), "message": f.message,
              "page": f.page} for f in fin.findings],
            reason="no transaction table could be read from the text" if fin.abstained else None))
        # structure (bank profiles, when loaded, set aside what this bank's software always does)
        s_score = None if struct.abstained else struct.score
        if self.profiles and bank and not struct.abstained:
            s_score = self.profiles.score(struct, bank, producer)
        s_findings = []
        for f in struct.findings:
            pages_hit = sorted({loc["page"] for loc in f.locations if loc.get("page") is not None})
            s_findings.append({"check": f.check, "title": CHECK_TITLE.get(f.check, f.check),
                               "message": f.message,
                               "page": f.page if f.page is not None else
                               (pages_hit[0] if pages_hit else None)})
            add_boxes("structure", f.locations, CHECK_TITLE.get(f.check, f.check))
        reason = "the file has no text layer" if struct.abstained else None
        if s_findings and s_score == 0:
            reason = "what was found matches how this bank's genuine statements are built"
        signals.append(self._signal("structure", s_score, struct.abstained, s_findings,
                                    reason=reason))
        # template
        t_score = None
        if self.matcher is not None:
            tpl = self.matcher.check(pdf, bank_id=self._template_id(bank), password=password)
            t_score = None if tpl.abstained else tpl.score
            t_findings = []
            for f in tpl.findings:
                pages_hit = sorted({loc["page"] for loc in f.locations if loc.get("page") is not None})
                t_findings.append({"check": f.check, "title": CHECK_TITLE.get(f.check, f.check),
                                   "message": f.message, "page": pages_hit[0] if pages_hit else None})
                add_boxes("template", f.locations, CHECK_TITLE.get(f.check, f.check))
            signals.append(self._signal(
                "template", t_score, tpl.abstained, t_findings,
                reason=("no layout profile for this bank" if tpl.abstained else None)))
        else:
            signals.append(self._signal("template", None, True, [], not_run=True,
                                        reason="no bank profiles loaded on this server"))
        # OCR arithmetic
        o_score = None
        if self.ocr is not None:
            from forgelens.signals.ocr_financial import check_pdf

            rep = check_pdf(pdf, self.ocr, self.s.dpi, password)
            o_score = None if rep.abstained else rep.score
            o_findings = [{"check": "ocr_summary" if m.startswith("summary") else "ocr_break",
                           "title": CHECK_TITLE["ocr_summary" if m.startswith("summary") else "ocr_break"],
                           "message": m[0].upper() + m[1:], "page": None} for m in rep.findings]
            signals.append(self._signal(
                "ocr_financial", o_score, rep.abstained, o_findings,
                reason="too few rows could be read from the page image" if rep.abstained else None))
        else:
            signals.append(self._signal("ocr_financial", None, True, [], not_run=True,
                                        reason="OCR is not installed on this server"))
        # image model, with a heat map per page
        i_score, i_area, heat = None, None, {}
        if self.detector is not None:
            from forgelens.signals.image.pages import page_scores

            peaks, areas = [], []
            for i, (rgb, _) in enumerate(render_pages_native(pdf, self.s.dpi, password)):
                prob = self.detector.predict(rgb).prob
                sc = page_scores(prob)
                peaks.append(sc["peak"])
                areas.append(sc["area"])
                heat[i] = prob
            i_score = max(peaks) if peaks else None
            i_area = max(areas) if areas else None
            signals.append(self._signal(
                "image", i_score, i_score is None,
                [{"check": "image_regions", "title": "Pixels the model reads as edited",
                  "message": f"Strongest on page {int(np.argmax(peaks)) + 1}; "
                             f"{max(areas):.2%} of that page's area is above 0.5.",
                  "page": int(np.argmax(peaks))}] if i_score is not None and i_score > 0.5 else []))
        else:
            signals.append(self._signal("image", None, True, [], not_run=True,
                                        reason="the image model runs only on the GPU server"))

        # pages: previews with heat maps and evidence boxes
        pages = []
        for i, rgb in enumerate(render_pages(pdf, PREVIEW_DPI, password)):
            h, w = rgb.shape[:2]
            pages.append({"index": i, "width_pt": sizes[i][0], "height_pt": sizes[i][1],
                          "image": _jpeg(rgb),
                          "heat": _heat_png(heat[i], (w, h)) if i in heat else None,
                          "boxes": boxes.get(i, [])})

        if kind == "digital":  # as in evaluation: pixels and OCR are not counted on text PDFs
            for sig in signals:
                if sig["id"] in ("image", "ocr_financial") and sig["status"] != "not_run":
                    sig["counted"] = False
                    sig["note"] = ("Shown for reference. On a PDF with a text layer the verdict "
                                   "rests on the text and the file's structure, which see edits "
                                   "here more reliably than the page image.")
        if self.final is not None:  # a check the fusion model was fitted without is shown only
            used = set(self.final["signals"])
            for sig in signals:
                if sig["counted"] and sig["status"] != "not_run" and sig["id"] not in used:
                    sig["counted"] = False
                    sig["note"] = ("Shown for reference. The combined score on this server was "
                                   "fitted without this check.")
        scores = {"financial": None if fin.abstained else fin.score, "structure": s_score,
                  "template": t_score, "ocr_financial": o_score, "image": i_score}
        verdict = self._verdict(scores, kind, signals,
                                None if kind == "digital" else i_area)
        return {
            "file": name or pdf.name, "kind": kind, "kind_label": KIND_LABEL.get(kind, kind),
            "pages": pages, "signals": signals, "verdict": verdict,
            "bank": bank or None, "seconds": round(time.perf_counter() - t0, 1),
            "capabilities": self.capabilities(),
        }

    @staticmethod
    def _signal(sid: str, score, abstained: bool, findings: list[dict], not_run: bool = False,
                reason: str | None = None) -> dict:
        status = "not_run" if not_run else "abstained" if abstained else \
            "flagged" if findings and score is not None and score > 0 else "clear"
        return {"id": sid, "name": SIGNAL_NAME[sid], "what": SIGNAL_WHAT[sid], "status": status,
                "score": None if score is None else round(float(score), 4),
                "findings": findings, "reason": reason, "counted": True, "note": None}

    def _verdict(self, scores: dict, kind: str, signals: list[dict],
                 image_area: float | None = None) -> dict:
        flagged = [s["name"] for s in signals if s["status"] == "flagged" and s["counted"]]
        judged = [s for s in signals if s["counted"] and s["status"] in ("flagged", "clear")]
        if self.final is None:
            level = "suspicious" if flagged else "clear" if judged else "unknown"
            return {"level": level, "fused": None, "thresholds": None, "flagged_by": flagged,
                    "basis": "signals", "headline": {
                        "suspicious": "Worth a closer look", "clear": "No sign of editing found",
                        "unknown": "Not enough to go on"}[level]}
        from forgelens.fusion.fuse import Statement, apply_final, threshold_for

        st = Statement("upload.pdf", "genuine", "upload", "none", "", "upload")
        st.kind = kind
        st.scores = {k: v for k, v in for_fusion(scores, kind).items()
                     if k in self.final["signals"]}
        for k in self.final["signals"]:
            st.scores.setdefault(k, None)
        st.image_area = image_area
        fused = float(apply_final(self.final, [st])[0])
        t1, t5 = threshold_for(self.final, kind, 0.01), threshold_for(self.final, kind, 0.05)
        level = "forged" if fused > t1 else "suspicious" if fused > t5 else "clear"
        headline = {"forged": "Likely edited", "suspicious": "Worth a closer look",
                    "clear": "No sign of editing found"}[level]
        return {"level": level, "fused": round(fused, 4),
                "thresholds": {"0.01": round(float(t1), 4), "0.05": round(float(t5), 4)},
                "flagged_by": flagged, "basis": "fusion", "headline": headline}
