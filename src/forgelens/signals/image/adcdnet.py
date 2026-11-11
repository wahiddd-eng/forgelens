"""Run the official ADCD-Net code (``third_party/ADCD-Net``) without editing it.

The upstream modules read their settings from a module named ``cfg``. ``configure`` imports
that module and overwrites the paths and evaluation settings in memory, so the submodule
stays at its pinned commit and every run states its settings in one place.

``preflight`` checks everything a long run depends on before any GPU time is spent: the
Python packages, the checkpoint files, the dataset layout, the OCR masks and whether the
installed PyTorch has kernels for the GPU. Missing OCR masks matter most: upstream silently
treats a missing mask as "no text", which lowers the scores without any error.

PyTorch and the upstream dependencies are imported only inside functions, so this module
can be imported (and ``preflight`` run) on a machine without them.
"""

from __future__ import annotations

import hashlib
import importlib
import pickle
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# The seven test sets of the ForensicHub Doc Protocol, in upstream's names.
DOCTAMPER_SETS = ("FCD", "SCD", "TestingSet")
CROSS_DOMAIN_SETS = ("T-SROIE_test", "OSTF_test", "Tampered-IC13_test",
                     "RealTextManipulation_test")
DOC_PROTOCOL = DOCTAMPER_SETS + CROSS_DOMAIN_SETS

# Short names used in the paper's Table 1.
SHORT_NAMES = {"FCD": "FCD", "SCD": "SCD", "TestingSet": "Test", "T-SROIE_test": "T-SROIE",
               "OSTF_test": "OSTF", "Tampered-IC13_test": "TPIC-13",
               "RealTextManipulation_test": "RTM"}

# ADCD-Net's published per-image F1 (ICCV 2025, Table 1; upstream README, fig/docpro.png).
PUBLISHED_F1 = {"FCD": 0.803, "SCD": 0.718, "TestingSet": 0.791, "T-SROIE_test": 0.623,
                "OSTF_test": 0.441, "Tampered-IC13_test": 0.579,
                "RealTextManipulation_test": 0.159}
PUBLISHED_AVERAGES = {"in_domain": 0.771, "cross_domain": 0.450, "all": 0.588}

# import name -> pip name
PACKAGES = {"torch": "torch", "torchvision": "torchvision", "albumentations": "albumentations",
            "jpeg2dct": "jpeg2dct", "efficientnet_pytorch": "efficientnet_pytorch",
            "einops": "einops", "lmdb": "lmdb", "cv2": "opencv-python-headless", "six": "six",
            "PIL": "pillow", "numpy": "numpy"}
UPSTREAM_ALBUMENTATIONS = "2.0.8"


def resolve_datasets(names: list[str]) -> list[str]:
    """Map user-facing names (``FCD``, ``Test``, ``RTM``, ``in-domain``, ``all``…) to
    upstream dataset names, keeping the Doc Protocol order and dropping duplicates."""
    lookup = {n.lower(): n for n in DOC_PROTOCOL}
    lookup.update({s.lower(): n for n, s in SHORT_NAMES.items()})
    lookup.update({n.lower().removesuffix("_test"): n for n in CROSS_DOMAIN_SETS})
    groups = {"all": DOC_PROTOCOL, "in-domain": DOCTAMPER_SETS,
              "cross-domain": CROSS_DOMAIN_SETS}
    chosen: set[str] = set()
    for name in names:
        key = name.strip().lower()
        if key in groups:
            chosen.update(groups[key])
        elif key in lookup:
            chosen.add(lookup[key])
        else:
            raise ValueError(f"unknown dataset {name!r}; choose from "
                             f"{', '.join(SHORT_NAMES.values())}, in-domain, cross-domain, all")
    return [n for n in DOC_PROTOCOL if n in chosen]


