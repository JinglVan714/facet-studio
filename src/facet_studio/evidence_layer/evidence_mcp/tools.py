"""Evidence MCP 的纯工具实现。

- 只读证据；不写 substrate；
- 角色权限：writer 不能拿坐标；verifier/renderer/human 可以；
- context policy：detail / limit / max_chars / cursor；不 dump 全量；
- 失败明确：抛 ToolError，由 server 转成 MCP error。

这些函数不依赖 FastMCP，测试可以直接调用。
"""
from __future__ import annotations

import base64
import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..constants import DATA_DIR
from ..evidence_store import EvidenceError, EvidenceStore

ROLES = ("planner", "writer", "verifier", "renderer", "human", "admin")
COORD_ROLES = {"verifier", "renderer", "human", "admin"}
QUOTE_ROLES = {"writer", "verifier", "renderer", "human", "admin"}
DETAILS = ("index", "summary", "full")
MAX_LIMIT = 50
MAX_CHARS = 4000


class ToolError(RuntimeError):
    """MCP 工具错误；server 层会转成错误响应。"""

    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def _check_role(role: str) -> str:
    if role not in ROLES:
        raise ToolError("permission_denied", f"未知角色：{role!r}", f"可选：{ROLES}")
    return role


def _check_detail(detail: str) -> str:
    if detail not in DETAILS:
        raise ToolError("invalid_query", f"detail 非法：{detail!r}", f"可选：{DETAILS}")
    return detail


@lru_cache(maxsize=32)
def _store_cached(video_id: str, data_dir: str) -> EvidenceStore:
    return EvidenceStore.load(video_id, Path(data_dir) if data_dir else None)


def get_store(video_id: str, data_dir: str | Path | None = None,
              *, reload: bool = False) -> EvidenceStore:
    key = str(data_dir) if data_dir is not None else ""
    if reload:
        _store_cached.cache_clear()
    try:
        return _store_cached(video_id, key)
    except FileNotFoundError as e:
        raise ToolError("video_not_found", str(e), "先跑证据层，或检查 video_id") from e
    except EvidenceError as e:
        raise ToolError("stale_snapshot", str(e)) from e


def _log(tool: str, role: str, args: dict, result: Any, error: str | None = None,
         latency_ms: int = 0) -> None:
    path = os.environ.get("LMIND_MCP_LOG", "").strip()
    if not path:
        return
    if path == "1":
        path = str(DATA_DIR / "_ops" / "mcp_calls.jsonl")
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool": tool,
        "role": role,
        "args_hash": "sha256:" + _hash(json.dumps(args, sort_keys=True, ensure_ascii=False)),
        "result_chars": len(json.dumps(result, ensure_ascii=False)) if result is not None else 0,
        "error": error,
        "latency_ms": latency_ms,
    }
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - 打点是旁路
        pass


def _hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _truncate(payload: dict, max_chars: int = MAX_CHARS) -> dict:
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        payload["truncated"] = False
        return payload
    # 不截断 JSON 文本（会产生非法 JSON）；改为减少 items
    payload["truncated"] = True
    items = payload.get("items")
    if isinstance(items, list):
        while items and len(json.dumps(payload, ensure_ascii=False)) > max_chars:
            items.pop()
        payload["hint"] = "结果已截断；用 cursor / 更精确的 query / detail=summary 继续"
    return payload


