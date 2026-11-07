"""External source ledger.

External sources are **not** video assertions and must never be mixed into a
video-assertion citation. Each source needs:
  - url
  - title/publisher (recommended; not mechanically required)
  - retrieved_at
  - quote (verbatim excerpt)
  - text_hash (if full text was retrieved)
  - supports (what claim/assertion it is used for)
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


class SourceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def source_id_for(url: str, quote: str) -> str:
    return "src-" + hashlib.sha256(f"{_norm(url)}|{_norm(quote)}".encode("utf-8")).hexdigest()[:16]


@dataclass
class SourceLedger:
    sources: dict[str, dict] = field(default_factory=dict)
    conflicts: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------ add
    def add(self, record: dict) -> dict:
        rec = self._validate(record)
        self.sources[rec["source_id"]] = rec
        return rec

    def add_external(self, *, url: str, quote: str, title: str = "",
                     publisher: str = "", retrieved_at: str | None = None,
                     text: str = "", supports: list[str] | None = None,
                     retrieved_by: str = "http", source_type: str = "external_source",
                     status: str = "retrieved") -> dict:
        return self.add({
            "source_id": source_id_for(url, quote),
            "source_type": source_type,
            "url": url,
            "title": title,
            "publisher": publisher,
            "retrieved_at": retrieved_at or _now(),
            "quote": quote,
            "quote_hash": _hash(quote),
            "text": text,
            "text_hash": _hash(text) if text else None,
            "supports": list(supports or []),
            "retrieved_by": retrieved_by,
            "status": status,
        })

    def add_conflict(self, *, source_id: str, assertion_id: str | None = None,
                     advice: str = "avoid", note: str = "") -> dict:
        if source_id not in self.sources:
            raise SourceError("unknown_source", f"没有 source_id={source_id!r}")
        if advice not in ("avoid", "prefer_source", "prefer_screen", "resolved_term", "cite_conflict"):
            raise SourceError("bad_advice", f"不支持的 advice={advice!r}")
        conflict = {
            "conflict_id": "x-" + hashlib.sha256(
                f"{source_id}|{assertion_id}|{advice}|{note}".encode("utf-8")).hexdigest()[:12],
            "source_id": source_id,
            "assertion_id": assertion_id,
            "advice": advice,
            "note": note,
        }
        if conflict not in self.conflicts:
            self.conflicts.append(conflict)
        return conflict

    # ------------------------------------------------------------ read
    def get(self, source_id: str) -> dict | None:
        return self.sources.get(source_id)

    def list(self) -> list[dict]:
        return [self.sources[k] for k in sorted(self.sources)]

    def render(self) -> str:
        if not self.sources:
            return ""
        lines = [
            "## external_sources（外部资料，不是视频原话）",
            "以下资料只能支撑外部事实；不能伪装成视频 assertion，也不能与视频证据混写在同一句。",
        ]
        for s in self.list():
            lines.append(f"- source_id: {s['source_id']}")
            lines.append(f"  url: {s['url']}")
            if s.get("title"):
                lines.append(f"  title: {s['title']}")
            if s.get("publisher"):
                lines.append(f"  publisher: {s['publisher']}")
            lines.append(f"  retrieved_at: {s['retrieved_at']}")
            lines.append(f"  quote: {s['quote']}")
            if s.get("supports"):
                lines.append(f"  supports: {', '.join(s['supports'])}")
        if self.conflicts:
            lines.append("### external_conflicts")
            for c in self.conflicts:
                lines.append(
                    f"- {c['conflict_id']}: source={c['source_id']} "
                    f"assertion={c.get('assertion_id')} advice={c['advice']} {c.get('note') or ''}"
                )
        return "\n".join(lines)

    def hash(self) -> str:
        blob = json.dumps({"sources": self.list(), "conflicts": self.conflicts},
                          ensure_ascii=False, sort_keys=True)
        return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "schema_version": "research/ledger/v1",
            "sources": self.list(),
            "conflicts": list(self.conflicts),
            "ledger_hash": self.hash(),
        }

    def write(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return p

    @classmethod
    def from_records(cls, records: list[dict] | None) -> "SourceLedger":
        ledger = cls()
        for rec in records or []:
            ledger.add(rec)
        return ledger

    @classmethod
    def load(cls, path: str | Path) -> "SourceLedger":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        ledger = cls.from_records(data.get("sources") or [])
        ledger.conflicts = list(data.get("conflicts") or [])
        return ledger

    # ------------------------------------------------------------ validate
    @staticmethod
    def _validate(record: dict) -> dict:
        if not isinstance(record, dict):
            raise SourceError("schema", "source 必须是 object")
        url = _norm(record.get("url") or "")
        quote = _norm(record.get("quote") or "")
        retrieved_at = _norm(record.get("retrieved_at") or "")
        if not url or urlparse(url).scheme not in ("http", "https"):
            raise SourceError("missing_url", "external source 必须有 http(s) URL")
        if not retrieved_at:
            raise SourceError("missing_retrieved_at", "external source 必须有 retrieved_at")
        if not quote:
            raise SourceError("missing_quote", "external source 必须有 quote")
        text = record.get("text") or ""
        retrieved_by = record.get("retrieved_by") or "http"
        if retrieved_by != "user_provided" and not text:
            raise SourceError(
                "missing_text",
                "抓取来源必须保留 text/text_hash，才能验证 quote 是逐字子串",
            )
        if text and _norm(quote) not in _norm(text):
            raise SourceError("quote_not_in_text", "quote 不是抓取正文的逐字子串")
        rec = dict(record)
        rec.update({
            "source_type": "external_source",
            "url": url,
            "quote": quote,
            "retrieved_at": retrieved_at,
            "quote_hash": _hash(quote),
            "text": text,
            "text_hash": _hash(text) if text else record.get("text_hash"),
            "supports": list(record.get("supports") or []),
        })
        rec["source_id"] = record.get("source_id") or source_id_for(url, quote)
        if not re.match(r"^src-[0-9a-f]{16}$", rec["source_id"]):
            raise SourceError("bad_source_id", f"非法 source_id={rec['source_id']!r}")
        return rec
