#!/usr/bin/env bash
# Set up the ForgeLens + ADCD-Net environment on the SRMIST DGX A100 (or any Linux GPU
# machine) without sudo. Safe to run again: finished steps are skipped or repeated quickly.
#
#   cd ~/forgelens && bash scripts/setup_dgx.sh
#
# It
#   1. checks the GPUs and tells you to pick yours with CUDA_VISIBLE_DEVICES;
#   2. gets Python 3.10.14 through pyenv (upstream's version; falls back to pyenv's default);
#   3. creates a virtual environment (default ~/venvs/forgelens);
#   4. installs PyTorch 2.3.0 + torchvision 0.18.0 (CUDA 12.1 wheels) and checks the GPU;
#   5. installs ForgeLens and the packages in requirements-adcdnet.txt;
#   6. builds jpeg2dct, first compiling libjpeg-turbo into the environment if the system has
#      no libjpeg headers (no sudo needed);
#   7. runs `scripts/eval_adcdnet.py --check` if configs/adcdnet_eval.yaml exists.
#
# Settings (environment variables):
#   VENV=~/venvs/forgelens     where to create the environment
#   PYTHON_VERSION=3.10.14     Python to install with pyenv
#   PYTHON_BIN=/path/python    use this interpreter instead of pyenv
#   TORCH_SPEC="torch==2.3.0 torchvision==0.18.0"
#   WHEELS=~/wheels            install from downloaded wheels only (no internet)
#   LIBJPEG_TARBALL=file       libjpeg-turbo source if GitHub cannot be reached
#   FORCE_LOCAL_LIBJPEG=1      build libjpeg-turbo even if the system has the headers
#
# Everything is also written to ~/forgelens_setup.log.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$HOME/venvs/forgelens}"
PYTHON_VERSION="${PYTHON_VERSION:-3.10.14}"
TORCH_SPEC="${TORCH_SPEC:-torch==2.3.0 torchvision==0.18.0}"
LIBJPEG_VERSION="3.0.4"
LOG="$HOME/forgelens_setup.log"

