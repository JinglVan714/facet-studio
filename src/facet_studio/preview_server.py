"""Tiny local preview server for product_v1 run artifacts.

P1 does not ship a custom frontend; this server lets LibreChat/tool output link
to the rendered reader page and figures.  It serves only `runs/product_v1`.

    PYTHONPATH=src python -m facet_studio.preview_server
    # http://127.0.0.1:8765/runs/<run_id>/<form>/reader.html
"""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import get_settings

app = FastAPI(title="Facet Studio preview")


def _runs_root() -> Path:
    root = get_settings().runs_root / "product_v1"
    root.mkdir(parents=True, exist_ok=True)
    return root


app.mount(
    "/runs",
    StaticFiles(directory=str(_runs_root()), html=True),
    name="runs",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> JSONResponse:
    root = _runs_root()
    runs = sorted(
        [item.name for item in root.iterdir() if item.is_dir()],
        reverse=True,
    )
    return JSONResponse(
        {
            "service": "facet_studio-preview",
            "runs": runs[:50],
            "hint": "open /runs/<run_id>/<form>/reader.html",
        }
    )


def main() -> None:
    uvicorn.run(
        "facet_studio.preview_server:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )


if __name__ == "__main__":
    main()
