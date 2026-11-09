"""项目级常量与路径。基线数字由 2026-10-13 的本机实测得出（见 docs/layer0-probe-report.md）。

原则（PROJECT-BRIEF 硬约束 1）：能配置的都不写死在流程代码里；
凡「为某类素材设的习惯」一律登记为可调参数（见 settings/params.json）。
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(
    os.getenv("FACET_STUDIO_PROJECT_ROOT")
    or Path(__file__).resolve().parents[3]
).resolve()


def load_env() -> None:
    """把仓库根的 `.env` 读进环境变量（`setdefault` ⇒ 幂等、不覆盖已有值）。

    **放在 constants 而不是 extract_l1**：它是全项目最底层的模块，谁都 import 得到，
    而 `tracing` 判断「LANGFUSE_* 配了没有」必须在这里之前完成。
    上一版它只写在 `extract_l1._load_env` 里、由 `_client()` 调用——
    于是 `tracing` 先跑时看到的是"未配置"，打点因此静默不生效（探针抓到的）。
    **同一件事只能有一份实现**（spec §8.0d 的教训）。
    """
    p = PROJECT_ROOT / ".env"
    if not p.exists():
        return
    import os

    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


# Load the project .env before deriving paths.  A `FACET_STUDIO_DATA_ROOT`
# that exists only in .env must be visible to DATA_DIR; deriving paths first
# would freeze the default and silently ignore the configured root.
load_env()

DATA_DIR = Path(
    os.getenv("FACET_STUDIO_DATA_ROOT") or PROJECT_ROOT / "data"
).expanduser().resolve()
RESULTS_DIR = PROJECT_ROOT / "results"
SETTINGS_DIR = Path(
    os.getenv("FACET_STUDIO_SETTINGS_ROOT") or PROJECT_ROOT / "settings"
).expanduser().resolve()
TOOLS_DIR = PROJECT_ROOT / "tools"

COOKIES_PATH = DATA_DIR / "cookies" / "bilibili.txt"

# ---- 音频 ----
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2            # s16
CHANNELS = 1

# ---- 抽帧（可调参数，登记于 manifest）----
DEFAULT_FRAME_INTERVAL_S = 30.0     # 固定间隔档：屏幕录制类素材的基线
DEFAULT_SCENE_THRESHOLD = 27.0      # 场景切分档：实拍类素材更适用
DEFAULT_MIN_SCENE_LEN_S = 2.5
DEFAULT_SCENE_MAX_SCENES = 400      # 防止切分失效时产生过多帧
DEFAULT_FRAME_HEIGHT = 720
DEFAULT_PHASH_DISTANCE = 8          # 仅用于标记重复，不删帧

# ---- ASR ----
# 3.0 free tier can be exhausted (status=44); 3.1 is the current working
# streaming model on the same endpoint and supports word timestamps.
DEFAULT_ASR_MODEL = "qwen-audio-3.1-asr-flash-streaming"
DEFAULT_ASR_WS_ENDPOINT = "wss://maas.qianwenaiapi.com/api-ws/v1/inference"
DEFAULT_VLM_MODEL = "qwen3.8-27b"
# 额度用尽时的备选（用户提供）：同理是视觉模型，接口一致，只换 model 名
DEFAULT_VLM_FALLBACK = "qwen3.7-max-2026-06-08"
DEFAULT_VLM_ENDPOINT = "https://maas.qianwenaiapi.com/api/v1"

# ---- 语言契约（D6/§8-6 的显式声明：底稿跟随素材语言）----
DEFAULT_OUTPUT_LANGUAGE = "source"