exec 3>&1 4>&2                      # the terminal, for pip's progress bar
exec > >(tee -a "$LOG") 2>&1
step() { printf '\n==> %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*"; }
die()  { printf '\nSETUP STOPPED: %s\n(full log: %s)\n' "$*" "$LOG"; exit 1; }
echo "ForgeLens setup, $(date), repo $REPO"

if [[ $EUID -eq 0 ]]; then
    warn "running as root; on the DGX run this as your own user, never with sudo"
fi

# ------------------------------------------------------------------ 1. GPUs
step "1/7 GPUs"
if command -v nvidia-smi >/dev/null; then
    nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu \
        --format=csv,noheader | sed 's/^/  GPU /'
    gpus=$(nvidia-smi -L | wc -l)
    if [[ $gpus -gt 1 && -z "${CUDA_VISIBLE_DEVICES:-}" ]]; then
        warn "$gpus GPUs are visible; we may use at most 2, whichever are free. Pick them"
        warn "per job:  export CUDA_VISIBLE_DEVICES=\$(bash scripts/free_gpus.sh 2)"
    elif [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
        echo "  CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
    fi
else
    warn "nvidia-smi not found: no NVIDIA driver here, PyTorch will only use the CPU"
fi
df -h "$HOME" | sed 's/^/  /'

# ------------------------------------------------------------------ 2. Python
step "2/7 Python"
if [[ -z "${PYTHON_BIN:-}" ]]; then
    export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
    export PATH="$PYENV_ROOT/bin:$PATH"
    if ! command -v pyenv >/dev/null && [[ -x /home/faculty/utils/install_pyenv.sh ]]; then
        echo "  pyenv not found; running the Centre for AI's installer"
        /home/faculty/utils/install_pyenv.sh
    fi
    command -v pyenv >/dev/null || die "pyenv not found; set PYTHON_BIN=/path/to/python3.10"
    eval "$(pyenv init -)"
    if pyenv install --skip-existing "$PYTHON_VERSION"; then
        PYTHON_BIN="$(pyenv root)/versions/$PYTHON_VERSION/bin/python"
    else
        warn "could not install Python $PYTHON_VERSION (python.org blocked or build tools"
        warn "missing); using pyenv's default instead. PyTorch 2.3 also supports 3.11"
        PYTHON_BIN="$(pyenv which python)"
    fi
fi
"$PYTHON_BIN" - <<'EOF' || die "this Python lacks modules pip or the code needs (see above)"
import importlib.util, sys
print(f"  {sys.executable}: Python {sys.version.split()[0]}")
missing = [m for m in ("ssl", "ctypes", "bz2", "lzma", "sqlite3", "zlib")
           if importlib.util.find_spec(m) is None]
if missing:
    print("  missing standard modules:", ", ".join(missing),
          "(Python was built without their system libraries)")
    sys.exit(1)
if sys.version_info[:2] not in ((3, 10), (3, 11), (3, 12)):
    print("  PyTorch 2.3 needs Python 3.8-3.12"); sys.exit(1)
EOF

# ------------------------------------------------------------------ 3. environment
step "3/7 Virtual environment $VENV"
if [[ ! -x "$VENV/bin/python" ]]; then
    "$PYTHON_BIN" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
PIP=(python -m pip --disable-pip-version-check)
if [[ -n "${WHEELS:-}" ]]; then
    export PIP_NO_INDEX=1 PIP_FIND_LINKS="$WHEELS"
    echo "  offline: installing only from $WHEELS"
elif ! timeout 60 "${PIP[@]}" download --no-deps --quiet -d "$(mktemp -d)" six; then
    die "pip cannot reach the package index. Download the wheels on another machine
  (see requirements-adcdnet.txt) and run again with WHEELS=/path/to/wheels"
fi
"${PIP[@]}" install --quiet --upgrade pip setuptools wheel

# ------------------------------------------------------------------ 4. PyTorch
step "4/7 PyTorch ($TORCH_SPEC)"
# About 3 GB. Written straight to the terminal so pip shows its progress bar (it hides it when
# output goes through tee); pip writes its own full log to $LOG.
echo "  downloading about 3 GB; on a slow connection this takes an hour or more"
# shellcheck disable=SC2086
"${PIP[@]}" install --log "$LOG" $TORCH_SPEC >&3 2>&4
python - <<'EOF'
import torch
print(f"  torch {torch.__version__}, CUDA {torch.version.cuda}, "
      f"{torch.cuda.device_count()} GPU(s) visible")
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        arch = f"sm_{p.major}{p.minor}"
        ok = arch in torch.cuda.get_arch_list()
        print(f"  cuda:{i} {p.name} {p.total_memory / 2**30:.0f} GB {arch}"
              f"{'' if ok else '  <-- NOT SUPPORTED by this PyTorch build'}")
    x = torch.randn(1024, 1024, device="cuda")
    print(f"  matmul on GPU OK ({(x @ x).sum().item():.1f})")
else:
    print("  ! CUDA not available: check the driver (nvidia-smi) and CUDA_VISIBLE_DEVICES")
EOF

# ------------------------------------------------------------------ 5. packages
step "5/7 ForgeLens and ADCD-Net packages"
"${PIP[@]}" install --quiet $(grep -vE '^\s*(#|$)|jpeg2dct' "$REPO/requirements-adcdnet.txt")
"${PIP[@]}" install --quiet -e "$REPO[dev]"  # not [ml]: it pulls opencv-python and newer numpy
if [[ ! -f "$REPO/third_party/ADCD-Net/model/model.py" ]]; then
    echo "  fetching the ADCD-Net submodule"
    git -C "$REPO" submodule update --init || warn "could not fetch the ADCD-Net submodule;
    copy third_party/ADCD-Net from another clone"
fi

# ------------------------------------------------------------------ 6. jpeg2dct
step "6/7 jpeg2dct"
if python -c "import jpeg2dct.numpy" 2>/dev/null; then
    echo "  already installed"
else
    command -v g++ >/dev/null || die "no C++ compiler (g++); ask the Centre for AI for build-essential"
    has_headers=0
    for d in /usr/include /usr/include/x86_64-linux-gnu /usr/local/include; do
        [[ -f $d/jpeglib.h ]] && has_headers=1
    done
    if [[ $has_headers -eq 1 && -z "${FORCE_LOCAL_LIBJPEG:-}" ]]; then
        echo "  system libjpeg headers found"
    else
        echo "  no libjpeg headers: building libjpeg-turbo $LIBJPEG_VERSION into $VENV"
        command -v cmake >/dev/null || "${PIP[@]}" install --quiet cmake
        build="$(mktemp -d)"
        url="https://github.com/libjpeg-turbo/libjpeg-turbo/archive/refs/tags/$LIBJPEG_VERSION.tar.gz"
        if [[ -n "${LIBJPEG_TARBALL:-}" ]]; then
            tar xzf "$LIBJPEG_TARBALL" -C "$build"
        elif curl -fsSL "$url" -o "$build/src.tar.gz" 2>/dev/null \
                || wget -q "$url" -O "$build/src.tar.gz" 2>/dev/null; then
            tar xzf "$build/src.tar.gz" -C "$build"
        elif ! git -c advice.detachedHead=false clone -q --depth 1 --branch "$LIBJPEG_VERSION" \
                https://github.com/libjpeg-turbo/libjpeg-turbo.git \
                "$build/libjpeg-turbo-$LIBJPEG_VERSION"; then
            die "cannot download libjpeg-turbo; get $url elsewhere and run again with
  LIBJPEG_TARBALL=/path/to/it"
        fi
        simd=ON
        command -v nasm >/dev/null || command -v yasm >/dev/null || simd=OFF
        # Static library with position-independent code: jpeg2dct then carries libjpeg
        # inside itself and needs nothing at run time.
        cmake -S "$build"/libjpeg-turbo-* -B "$build/out" -DCMAKE_INSTALL_PREFIX="$VENV" \
            -DCMAKE_INSTALL_LIBDIR=lib -DENABLE_SHARED=OFF -DENABLE_STATIC=ON \
            -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DWITH_SIMD=$simd -DCMAKE_BUILD_TYPE=Release \
            > "$build/cmake.log" || die "libjpeg-turbo configure failed: $build/cmake.log"
        cmake --build "$build/out" -j "$(nproc)" > "$build/build.log" \
            || die "libjpeg-turbo build failed: $build/build.log"
        cmake --install "$build/out" > /dev/null
        # -L (not LIBRARY_PATH) so the linker takes our libjpeg.a before a system
        # libjpeg.so: headers and library must be the same libjpeg version.
        export CPATH="$VENV/include${CPATH:+:$CPATH}"
        export LDFLAGS="-L$VENV/lib${LDFLAGS:+ $LDFLAGS}"
    fi
    "${PIP[@]}" install --no-build-isolation jpeg2dct \
        || die "jpeg2dct did not build; the compiler output is above"
fi
python - <<'EOF'
import io

import numpy as np
from jpeg2dct.numpy import loads
from PIL import Image

buf = io.BytesIO()
Image.fromarray(np.full((64, 64, 3), 128, np.uint8)).save(buf, "JPEG")
y, cb, cr = loads(buf.getvalue())
print(f"  jpeg2dct reads DCT coefficients: Y {y.shape}")
EOF

# ------------------------------------------------------------------ 7. check
step "7/7 ADCD-Net pre-flight check"
config="$REPO/configs/adcdnet_eval.yaml"
if [[ -f $config ]]; then
    python "$REPO/scripts/eval_adcdnet.py" --config "$config" --tag setup --check \
        || warn "fix the problems listed above, then run the check again"
else
    echo "  no $config yet: copy configs/adcdnet_eval.example.yaml, set the paths, and run"
    echo "  python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag dgx --check"
fi

cat <<EOF

Setup finished. In every new terminal:
    source $VENV/bin/activate
Run long jobs inside tmux so they survive a disconnect:
    tmux new -s eval        (detach: Ctrl-b d, return: tmux attach -t eval)
EOF
command -v tmux >/dev/null || warn "tmux is not installed here; ask the Centre for AI, or use screen/nohup"