@dataclass
class Paths:
    """Where the checkpoints and test data are.

    ``doctamper_root`` follows upstream's layout: ``DocTamperV1/DocTamperV1-<set>/`` (LMDB)
    and ``exp_data/qt_table.pk`` plus ``exp_data/pks/`` (JPEG records from the DocTamper
    repository). ``ocr_root`` holds ``<set>/char_seg/*.pkl`` (``DocTamperOCR`` in the
    ADCD-Net download). ``pkl_dir`` holds ``<set>.pkl`` path lists for the cross-domain sets,
    made by upstream's ``build_path_pkl.py``.
    """

    upstream: Path
    ckpt: Path
    docres: Path
    doctamper_root: Path | None = None
    ocr_root: Path | None = None
    pkl_dir: Path | None = None
    qt_path: Path | None = None
    jpeg_record_dir: Path | None = None

    def __post_init__(self):
        for name, value in vars(self).items():
            if value is not None:
                setattr(self, name, Path(value).expanduser())
        if self.doctamper_root is not None:
            self.ocr_root = self.ocr_root or self.doctamper_root / "DocTamperData"
            self.qt_path = self.qt_path or self.doctamper_root / "exp_data" / "qt_table.pk"
            self.jpeg_record_dir = self.jpeg_record_dir or self.doctamper_root / "exp_data" / "pks"
        if self.qt_path is None:
            raise ValueError("give doctamper_root or qt_path (qt_table.pk is needed for every set)")

    def lmdb_dir(self, name: str) -> Path:
        return self.doctamper_root / "DocTamperV1" / f"DocTamperV1-{name}"

    def ocr_dir(self, name: str) -> Path:
        return self.ocr_root / name / "char_seg"

    def jpeg_record(self, name: str, min_qf: int) -> Path:
        return self.jpeg_record_dir / f"DocTamperV1-{name}_{min_qf}.pk"


@dataclass
class Settings:
    """Evaluation settings; the defaults are the Doc Protocol's."""

    min_qf: int = 75  # selects the JPEG record file
    compression: str = "protocol"  # "protocol": DocTamper's recorded JPEG QFs; "none": QF 100
    shift_1p: bool = False  # robustness test: shift DocTamper images by one pixel
    val_max_size: int = 512  # cross-domain images are resized to this longest side


# ---------------------------------------------------------------- checks

def missing_packages() -> list[str]:
    """pip names of the packages the upstream code needs that cannot be imported."""
    missing = []
    for module, pip_name in PACKAGES.items():
        try:
            importlib.import_module("jpeg2dct.numpy" if module == "jpeg2dct" else module)
        except Exception:  # noqa: BLE001 - a broken install fails in many ways
            missing.append(pip_name)
    return missing


def _lmdb_samples(path: Path) -> int | None:
    try:
        import lmdb
    except ImportError:
        return None
    env = lmdb.open(str(path), readonly=True, lock=False, readahead=False, meminit=False)
    try:
        with env.begin(write=False) as txn:
            value = txn.get(b"num-samples")
        return int(value) if value is not None else None
    finally:
        env.close()


def _check_doctamper(paths: Paths, name: str, settings: Settings, problems: list[str],
                     notes: list[str], allow_missing_ocr: bool) -> None:
    if paths.doctamper_root is None:
        problems.append(f"{name}: --doctamper-root is not set")
        return
    lmdb_dir = paths.lmdb_dir(name)
    if not (lmdb_dir / "data.mdb").exists():
        problems.append(f"{name}: no LMDB at {lmdb_dir} (expected data.mdb inside)")
        return
    samples = _lmdb_samples(lmdb_dir)
    if settings.compression == "protocol" and not paths.jpeg_record(name, settings.min_qf).exists():
        problems.append(f"{name}: JPEG record {paths.jpeg_record(name, settings.min_qf)} not found "
                        "(the pks folder from the DocTamper repository)")
    ocr_dir = paths.ocr_dir(name)
    found = len(list(ocr_dir.glob("*.pkl"))) if ocr_dir.is_dir() else 0
    if found == 0:
        hint = ""
        if (paths.ocr_root / name).is_dir() and any((paths.ocr_root / name).glob("*.pkl")):
            hint = f"; the masks are directly in {paths.ocr_root / name}, move them into char_seg/"
        message = (f"{name}: no OCR masks in {ocr_dir}{hint}. Without them upstream scores "
                   "every image as if it had no text, which silently lowers F1")
        (notes if allow_missing_ocr else problems).append(message)
    elif samples is not None and found < samples:
        notes.append(f"{name}: OCR masks for {found} of {samples} images; the rest are treated "
                     "as having no text (upstream does the same)")
    if samples is not None:
        notes.append(f"{name}: {samples} images")


