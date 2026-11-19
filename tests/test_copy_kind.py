import pymupdf
import pytest

from forgelens.forgery.launder import launder
from forgelens.fusion.copy_kind import FROM_LAUNDERING, copy_kind


@pytest.fixture
def statement(tmp_path):
    src = tmp_path / "s.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "Closing balance 1,23,456.78")
        doc.save(src)
    return src


@pytest.mark.parametrize("method", ["raster", "screenshot", "whatsapp"])
def test_each_laundering_is_recognised_from_the_file(statement, tmp_path, method):
    out = tmp_path / f"{method}.pdf"
    record = {"statement_id": "s", "label": "genuine", "generated_on": "2026-11-01"}
    launder(statement, record, out, method=method, seed=1)
    assert copy_kind(out) == FROM_LAUNDERING[method]
    assert copy_kind(statement) == "digital"


def test_per_kind_thresholds_skip_rare_kinds():
    from forgelens.fusion.fuse import Statement, per_kind_thresholds

    sts = []
    for i in range(120):
        st = Statement(f"g{i}.pdf", "genuine", "genuine", "raster", "b", f"g{i}")
        st.kind = "scan" if i < 100 else "screenshot"
        sts.append(st)
    th = per_kind_thresholds(sts, [i / 120 for i in range(120)], (0.01,))
    assert set(th) == {"scan"}
