"""Evidence MCP stdio server（FastMCP）。

启动：
  python -m lmind.evidence_mcp.server --role writer
  python -m lmind.evidence_mcp.server --role verifier --data-dir data

角色固定：
- MCP client 不能通过参数提权；`role` 参数只允许与 server 默认角色一致。
- writer 不能取坐标/帧；verifier/renderer/human 可以。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import tools
from .tools import ToolError


def _role(default: str, requested: str) -> str:
    if not requested:
        return default
    if requested != default and default != "admin":
        raise ToolError("permission_denied",
                        f"server role={default!r}，不能提权到 {requested!r}")
    return requested


def build_server(*, default_role: str = "writer",
                 data_dir: str | Path | None = None,
                 name: str = "lmind-evidence") -> FastMCP:
    mcp = FastMCP(name)
    dd = str(data_dir) if data_dir is not None else None

    @mcp.tool()
    def list_videos() -> dict:
        """列出可用的视频证据。"""
        return tools.list_videos(data_dir=dd)

    @mcp.tool()
    def get_video(video_id: str, role: str = "") -> dict:
        """取视频元数据、证据 hash 与统计。"""
        return tools.get_video(video_id, data_dir=dd, role=_role(default_role, role))

    @mcp.tool()
    def search_evidence(video_id: str, query: str, filters: dict | None = None,
                        detail: str = "summary", limit: int = 10,
                        cursor: str | None = None, include_quote: bool = False,
                        include_coordinates: bool = False,
                        role: str = "") -> dict:
        """按 query 检索断言。detail=index|summary|full；writer 不能取坐标。"""
        return tools.search_evidence(
            video_id, query, filters=filters, detail=detail, limit=limit,
            cursor=cursor, include_quote=include_quote,
            include_coordinates=include_coordinates, data_dir=dd,
            role=_role(default_role, role),
        )

    @mcp.tool()
    def get_assertion(video_id: str, assertion_id: str, detail: str = "full",
                      include_quote: bool = True,
                      include_coordinates: bool = False,
                      role: str = "") -> dict:
        """取单条断言；writer 默认拿 opaque frame_ref，不拿时间。"""
        return tools.get_assertion(
            video_id, assertion_id, detail=detail, include_quote=include_quote,
            include_coordinates=include_coordinates, data_dir=dd,
            role=_role(default_role, role),
        )

    @mcp.tool()
    def get_unit_context(video_id: str, unit_id: str, before: int = 2, after: int = 2,
                         include_time: bool = False, role: str = "") -> dict:
        """取 unit 前后上下文；writer 默认不取时间。"""
        return tools.get_unit_context(
            video_id, unit_id, before=before, after=after, include_time=include_time,
            data_dir=dd, role=_role(default_role, role),
        )

    @mcp.tool()
    def get_conflicts(video_id: str, assertion_id: str | None = None,
                      include_resolved: bool = True, role: str = "") -> dict:
        """取 ASR/画面冲突及 advice；不要静默裁决。"""
        return tools.get_conflicts(
            video_id, assertion_id, include_resolved=include_resolved,
            data_dir=dd, role=_role(default_role, role),
        )

    @mcp.tool()
    def get_frames(video_id: str, frame_refs: list[str] | None = None,
                   include_coordinates: bool = True, role: str = "") -> dict:
        """取帧文字/路径/时间；仅 verifier/renderer/human。"""
        return tools.get_frames(
            video_id, frame_refs, include_coordinates=include_coordinates,
            data_dir=dd, role=_role(default_role, role),
        )

    @mcp.tool()
    def render_citation(video_id: str, assertion_ids: list[str],
                        frame_refs: list[str] | None = None,
                        style: str = "numeric", include_time: bool = True,
                        role: str = "") -> dict:
        """从证据派生 quote/time/frame；仅 renderer/verifier/human。"""
        return tools.render_citation(
            video_id, assertion_ids, frame_refs, style=style, include_time=include_time,
            data_dir=dd, role=_role(default_role, role),
        )

    @mcp.tool()
    def get_provenance(video_id: str, role: str = "") -> dict:
        """取证据 hash/文件路径/统计。"""
        return tools.get_provenance(video_id, data_dir=dd, role=_role(default_role, role))

    return mcp


def selftest(*, data_dir: str | Path | None = None) -> dict:
    videos = tools.list_videos(data_dir=data_dir)
    if not videos["items"]:
        raise SystemExit("没有可用视频")
    # Do not hardcode a phrase from one video: take a real assertion's text as
    # the query so the smoke works for any substrate.
    vid, query = None, None
    for item in videos["items"]:
        store = tools.get_store(item["video_id"], data_dir)
        if store.assertions:
            vid = item["video_id"]
            query = (store.assertions[0].get("text") or "")[:12]
            break
    if not vid or not query:
        raise SystemExit("没有可检索的断言")
    search = tools.search_evidence(vid, query, limit=3, data_dir=data_dir,
                                   role="writer")
    out = {
        "videos": len(videos["items"]),
        "video": tools.get_video(vid, data_dir=data_dir, role="writer"),
        "search": search,
        "assertion": tools.get_assertion(
            vid, search["items"][0]["assertion_id"],
            data_dir=data_dir, role="writer"),
        "provenance": tools.get_provenance(vid, data_dir=data_dir, role="writer"),
    }
    # 权限自检：writer 取帧必须被拒
    try:
        tools.get_frames(vid, ["f-x"], data_dir=data_dir, role="writer")
        out["permission_check"] = "FAIL: writer 取帧未被拒"
    except ToolError as e:
        out["permission_check"] = f"OK: {e.code}"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lmind-evidence-mcp")
    ap.add_argument("--role", default="writer", choices=tools.ROLES)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--name", default="lmind-evidence")
    args = ap.parse_args(argv)
    if args.selftest:
        print(json.dumps(selftest(data_dir=args.data_dir), ensure_ascii=False, indent=2))
        return 0
    mcp = build_server(default_role=args.role, data_dir=args.data_dir, name=args.name)
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
