#!/usr/bin/env bash
# Download everything Phase 1 needs onto the DGX (or any Linux machine), into ~/forgelens-data,
# laid out the way configs/adcdnet_eval.example.yaml expects. Run it inside tmux: on a slow
# link this takes many hours. Safe to run again: finished items are skipped, and Hugging Face
# and Google Drive downloads resume where they stopped.
#
#   tmux new -s data
#   source ~/venvs/forgelens/bin/activate
#   bash scripts/download_data.sh                       # everything, smallest first
#   bash scripts/download_data.sh adcdnet doctamper     # only some items
#   bash scripts/download_data.sh --check               # what is there, what is missing
#
# Items, in the order they run:
#   doctamper-meta  qt_table.pk and the JPEG records (pks/) from the DocTamper GitHub repo
#   adcdnet         ADCD-Net checkpoint, DocRes checkpoint, DocTamper OCR masks (Google Drive)
#   cross-domain    T-SROIE, OSTF, TPIC-13, RTM test sets (Hugging Face, Doc Protocol)
#   doctamper       DocTamper LMDBs (Kaggle; needs ~/.kaggle/kaggle.json)
#   aiforge         AIForge-Doc v1 (Hugging Face, gated: needs your token and granted access)
#
# Accounts: `hf auth login` (or huggingface-cli login) for Hugging Face; a Kaggle API token in
# ~/.kaggle/kaggle.json (kaggle.com -> Settings -> API -> Create New Token, then chmod 600).
# If an archive asks for a password (DocTamper's licence), it is asked for here and never saved.
# Archives are deleted once unpacked, to save space; KEEP_ARCHIVES=1 keeps them.
# Licences: DocTamper and AIForge-Doc are non-commercial only; do not redistribute them.

set -uo pipefail

DATA="${FORGELENS_DATA:-$HOME/forgelens-data}"
LOG="$HOME/forgelens_download.log"
ADCD_GDRIVE_ID="1-5BU3Bavs6SGJpaByua_FhDuUJGoo-iS"
DOC_PROTOCOL_REPO="Jason37437/Doc-Protocol-Data"
AIFORGE_REPO="Scam-AI/AIForge-Doc-v1"
KAGGLE_DOCTAMPER="dinmkeljiame/doctamper"
ALL=(doctamper-meta adcdnet cross-domain doctamper aiforge)

mkdir -p "$DATA"
exec 3>&1 4>&2
exec > >(tee -a "$LOG") 2>&1
step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '  ✓ %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*"; }
failed=()

archive_kind() {  # zip, tar.gz, 7z, or nothing
    python - "$1" <<'EOF'
import sys
import tarfile
import zipfile

p = sys.argv[1]
if zipfile.is_zipfile(p):
    print("zip")
elif tarfile.is_tarfile(p):
    print("tar.gz")
elif open(p, "rb").read(6) == b"7z\xbc\xaf\x27\x1c":
    print("7z")
EOF
}

zip_encrypted() {  # true if any member of the zip needs a password
    python -c 'import sys, zipfile; sys.exit(0 if any(i.flag_bits & 1 for i in zipfile.ZipFile(sys.argv[1]).infolist()) else 1)' "$1"
}

need_py() {  # install a Python package into the active environment if missing
    python -c "import $1" 2>/dev/null || python -m pip install --quiet "$2"
}

