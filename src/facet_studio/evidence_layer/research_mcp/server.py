"""Research MCP stdio server (FastMCP).

Start:
  python -m lmind.research_mcp.server --role writer
  python -m lmind.research_mcp.server --role verifier --ledger runs/research.json
  python -m lmind.research_mcp.server --selftest

External sources are fetched with URL + verbatim quote + retrieved_at, kept in
a source ledger, and never mixed with video assertions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import tools
from .ledger import SourceError, SourceLedger

ROLES = ("writer", "verifier", "human", "admin")


def _role(default: str, requested: str) -> str:
    if not requested:
        return default
    if requested != default and default != "admin":
        raise SourceError("permission_denied",
                          f"server role={default!r}，不能提权到 {requested!r}")
    return requested


def _require_human(role: str) -> None:
    if role not in ("verifier", "human", "admin"):
        raise SourceError("permission_denied", "只有 verifier/human/admin 能写来源账本")


def build_server(*, default_role: str = "writer",
                 fixture_dir: str | Path | None = None,
                 ledger_path: str | Path | None = None,
                 name: str = "lmind-research") -> FastMCP:
    ledger = SourceLedger.load(ledger_path) if ledger_path and Path(ledger_path).exists() \
        else SourceLedger()
    fixture = str(fixture_dir) if fixture_dir is not None else None
    mcp = FastMCP(name)

    def _save() -> None:
        if ledger_path:
            ledger.write(ledger_path)

    @mcp.tool()
    def search_external(query: str, limit: int = 5, urls: list[str] | None = None,
                        role: str = "") -> dict:
        """检索外部资料；默认 fixture provider，也可给 urls 直接抓取。"""
        _role(default_role, role)
        return tools.search_external(query, fixture_dir=fixture, urls=urls, limit=limit)

    @mcp.tool()
    def fetch_source(url: str, query: str = "", supports: list[str] | None = None,
                     role: str = "") -> dict:
        """抓取 URL，抽取逐字 quote，并写入 source ledger。"""
        _role(default_role, role)
        rec = tools.fetch_source(url, query=query or None, supports=supports,
                                 ledger=ledger)
        _save()
        return rec

    @mcp.tool()
    def quote_source(source_id: str = "", url: str = "", query: str = "",
                     role: str = "") -> dict:
        """从已抓取来源或 URL 重新抽取逐字 quote。"""
        _role(default_role, role)
        return tools.quote_source(source_id=source_id or None, url=url or None,
                                  query=query or None, ledger=ledger)

    @mcp.tool()
    def list_sources(role: str = "") -> dict:
        """列出 source ledger。"""
        _role(default_role, role)
        return {"schema_version": "research/ledger/v1",
                "items": ledger.list(), "count": len(ledger.sources),
                "hash": ledger.hash()}

    @mcp.tool()
    def get_source(source_id: str, role: str = "") -> dict:
        """取单条外部来源。"""
        _role(default_role, role)
        rec = ledger.get(source_id)
        if rec is None:
            raise SourceError("unknown_source", f"没有 source_id={source_id!r}")
        return rec

    @mcp.tool()
    def add_source(url: str, quote: str, title: str = "", publisher: str = "",
                   retrieved_at: str = "", supports: list[str] | None = None,
                   role: str = "") -> dict:
        """人工/评测加入一条外部来源；quote 必须逐字提供。"""
        r = _role(default_role, role)
        _require_human(r)
        rec = ledger.add_external(
            url=url, quote=quote, title=title, publisher=publisher,
            retrieved_at=retrieved_at or None, supports=supports,
            retrieved_by="user_provided",
        )
        _save()
        return rec

    @mcp.tool()
    def mark_conflict(source_id: str, assertion_id: str = "",
                      advice: str = "avoid", note: str = "",
                      role: str = "") -> dict:
        """记录外部来源与视频 assertion 的冲突；不静默裁决。"""
        r = _role(default_role, role)
        _require_human(r)
        rec = ledger.add_conflict(source_id=source_id,
                                  assertion_id=assertion_id or None,
                                  advice=advice, note=note)
        _save()
        return rec

    @mcp.tool()
    def export_ledger(path: str = "", role: str = "") -> dict:
        """导出 source ledger JSON；不传 path 则返回内容。"""
        r = _role(default_role, role)
        _require_human(r)
        if path:
            p = ledger.write(path)
            return {"written": str(p), "count": len(ledger.sources),
                    "hash": ledger.hash()}
        return ledger.to_dict()

    return mcp


def selftest() -> dict:
    import tempfile

    text = ("今天我们来演示一个外部资料工具。它要求每条事实带上 URL、"
            "检索时间和逐字引文，不能把网页内容伪装成视频原话。"
            "第二段解释 source ledger 如何记录这些字段。")
    fixture = {"url": "https://example.com/demo", "title": "Demo",
               "publisher": "Example", "text": text}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "demo.json"
        p.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
        search = tools.search_external("逐字引文", fixture_dir=td, limit=3)
        quote = tools.extract_quote(text, "逐字引文")
    ledger = SourceLedger()
    rec = ledger.add_external(url=fixture["url"], quote=quote["quote"],
                              title=fixture["title"], publisher=fixture["publisher"],
                              text=text, retrieved_by="selftest")
    errors = []
    for bad in (
        {"source_id": "src-0000000000000000", "url": "",
         "quote": "x", "retrieved_at": "now"},
        {"source_id": "src-0000000000000000", "url": "https://example.com",
         "quote": "", "retrieved_at": "now"},
        {"source_id": "src-0000000000000000", "url": "https://example.com",
         "quote": "x", "retrieved_at": ""},
    ):
        try:
            ledger.add(bad)
            errors.append("missing-field check did not fire")
        except SourceError:
            pass
    return {
        "search_items": len(search["items"]),
        "quote": quote["quote"],
        "source_id": rec["source_id"],
        "ledger_hash": ledger.hash(),
        "missing_field_checks": "OK" if not errors else errors,
        "render_has_warning": "不是视频原话" in ledger.render(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lmind-research-mcp")
    ap.add_argument("--role", default="writer", choices=ROLES)
    ap.add_argument("--fixture-dir", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--name", default="lmind-research")
    args = ap.parse_args(argv)
    if args.selftest:
        print(json.dumps(selftest(), ensure_ascii=False, indent=2))
        return 0
    mcp = build_server(default_role=args.role, fixture_dir=args.fixture_dir,
                       ledger_path=args.ledger, name=args.name)
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