def _cursor_decode(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        return max(0, int(json.loads(raw).get("offset") or 0))
    except Exception as e:  # noqa: BLE001
        raise ToolError("invalid_query", f"cursor 非法：{cursor!r}") from e


def _cursor_encode(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _assertion_view(store: EvidenceStore, a: dict, *, detail: str,
                    include_quote: bool, include_coordinates: bool,
                    role: str) -> dict:
    seg_id, seg_label = store.assertion_segment(a)
    frame_refs = [store.frame_ref(f) for f in (a.get("frame_refs") or [])]
    frame_refs = [r for r in frame_refs if store.frame_available(r)]
    out: dict[str, Any] = {
        "assertion_id": a.get("id"),
        "text": a.get("text"),
        "kind": a.get("kind"),
        "status": a.get("status"),
        "segment_id": seg_id,
        "segment_label": seg_label,
        "has_frames": bool(frame_refs),
        "quote_available": bool(a.get("quote")),
    }
    if detail == "index":
        return out

    out["boundary"] = a.get("boundary")
    out["frame_refs"] = frame_refs
    out["relations"] = [
        {"to_id": r.get("to_id"), "rel_type": r.get("rel_type"), "advisory": True}
        for r in store.relations if r.get("from_id") == a.get("id")
    ]
    conflicts = store.conflicts_for(a)
    if role not in COORD_ROLES:
        conflicts = [{k: v for k, v in c.items() if k != "unit_ids"} for c in conflicts]
    out["conflicts"] = conflicts

    if detail == "full":
        if include_quote or role in QUOTE_ROLES:
            out["quote"] = a.get("quote") or ""
            out["quote_source"] = a.get("quote_source")
        if include_coordinates and role in COORD_ROLES:
            out["unit_ids"] = list(a.get("unit_ids") or [])
            out["anchors"] = list(a.get("anchors") or [])
        elif include_coordinates and role not in COORD_ROLES:
            raise ToolError(
                "permission_denied",
                f"角色 {role!r} 不允许读取时间/unit 坐标",
                "用 frame_ref 引用；坐标只给 verifier/renderer",
            )
    return out


def _video_meta(store: EvidenceStore) -> dict:
    duration = None
    for strat in (store.frames_index or {}).get("strategies", {}).values():
        if strat.get("frames"):
            duration = max((f.get("t_ms") or 0) for f in strat["frames"]) / 1000.0
            break
    return {
        "video_id": store.video_id,
        "duration_s": duration,
        "has_frames": store.has_available_frames(),
        "assertion_count": len(store.assertions),
        "unit_count": len(store.units),
        "relation_count": len(store.relations),
        "source_sha256": dict(store.source_sha256),
    }


# ---------------------------------------------------------------- tools


def list_videos(data_dir: str | Path | None = None) -> dict:
    base = Path(data_dir) if data_dir is not None else DATA_DIR
    out = []
    if base.exists():
        for p in sorted(base.iterdir()):
            if not p.is_dir():
                continue
            if (p / "substrate" / "assertions.jsonl").exists() or \
                    (p / "substrate" / "assertions_reduced.jsonl").exists():
                out.append({"video_id": p.name, "has_substrate": True})
    return {"items": out, "count": len(out), "truncated": False}


def get_video(video_id: str, *, data_dir: str | Path | None = None,
              role: str = "writer") -> dict:
    t0 = time.perf_counter()
    _check_role(role)
    try:
        store = get_store(video_id, data_dir)
        out = _video_meta(store)
        out["provenance"] = store.provenance()
        _log("get_video", role, {"video_id": video_id}, out,
             latency_ms=int((time.perf_counter() - t0) * 1000))
        return out
    except ToolError as e:
        _log("get_video", role, {"video_id": video_id}, None, e.code,
             int((time.perf_counter() - t0) * 1000))
        raise


def search_evidence(video_id: str, query: str, *, filters: dict | None = None,
                    detail: str = "summary", limit: int = 10,
                    cursor: str | None = None, include_quote: bool = False,
                    include_coordinates: bool = False,
                    data_dir: str | Path | None = None,
                    role: str = "writer", max_chars: int = MAX_CHARS) -> dict:
    t0 = time.perf_counter()
    _check_role(role)
    _check_detail(detail)
    if not query or not query.strip():
        raise ToolError("invalid_query", "query 不能为空", "例如：一个关键词或短语")
    if limit < 1:
        raise ToolError("invalid_query", "limit 必须 >= 1")
    limit = min(int(limit), MAX_LIMIT)
    try:
        store = get_store(video_id, data_dir)
        offset = _cursor_decode(cursor)
        # 多取 1 条判断 next_cursor
        hits = store.search(query, filters=filters, limit=min(MAX_LIMIT, offset + limit + 1))
        page = hits[offset: offset + limit]
        items = [_assertion_view(store, a, detail=detail,
                                 include_quote=include_quote,
                                 include_coordinates=include_coordinates,
                                 role=role) for a in page]
        next_cursor = None
        if len(hits) > offset + limit:
            next_cursor = _cursor_encode(offset + limit)
        out = {
            "video_id": video_id,
            "items": items,
            "next_cursor": next_cursor,
            "truncated": False,
            "provenance": store.provenance(),
        }
        out = _truncate(out, max_chars=max_chars)
        _log("search_evidence", role, {"video_id": video_id, "query": query,
                                       "filters": filters, "detail": detail},
             out, latency_ms=int((time.perf_counter() - t0) * 1000))
        return out
    except ToolError as e:
        _log("search_evidence", role, {"video_id": video_id, "query": query},
             None, e.code, int((time.perf_counter() - t0) * 1000))
        raise


def get_assertion(video_id: str, assertion_id: str, *, detail: str = "full",
                  include_quote: bool = True, include_coordinates: bool = False,
                  data_dir: str | Path | None = None,
                  role: str = "writer") -> dict:
    t0 = time.perf_counter()
    _check_role(role)
    _check_detail(detail)
    try:
        store = get_store(video_id, data_dir)
        a = store.assertion(assertion_id)
        if not a:
            raise ToolError("assertion_not_found", f"找不到断言：{assertion_id!r}",
                            "先用 search_evidence 查 id；assertion_id 只在单条视频内唯一")
        out = _assertion_view(store, a, detail=detail, include_quote=include_quote,
                              include_coordinates=include_coordinates, role=role)
        out["video_id"] = store.video_id
        out["provenance"] = store.provenance()
        _log("get_assertion", role, {"assertion_id": assertion_id,
                                     "include_coordinates": include_coordinates},
             out, latency_ms=int((time.perf_counter() - t0) * 1000))
        return out
    except ToolError as e:
        _log("get_assertion", role, {"assertion_id": assertion_id}, None, e.code,
             int((time.perf_counter() - t0) * 1000))
        raise


def get_unit_context(video_id: str, unit_id: str, *, before: int = 2, after: int = 2,
                     include_time: bool = False,
                     data_dir: str | Path | None = None,
                     role: str = "writer") -> dict:
    t0 = time.perf_counter()
    _check_role(role)
    before = max(0, min(int(before), 10))
    after = max(0, min(int(after), 10))
    if include_time and role not in COORD_ROLES:
        raise ToolError("permission_denied", f"角色 {role!r} 不允许读取时间")
    try:
        store = get_store(video_id, data_dir)
        idx = next((i for i, u in enumerate(store.units) if u.get("unit_id") == unit_id), None)
        if idx is None:
            raise ToolError("not_found", f"找不到 unit：{unit_id!r}")
        units = store.units
        lo, hi = max(0, idx - before), min(len(units), idx + after + 1)

        def _u(u):
            row = {"unit_id": u.get("unit_id"), "sid": u.get("sid"),
                   "raw": u.get("raw"), "len": u.get("len"),
                   "filler_only": u.get("filler_only")}
            if include_time and role in COORD_ROLES:
                row["t"] = u.get("t")
            return row

        out = {
            "unit_id": unit_id,
            "video_id": store.video_id,
            "before": [_u(u) for u in units[lo:idx]],
            "unit": _u(units[idx]),
            "after": [_u(u) for u in units[idx + 1:hi]],
            "truncated": False,
            "provenance": store.provenance(),
        }
        _log("get_unit_context", role, {"unit_id": unit_id}, out,
             latency_ms=int((time.perf_counter() - t0) * 1000))
        return out
    except ToolError as e:
        _log("get_unit_context", role, {"unit_id": unit_id}, None, e.code,
             int((time.perf_counter() - t0) * 1000))
        raise


def get_conflicts(video_id: str, assertion_id: str | None = None, *,
                  include_resolved: bool = True,
                  data_dir: str | Path | None = None,
                  role: str = "writer") -> dict:
    t0 = time.perf_counter()
    _check_role(role)
    try:
        store = get_store(video_id, data_dir)
        if assertion_id:
            a = store.assertion(assertion_id)
            if not a:
                raise ToolError("assertion_not_found", f"找不到断言：{assertion_id!r}")
            items = store.conflicts_for(a)
        else:
            items = store.all_conflicts()
        if not include_resolved:
            items = [x for x in items if x.get("advice") != "resolved_term"]
        if role not in COORD_ROLES:
            items = [{k: v for k, v in x.items() if k != "unit_ids"} for x in items]
        out = {
            "video_id": video_id,
            "items": items,
            "advice_policy": "不要静默选一个；按 advice 或写‘有说法认为’",
            "truncated": False,
            "provenance": store.provenance(),
        }
        _log("get_conflicts", role, {"video_id": video_id, "assertion_id": assertion_id},
             out, latency_ms=int((time.perf_counter() - t0) * 1000))
        return out
    except ToolError as e:
        _log("get_conflicts", role, {"video_id": video_id, "assertion_id": assertion_id},
             None, e.code, int((time.perf_counter() - t0) * 1000))
        raise


def get_frames(video_id: str, frame_refs: list[str] | None = None, *,
               include_coordinates: bool = True,
               data_dir: str | Path | None = None,
               role: str = "verifier") -> dict:
    t0 = time.perf_counter()
    _check_role(role)
    if role not in COORD_ROLES:
        raise ToolError("permission_denied",
                        f"角色 {role!r} 不允许读取帧坐标/路径",
                        "用 get_assertion 的 opaque frame_ref；renderer/verifier 才能取帧")
    if not include_coordinates:
        raise ToolError("invalid_query", "get_frames 需要 include_coordinates=true")
    try:
        store = get_store(video_id, data_dir)
        refs = frame_refs or []
        items = []
        for ref in refs:
            rec = store.frame(ref)
            if rec is None:
                items.append({"frame_ref": ref, "found": False})
            else:
                items.append({"frame_ref": ref, "found": True, **rec})
        out = {"video_id": video_id, "items": items, "truncated": False,
               "provenance": store.provenance()}
        _log("get_frames", role, {"video_id": video_id, "frame_refs": refs}, out,
             latency_ms=int((time.perf_counter() - t0) * 1000))
        return out
    except ToolError as e:
        _log("get_frames", role, {"video_id": video_id, "frame_refs": frame_refs}, None,
             e.code, int((time.perf_counter() - t0) * 1000))
        raise


def render_citation(video_id: str, assertion_ids: list[str],
                    frame_refs: list[str] | None = None, *,
                    style: str = "numeric", include_time: bool = True,
                    data_dir: str | Path | None = None,
                    role: str = "renderer") -> dict:
    t0 = time.perf_counter()
    _check_role(role)
    if role not in COORD_ROLES:
        raise ToolError("permission_denied",
                        f"角色 {role!r} 不允许生成 quote/time/frame 引用",
                        "renderer/verifier/human 才能调用")
    try:
        store = get_store(video_id, data_dir)
        refs = []
        for aid in assertion_ids:
            a = store.assertion(aid)
            if not a:
                refs.append({"assertion_id": aid, "found": False})
                continue
            anchors = a.get("anchors") or [{}]
            row = {
                "assertion_id": aid,
                "found": True,
                "quote": a.get("quote") or "",
                "unit_ids": list(a.get("unit_ids") or []),
            }
            if include_time:
                an = anchors[0]
                row["time"] = {
                    "start_ms": an.get("start_ms"),
                    "end_ms": an.get("end_ms"),
                    "display": _display_time(an.get("start_ms"), an.get("end_ms")),
                }
            refs.append(row)
        frames = []
        for ref in frame_refs or []:
            rec = store.frame(ref)
            if rec:
                frames.append({
                    "frame_ref": ref,
                    "path": rec.get("path"),
                    "t_ms": rec.get("t_ms"),
                    "display": _display_time(rec.get("t_ms"), None),
                    "text": rec.get("text"),
                })
        out = {"video_id": store.video_id, "style": style,
               "assertions": refs, "frames": frames, "truncated": False,
               "provenance": store.provenance()}
        _log("render_citation", role, {"assertion_ids": assertion_ids,
                                       "frame_refs": frame_refs}, out,
             latency_ms=int((time.perf_counter() - t0) * 1000))
        return out
    except ToolError as e:
        _log("render_citation", role, {"assertion_ids": assertion_ids}, None, e.code,
             int((time.perf_counter() - t0) * 1000))
        raise


def get_provenance(video_id: str, *, data_dir: str | Path | None = None,
                   role: str = "writer") -> dict:
    _check_role(role)
    store = get_store(video_id, data_dir)
    return store.provenance()


def _display_time(start_ms, end_ms=None) -> str | None:
    if start_ms is None:
        return None

    def _fmt(ms: int) -> str:
        s, ms = divmod(int(ms), 1000)
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}.{ms // 100}"

    if end_ms is None:
        return _fmt(start_ms)
    return f"{_fmt(start_ms)}–{_fmt(end_ms)}"
