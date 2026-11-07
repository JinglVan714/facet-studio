# P5 证据层迁移（2026-11-07）

> 来源：`D:\秋招\个人作品\知识底稿核心-clean`（只读探索，再由人工确认后复制）。
> 目标：新 BV / 本地视频 → 下载/抽帧/ASR/VLM/substrate → `content.md + figures` → 现有写作 workflow。
> 不是 writing 层；写作层仍只读 content manuscript。

## 1. 迁移了什么

- 代码：`src/facet_studio/evidence_layer/`（`lmind` 包整体，排除 `__pycache__`）。
- 配置：`settings/params.json`、`settings/pricing.json`。
- 依赖：`requirements.txt` 增加 `yt-dlp`；其余 `av/dashscope/imageio-ffmpeg/scenedetect/Pillow/imagehash/numpy` 已在依赖中。
- 桥接：`src/facet_studio/ingest.py`；MCP 工具 `ingest_source`。
- 未复制：`data/`（原始媒体/帧/ASR/cookies）、`runs/`、`tools/ffmpeg.exe`、`.env`、外部 `.git`。

原始最小备份在本地 `vendor/evidence_core/`（已 gitignore，不入库）；集成副本在 `src/facet_studio/evidence_layer/`。

## 2. 路径与配置

- `PROJECT_ROOT`：`FACET_STUDIO_PROJECT_ROOT` 或项目根。
- `DATA_DIR`：`FACET_STUDIO_DATA_ROOT` 或 `<project>/data`。
- `SETTINGS_DIR`：`FACET_STUDIO_SETTINGS_ROOT` 或 `<project>/settings`。
- `COOKIES_PATH`：`<data>/cookies/bilibili.txt`（可选；存在才传给 yt-dlp；不读内容、不提交）。
- `.env`：`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DASHSCOPE_API_KEY`；VLM/ASR 需要 `DASHSCOPE_API_KEY`。
- 模型默认：ASR `qwen-audio-3.0-asr-flash-streaming`；VLM `qwen3.8-27b`（fallback `qwen3.7-max-2026-06-08`）；L1 `deepseek-flash`。
- `settings/params.json` 目前是登记表，代码实际默认值在 `evidence_layer/constants.py`。

## 3. 链路

```text
ingest_source(target)
  → acquire_url / acquire_local
  → data/<video_id>/source.json + raw media
  → run_ingest(profile)
       frames + ASR (layer0)
       VLM frame captions
       contract + units + assertions/relations (L1)
       manifest
  → content_manuscript.build_content_manuscript
  → runs/writing_rebuild_2026-11-04/<video_id>/content_final_v3/content.md + figures/
```

之后正常走 `list_sources → resolve_source → start_workflow/plan_article → ...`；`_content_path` 已经会读这个缓存路径。

## 4. 验证（2026-11-07）

- 复制备份 `vendor/evidence_core`：`pytest -q` → **17 passed**（使用一个小体积 sample：substrate + frames_index + frames_vlm JSON；不含媒体）。
- `lmind.evidence_mcp.server --selftest --data-dir <project>/data` → 通过；writer 取帧权限检查 `permission_denied`。
- `lmind.audio` / `acquire_local`：本地视频登记可用；`source.json` 写入成功，`media_has_av_streams=True`。
- `run_ingest` 在缓存 metadata 上复用已有 frames/ASR/VLM/contract/assertions，无模型调用；manifest checks 正常。
- `content_manuscript` 从证据层数据重建 BV17：**4,213 字 / 10 图**（与缓存 `content_final_v3` 一致）。
- 集成测试：`tests/writing_v4/test_ingest.py`（mock acquisition/ingest/content）通过；全量 **580 passed**。

## 5. 尚未验证 / 注意

- **没有真实跑新视频下载 + ASR/VLM 端到端**；需要网络、`DASHSCOPE_API_KEY`、可选 cookie。下一步验收：一条没缓存的 BV/本地视频跑完整链路并人工看产物。
- 源项目没有 CLI；入口是 Python API。`run_ingest` 不负责下载，必须先 acquire。
- `run_ingest` 的 VLM 失败批次默认拒绝继续；显式 `allow_partial_vlm=True` 才接受 partial。
- `profile="quality"` 才有 scene 帧；`fast` 只用固定 30s 帧。内容稿默认用 quality 以获得更多帧候选。
- 证据层与 Evidence MCP 仍可独立使用；产品 MCP 目前只暴露 `ingest_source`，不暴露全部 evidence tools。
- 不要复制/读取 `data/cookies/bilibili.txt`；不要把 `vendor/` 或 `data/` 提交。
