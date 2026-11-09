"""Tiny local preview + run-detail server for product_v1 artifacts.

P1 does not ship a custom frontend; this server lets LibreChat/tool output link
to the rendered reader page, figures and the local run trace.

    PYTHONPATH=src python -m facet_studio.preview_server
    # http://127.0.0.1:8765/runs/<run_id>            -> run detail (Story/Trace/Quality)
    # http://127.0.0.1:8765/runs/<run_id>/api/trace  -> live JSON trace
    # http://127.0.0.1:8765/runs/<run_id>/<form>/reader.html
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .core.config import get_settings
from .observability import FINAL_STATUSES, collect_runs_dashboard, collect_trace
from .observability_ui import DASHBOARD_HTML, RUN_DETAIL_HTML

app = FastAPI(title="Facet Studio preview")


def _runs_root() -> Path:
    root = get_settings().runs_root / "product_v1"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_run_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    if not safe or safe in {".", ".."}:
        raise HTTPException(status_code=404, detail="run not found")
    return safe


def _run_meta(run_id: str) -> tuple[Path, dict[str, Any]]:
    run_dir = _runs_root() / _safe_run_id(run_id)
    meta_path = run_dir / "run_meta.json"
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="run not found")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="run_meta.json is invalid") from exc
    return run_dir, meta


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
            "hint": "open /runs for the run dashboard; /runs/<run_id> for Live/Trace/Stats",
        }
    )


@app.get("/api/runs")
def runs_dashboard() -> JSONResponse:
    return JSONResponse(collect_runs_dashboard(get_settings().runs_root))


@app.get("/runs", response_class=HTMLResponse)
@app.get("/runs/", response_class=HTMLResponse)
def runs_page() -> str:
    return DASHBOARD_HTML


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(run_id: str) -> str:
    _run_meta(run_id)
    return RUN_DETAIL_HTML.replace("__RUN_ID__", _safe_run_id(run_id))


def _trace_signature(run_dir: Path) -> tuple[tuple[str, int, int], ...]:
    names = (
        "run_meta.json",
        "workflow.json",
        "llm_calls.jsonl",
        "tool_calls.jsonl",
        "decision_records.jsonl",
        "trace.json",
    )
    items: list[tuple[str, int, int]] = []
    for name in names:
        path = run_dir / name
        if path.is_file():
            stat = path.stat()
            items.append((name, stat.st_mtime_ns, stat.st_size))
    return tuple(items)


@app.get("/runs/{run_id}/stream")
async def run_stream(run_id: str, request: Request) -> StreamingResponse:
    run_dir, _meta = _run_meta(run_id)

    async def events():
        last: tuple[tuple[str, int, int], ...] | None = None
        while True:
            if await request.is_disconnected():
                break
            current = _trace_signature(run_dir)
            if current != last:
                meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8-sig"))
                final = str(meta.get("status") or "") in FINAL_STATUSES
                trace = collect_trace(
                    run_id,
                    run_dir,
                    meta,
                    include_checks=final,
                    include_grounding=final,
                    live=not final,
                )
                yield f"data: {json.dumps(trace, ensure_ascii=False)}\n\n"
                last = current
                if final:
                    break
            else:
                yield ": ping\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/runs/{run_id}/api/trace")
def run_trace(run_id: str) -> JSONResponse:
    run_dir, meta = _run_meta(run_id)
    final = str(meta.get("status") or "") in FINAL_STATUSES
    trace = collect_trace(
        run_id,
        run_dir,
        meta,
        include_checks=final,
        include_grounding=final,
        live=not final,
    )
    return JSONResponse(trace)


# Static artifacts stay under /runs/<run_id>/<form>/... and must be mounted
# after the run-detail routes above.
app.mount(
    "/runs",
    StaticFiles(directory=str(_runs_root()), html=True),
    name="runs",
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
