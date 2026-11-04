"""Tests for template-rebuilt forgeries and the template-matching signal."""

from __future__ import annotations

from decimal import Decimal

import pytest

from forgelens.generator import BANKS, build_statement, get_bank
from forgelens.generator.models import Statement
from forgelens.signals.template.matcher import _amount_style, _date_shape


def test_ground_truth_round_trip():
    st = build_statement(seed=8, bank=get_bank("ganga_mercantile"))
    record = st.ground_truth()
    assert Statement.from_ground_truth(record).ground_truth() == record


def test_same_seed_differs_between_banks():
    names = {build_statement(seed=5, bank=b).customer.name for b in BANKS.values()}
    assert len(names) == len(BANKS)


@pytest.mark.parametrize(("text", "style"), [
    ("1,23,456.78", ("indian", "")),
    ("123,456.78", ("western", "")),
    ("123456.78", ("none", "")),
    ("12,34,567.00 Cr", ("indian", "Cr")),
    ("1,234.00", None),  # too short to tell the grouping
])
def test_amount_style(text, style):
    assert _amount_style(text) == style


def test_date_shape():
    assert _date_shape("03-Sep-2025") == "99-AAA-9999"
    assert _date_shape("03/09/25") == "99/99/99"


weasyprint = pytest.importorskip("weasyprint")
pymupdf = pytest.importorskip("pymupdf")

from forgelens.forgery import forge, launder, rebuild
from forgelens.generator import locate_fields, render_pdf
from forgelens.signals.financial import check_statement
from forgelens.signals.pdf_structure import analyze_pdf
from forgelens.signals.template import TemplateMatcher, fit_profiles

BANK_IDS = ("deccan_cooperative", "sahyadri")


def _genuine(tmp, bank_id: str, seed: int):
    bank = get_bank(bank_id)
    st = build_statement(seed=seed, bank=bank, months=2)
    pdf = render_pdf(st, bank, tmp / f"{st.statement_id}.pdf")
    record = st.ground_truth()
    record["layout"] = locate_fields(pdf, st, bank)
    return pdf, record


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tpl")
    train = [(b, _genuine(tmp, b, s)[0]) for b in BANK_IDS for s in (100, 101, 102)]
    matcher = TemplateMatcher(fit_profiles(train))
    tests = {b: _genuine(tmp, b, 200) for b in BANK_IDS}
    return tmp, matcher, tests


def test_profiles_learn_bank_names_and_fonts(env):
    _, matcher, _ = env
    assert matcher.profiles["sahyadri"]["bank_name"] == "Sahyadri Bank"
    assert all(f.startswith("Carlito") for f in matcher.profiles["sahyadri"]["fonts"])


@pytest.mark.parametrize("bank_id", BANK_IDS)
def test_unseen_genuine_statement_matches_its_template(env, bank_id):
    _, matcher, tests = env
    pdf, _ = tests[bank_id]
    report = matcher.check(pdf)
    assert report.bank_id == bank_id
    assert not report.suspicious, [f.message for f in report.findings]


def test_reprinted_genuine_statement_still_matches(env, tmp_path):
    from forgelens.forgery import ghostscript

    if ghostscript() is None:
        pytest.skip("Ghostscript not installed")
    _, matcher, tests = env
    pdf, record = tests["deccan_cooperative"]
    out = tmp_path / "reprint.pdf"
    launder(pdf, record, out, method="reprint", seed=1)
    assert not matcher.check(out).suspicious


@pytest.mark.parametrize("bank_id", BANK_IDS)
def test_exact_rebuild_defeats_every_signal(env, tmp_path, bank_id):
    _, matcher, tests = env
    _, record = tests[bank_id]
    out = tmp_path / "exact.pdf"
    label = rebuild(record, out, variant="rebuilt_exact", seed=3)
    assert label["label"] == "forged" and label["forgery"]["balance_consistent"]
    assert Decimal(label["closing_balance"]) > Decimal(record["closing_balance"])
    assert label["edits"] and all(e["new_bbox"] for e in label["edits"])
    assert check_statement(out).consistent
    assert not analyze_pdf(out).suspicious
    assert not matcher.check(out).suspicious


@pytest.mark.parametrize("bank_id", BANK_IDS)
def test_imitation_rebuild_is_caught_by_template(env, tmp_path, bank_id):
    _, matcher, tests = env
    _, record = tests[bank_id]
    out = tmp_path / "imitation.pdf"
    label = rebuild(record, out, variant="rebuilt_imitation", seed=3)
    assert label["forgery"]["imitation"]["font_family"] != get_bank(bank_id).font_family
    assert check_statement(out).consistent
    report = matcher.check(out)
    assert report.suspicious
    assert {"unexpected_font", "table_font", "table_font_size", "masthead"} & {
        f.check for f in report.findings}


def test_pdf_edit_with_fallback_font_is_localised(env, tmp_path):
    _, matcher, tests = env
    pdf, record = tests["sahyadri"]
    out = tmp_path / "edit.pdf"
    label = forge(pdf, record, out, operation="holder_name", seed=2, font_strategy="fallback")
    report = matcher.check(out)
    finding = next(f for f in report.findings if f.check == "unexpected_font")
    edit = label["edits"][0]
    assert any(loc["page"] == edit["page"] and loc["text"] == edit["new"]
               for loc in finding.locations)


def test_template_abstains_without_text_or_known_bank(env, tmp_path):
    _, matcher, tests = env
    pdf, record = tests["sahyadri"]
    raster = tmp_path / "raster.pdf"
    launder(pdf, record, raster, method="raster", seed=1, dpi=72)
    report = matcher.check(raster)
    assert report.abstained and report.score == 0.5 and not report.suspicious
    other = TemplateMatcher({k: v for k, v in matcher.profiles.items() if k != "sahyadri"})
    assert other.check(pdf).abstained


def test_profiles_save_and_load(env, tmp_path):
    _, matcher, tests = env
    path = tmp_path / "profiles.json"
    matcher.save(path)
    loaded = TemplateMatcher.load(path)
    pdf, _ = tests["deccan_cooperative"]
    assert loaded.check(pdf).to_dict()["suspicious"] is False


def test_rebuild_rejects_unknown_variant(env, tmp_path):
    _, _, tests = env
    with pytest.raises(ValueError):
        rebuild(tests["sahyadri"][1], tmp_path / "x.pdf", variant="photocopy")
