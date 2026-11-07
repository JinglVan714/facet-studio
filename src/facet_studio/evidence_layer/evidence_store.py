"""证据层的新访问面：只读 substrate，不依赖旧 `lmind.projection`。

为什么单独一份：
- v1 的写作层与 Evidence MCP 都要读证据；
- 旧 `lmind/projection/io.py` 是 v0 实现，新层禁止 import 它（迁移文档的防污染规则）；
- 这里保持与底稿文件格式一致，但把 **frame_id 转成 opaque frame_ref**，
  避免 Writer 从 `00000_000003880` 这种 ID 里读出精确毫秒时间。

只读原则：
- 不写 substrate；
- 不生成 quote；quote 只从 assertions.jsonl / assertions_reduced.jsonl 读；
- 所有 hash 用完整 SHA256。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .constants import DATA_DIR


class EvidenceError(RuntimeError):
    """证据读取/映射错误。"""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _pick(sub: Path, preferred: str, fallback: str) -> Path:
    p = sub / preferred
    return p if p.exists() else sub / fallback


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower()


@dataclass(frozen=True)
class EvidenceStore:
    """一条视频的只读证据快照。"""

    video_id: str
    root: Path
    assertions: list[dict]
    relations: list[dict]
    units: list[dict]
    contract: dict
    corrections: dict
    ledger: list[dict]
    frames_vlm: dict
    frames_index: dict
    source_files: dict[str, Any]
    source_sha256: dict[str, str | None]

    # ------------------------------------------------------------ load

    @classmethod
    def load(cls, video_id: str, data_dir: Path | None = None) -> "EvidenceStore":
        base = Path(data_dir) if data_dir is not None else DATA_DIR
        root = base / video_id
        sub = root / "substrate"
        if not sub.exists():
            raise FileNotFoundError(f"缺少 substrate 目录：{sub}")

        a_path = _pick(sub, "assertions_reduced.jsonl", "assertions.jsonl")
        r_path = _pick(sub, "relations_reduced.jsonl", "relations.jsonl")
        units_path = sub / "units.jsonl"
        contract_path = sub / "contract.json"
        corrections_path = sub / "corrections_asr_vs_screen.json"
        ledger_path = sub / "corrections_ledger.jsonl"
        frames_index_path = root / "frames_index.json"

        frames_vlm, frame_files, frame_hash = _load_frames_vlm(root)

        source_files = {
            "assertions": str(a_path) if a_path.exists() else None,
            "relations": str(r_path) if r_path.exists() else None,
            "units": str(units_path) if units_path.exists() else None,
            "contract": str(contract_path) if contract_path.exists() else None,
            "corrections": str(corrections_path) if corrections_path.exists() else None,
            "ledger": str(ledger_path) if ledger_path.exists() else None,
            "frames_vlm": frame_files or None,
            "frames_index": str(frames_index_path) if frames_index_path.exists() else None,
        }
        source_sha256 = {
            "assertions": _sha256_file(a_path),
            "relations": _sha256_file(r_path),
            "units": _sha256_file(units_path),
            "contract": _sha256_file(contract_path),
            "corrections": _sha256_file(corrections_path),
            "ledger": _sha256_file(ledger_path),
            "frames_vlm": frame_hash,
            "frames_index": _sha256_file(frames_index_path),
        }
        return cls(
            video_id=video_id,
            root=root,
            assertions=_read_jsonl(a_path),
            relations=_read_jsonl(r_path),
            units=_read_jsonl(units_path),
            contract=_read_json(contract_path, {}),
            corrections=_read_json(corrections_path, {}),
            ledger=_read_jsonl(ledger_path),
            frames_vlm=frames_vlm,
            frames_index=_read_json(frames_index_path, {}),
            source_files=source_files,
            source_sha256=source_sha256,
        )

    # ------------------------------------------------------------ indexes

    def assertion(self, assertion_id: str) -> dict | None:
        return next((a for a in self.assertions if a.get("id") == assertion_id), None)

    def unit(self, unit_id: str) -> dict | None:
        return next((u for u in self.units if u.get("unit_id") == unit_id), None)

    def assertion_ids(self) -> set[str]:
        return {a["id"] for a in self.assertions if a.get("id")}

    def segment_of_unit(self, unit_id: str) -> tuple[str | None, str | None]:
        for seg in self.contract.get("segments") or []:
            if unit_id in (seg.get("unit_ids") or []):
                return seg.get("segment_id"), seg.get("label")
        return None, None

    def assertion_segment(self, assertion: dict) -> tuple[str, str]:
        uid = (assertion.get("unit_ids") or [None])[0]
        seg_id, label = self.segment_of_unit(uid) if uid else (None, None)
        return seg_id or "unsegmented", label or ""

    # ------------------------------------------------------------ search

    def search(self, query: str, *, filters: dict | None = None,
               limit: int = 10) -> list[dict]:
        """简单可复现的检索：子串匹配 + 词项命中数；不调模型/embedding。"""
        q = (query or "").strip()
        if not q:
            raise EvidenceError("query 不能为空")
        terms = [t for t in re.split(r"\s+", q) if t]
        filters = filters or {}
        kinds = set(filters.get("kind") or [])
        statuses = set(filters.get("status") or [])
        segments = set(filters.get("segment_id") or [])
        has_frames = filters.get("has_frames")

        hits: list[dict] = []
        for a in self.assertions:
            if a.get("status") == "unsupported":
                continue
            if kinds and a.get("kind") not in kinds:
                continue
            if statuses and a.get("status") not in statuses:
                continue
            seg_id, seg_label = self.assertion_segment(a)
            if segments and seg_id not in segments:
                continue
            if has_frames is not None and bool(a.get("frame_refs")) != bool(has_frames):
                continue
            hay = _norm((a.get("text") or "") + "\n" + (a.get("quote") or ""))
            score = 0.0
            if _norm(q) in hay:
                score += 3.0
            score += sum(1.0 for t in terms if _norm(t) in hay)
            if score > 0:
                row = dict(a)
                row["segment_id"] = seg_id
                row["segment_label"] = seg_label
                row["score"] = round(score, 4)
                hits.append(row)
        hits.sort(key=lambda x: (-x["score"], x.get("id") or ""))
        return hits[:max(0, min(int(limit), 50))]

    # ------------------------------------------------------------ conflicts

    def _ledger_index(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.ledger:
            key = e.get("key")
            if not key and e.get("sid") and e.get("asr") is not None:
                key = f"{self.video_id}|{e['sid']}|{e['asr']}"
            if key:
                out[key] = e
        return out

    def conflicts_for(self, assertion: dict) -> list[dict]:
        a_units = set(assertion.get("unit_ids") or [])
        a_sids = {x.get("sid") for x in (assertion.get("anchors") or []) if x.get("sid")}
        ledger = self._ledger_index()
        out: list[dict] = []
        seen: set[str] = set()
        for row in self.corrections.get("conflicts") or []:
            r_units = set(row.get("unit_ids") or [])
            if r_units:
                if not (a_units & r_units):
                    continue
            elif row.get("sid") not in a_sids:
                continue
            cid = self._conflict_id(row)
            if cid in seen:
                continue
            mapped = self._map_conflict(row, ledger)
            if mapped is not None:
                seen.add(cid)
                out.append(mapped)
        return out

    def all_conflicts(self) -> list[dict]:
        ledger = self._ledger_index()
        out = []
        for row in self.corrections.get("conflicts") or []:
            mapped = self._map_conflict(row, ledger)
            if mapped is not None:
                out.append(mapped)
        return out

    def _conflict_id(self, row: dict) -> str:
        blob = "|".join(str(row.get(k) or "") for k in ("sid", "frame_id", "asr", "screen"))
        return "c-" + _sha256_text(blob)[:12]

    def _map_conflict(self, row: dict, ledger: dict[str, dict]) -> dict | None:
        key = f"{self.video_id}|{row.get('sid')}|{row.get('asr')}"
        entry = ledger.get(key)
        advice = "avoid"
        resolved_term = None
        if entry:
            decision = entry.get("decision")
            if decision in ("accept_asr", "not_a_conflict"):
                return None
            if decision == "accept_screen":
                advice = "prefer_screen"
            elif decision == "custom":
                advice = "resolved_term"
                resolved_term = (entry.get("new") or "").strip()
                if not resolved_term:
                    raise EvidenceError(f"账本 custom 裁定缺 new：{key!r}")
            else:
                raise EvidenceError(f"账本 decision 非法：{decision!r}（key={key!r}）")
        out = {
            "conflict_id": self._conflict_id(row),
            "kind": "asr_vs_screen",
            "advice": advice,
            "asr": row.get("asr"),
            "screen": row.get("screen"),
            "window": row.get("window"),
            "frame_ref": self.frame_ref(row.get("frame_id")) if row.get("frame_id") else None,
            "unit_ids": list(row.get("unit_ids") or []),
        }
        if advice == "resolved_term":
            out["resolved_term"] = resolved_term
        return out

    # ------------------------------------------------------------ frames

    def _frames(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        per_frame = (self.frames_vlm or {}).get("per_frame") or {}
        index = {}
        for strat in (self.frames_index or {}).get("strategies", {}).values():
            for f in strat.get("frames") or []:
                p = f.get("file")
                if p:
                    index[Path(p).stem] = {"path": p, "t_ms": f.get("t_ms")}
        for fid, rec in per_frame.items():
            meta = index.get(fid) or {}
            out[fid] = {
                "frame_id": fid,
                "text": (rec.get("text") or ""),
                "is_representative": bool(rec.get("is_representative", True)),
                "path": meta.get("path"),
                "t_ms": meta.get("t_ms"),
                "advisory": True,
            }
        # frames_index 里有、frames_vlm 没转录的帧也保留
        for fid, meta in index.items():
            if fid not in out:
                out[fid] = {"frame_id": fid, "text": "", "is_representative": True,
                            "path": meta.get("path"), "t_ms": meta.get("t_ms"),
                            "advisory": True}
        return out

    def frame(self, frame_ref: str) -> dict | None:
        fid = self.resolve_frame_ref(frame_ref)
        return self._frames().get(fid) if fid else None

    def frame_available(self, frame_ref: str) -> bool:
        """A frame metadata row only counts if its image exists locally.

        The clean repo ships substrate but not raw media; without this check the
        writer would be told frames are available and would try to cite them.
        """
        rec = self.frame(frame_ref)
        path = rec.get("path") if rec else None
        return bool(path and (self.root / path).exists())

    def has_available_frames(self) -> bool:
        return any(self.frame_available(self.frame_ref(fid)) for fid in self._frames())

    def frame_ref(self, frame_id: str) -> str:
        """把带时间的 frame_id 变成不透明 ref，避免 Writer 读时间。"""
        return "f-" + _sha256_text(f"{self.video_id}|{frame_id}")[:12]

    def resolve_frame_ref(self, frame_ref: str) -> str | None:
        if not frame_ref:
            return None
        if frame_ref.startswith("f-"):
            for fid in self._frames():
                if self.frame_ref(fid) == frame_ref:
                    return fid
            return None
        # 兼容旧数据：如果调用方直接给 raw frame_id
        return frame_ref if frame_ref in self._frames() else None

    def frames_for_assertion(self, assertion: dict) -> list[dict]:
        out = []
        for fid in assertion.get("frame_refs") or []:
            rec = self._frames().get(fid)
            if rec:
                out.append({**rec, "frame_ref": self.frame_ref(fid)})
        return out

    def frames_in_range(self, start_ms, end_ms) -> list[dict]:
        """Read-only frame candidates for a section time window.

        Used by the renderer when the Planner marks a section `media=required`
        but the section's assertions have no per-assertion frame_refs. This does
        not create evidence or modify the substrate.
        """
        try:
            start = float(start_ms)
            end = float(end_ms)
        except (TypeError, ValueError):
            return []
        out = []
        for fid, rec in self._frames().items():
            t = rec.get("t_ms")
            if not isinstance(t, (int, float)) or not (start <= t <= end):
                continue
            if not self.frame_available(self.frame_ref(fid)):
                continue
            out.append({**rec, "frame_ref": self.frame_ref(fid)})
        return out

    # ------------------------------------------------------------ provenance

    def provenance(self) -> dict:
        return {
            "video_id": self.video_id,
            "source_sha256": dict(self.source_sha256),
            "source_files": dict(self.source_files),
            "assertion_count": len(self.assertions),
            "unit_count": len(self.units),
            "relation_count": len(self.relations),
        }

    def evidence_input_hash(self, keys: Iterable[str] | None = None) -> str:
        """对写入/读取实际依赖的证据文件做 canonical hash。

        `keys` 默认覆盖 assertions/relations/units/contract/corrections/ledger/frames。
        旧的 v0 只覆盖 assertions/units/contract；这里补全输入闭包。
        """
        keys = tuple(keys or ("assertions", "relations", "units", "contract",
                              "corrections", "ledger", "frames_vlm", "frames_index"))
        payload = {k: self.source_sha256.get(k) for k in keys}
        return "sha256:" + _sha256_text(json.dumps(payload, sort_keys=True,
                                                   ensure_ascii=False, separators=(",", ":")))

    def is_stale(self, recorded: dict | None) -> tuple[bool, list[str]]:
        recorded = recorded or {}
        issues = []
        for key in ("assertions", "units", "contract"):
            if self.source_sha256.get(key) is None:
                issues.append(key)
            elif recorded.get(key) != self.source_sha256.get(key):
                issues.append(key)
        for key in ("relations", "corrections", "ledger", "frames_vlm", "frames_index"):
            if key in recorded and recorded.get(key) != self.source_sha256.get(key):
                issues.append(key)
        return (not issues, issues)


def _load_frames_vlm(root: Path) -> tuple[dict, list[str], str | None]:
    """合并 frames_vlm*.json；后读非空覆盖，空文本不覆盖非空。"""
    paths = sorted(root.glob("frames_vlm*.json"))
    merged: dict[str, dict] = {}
    for p in paths:
        doc = _read_json(p, {})
        for fid, rec in (doc.get("per_frame") or {}).items():
            prev = merged.get(fid)
            if prev is None:
                merged[fid] = rec
                continue
            new_text = (rec.get("text") or "").strip()
            old_text = (prev.get("text") or "").strip()
            if new_text or not old_text:
                merged[fid] = rec
    hashes = {p.name: _sha256_file(p) for p in paths if p.exists()}
    composite = None
    if hashes:
        composite = "sha256:" + _sha256_text(
            json.dumps(hashes, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    return {"per_frame": merged}, [str(p) for p in paths], composite
