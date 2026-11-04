"""The reader and signals on files real applicants upload: locked, damaged, signed,
linearised, or with table headers only on the first page."""

from __future__ import annotations

import shutil
import subprocess

import pytest

pytest.importorskip("weasyprint")
pymupdf = pytest.importorskip("pymupdf")

from forgelens.forgery import forge, ghostscript
from forgelens.generator import BANKS, build_statement, get_bank, locate_fields, render_pdf
from forgelens.reader import PasswordRequired, UnreadablePDF, font_key, open_pdf, parse_statement
from forgelens.signals.financial import check_statement
from forgelens.signals.pdf_structure import analyze_pdf
from forgelens.signals.template import TemplateMatcher, fit_profiles


@pytest.fixture(scope="module")
def genuine(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("robust")
    bank = get_bank("sahyadri")
    st = build_statement(seed=31, bank=bank, months=2)
    pdf = render_pdf(st, bank, tmp / f"{st.statement_id}.pdf")
    record = st.ground_truth()
    record["layout"] = locate_fields(pdf, st, bank)
    train = [(bank.bank_id, render_pdf(build_statement(seed=s, bank=bank, months=2), bank,
                                       tmp / f"train_{s}.pdf")) for s in (1, 2)]
    return st, pdf, record, TemplateMatcher(fit_profiles(train))


@pytest.fixture(scope="module")
def locked(genuine, tmp_path_factory):
    _, pdf, _, _ = genuine
    out = tmp_path_factory.mktemp("locked") / "locked.pdf"
    with pymupdf.open(pdf) as doc:
        doc.save(out, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="01011990", owner_pw="bank")
    return out


# ---------------------------------------------------------------- opening files

def test_password_protected_statement_needs_the_password(genuine, locked):
    st, _, _, _ = genuine
    with pytest.raises(PasswordRequired):
        open_pdf(locked)
    with pytest.raises(PasswordRequired, match="wrong"):
        open_pdf(locked, password="12345678")
    parsed = parse_statement(locked, password="01011990")
    assert [r.balance for r in parsed.rows] == [t.balance for t in st.transactions]


def test_signals_abstain_on_a_locked_file_and_read_it_with_the_password(genuine, locked):
    _, _, _, matcher = genuine
    fin, struct, tpl = check_statement(locked), analyze_pdf(locked), matcher.check(locked)
    assert fin.abstained and "password" in fin.error
    assert struct.abstained and struct.score == 0.5 and "password" in struct.error
    assert tpl.abstained and "password" in tpl.reason
    assert check_statement(locked, password="01011990").consistent
    assert not analyze_pdf(locked, password="01011990").suspicious
    assert not matcher.check(locked, password="01011990").suspicious


@pytest.mark.parametrize("content", [b"", b"%PDF-1.7\nnot really a pdf", b"\x89PNG\r\n\x1a\n"])
def test_damaged_files_raise_one_error_type_and_signals_abstain(tmp_path, content):
    bad = tmp_path / "upload.pdf"
    bad.write_bytes(content)
    with pytest.raises(UnreadablePDF):
        parse_statement(bad)
    assert check_statement(bad).abstained
    report = analyze_pdf(bad)
    assert report.abstained and report.error and not report.suspicious


def test_missing_file_is_a_caller_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        open_pdf(tmp_path / "nope.pdf")


# ---------------------------------------------------------------- genuine files that look edited

@pytest.mark.parametrize("bank_id", sorted(BANKS))
def test_continuation_pages_without_a_header_are_read(tmp_path, pdf_tools, bank_id):
    bank = get_bank(bank_id)
    st = build_statement(seed=3, bank=bank, months=4)
    pdf = render_pdf(st, bank, tmp_path / "multi.pdf")
    with pymupdf.open(pdf) as doc:
        assert doc.page_count > 1
    bare = pdf_tools.remove_repeated_headers(pdf, tmp_path / "bare.pdf",
                                             tuple(bank.label(k) for k in bank.columns))
    parsed = parse_statement(bare)
    assert len(parsed.header_labels) == 1  # the header really is gone after page 1
    assert [r.balance for r in parsed.rows] == [t.balance for t in st.transactions]
    assert check_statement(bare).consistent


def test_linearised_genuine_statement_is_not_flagged(genuine, tmp_path):
    _, pdf, _, _ = genuine
    out = tmp_path / "linear.pdf"
    if ghostscript():  # Ghostscript's linearised files have two save sections
        subprocess.run([ghostscript(), "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
                        "-dFastWebView=true", "-o", str(out), str(pdf)], check=True,
                       capture_output=True)
    elif shutil.which("qpdf"):
        subprocess.run(["qpdf", "--linearize", str(pdf), str(out)], check=True)
    else:
        pytest.skip("needs Ghostscript or qpdf to linearise")
    report = analyze_pdf(out)
    assert report.stats["linearized"]
    assert "incremental_update" not in {f.check for f in report.findings}


def test_signed_genuine_statement_is_not_flagged(genuine, tmp_path, pdf_tools):
    _, pdf, _, _ = genuine
    signed = pdf_tools.sign(pdf, tmp_path / "signed.pdf")
    report = analyze_pdf(signed)
    assert report.stats["signatures"] == 1 and report.stats["startxref_count"] == 2
    assert not report.suspicious, [f.message for f in report.findings]
    assert check_statement(signed).consistent


@pytest.mark.parametrize(("save_mode", "expected"), [
    ("incremental", {"incremental_update", "modified_after_signing"}),
    ("rewrite", {"signature_broken", "modified_after_signing"}),
])
def test_editing_a_signed_statement_is_caught(genuine, tmp_path, pdf_tools, save_mode, expected):
    _, pdf, record, _ = genuine
    signed = pdf_tools.sign(pdf, tmp_path / "signed.pdf")
    out = tmp_path / "edited.pdf"
    forge(signed, record, out, operation="holder_name", seed=1, save_mode=save_mode,
          font_strategy="matched")
    assert expected <= {f.check for f in analyze_pdf(out).findings}


def test_font_key_treats_semi_condensed_as_condensed():
    assert font_key("DejaVu-Sans-Semi-Condensed") == font_key("DejaVu Sans Condensed")
    assert font_key("ABCDEF+DejaVuSansCondensed-Bold") == ("dejavusanscondensed", "bold")
