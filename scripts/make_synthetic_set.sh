#!/usr/bin/env bash
# Build the v4 synthetic statement set (the README's "Reproduce the results" commands) into
# one folder, checking first that this machine can render PDFs. Safe to run again: finished
# steps are skipped, and a step interrupted part-way is redone.
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
# A step counts as done only when it finished: its folder gets a .complete marker afterwards.
# An interrupted step (lost connection, reboot) is redone from scratch.
run_step() {  # run_step <folder> <command...>
    local dir=$1; shift
    if [[ -f $dir/.complete ]]; then echo "  already there"; return 0; fi
    rm -rf "$dir"
    "$@" && touch "$dir/.complete" || { echo "  ! this step failed; run the script again"; return 1; }
}

step "genuine statements (10 banks x 30)"
run_step "$D/genuine" "$PY" "$REPO/scripts/generate_statements.py" --bank all --count 30 --seed 2000 --out "$D/genuine" || exit 1
step "PDF-edit forgeries"
run_step "$D/forged/pdf_edit" "$PY" "$REPO/scripts/forge_pdf_edits.py" --genuine "$D/genuine" --out "$D/forged/pdf_edit" --masks || exit 1
step "rebuilt forgeries"
run_step "$D/forged/rebuild" "$PY" "$REPO/scripts/forge_rebuild.py" --genuine "$D/genuine" --out "$D/forged/rebuild" --masks || exit 1
methods=(raster)
(( GS )) && methods=(reprint raster)
for m in "${methods[@]}"; do
    step "$m laundering"
    run_step "$D/genuine_$m" "$PY" "$REPO/scripts/launder_pdfs.py" --input "$D/genuine" --out "$D/genuine_$m" --method "$m" || exit 1
    run_step "$D/forged_$m" "$PY" "$REPO/scripts/launder_pdfs.py" --input "$D/forged" --out "$D/forged_$m" --method "$m" --masks || exit 1
done

step "done"
for sub in genuine forged genuine_reprint forged_reprint genuine_raster forged_raster; do
    [[ -d $D/$sub ]] && printf '  %-16s %5d PDFs\n' "$sub" "$(find "$D/$sub" -name '*.pdf' | wc -l)"
done
echo "Next: python scripts/eval_adcdnet_pages.py --config configs/adcdnet_eval.yaml --tag v4 \\"
echo "        --data $D/genuine $D/forged $D/genuine_raster $D/forged_raster ... --resume"
