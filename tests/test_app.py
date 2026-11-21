"""The web app: the engine's verdict and evidence, the upload handler, and the bundled data."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("weasyprint")
pymupdf = pytest.importorskip("pymupdf")

from forgelens.app.engine import CHECK_TITLE, Engine, Settings, for_fusion
from forgelens.forgery import forge
from forgelens.generator import build_statement, get_bank, locate_fields, render_pdf

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "src" / "forgelens" / "app" / "static"
TEMPLATES = REPO / "experiments" / "templates_v4.json"
BANK = get_bank("himalaya_national")


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("app")
    st = build_statement(seed=8101, bank=BANK, months=2)
    pdf = render_pdf(st, BANK, d / "genuine.pdf")
    record = st.ground_truth()
    record["layout"] = locate_fields(pdf, st, BANK)
    edited = d / "edited.pdf"
    label = forge(pdf, record, edited, operation="credit_amount", seed=3,
                  save_mode="incremental", font_strategy="fallback")
    locked = d / "locked.pdf"
    with pymupdf.open(pdf) as doc:
        doc.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="fictional", owner_pw="o")
    return {"genuine": pdf, "edited": edited, "locked": locked, "label": label}


@pytest.fixture(scope="module")
def engine():
    return Engine(Settings(templates=TEMPLATES if TEMPLATES.exists() else None, ocr=False,
                           device="cpu"))


def test_genuine_statement_is_clear(engine, files):
    r = engine.analyze(files["genuine"])
    assert r["verdict"]["level"] == "clear"
    assert r["verdict"]["basis"] == "signals"  # no fusion model on this machine
    assert r["kind"] == "digital"
    assert all(s["status"] in ("clear", "not_run") for s in r["signals"])
    assert len(r["pages"]) >= 1 and r["pages"][0]["image"].startswith("data:image/jpeg;base64,")


def test_edited_statement_is_flagged_with_located_evidence(engine, files):
    r = engine.analyze(files["edited"])
    assert r["verdict"]["level"] == "suspicious"
    by_id = {s["id"]: s for s in r["signals"]}
    assert by_id["financial"]["status"] == "flagged"
    assert by_id["structure"]["status"] == "flagged"
    assert "Arithmetic in the text" in r["verdict"]["flagged_by"]
    boxes = [b for p in r["pages"] for b in p["boxes"]]
    assert boxes, "the patched-in text should be marked on its page"
    for p in r["pages"]:
        for b in p["boxes"]:
            x0, y0, x1, y1 = b["bbox"]
            assert 0 <= x0 < x1 <= p["width_pt"] + 1 and 0 <= y0 < y1 <= p["height_pt"] + 1
    for s in r["signals"]:  # every finding has a plain-language title, never a raw check id
        for f in s["findings"]:
            assert f["title"] and "_" not in f["title"]


def test_locked_pdf_asks_for_password_and_opens_with_it(engine, files):
    r = engine.analyze(files["locked"])
    assert r["error"] == "password"
    r = engine.analyze(files["locked"], password="fictional")
    assert "error" not in r and r["verdict"]["level"] == "clear"


def test_image_and_ocr_are_not_counted_on_text_pdfs():
    scores = {"financial": 0.0, "structure": 0.0, "image": 0.9, "ocr_financial": 0.8}
    assert for_fusion(scores, "digital")["image"] is None
    assert for_fusion(scores, "digital")["ocr_financial"] is None
    assert for_fusion(scores, "screenshot")["image"] == 0.9


def test_screenshot_without_image_checks_is_not_enough_to_go_on(engine, files, tmp_path):
    from forgelens.forgery.launder import launder

    out = tmp_path / "shot.pdf"
    launder(files["edited"], files["label"], out, method="screenshot", seed=1)
    r = engine.analyze(out)
    assert r["kind"] == "screenshot"
    assert r["verdict"]["level"] == "unknown"  # never "clear" on checks that could not judge


def test_every_check_has_a_title():
    from forgelens.signals.financial import checker
    from forgelens.signals.pdf_structure.analyzer import WEIGHTS
    from forgelens.signals.template import matcher

    src = Path(checker.__file__).read_text() + Path(matcher.__file__).read_text()
    ids = set(re.findall(r'(?:Finding|TemplateFinding)\(\s*"([a-z_]+)"', src)) | set(WEIGHTS)
    ids |= {"running_balance", "unexpected_font"}
    assert ids <= set(CHECK_TITLE), ids - set(CHECK_TITLE)


# ------------------------------------------------------------------ server

@pytest.fixture(scope="module")
def client(engine):
    pytest.importorskip("fastapi")
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    from forgelens.app.server import create_app

    return TestClient(create_app(engine))


def test_upload_is_examined_and_deleted(client, files):
    before = set(Path(tempfile.gettempdir()).glob("forgelens_*"))
    with open(files["edited"], "rb") as fh:
        r = client.post("/api/analyze", files={"file": ("statement.pdf", fh, "application/pdf")})
    assert r.status_code == 200
    assert r.json()["verdict"]["level"] == "suspicious"
    assert r.json()["file"] == "statement.pdf"
    assert set(Path(tempfile.gettempdir()).glob("forgelens_*")) == before


def test_upload_errors_are_plain(client, files):
    with open(files["locked"], "rb") as fh:
        r = client.post("/api/analyze", files={"file": ("x.pdf", fh, "application/pdf")})
    assert r.status_code == 400 and r.json()["error"] == "password"
    r = client.post("/api/analyze", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and r.json()["error"] == "type"
    r = client.post("/api/analyze", files={"file": ("broken.pdf", b"%PDF-1.4 nonsense", "application/pdf")})
    assert r.status_code == 400 and r.json()["error"] == "unreadable"


def test_png_upload_is_examined_as_a_page(client, files, tmp_path):
    with pymupdf.open(files["genuine"]) as doc:
        png = doc[0].get_pixmap(dpi=100).tobytes("png")
    r = client.post("/api/analyze", files={"file": ("photo.png", png, "image/png")})
    assert r.status_code == 200
    assert r.json()["kind"] != "digital"


def test_status_and_pages_are_served(client):
    assert client.get("/api/status").json()["fusion"] is False
    assert "Examine a statement" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/results.json").status_code == 200


# ------------------------------------------------------------------ bundled data

def test_results_json_matches_the_result_files():
    R = json.loads((STATIC / "results.json").read_text())
    fusion = (REPO / "experiments/results/fusion_test.md").read_text()
    ablations = (REPO / "experiments/results/ablations_test.md").read_text()
    real = (REPO / "experiments/results/real_pilot_20261118.md").read_text()
    assert f"**{R['headline']['test_set']['caught_1']}%**" in fusion
    assert f"**{R['headline']['traceable']['caught_1']}%**" in ablations
    assert "**3 (10.3%, CI 3.6–26.4%)**" in real and R["headline"]["real"]["runs"][-1]["rate"] == 10.3
    for row in R["ablations"]["rows"][1:]:
        assert f"| {row['value']}% |" in ablations
    phone = (REPO / "experiments/results/phone_laundering.md").read_text()
    for row in R["copies"]["rows"]:
        assert f"| {row['n']} | {row['one']}% | {row['per_kind']}% |" in phone


def test_static_page_never_writes_server_text_as_html():
    js = (STATIC / "app.js").read_text()
    assert js.count(".innerHTML") == 1  # the fixed icon markup, nothing from the server
    assert "insertAdjacentHTML" not in js and "outerHTML" not in js
