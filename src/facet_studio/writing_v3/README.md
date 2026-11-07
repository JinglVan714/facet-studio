# writing_v3

> 当前阶段：substrate v1 已冻结；writing 层从零设计。接口/证据/限制见 [docs/substrate-v1-freeze.md](../../../docs/substrate-v1-freeze.md)。
> substrate v1：transcript / claim_extract / pack_from_claims / light_context / edited_transcript / bind_article / quote_hygiene / generate / trace。
> 实验/历史（不是 writing 基线）：one_call_writer / prose_writer_probe / comprehension_view / writer_view / bind_merged_frames / probe*。
> writing 层不要复用占位 skill `reader_first_explainer`；可参考 trace/usage/cache 实现，不继承 writing 设计。

Pipeline（substrate v1）：

1. `transcript.py` — ASR units → sentences → passages (deterministic).
2. `claim_extract.py` — passages → writing-level claims (1 model call/video).
3. `evidence_pack.py` / `pack_from_claims.py` — claims → EvidencePack (deterministic, coverage-aware).
4. `edited_transcript.py` — pack + passages + sentences → one linear writer-facing text + audit-only `source_map`; full/anchored + auto; no IDs/timecodes, boundary markers, no hard truncation (P0).
5. `one_call_writer.py` — pack + skill + request → reader (1 Writer call; still the structured contract; prose-only is P1).
6. `bind_article.py` — article + pack (+ full transcript / source_map) → deterministic fact/quote/paragraph binding (P0).
7. `trace.py` — trace.jsonl + stage_receipts (inputs/outputs/hashes/counts/decisions/samples).

Commands (from project root; Python 3.11):

```bash
# 1) units -> sentences/passages
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m facet_studio.writing_v3.transcript \
  --units data/<video>/substrate/units.jsonl \
  --contract data/<video>/substrate/contract.json \
  --out-dir runs/v3_poc/<video>_transcript

# 2) passages -> claims (one model call)
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m facet_studio.writing_v3.claim_extract \
  --passages runs/v3_poc/<video>_transcript/passages.json \
  --out-dir runs/v3_poc/<video>_claims

# 3) claims -> EvidencePack
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m facet_studio.writing_v3.pack_from_claims \
  --claims runs/v3_poc/<video>_claims/claims.json \
  --passages runs/v3_poc/<video>_transcript/passages.json \
  --sentences runs/v3_poc/<video>_transcript/sentences.json \
  --snapshot runs/<substrate_run>/evidence_snapshot.json \
  --outline runs/<substrate_run>/temporal_outline.json \
  --knowledge runs/<substrate_run>/knowledge_snapshot.json \
  --request handoffs/2026-10-31/examples/<video>_request.json \
  --contract data/<video>/substrate/contract.json \
  --video-id <video> \
  --out runs/v3_poc/<video>_pack.json \
  --writer-out runs/v3_poc/<video>_writer_view.json \
  --writer-bundle-dir runs/v3_poc/<video>_bundle
# optional: --writer-part-max-chars 2000 for C part grouping

# 4) edited transcript (writer-facing text + audit source_map; no model)
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m facet_studio.writing_v3.edited_transcript \
  --pack runs/v3_poc/<video>_pack.json \
  --passages runs/v3_poc/<video>_transcript/passages.json \
  --sentences runs/v3_poc/<video>_transcript/sentences.json \
  --mode auto \
  --out-text runs/v3_poc/<video>_edited.txt \
  --out-source-map runs/v3_poc/<video>_source_map.json \
  --out-manifest runs/v3_poc/<video>_edited_manifest.json

# 5) one Writer (structured contract, kept for comparison; prose-only is P1)
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m facet_studio.writing_v3.one_call_writer \
  --pack runs/v3_poc/<video>_pack.json \
  --skill-dir skills/writing/reader_first_explainer \
  --request handoffs/2026-10-31/examples/<video>_request.json \
  --out-dir runs/v3_poc/<video>_one_call

# 6) post-hoc article binding (no model)
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m facet_studio.writing_v3.bind_article \
  --article runs/v3_poc/<video>_one_call/reader.md \
  --pack runs/v3_poc/<video>_pack.json \
  --sentences runs/v3_poc/<video>_transcript/sentences.json \
  --rendered-text runs/v3_poc/<video>_edited.txt \
  --source-map runs/v3_poc/<video>_source_map.json \
  --out runs/v3_poc/<video>_article_binding.json

# 7) S2 probe (dry-run by default; --run calls the model)
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m facet_studio.writing_v3.probe \
  --case-id <video> \
  --units data/<video>/substrate/units.jsonl \
  --passages runs/v3_poc/<video>_transcript/passages.json \
  --writer-view runs/v3_poc/<video>_writer_view.json \
  --questions docs/s2-probe/questions_<video>.json \
  --out-dir runs/s2_probe/dry_run/<video>
```

P1 prose evaluation: `prose_writer_probe.py` (dry-run by default; `--run` calls the model once, Markdown-only contract). It is an evaluation harness, not a product path.

M1 light path (no claim extraction):
- `light_context.py` — transcript + outline + frames_index + captions → no-claim context + full edited text.
- `quote_hygiene.py` — remove quote marks around non-exact paraphrases.
- `generate.py` — edited text/article → prose Writer (optional `--run`) → quote hygiene → `bind_article` → article/reader/binding. Dry-run by default.

P0/P1/P1b/P3/M1 evidence: `runs/p0_edit/analysis.md`、`runs/p1_prose/analysis.md`、`runs/p1b_prose/analysis.md`、`runs/p3_light/analysis.md`、`runs/m1_light/analysis.md`、`runs/m1_real/analysis.md`；旧 P0 `handoffs/2026-10-31/p0-one-call.md`、samples `handoffs/2026-10-31/examples/`。