def _check_cross_domain(paths: Paths, name: str, problems: list[str], notes: list[str]) -> None:
    if paths.pkl_dir is None:
        problems.append(f"{name}: --pkl-dir is not set (run upstream build_path_pkl.py)")
        return
    pkl = paths.pkl_dir / f"{name}.pkl"
    if not pkl.exists():
        problems.append(f"{name}: path list {pkl} not found (run upstream build_path_pkl.py)")
        return
    with open(pkl, "rb") as f:
        entries = pickle.load(f)  # written by our own build_path_pkl run
    gone = [p for entry in entries for p in entry if not Path(p).exists()]
    if gone:
        problems.append(f"{name}: {len(gone)} files listed in {pkl.name} do not exist, e.g. "
                        f"{gone[0]}. The list holds absolute paths: rebuild it on this machine")
    notes.append(f"{name}: {len(entries)} images")


def gpu_report(device: str) -> tuple[list[str], list[str]]:
    """Problems and notes about the GPU and whether this PyTorch build supports it."""
    import torch

    if not device.startswith("cuda"):
        return [], [f"device {device}: no GPU; expect a full run to take days"]
    if not torch.cuda.is_available():
        return [f"device {device}: CUDA is not available to PyTorch {torch.__version__}"], []
    index = torch.device(device).index or 0
    if index >= torch.cuda.device_count():
        return [f"device {device}: only {torch.cuda.device_count()} GPU(s) visible"], []
    props = torch.cuda.get_device_properties(index)
    arch = f"sm_{props.major}{props.minor}"
    built = torch.cuda.get_arch_list()
    note = (f"GPU {index}: {props.name}, {props.total_memory / 2**30:.0f} GB, {arch}; PyTorch "
            f"{torch.__version__} (CUDA {torch.version.cuda})")
    if built and arch not in built and f"compute_{props.major}{props.minor}" not in built:
        problem = (f"PyTorch {torch.__version__} has no kernels for {props.name} ({arch}); "
                   f"built for {', '.join(built)}. RTX 50-series GPUs need PyTorch 2.7+ with "
                   "CUDA 12.8+")
        return [problem], [note]
    return [], [note]


def preflight(paths: Paths, datasets: list[str], settings: Settings, device: str = "cuda",
              allow_missing_ocr: bool = False) -> tuple[list[str], list[str]]:
    """Return (problems, notes). Any problem means a run would fail or give wrong numbers."""
    problems: list[str] = []
    notes: list[str] = []
    for f in ("cfg.py", "ds.py", "model/model.py"):
        if not (paths.upstream / f).exists():
            problems.append(f"upstream code not found at {paths.upstream} (missing {f}); run "
                            "git submodule update --init")
            break
    missing = missing_packages()
    if missing:
        problems.append("missing Python packages: " + " ".join(missing))
    else:
        import albumentations

        if albumentations.__version__ != UPSTREAM_ALBUMENTATIONS:
            notes.append(f"albumentations {albumentations.__version__}; upstream pins "
                         f"{UPSTREAM_ALBUMENTATIONS}")
    for label, path in (("checkpoint", paths.ckpt), ("DocRes checkpoint", paths.docres),
                        ("JPEG quantisation tables", paths.qt_path)):
        if not path.is_file():
            problems.append(f"{label} not found: {path}")
    for name in datasets:
        if name in DOCTAMPER_SETS:
            _check_doctamper(paths, name, settings, problems, notes, allow_missing_ocr)
        else:
            _check_cross_domain(paths, name, problems, notes)
    if "torch" not in missing:
        gpu_problems, gpu_notes = gpu_report(device)
        problems += gpu_problems
        notes += gpu_notes
    return problems, notes


# ---------------------------------------------------------------- running upstream code

