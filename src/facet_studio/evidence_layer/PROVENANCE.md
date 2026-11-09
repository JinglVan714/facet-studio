# Provenance

- Copied from an internal read-only source on 2026-11-07.
- Only source code was copied; `data/`, `runs/`, `tools/ffmpeg.exe`, `.env`, cookies and git history were not copied.
- Path constants were adapted to `FACET_STUDIO_PROJECT_ROOT` / `FACET_STUDIO_DATA_ROOT` / `FACET_STUDIO_SETTINGS_ROOT`.
- Original project tests are kept in the local ignored backup `vendor/evidence_core/`; they passed 17/17 with a small sample before integration.
- This package is the evidence layer (acquisition → ASR/VLM → substrate). It does not generate the product `content.md`; `facet_studio.ingest` bridges to `writing_v4.content_manuscript`.
