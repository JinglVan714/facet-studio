"""Prompt registry loader (versioned, hashed, file-backed)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .hashing import file_sha256


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    text: str
    sha256: str
    path: str


class PromptRegistry:
    def __init__(self, prompts_root: Path, snapshot: dict[str, dict] | None = None):
        self.root = prompts_root
        self._snapshot = snapshot or None
        manifest_path = prompts_root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"缺少 prompts manifest: {manifest_path}")
        self._manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

    def load(self, prompt_id: str) -> PromptTemplate:
        if self._snapshot and prompt_id in self._snapshot:
            entry = self._snapshot[prompt_id]
            return PromptTemplate(
                prompt_id=prompt_id,
                version=str(entry.get("version", "0")),
                text=str(entry["text"]),
                sha256=str(entry["sha256"]),
                path=str(entry.get("file", prompt_id)),
            )
        entry = self._manifest.get(prompt_id)
        if not entry:
            raise KeyError(f"prompt 未注册: {prompt_id}")
        path = self.root / entry["file"]
        if not path.exists():
            raise FileNotFoundError(path)
        return PromptTemplate(
            prompt_id=prompt_id,
            version=str(entry.get("version", "0")),
            text=path.read_text(encoding="utf-8"),
            sha256=file_sha256(path),
            path=str(path.name),
        )

    def snapshot(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for prompt_id in self._manifest:
            template = self.load(prompt_id)
            result[prompt_id] = {
                "version": template.version,
                "sha256": template.sha256,
                "file": template.path,
                "text": template.text,
            }
        return result

    def versions(self) -> dict[str, str]:
        if self._snapshot:
            return {k: str(v.get("version", "0")) for k, v in self._snapshot.items()}
        return {k: str(v.get("version", "0")) for k, v in self._manifest.items()}