def configure(paths: Paths, settings: Settings):
    """Import upstream's ``cfg`` module and point it at our paths and settings."""
    root = str(paths.upstream)
    if root not in sys.path:
        sys.path.insert(0, root)
    cfg = importlib.import_module("cfg")
    if Path(cfg.__file__).resolve().parent != paths.upstream.resolve():
        raise RuntimeError(f"imported a different cfg module: {cfg.__file__}")
    cfg.mode = "val"
    cfg.ckpt = str(paths.ckpt)
    cfg.docres_ckpt_path = str(paths.docres)
    cfg.qt_path = str(paths.qt_path)
    if paths.doctamper_root is not None:
        cfg.root = str(paths.doctamper_root)
        cfg.data_root = str(paths.doctamper_root / "DocTamperV1")
        cfg.ocr_root = str(paths.ocr_root)
        cfg.jpeg_record_dir = str(paths.jpeg_record_dir)
    if paths.pkl_dir is not None:
        cfg.pkl_dir = str(paths.pkl_dir)
    cfg.min_qf = settings.min_qf
    cfg.multi_jpeg_val = settings.compression == "protocol"
    cfg.jpeg_record = False  # with multi_jpeg_val off, compress once at QF 100
    cfg.shift_1p = settings.shift_1p
    cfg.val_aug = None
    cfg.val_max_size = settings.val_max_size
    return cfg


def load_model(paths: Paths, device: str, allow_missing_keys: bool = False):
    """Build ADCD-Net and load the checkpoint. Returns (model, info).

    Upstream loads with ``strict=False`` and only logs missing keys; here a missing key is an
    error, because it means part of the network keeps random weights.
    """
    import torch
    from model.model import ADCDNet  # upstream, importable after configure()

    model = ADCDNet()  # also loads the DocRes backbone from cfg.docres_ckpt_path
    state = torch.load(paths.ckpt, map_location="cpu", weights_only=True)
    state = state.get("model", state)
    state = {k.removeprefix("module."): v for k, v in state.items()}
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing and not allow_missing_keys:
        raise RuntimeError(f"{len(missing)} weights missing from {paths.ckpt}, e.g. "
                           f"{missing[:3]}; is this the ADCD-Net checkpoint?")
    model.to(device).eval()
    return model, {"missing_keys": list(missing), "unexpected_keys": list(unexpected),
                   "parameters": sum(p.numel() for p in model.parameters())}


def build_dataset(name: str):
    """Upstream's evaluation dataset for ``name`` (call ``configure`` first)."""
    from ds import DtdValDs, GeneralValDs

    return DtdValDs(name) if name in DOCTAMPER_SETS else GeneralValDs(name)


def collate(batch):
    """Upstream's padding collate, after setting aside items that failed to load.

    Returns ``(padded, failures)``; ``padded`` is None when every item failed.
    """
    from ds import pad_collate

    ok = [item for item in batch if "error" not in item]
    failures = [item for item in batch if "error" in item]
    return (pad_collate(ok) if ok else None), failures


def worker_init(_worker_id: int) -> None:
    """Reopen the LMDB environment in each data-loading process: an environment opened
    before the fork must not be used in the child."""
    import lmdb
    import torch

    dataset = torch.utils.data.get_worker_info().dataset
    inner = getattr(dataset, "dataset", dataset)
    if hasattr(inner, "lmdb"):
        inner.lmdb = lmdb.open(inner.lmdb.path(), max_readers=64, readonly=True, lock=False,
                               readahead=False, meminit=False)


class Guarded:
    """Wrap a dataset so one unreadable image is recorded instead of ending the run."""

    def __init__(self, dataset, indices=None):
        self.dataset = dataset
        self.indices = list(range(len(dataset))) if indices is None else list(indices)

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, i):
        index = self.indices[i]
        try:
            return self.dataset[index]
        except Exception as exc:  # noqa: BLE001 - recorded per image and reported
            return {"error": f"{type(exc).__name__}: {exc}", "img_name": f"{index:06d}"}


# ---------------------------------------------------------------- provenance

def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def upstream_commit(upstream: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def environment() -> dict:
    """Versions of the deep-learning stack and the GPU used."""
    from importlib import metadata

    import torch

    info = {"torch": torch.__version__, "cuda": torch.version.cuda,
            "cudnn": torch.backends.cudnn.version(), "gpu": None}
    for pip_name in ("torchvision", "albumentations", "jpeg2dct", "efficientnet_pytorch",
                     "numpy", "opencv-python-headless"):
        try:
            info[pip_name] = metadata.version(pip_name)
        except metadata.PackageNotFoundError:
            info[pip_name] = None
    if torch.cuda.is_available():
        info["gpu"] = torch.cuda.get_device_name(torch.cuda.current_device())
    return info
