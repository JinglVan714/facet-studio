"""End-to-end ingest orchestration (layer 0 → VLM → contract → L1).

This is a general workflow, not a per-video script. It reuses existing
intermediates unless `force=True`, so rerunning is cheap and auditable.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .constants import DATA_DIR
from .frame_transcribe import (DEFAULT_VLM_MODEL, select_fast_frames,
                               transcribe_frames)
from .pipeline import step_frames, step_manifest, step_transcribe


def _exists(video_id: str, *parts: str) -> bool:
    return (DATA_DIR / video_id).joinpath(*parts).exists()


def run_ingest(video_id: str, *, profile: str = "fast", force: bool = False,
               vlm_concurrency: int = 4, l1_concurrency: int = 4,
               max_scene_frames: int = 12, model: str = "deepseek-flash",
               vlm_model: str = DEFAULT_VLM_MODEL,
               vlm_batch_size: int = 8,
               allow_partial_vlm: bool = False,
               scene: bool | None = None,
               print_summary: bool = True) -> dict:
    t_all = time.time()
    stages: dict[str, float] = {}
    # Fast profile is transcript + fixed 30s frames only. Scene detection and
    # transcription are an explicit quality/opt-in cost.
    use_scene = (profile == "quality") if scene is None else bool(scene)
    root = DATA_DIR / video_id
    if not (root / "source.json").exists():
        raise FileNotFoundError(f"没有 {root / 'source.json'}，请先跑 acquire")

    # Layer 0: only run missing stages; ASR and frame extraction can overlap.
    t = time.time()
    jobs = []
    if force or not (root / "frames_index.json").exists():
        jobs.append(("frames", lambda v: step_frames(v, do_scene=use_scene)))
    if force or not (root / "transcript" / "transcript.json").exists():
        jobs.append(("asr", step_transcribe))
    if len(jobs) == 2:
        with ThreadPoolExecutor(max_workers=2) as ex:
            results = {name: ex.submit(fn, video_id) for name, fn in jobs}
            for f in results.values():
                f.result()
    else:
        for _, fn in jobs:
            fn(video_id)
    stages["layer0"] = round(time.time() - t, 1)

    # VLM: fixed frames always; scene frames only when scene is enabled.
    t = time.time()
    vlm_jobs = []
    for dir_name in (("frames", "frames_scene") if use_scene else ("frames",)):
        summary_path = root / f"frames_vlm__{dir_name}.json"
        if summary_path.exists() and not force:
            try:
                prev = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                prev = {}
            if not (prev.get("failed_batches") or []):
                continue
            # A previous run left failed batches; retry instead of silently
            # treating the partial transcript as complete.
        only = None
        if profile == "fast" and dir_name == "frames_scene":
            only = select_fast_frames(video_id, dir_name, max_scene_frames)
        vlm_jobs.append((dir_name, only))

    def _one_vlm(dir_name: str, only):
        return transcribe_frames(video_id, frame_dir_name=dir_name,
                                 model=vlm_model, batch_size=vlm_batch_size,
                                 concurrency=vlm_concurrency, only_files=only)

    if len(vlm_jobs) > 1:
        with ThreadPoolExecutor(max_workers=len(vlm_jobs)) as ex:
            summaries = list(ex.map(lambda job: _one_vlm(*job), vlm_jobs))
    else:
        summaries = [_one_vlm(*job) for job in vlm_jobs]
    failed = {name: summary.get("failed_batches") or []
              for name, summary in zip((j[0] for j in vlm_jobs), summaries)
              if summary.get("failed_batches")}
    if failed and not allow_partial_vlm:
        raise RuntimeError(
            "VLM 有失败批次，拒绝用不完整帧文本继续 ingest："
            f"{failed}；可用 --force 重跑或用 --allow-partial-vlm 显式接受")
    vlm_ran = bool(vlm_jobs)
    stages["vlm"] = round(time.time() - t, 1)

    # Contract: one model call over the whole transcript's units.
    t = time.time()
    contract_path = root / "substrate" / "contract.json"
    contract_rebuilt = force or not contract_path.exists()
    if contract_rebuilt:
        from .contract import _linearize, build_contract, write_contract
        from .corpus import load_corpus
        from .extract_l1 import _client
        from .units import build_units
        corpus = load_corpus(video_id)
        units, _ = build_units(corpus)
        contract = build_contract(_client(), model, _linearize(units))
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        write_contract(contract, contract_path.parent)
    stages["contract"] = round(time.time() - t, 1)

    # L1: chunk checkpoints make this resumable; skip if already present.
    t = time.time()
    assertions = root / "substrate" / "assertions.jsonl"
    if force or contract_rebuilt or vlm_ran or not assertions.exists():
        from .run_l1 import run_l1_units
        report = run_l1_units(video_id, model=model, concurrency=l1_concurrency)
        stages["l1"] = round(time.time() - t, 1)
        l1_summary = {"assertions": report.get("assertion_count"),
                      "relations": report.get("relation_count")}
    else:
        l1_summary = {"skipped": "assertions.jsonl exists"}
        stages["l1"] = round(time.time() - t, 1)

    t = time.time()
    manifest = step_manifest(video_id)
    stages["manifest"] = round(time.time() - t, 1)
    out = {
        "video_id": video_id,
        "profile": profile,
        "scene": use_scene,
        "wall_clock_s": round(time.time() - t_all, 1),
        "stages": stages,
        "l1": l1_summary,
        "contract": str(contract_path),
        "manifest": str(root / "manifest.json"),
        "checks": manifest.get("checks"),
    }
    if print_summary:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return out
