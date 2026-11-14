#!/usr/bin/env bash
# Make the OCR masks and path lists the four cross-domain test sets need, in a separate
# PaddleOCR environment (~/venvs/paddleocr) so Paddle cannot disturb the PyTorch one.
# Runs on the CPU: Paddle's GPU builds come from paddlepaddle.org.cn, which the DGX may not
# reach. Run it inside tmux; it resumes where it stopped.
#
#   tmux new -s ocr
#   bash scripts/make_ocr_masks.sh                 # all four sets
#   bash scripts/make_ocr_masks.sh --limit 5       # a quick test first
#
# Options after the script name go to scripts/make_ocr_masks.py (--root, --datasets, ...).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${PADDLE_VENV:-$HOME/venvs/paddleocr}"
PYTHON_VERSION="${PYTHON_VERSION:-3.10.14}"
LOG="$HOME/forgelens_ocr.log"
exec > >(tee -a "$LOG") 2>&1

if [[ ! -x $VENV/bin/python ]]; then
    export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
    export PATH="$PYENV_ROOT/bin:$PATH"
    py="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/python"
    [[ -x $py ]] || py="$(command -v python3)"
    echo "==> creating $VENV with $py"
    "$py" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
if ! python -c "import paddleocr, paddle" 2>/dev/null; then
    echo "==> installing PaddlePaddle 3 (CPU) and PaddleOCR 3 (about 1 GB)"
    python -m pip install --quiet --upgrade pip
    python -m pip install "paddlepaddle>=3.0,<4" "paddleocr>=3.0,<4" \
        "opencv-python-headless<4.11" tqdm
fi
python -c "import paddle; print('  paddle', paddle.__version__)"
# The detection model comes from Hugging Face (the DGX reaches it; Baidu's hosts may not).
export PADDLE_PDX_MODEL_SOURCE="${PADDLE_PDX_MODEL_SOURCE:-huggingface}"
# Paddle uses every core by default; leave some for the other users of the server.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-16}"
echo "==> making masks ($(date)); log: $LOG"
python "$REPO/scripts/make_ocr_masks.py" "$@"
