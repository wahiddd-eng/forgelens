#!/usr/bin/env bash
# Build the v4 synthetic statement set (the README's "Reproduce the results" commands) into
# one folder, checking first that this machine can render PDFs. Safe to run again: finished
# steps are skipped.
#
#   bash scripts/make_synthetic_set.sh                      # into ~/forgelens-data/synthetic_v4
#   bash scripts/make_synthetic_set.sh /path/to/folder
#
# Makes genuine/, forged/{pdf_edit,rebuild}/ and their _reprint and _raster versions: 300
# genuine and 600 forged statements, each also reprinted (needs Ghostscript) and rasterised.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="${1:-$HOME/forgelens-data/synthetic_v4}"
PY="${PYTHON:-python}"
mkdir -p "$D"

echo "==> checking that PDFs can be rendered here"
if ! "$PY" - <<'EOF'
import tempfile
from weasyprint import HTML
with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
    HTML(string="<p style='font-family: Liberation Sans'>1,23,456.00</p>").write_pdf(f.name)
print("  WeasyPrint OK")
EOF
then
    echo "  ! WeasyPrint cannot render here (it needs the Pango library: libpango-1.0-0)."
    echo "    Ask the Centre for AI to install it, or build the set on another Linux machine"
    echo "    and copy it here."
    exit 1
fi
if command -v gs >/dev/null; then echo "  Ghostscript OK"; GS=1
else echo "  ! no Ghostscript: the reprinted versions are skipped"; GS=0; fi
fc-list 2>/dev/null | grep -qiE "liberation|carlito|dejavu" \
    || echo "  ! none of the expected fonts (Liberation, Carlito, DejaVu): pages render with others"

step() { echo; echo "==> $*"; }
done_if() { [[ -n "$(find "$1" -name '*.pdf' -print -quit 2>/dev/null)" ]]; }

step "genuine statements (10 banks x 30)"
done_if "$D/genuine" && echo "  already there" || \
    "$PY" "$REPO/scripts/generate_statements.py" --bank all --count 30 --seed 2000 --out "$D/genuine"
step "PDF-edit forgeries"
done_if "$D/forged/pdf_edit" && echo "  already there" || \
    "$PY" "$REPO/scripts/forge_pdf_edits.py" --genuine "$D/genuine" --out "$D/forged/pdf_edit" --masks
step "rebuilt forgeries"
done_if "$D/forged/rebuild" && echo "  already there" || \
    "$PY" "$REPO/scripts/forge_rebuild.py" --genuine "$D/genuine" --out "$D/forged/rebuild" --masks
methods=(raster)
(( GS )) && methods=(reprint raster)
for m in "${methods[@]}"; do
    step "$m laundering"
    done_if "$D/genuine_$m" && echo "  genuine_$m already there" || \
        "$PY" "$REPO/scripts/launder_pdfs.py" --input "$D/genuine" --out "$D/genuine_$m" --method "$m"
    done_if "$D/forged_$m" && echo "  forged_$m already there" || \
        "$PY" "$REPO/scripts/launder_pdfs.py" --input "$D/forged" --out "$D/forged_$m" --method "$m" --masks
done

step "done"
for sub in genuine forged genuine_reprint forged_reprint genuine_raster forged_raster; do
    [[ -d $D/$sub ]] && printf '  %-16s %5d PDFs\n' "$sub" "$(find "$D/$sub" -name '*.pdf' | wc -l)"
done
echo "Next: python scripts/eval_adcdnet_pages.py --config configs/adcdnet_eval.yaml --tag v4 \\"
echo "        --data $D/genuine $D/forged $D/genuine_raster $D/forged_raster ... --resume"