unpack() {  # unpack <archive> <into>: zip (asks for a password if needed), tar, or 7z
    local archive=$1 into=$2
    mkdir -p "$into"
    case "$archive" in
        *.zip)
            if ! zip_encrypted "$archive"; then
                unzip -q -n "$archive" -d "$into"
                return
            fi
            local pw tries
            for tries in 1 2 3; do
                read -r -s -p "  password for $(basename "$archive") (not saved): " pw </dev/tty
                echo
                # unzip cannot open AES-encrypted zips (made by 7-Zip or WinRAR); 7z can
                if unzip -q -n -P "$pw" "$archive" -d "$into" 2>/dev/null \
                    || { command -v 7z >/dev/null && 7z x -aos -p"$pw" "-o$into" "$archive" >/dev/null; }
                then
                    unset pw; return 0
                fi
                warn "wrong password, or an AES zip without 7z installed (attempt $tries of 3)"
            done
            unset pw; return 1 ;;
        *.tar|*.tar.gz|*.tgz) tar xf "$archive" -C "$into" ;;
        *.7z) command -v 7z >/dev/null || need_py py7zr py7zr
              if command -v 7z >/dev/null; then 7z x -aos "-o$into" "$archive" >/dev/null
              else python -m py7zr x "$archive" "$into"; fi ;;
        *) warn "do not know how to unpack $archive"; return 1 ;;
    esac
}

tidy() {  # delete downloaded archives once their contents are in place (KEEP_ARCHIVES=1 keeps)
    [[ ${KEEP_ARCHIVES:-0} == 1 ]] && return
    find "$1" -type f \( -name '*.zip' -o -name '*.7z' -o -name '*.tar' -o -name '*.tar.gz' \
        -o -name '*.tgz' \) -delete 2>/dev/null
    ok "removed the downloaded archives to save space"
}

# ------------------------------------------------------------------ items

doctamper_meta() {
    local dst="$DATA/DocTamper/exp_data"
    if [[ -f $dst/qt_table.pk && -d $dst/pks ]]; then ok "already there: $dst"; return; fi
    local repo="$DATA/.src/DocTamper"
    [[ -d $repo/.git ]] || git clone -q --depth 1 https://github.com/qcf-568/DocTamper.git "$repo" \
        || return 1
    mkdir -p "$dst"
    cp "$repo/qt_table.pk" "$dst/" && cp -r "$repo/pks" "$dst/" || return 1
    ok "qt_table.pk and $(ls "$dst/pks" | wc -l) JPEG record files in $dst"
}

