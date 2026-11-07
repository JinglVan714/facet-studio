"""层 1 · 运行器：语料 → 知识底稿（断言 + 关系 + 校验报告）。

流程：load_corpus → make_chunks → 逐片抽取 → 校验 → 落盘。
落盘格式（可 diff、可增量、可回链）：
    data/<video_id>/substrate/assertions.jsonl
    data/<video_id>/substrate/relations.jsonl
    data/<video_id>/substrate/layer1_report.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .constants import DATA_DIR
from .corpus import load_corpus, make_chunks
from .extract_l1 import DEFAULT_MODEL, extract_chunk, _client, _load_env  # noqa: F401
from .validate_l1 import validate, write_report, write_report as write_report_suffixed


def substrate_dir(video_id: str) -> Path:
    return DATA_DIR / video_id / "substrate"


def _chunk_cache_key(chunk: dict, model: str, frames_hash: str = "") -> str:
    """逐片检查点的键：提示词版本 + 模型 + 该片 owned 单元的内容指纹。

    三者任一变化就重跑该片。**要在这里显式带上提示词版本**——否则改了提示词却命中旧缓存，
    会得到"以为升级了其实没跑"的假象（`extract_l1.extract_chunk_to` 的旧缓存就有这个隐患，
    见 spec I4：缓存键必须含 prompt_version + 配置 hash）。
    """
    import hashlib
    from .extract_l1 import SCHEMA_VERSION
    from .prompts_l1 import PROMPT_VERSION_UNITS
    from .units import UNIT_VERSION, config_hash

    # 五样都要带：提示词版本、单元定义版本、单元配置 hash、**schema 版本**、模型。
    # 少了 schema 版本，改了校验规则仍会命中旧缓存 —— 那正是这次要避免的假象。
    blob = "|".join([PROMPT_VERSION_UNITS, UNIT_VERSION, config_hash(),
                     SCHEMA_VERSION, model, frames_hash, *chunk["owned"]])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def reanchor(video_id: str) -> dict:
    """重算已有断言的锚点（不重跑模型）：用于算法改进后把旧产物升级到字级。

    ⚠️ 2026-10-16（审计 A1 的同族）：它**就地覆盖 `assertions.jsonl`**，此前也绕开闸门。
    这是就地写，但**不能直接开 `allow_overwrite=True` 了事**——D1 的意思是
    "覆盖前必须并存一份"。所以先 `backup_verified` 再写；备份不通过就中止。
    锚点是可复算的（同样的语料 + 同样的算法 ⇒ 同样的结果），
    备份的代价只有一次，换来的是"升级完发现算法更差"时能退回去。
    """
    import time as _t

    from .anchor import enrich_assertion_anchors
    from .artifacts import backup_verified, OverwriteRefused, guarded_write_jsonl

    corpus = load_corpus(video_id)
    out_dir = substrate_dir(video_id)
    a_path = out_dir / "assertions.jsonl"
    if not a_path.exists():
        raise FileNotFoundError(f"没有 {a_path}")
    bak = backup_verified(a_path, f"_preanchor{_t.strftime('%Y%m%d-%H%M%S')}")
    if bak is None:
        raise SystemExit(f"[reanchor] 拒绝就地重算：{a_path.name} 的备份未通过校验。")
    assertions = [json.loads(l) for l in a_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    before = sum(1 for a in assertions for an in (a.get("anchors") or [])
                 if an.get("precision") == "word")
    for a in assertions:
        a["anchors"] = [{"sid": x.get("sid"), "start_ms": x.get("start_ms"),
                         "end_ms": x.get("end_ms")} for x in (a.get("anchors") or [])]
        enrich_assertion_anchors(a, corpus)
    after = sum(1 for a in assertions for an in (a.get("anchors") or [])
                if an.get("precision") == "word")
    try:
        r = guarded_write_jsonl(a_path, assertions, what="assertions.jsonl",
                                allow_overwrite=True)     # 备份已在上面验过
    except OverwriteRefused as e:                          # 到这儿说明 allow_overwrite 没生效
        raise SystemExit(f"[reanchor] {e}") from e
    res = {"video_id": video_id, "assertions": len(assertions),
           "word_level_before": before, "word_level_after": after,
           "backup": bak.name, "written": r["written"]}
    print(f"[reanchor] 字级锚点 {before} -> {after} / "
          f"{sum(len(a.get('anchors') or []) for a in assertions)} 个锚点；"
          f"备份 {bak.name}（{r['reason']}）")
    return res


def prepare_l1(video_id: str, *, chunk_minutes: float = 15.0,
               use_frames: bool = True) -> dict:
    """**L1 的唯一切分入口**——`run_l1_units` 与执行器共用它。

    为什么必须共用：此前执行器自己走 `make_chunks`（时间窗）+ `extract_chunk_to`（v4），
    与 `lmind l1` 完全分叉。实测 `BV1B5411A7ax` 在执行器口径下只切出 **1 片**（整片一次全片调用），
    而 `lmind l1` 切 8 片。**同一个项目里两条 L1，跑哪条看你敲了哪个命令**——这是最坏的一种不一致。

    分片优先级：有 `contract.json` 用契约的语义分段，否则退回单元时间窗。
    """
    from .units import build_units, make_unit_chunks

    corpus = load_corpus(video_id)
    if not use_frames:
        corpus["frames"] = {}
    units, ustats = build_units(corpus)
    units_by_id = {u["unit_id"]: u for u in units}
    corpus["units_by_id"] = units_by_id      # 供校验器做"引文 == 单元拼接"核对

    ctr_path = substrate_dir(video_id) / "contract.json"
    if ctr_path.exists():
        from .contract import make_contract_chunks

        ctr = json.loads(ctr_path.read_text(encoding="utf-8"))
        chunks = make_contract_chunks(ctr, units)
        chunking = "contract"
    else:
        chunks = make_unit_chunks(units, chunk_minutes=chunk_minutes)
        chunking = "time_window"
    return {"corpus": corpus, "units": units, "units_by_id": units_by_id,
            "ustats": ustats, "chunks": chunks, "chunking": chunking}


def extract_one_chunk(chunk: dict, corpus: dict, units_by_id: dict, model: str,
                      ckpt_dir: Path, frames_hash: str = "") -> dict:
    """单片抽取 + **逐片检查点**——`run_l1_units` 与执行器共用。

    检查点键含 提示词版本 / 单元定义版本 / 配置 hash / schema 版本 / 模型 / owned 单元，
    任一变化就重跑该片（否则会得到"以为升级了其实没跑"的假象，见 spec I4）。
    """
    from .extract_l1 import extract_chunk_units

    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ck = ckpt_dir / f"{chunk['chunk_id']}.json"
    key = _chunk_cache_key(chunk, model, frames_hash=frames_hash)
    if ck.exists():
        try:
            cached = json.loads(ck.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cached = None
        if cached and cached.get("_key") == key:
            return {**cached, "_cached": True}
    r = extract_chunk_units(_client(), corpus, units_by_id, chunk, model)
    r = {**r, "_key": key}
    ck.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    return {**r, "_cached": False}


def run_l1_units(video_id: str, *, model: str = DEFAULT_MODEL, chunk_minutes: float = 15.0,
                 limit_chunks: int | None = None, start_chunk: int = 0,
                 use_frames: bool = True, write: bool = True,
                 out_suffix: str = "", allow_overwrite: bool = False,
                 concurrency: int = 1) -> dict:
    """层 1（单元制 v5）：语料 → 单元 → 底稿。

    与 `run_l1` 的区别只在**证据的产出方**：
    - v4：模型自己写 `quote`（事后逐字校验，是一条比率：实测 0.50→0.996）
    - v5：**模型只挑 `unit_ids`，`quote` 由代码从单元原文拼接** ⇒ 逐字性由构造成立，不是比率

    另新增 `kind` / `status` / `boundary`（spec §2.6 的 statement 形状），
    以及 `corrections`——模型发现 ASR 错字时写成**待审建议**，不直接改证据。
    """
    import time as _t
    from .units import write_units
    from .extract_l1 import SCHEMA_VERSION
    from .prompts_l1 import PROMPT_VERSION_UNITS

    t_all = _t.time()
    prep = prepare_l1(video_id, chunk_minutes=chunk_minutes, use_frames=use_frames)
    corpus, units = prep["corpus"], prep["units"]
    units_by_id, ustats, chunking = prep["units_by_id"], prep["ustats"], prep["chunking"]
    # Frame text is evidence input: a VLM retry must invalidate chunk
    # checkpoints, otherwise the new frame text never reaches L1.
    import hashlib
    frame_blob = json.dumps(
        {k: (v.get("text") or "") for k, v in sorted((corpus.get("frames") or {}).items())},
        ensure_ascii=False, sort_keys=True)
    frames_hash = hashlib.sha256(frame_blob.encode("utf-8")).hexdigest()[:16]
    chunks = prep["chunks"]
    if chunking == "contract":
        n_seg = len(json.loads((substrate_dir(video_id) / "contract.json")
                               .read_text(encoding="utf-8")).get("segments") or [])
        print(f"[l1u] 分片来源：一致性契约（{n_seg} 段）")
    else:
        print("[l1u] 分片来源：时间窗（无 contract.json；先跑 lmind contract 可换成语义分段）")
    if limit_chunks is not None:
        chunks = chunks[start_chunk:start_chunk + limit_chunks]

    print(f"[l1u] {video_id}: 单元 {ustats['unit_count']}（内容 {ustats['content_unit_count']}）"
          f"、帧 {len(corpus.get('frames') or {})}、分片 {len(chunks)}")

    out_dir = substrate_dir(video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    if write:
        # units.jsonl 是共用的；过闸门（同版本幂等跳过，换了单元定义则拒绝）
        write_units(video_id, units, ustats, out_dir, allow_overwrite=allow_overwrite)

    assertions, relations, chunk_records = [], [], []
    ckpt_dir = out_dir / "_l1u_chunks"          # 逐片检查点：崩溃/中断只丢当前片
    workers = max(1, min(int(concurrency or 1), len(chunks) or 1))
    if workers <= 1:
        results = [extract_one_chunk(c, corpus, units_by_id, model, ckpt_dir,
                                     frames_hash=frames_hash)
                   for c in chunks]
    else:
        # Chunks are independent (context tail is copied into each prompt);
        # the OpenAI client is documented as thread-safe and shared.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(
                lambda c: extract_one_chunk(c, corpus, units_by_id, model, ckpt_dir,
                                            frames_hash=frames_hash),
                chunks))
    for chunk, r in zip(chunks, results):
        if r.get("_cached"):
            print(f"[l1u] {chunk['chunk_id']}: 命中检查点，跳过模型调用")
        assertions.extend(r["assertions"])
        relations.extend(r["relations"])
        rec = r["record"]
        st = r.get("status") or {}
        chunk_records.append({k: v for k, v in rec.items() if k != "raw"} | {"status": st})
        flag = "  ⚠ ESCALATED" if st.get("escalated") else (
            f"  （修复 {st['repairs']} 次）" if st.get("repairs") else "")
        drop = st.get("dropped_no_owned_unit") or 0
        print(f"[l1u] {rec['chunk_id']}: owned={len(chunk['owned'])} 单元 -> "
              f"{len(r['assertions'])} 断言 / {len(r['relations'])} 关系 ({rec['elapsed_s']}s)"
              + (f"  丢弃 {drop} 条（无 owned 单元）" if drop else "") + flag)

    report = validate(assertions, relations, corpus, chunk_ownership={})
    report["video_id"] = video_id
    report["total_elapsed_s"] = round(_t.time() - t_all, 1)
    report["model"] = model
    report["chunk_minutes"] = chunk_minutes
    report["chunks"] = chunk_records
    report["chunk_count"] = len(chunks)
    report["l1_mode"] = "units/v5"
    report["chunking"] = chunking
    report["schema_version"] = SCHEMA_VERSION
    report["prompt_version"] = PROMPT_VERSION_UNITS
    report["unit_stats"] = ustats
    # 帧引用是偏好不是门禁，但必须**可见**——否则"视觉线索没进证据链"会重新变成盲区
    n_with = sum(1 for a in assertions if a.get("frame_refs"))
    report["frame_refs"] = {
        "assertions_with_frame": n_with,
        "assertions_total": len(assertions),
        "rate": round(n_with / max(1, len(assertions)), 4),
        "total_refs": sum(len(a.get("frame_refs") or []) for a in assertions),
        "hard_requirement": False,
        "note": "帧引用不参与门禁（实测硬性要求会让修复链削减产出：95→37 条）；此处只报数",
    }

    if write:
        # ⚠️ `out_suffix` 必须生效：2026-10-15 因为这里漏了后缀，把 BV1B5411A7ax 的
        # v4 assertions.jsonl 覆盖掉了（v5 直接顶上）。**换版必须先并存，不许就地覆盖。**
        # 现在再加一道代码级闸门（`lmind/artifacts.py`）——纪律写在文档里挡不住手滑。
        from .artifacts import guarded_write_jsonl, OverwriteRefused

        try:
            for rows, name in ((assertions, f"assertions{out_suffix}.jsonl"),
                               (relations, f"relations{out_suffix}.jsonl")):
                res = guarded_write_jsonl(out_dir / name, rows, what=name,
                                          allow_overwrite=bool(out_suffix) or allow_overwrite)
                if not res["written"]:
                    print(f"[l1u] {name}：{res['reason']}")
        except OverwriteRefused as e:
            raise SystemExit(f"[l1u] {e}") from e
        write_report_suffixed(video_id, report, out_dir, out_suffix)

    cov, anch = report["coverage"], report["anchors"]
    print(f"[l1u] 断言 {report['assertion_count']} / 关系 {report['relation_count']} / "
          f"覆盖 {cov['coverage_ratio']} / 冲突 {len(report['ownership_conflicts'])} / "
          f"重复 {len(report['duplicate_assertions'])}")
    print(f"[l1u] 锚点：单元级 {anch['unit_level']}（占 {anch['unit_or_word_ratio']}）；"
          f"引文命中 {anch['quote_hit_levels']}")
    fr = report["frame_refs"]
    print(f"[l1u] 校验错误 {report['error_count']} 条；极性候选 {report['polarity']['suspect_count']}；"
          f"帧引用 {fr['assertions_with_frame']}/{fr['assertions_total']}（{fr['rate']:.0%}，仅报数）")
    if report["error_count"]:
        for e in report["errors"][:3]:
            print(f"       - {e['assertion']}: {e['errors'][0]}")
    print(f"[l1u] -> {out_dir}")
    return report


def revalidate(video_id: str, suffix: str = "", *, write: bool = True) -> dict:
    """**只重算报告，不调模型**：读已有的 assertions/relations 重跑校验。

    用途：校验器/指标改了之后，把已经付过钱的那批产物重新评一遍——
    否则"改了度量"和"重跑一遍"被绑死，等于每次改指标都要再花一次 token。
    **只读断言、写报告**，不动 `assertions*.jsonl` 一个字节。
    """
    from .extract_l1 import SCHEMA_VERSION
    from .prompts_l1 import PROMPT_VERSION_UNITS
    from .units import build_units

    out_dir = substrate_dir(video_id)
    a_path = out_dir / f"assertions{suffix}.jsonl"
    r_path = out_dir / f"relations{suffix}.jsonl"
    if not a_path.exists():
        raise FileNotFoundError(f"没有 {a_path}")
    assertions = [json.loads(l) for l in a_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    relations = ([json.loads(l) for l in r_path.read_text(encoding="utf-8").splitlines() if l.strip()]
                 if r_path.exists() else [])
    corpus = load_corpus(video_id)
    units, ustats = build_units(corpus)
    corpus["units_by_id"] = {u["unit_id"]: u for u in units}

    report = validate(assertions, relations, corpus, chunk_ownership={})
    prev = out_dir / f"layer1_report{suffix}.json"
    if prev.exists():
        try:                                   # 保留不重算的元信息（耗时、分片明细、模式）
            old = json.loads(prev.read_text(encoding="utf-8"))
            for k in ("total_elapsed_s", "chunks", "chunk_count", "model",
                      "chunking", "chunk_minutes", "frame_refs", "l1_mode"):
                if k in old:
                    report[k] = old[k]
        except Exception:  # noqa: BLE001
            pass
    report["video_id"] = video_id
    report["schema_version"] = SCHEMA_VERSION
    report["prompt_version"] = PROMPT_VERSION_UNITS
    report["unit_stats"] = ustats
    report["revalidated"] = True
    # 重算时间必须落在报告里：旧报告只有一个更早的 `validated_at`，
    # 读的人无法判断它是不是按当前校验器算的（阶段③ H2）。
    report["revalidated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    uc = report["unit_coverage"]
    print(f"[revalidate] {video_id}{suffix}: 断言 {report['assertion_count']} / "
          f"关系 {report['relation_count']} / 错误 {report['error_count']}")
    print(f"[revalidate] 句子级覆盖 {report['coverage']['coverage_ratio']} "
          f"vs **单元级覆盖 {uc.get('unit_coverage_ratio')}**"
          f"（{uc.get('cited_unit_count')}/{uc.get('content_unit_count')} 内容单元，"
          f"未引分档 {uc.get('uncited_len_buckets')}）")
    if write:
        write_report_suffixed(video_id, report, out_dir, suffix)
    return report


def run_l1(video_id: str, *, model: str = DEFAULT_MODEL, chunk_minutes: float = 15.0,
           limit_chunks: int | None = None, start_chunk: int = 0,
           use_frames: bool = True, out_suffix: str = "",
           allow_overwrite: bool = False) -> dict:
    """**v4 遗留路径**（模型自己写 `quote`；时间窗分片）。现行管线是 `run_l1_units`。

    ⚠️ 2026-10-16 修（审计 A1）：这个函数此前用**裸 `open("w")`** 写
    `assertions.jsonl` / `relations.jsonl`，是 `artifacts.py` 那道"唯一闸门"
    **唯一没覆盖到的写者**。后果实测：`evals.regenerate_once` 先 `unlink` 当前底稿、
    再调本函数 ⇒ **当前契约版底稿被 v4 时间窗版静默顶掉，绕开 D1/§8.0**。
    现在两个写者都过闸门，且 `--out-suffix` 真正生效（此前 `lmind l1 --no-units
    --out-suffix _x` 会**静默忽略后缀**——与当初那场事故同一个形状）。
    """
    t_all = time.time()
    corpus = load_corpus(video_id)
    if not use_frames:
        corpus["frames"] = {}
    chunks = make_chunks(corpus, chunk_minutes=chunk_minutes)
    if limit_chunks is not None:
        chunks = chunks[start_chunk:start_chunk + limit_chunks]

    print(f"[l1] {video_id}: {len(corpus['order'])} 句、{len(corpus.get('frames') or {})} 帧、"
          f"{len(chunks)} 个分片（chunk_minutes={chunk_minutes}）")

    client = _client()
    out_dir = substrate_dir(video_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    assertions: list[dict] = []
    relations: list[dict] = []
    chunk_records: list[dict] = []

    for chunk in chunks:
        r = extract_chunk(client, corpus, chunk, model, prev_tail_ids=[])
        assertions.extend(r["assertions"])
        relations.extend(r["relations"])
        rec = r["record"]
        st = r.get("status") or {}
        chunk_records.append({k: v for k, v in rec.items() if k != "raw"}
                             | {"status": st})
        flag = ""
        if st.get("escalated"):
            flag = "  ⚠ ESCALATED（兜底链用尽，本片产出不可信）"
        elif st.get("repairs"):
            flag = f"  （修复 {st['repairs']} 次）"
        print(f"[l1] {rec['chunk_id']}: owned={len(chunk['owned'])} 句 "
              f"-> {len(r['assertions'])} 断言 / {len(r['relations'])} 关系 "
              f"({rec['elapsed_s']}s){flag}")

    # 跨片边界的「已知盲区」计数：分片首尾各 3 条断言是可能的跨片端点
    boundary_ids = set()
    for chunk in chunks:
        for a in assertions:
            if a["chunk_id"] == chunk["chunk_id"]:
                pass
    chunk_first_last = {}
    for a in assertions:
        chunk_first_last.setdefault(a["chunk_id"], []).append(a["id"])
    for ids in chunk_first_last.values():
        if len(ids) >= 2:
            boundary_ids.update(ids[:3] + ids[-3:])

    report = validate(assertions, relations, corpus,
                      chunk_ownership={})
    report["video_id"] = video_id
    report["total_elapsed_s"] = round(time.time() - t_all, 1)
    report["model"] = model
    report["chunk_minutes"] = chunk_minutes
    report["chunks"] = chunk_records
    report["cross_chunk_candidates"] = sorted(boundary_ids)
    report["chunk_count"] = len(chunks)

    # 落盘：**过闸门**（见函数 docstring 的 A1 说明）
    from .artifacts import OverwriteRefused, guarded_write_jsonl

    try:
        for rows, name in ((assertions, f"assertions{out_suffix}.jsonl"),
                           (relations, f"relations{out_suffix}.jsonl")):
            res = guarded_write_jsonl(out_dir / name, rows, what=name,
                                      allow_overwrite=bool(out_suffix) or allow_overwrite)
            if not res["written"]:
                print(f"[l1] {name}：{res['reason']}")
    except OverwriteRefused as e:
        raise SystemExit(f"[l1] {e}") from e
    write_report(video_id, report, out_dir, out_suffix)

    cov = report["coverage"]
    atom = report["atomicity"]
    anch = report["anchors"]
    print(f"[l1] 断言 {report['assertion_count']} / 关系 {report['relation_count']} / "
          f"覆盖 {cov['coverage_ratio']}（未覆盖 {len(cov['uncovered_sids'])} 句）/ "
          f"冲突 {len(report['ownership_conflicts'])} / 重复 {len(report['duplicate_assertions'])}")
    print(f"[l1] 原子性：疑似非原子 {atom['suspect_count']}（{atom['suspect_ratio'] * 100:.1f}%），"
          f"断言符号数中位 {atom['text_len_median']}，断言/锚点句长度比中位 {atom['ratio_to_source_median']}")
    print(f"[l1] 锚点：字级 {anch['word_level']} / 句级回退 {anch['sentence_level_fallback']}"
          f"（字级率 {anch['word_level_ratio']}），帧引用 {anch['frame_refs_total']} 处")
    fos = report["frame_offset_stats"]
    print(f"[l1] 校验：错误 {report['error_count']} 条；帧偏差 窗口内 {fos['in_window']} / "
          f"容差内 {fos['within_tolerance']} / 越窗 {fos['out_of_window']}（最大 {fos['max_abs_offset_ms']}ms）")
    if report["error_count"]:
        for e in report["errors"][:3]:
            print(f"       - {e['assertion']}: {e['errors'][0]}")
    print(f"[l1] -> {out_dir}")
    return report
