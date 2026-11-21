"""The ForgeLens web app.

    python -m forgelens.app.server --fusion experiments/results/fusion_final-ft6/model.pkl \\
        --templates experiments/templates_dgx.json --image-config configs/adcdnet_ft6.yaml

then open http://localhost:8000 (on the DGX: ``ssh -L 8000:localhost:8000 srmist32@172.16.0.32``
from your laptop first). The server listens on this machine only.

Privacy: an upload is written to a private temporary folder, examined, and deleted before the
response is sent. Nothing is logged about its contents; the access log is off.
"""


import argparse
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from .engine import Engine, Settings

STATIC = Path(__file__).parent / "static"
MAX_BYTES = 40 * 1024 * 1024
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}


def _as_pdf(src: Path) -> Path:
    """Images (a screenshot, a photo) are examined as a one-page PDF, as in the evaluation."""
    if src.suffix.lower() not in IMAGE_TYPES:
        return src
    import pymupdf

    out = src.with_suffix(".pdf")
    img = pymupdf.open(src)
    r = img[0].rect
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=595 * r.height / r.width)
        page.insert_image(page.rect, filename=str(src))
        doc.save(out)
    return out


def create_app(engine: Engine):
    from fastapi import FastAPI, File, Form, UploadFile
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="ForgeLens", docs_url=None, redoc_url=None)

    @app.get("/api/status")
    def status():
        return engine.capabilities()

    # A plain function: FastAPI runs it in a worker thread, so a long examination never
    # blocks the server.
    @app.post("/api/analyze")
    def analyze(file: Annotated[UploadFile, File()], password: Annotated[str, Form()] = "",
                bank: Annotated[str, Form()] = ""):
        suffix = Path(file.filename or "upload.pdf").suffix.lower() or ".pdf"
        if suffix not in IMAGE_TYPES | {".pdf"}:
            return JSONResponse({"error": "type", "message": "Choose a PDF, PNG or JPEG file."},
                                status_code=400)
        tmp = Path(tempfile.mkdtemp(prefix="forgelens_"))
        try:
            src = tmp / f"upload{suffix}"
            size = 0
            with open(src, "wb") as fh:
                while chunk := file.file.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        return JSONResponse({"error": "size", "message": "Files up to 40 MB "
                                             "can be examined."}, status_code=413)
                    fh.write(chunk)
            result = engine.analyze(_as_pdf(src), password or None, bank or None,
                                    name=file.filename)
            code = 400 if "error" in result else 200
            return JSONResponse(result, status_code=code)
        except Exception:  # noqa: BLE001 - never echo the file's contents in an error
            return JSONResponse({"error": "failed", "message": "The examination failed on this "
                                 "file. Try another copy of the statement."}, status_code=500)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--fusion", type=Path, help="model.pkl from scripts/fuse_signals.py")
    p.add_argument("--templates", type=Path, help="profiles from scripts/fit_templates.py")
    p.add_argument("--image-config", type=Path, help="image-model YAML, e.g. configs/adcdnet_ft6.yaml")
    p.add_argument("--profiles", type=Path, help="bank profiles from scripts/eval_real.py")
    p.add_argument("--no-ocr", action="store_true")
    p.add_argument("--device", default="cuda")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args(argv)
    import uvicorn

    engine = Engine(Settings(fusion_model=args.fusion, templates=args.templates,
                             image_config=args.image_config, profiles=args.profiles,
                             ocr=not args.no_ocr, device=args.device))
    print("ForgeLens:", ", ".join(f"{k}={v}" for k, v in engine.capabilities().items()))
    uvicorn.run(create_app(engine), host=args.host, port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