adcdnet() {
    local dst="$DATA/adcdnet"
    if [[ -f $dst/ADCDNet.pth && -f $dst/docres.pkl && -d $dst/DocTamperOCR ]]; then
        ok "already there: $dst"; return
    fi
    local x="$dst/.download/x"
    if [[ ! -d $x ]]; then
        need_py gdown gdown || return 1
        mkdir -p "$dst/.download"
        local out="$dst/.download/adcdnet_data"
        python -m gdown --continue "$ADCD_GDRIVE_ID" -O "$out" || {
            warn "Google Drive refused or is unreachable. Download it on another machine from"
            warn "https://drive.google.com/file/d/$ADCD_GDRIVE_ID and copy it to $out"
            return 1
        }
        local kind  # gdown's file name says nothing; find out what it is
        kind=$(archive_kind "$out")
        [[ -n $kind ]] || { warn "the Google Drive file is not an archive: $(head -c 200 "$out" | tr -cd '[:print:]')"; return 1; }
        mv "$out" "$out.$kind"
        unpack "$out.$kind" "$x" || return 1
    fi
    # The archive nests further archives (DocTamperOCR.zip inside a folder): unpack those too.
    local z
    while IFS= read -r -d '' z; do
        [[ -e $z.unpacked ]] || { unpack "$z" "$(dirname "$z")" && touch "$z.unpacked"; } || return 1
    done < <(find "$x" -type f \( -name '*.zip' -o -name '*.7z' -o -name '*.tar*' \) -print0)
    # Put each piece at the top of $dst, wherever and however (letter case) the archive has it.
    local f found missing=()
    for f in ADCDNet.pth docres.pkl; do
        [[ -f $dst/$f ]] && continue
        found=$(find "$x" -type f -iname "$f" -print -quit)
        if [[ -n $found ]]; then mv "$found" "$dst/$f"; else missing+=("$f"); fi
    done
    if [[ ! -d $dst/DocTamperOCR ]]; then
        found=$(find "$x" -type d -iname DocTamperOCR -print -quit)
        if [[ -n $found ]]; then mv "$found" "$dst/DocTamperOCR"; else missing+=(DocTamperOCR/); fi
    fi
    [[ -d $dst/DocTamperOCR ]] && ok "DocTamperOCR/ ($(ls "$dst/DocTamperOCR" | tr '\n' ' ')) in $dst"
    for f in ADCDNet.pth docres.pkl; do [[ -f $dst/$f ]] && ok "$f in $dst"; done
    if (( ${#missing[@]} )); then
        warn "the Google Drive archive has no ${missing[*]}. It holds:"
        find "$x" -maxdepth 3 -not -name '*.pkl' | sed "s|$x|    |" | head -15
        warn "get the missing files from the ADCD-Net authors (README or GitHub issues) and put"
        warn "them in $dst"
        return 1
    fi
    tidy "$dst/.download"
}

hf_download() {  # hf_download <dataset repo> <local dir> [pattern]
    need_py huggingface_hub huggingface_hub || return 1
    python - "$@" <<'EOF'
import sys
from huggingface_hub import snapshot_download
from huggingface_hub.errors import GatedRepoError, RepositoryNotFoundError

repo, local, *pattern = sys.argv[1:]
try:
    path = snapshot_download(repo, repo_type="dataset", local_dir=local,
                             allow_patterns=pattern or None, max_workers=4)
except GatedRepoError:
    sys.exit(f"  ! {repo} is gated: log in with `hf auth login` using the account that was "
             "granted access")
except RepositoryNotFoundError:
    sys.exit(f"  ! {repo} not found, or your token cannot see it (log in with `hf auth login`)")
print(f"  downloaded {repo} into {path}")
EOF
}

cross_domain() {
    local dst="$DATA/cutted_datasets_fakes"
    if [[ -d $dst/OSTF_test && -d $dst/T-SROIE_test ]]; then ok "already there: $dst"; return; fi
    hf_download "$DOC_PROTOCOL_REPO" "$DATA/.download/doc-protocol" || return 1
    local zip; zip=$(find "$DATA/.download/doc-protocol" -name 'cutted_datasets_fakes*.zip' -print -quit)
    [[ -n $zip ]] || { warn "cutted_datasets_fakes.zip not found in the download"; return 1; }
    unpack "$zip" "$DATA/.download/doc-protocol/x" || return 1
    local inner; inner=$(find "$DATA/.download/doc-protocol/x" -type d -name OSTF_test -print -quit)
    mv "$(dirname "$inner")" "$dst" || return 1
    ok "$(ls "$dst" | tr '\n' ' ') in $dst"
    tidy "$DATA/.download/doc-protocol"
    local missing=0 d
    for d in "$dst"/*_test; do [[ -d $d/ocr ]] || missing=1; done
    if (( missing )); then
        warn "some sets have no ocr/ folder: their OCR masks must be made with upstream's"
        warn "seg_char.py (PaddleOCR) before build_path_pkl.py; ask Claude for that step"
    fi
}

doctamper() {
    local dst="$DATA/DocTamper/DocTamperV1"
    if [[ -f $dst/DocTamperV1-TestingSet/data.mdb && -f $dst/DocTamperV1-FCD/data.mdb \
          && -f $dst/DocTamperV1-SCD/data.mdb ]]; then ok "already there: $dst"; return; fi
    if [[ ! -f $HOME/.kaggle/kaggle.json && -z ${KAGGLE_KEY:-} ]]; then
        warn "no Kaggle token: create one at kaggle.com -> Settings -> API -> Create New Token,"
        warn "copy kaggle.json to ~/.kaggle/ and run: chmod 600 ~/.kaggle/kaggle.json"
        return 1
    fi
    need_py kaggle kaggle || return 1
    local dl="$DATA/.download/doctamper"
    mkdir -p "$dl"
    if ! ls "$dl"/*.zip >/dev/null 2>&1; then
        if command -v kaggle >/dev/null; then
            kaggle datasets download -d "$KAGGLE_DOCTAMPER" -p "$dl" || return 1
        else
            python -m kaggle datasets download -d "$KAGGLE_DOCTAMPER" -p "$dl" || return 1
        fi
    fi
    local z
    for z in "$dl"/*.zip; do unpack "$z" "$dl/x" || return 1; done
    # Nested archives (one per split) are common; unpack those too.
    find "$dl/x" -type f \( -name '*.zip' -o -name '*.7z' -o -name '*.tar*' \) -print0 |
        while IFS= read -r -d '' z; do unpack "$z" "$(dirname "$z")" || exit 1; done || return 1
    mkdir -p "$dst"
    local found=0 mdb dir name
    while IFS= read -r mdb; do
        dir=$(dirname "$mdb"); name=$(basename "$dir")
        case "$name" in
            *Train*) name=DocTamperV1-TrainingSet ;; *Test*) name=DocTamperV1-TestingSet ;;
            *FCD*) name=DocTamperV1-FCD ;; *SCD*) name=DocTamperV1-SCD ;; *) continue ;;
        esac
        [[ -e $dst/$name ]] || ln -s "$dir" "$dst/$name"
        found=$((found + 1))
    done < <(find "$dl/x" -name data.mdb)
    (( found )) || { warn "no LMDB (data.mdb) folders found in the Kaggle download"; return 1; }
    ok "$(ls "$dst" | tr '\n' ' ') in $dst (links into $dl/x)"
    tidy "$dl"
}

aiforge() {
    local dst="$DATA/AIForge-Doc-v1"
    if [[ -f $dst/.complete ]]; then ok "already there: $dst"; return; fi
    hf_download "$AIFORGE_REPO" "$dst" && touch "$dst/.complete"
}

check() {
    step "What is in $DATA"
    local p
    for p in DocTamper/exp_data/qt_table.pk DocTamper/exp_data/pks adcdnet/ADCDNet.pth \
             adcdnet/docres.pkl adcdnet/DocTamperOCR DocTamper/DocTamperV1/DocTamperV1-TestingSet \
             DocTamper/DocTamperV1/DocTamperV1-FCD DocTamper/DocTamperV1/DocTamperV1-SCD \
             cutted_datasets_fakes/OSTF_test AIForge-Doc-v1/.complete; do
        if [[ -e $DATA/$p ]]; then ok "${p%/.complete} ($(du -shL "$DATA/${p%/.complete}" 2>/dev/null | cut -f1))"
        else warn "missing: ${p%/.complete}"; fi
    done
    if [[ -e $DATA/DocTamper/DocTamperV1/DocTamperV1-TrainingSet ]]; then
        ok "DocTamper/DocTamperV1/DocTamperV1-TrainingSet (for fine-tuning)"
    else
        echo "  - DocTamperV1-TrainingSet not there (needed only for fine-tuning, not for evaluation)"
    fi
    df -h "$DATA" | tail -1 | awk '{print "  free space: " $4}'
}

# ------------------------------------------------------------------ main

if [[ ${1:-} == --check ]]; then check; exit 0; fi
items=("$@")
(( ${#items[@]} )) || items=("${ALL[@]}")
[[ -n ${VIRTUAL_ENV:-} ]] || warn "no virtual environment active; run: source ~/venvs/forgelens/bin/activate"
echo "Downloading into $DATA ($(date)); log: $LOG"
for item in "${items[@]}"; do
    step "$item"
    case "$item" in
        doctamper-meta) doctamper_meta ;;
        adcdnet) adcdnet ;;
        cross-domain) cross_domain ;;
        doctamper) doctamper ;;
        aiforge) aiforge ;;
        *) warn "unknown item $item (choose from: ${ALL[*]})"; false ;;
    esac || { failed+=("$item"); warn "$item did not finish; the rest continue"; }
done
check
if (( ${#failed[@]} )); then
    echo; echo "Not finished: ${failed[*]}. Fix what is shown above and run again for those."
    exit 1
fi
echo; echo "All done. Next: cp configs/adcdnet_eval.example.yaml configs/adcdnet_eval.yaml"
