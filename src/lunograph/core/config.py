"""Project paths and environment configuration.

Secrets are read from environment / ``.env`` and are never written to
artifacts or logs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_ENV_LOADED = False


def project_root() -> Path:
    override = os.getenv("LUNOGRAPH_PROJECT_ROOT")
    if override:
        return Path(override).resolve()
    # .../src/lunograph/core/config.py -> project root
    return Path(__file__).resolve().parents[3]


def parse_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def load_project_env(path: Path | None = None, *, force: bool = False) -> None:
    """Load ``.env`` without overwriting real environment variables."""
    global _ENV_LOADED
    if _ENV_LOADED and not force:
        return
    env_path = path or (project_root() / ".env")
    for key, value in parse_env_file(env_path).items():
        os.environ.setdefault(key, value)
    _ENV_LOADED = True


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_root: Path
    runs_root: Path
    skills_root: Path
    prompts_root: Path
    model: str
    base_url: str | None
    api_key: str | None = field(repr=False)
    # The 64k verifier can spend close to three minutes on reasoning; a
    # 180s client timeout cuts it at the finish line.  Keep headroom.
    timeout_s: float = 300.0
    # deepseek-flash spends a large share of the budget on reasoning before
    # emitting JSON; 32k truncates longer verification prompts (the final
    # verifier can burn the whole cap on reasoning).  Keep headroom and let
    # the model finish; the total budget below remains the real guardrail.
    max_output_tokens: int = 65536
    budget_max_calls: int = 32
    budget_max_tokens: int = 400_000
    section_concurrency: int = 3

    @property
    def provider_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def public_summary(self) -> dict[str, object]:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "provider_configured": self.provider_configured,
            "data_root": str(self.data_root),
            "runs_root": str(self.runs_root),
            "section_concurrency": self.section_concurrency,
        }


def get_settings(*, load_env: bool = True) -> Settings:
    if load_env:
        load_project_env()
    root = project_root()

    def _path(env_key: str, default: Path) -> Path:
        raw = os.getenv(env_key)
        return Path(raw).expanduser().resolve() if raw else default

    return Settings(
        project_root=root,
        data_root=_path("LUNOGRAPH_DATA_ROOT", root / "data"),
        runs_root=_path("LUNOGRAPH_RUNS_ROOT", root / "runs"),
        skills_root=_path("LUNOGRAPH_SKILLS_ROOT", root / "skills"),
        prompts_root=root / "src" / "lunograph" / "prompts",
        model=os.getenv("LUNOGRAPH_MODEL") or os.getenv("DEEPSEEK_MODEL", ""),
        base_url=(
            os.getenv("LUNOGRAPH_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL")
            or None
        ),
        api_key=os.getenv("LUNOGRAPH_API_KEY") or os.getenv("DEEPSEEK_API_KEY"),
        timeout_s=float(os.getenv("LUNOGRAPH_TIMEOUT_S", "300")),
        max_output_tokens=int(os.getenv("LUNOGRAPH_MAX_OUTPUT_TOKENS", "65536")),
        budget_max_calls=int(os.getenv("LUNOGRAPH_BUDGET_MAX_CALLS", "32")),
        budget_max_tokens=int(os.getenv("LUNOGRAPH_BUDGET_MAX_TOKENS", "400000")),
        section_concurrency=max(
            1, int(os.getenv("LUNOGRAPH_SECTION_CONCURRENCY", "3"))
        ),
    )
