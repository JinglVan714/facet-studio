# Substrate View Contract：lean view / index+parts / audit sidecar

> **历史文档（2026-10-31）**：A+C+D 是当时的消费契约，不是当前基线。当前 substrate v1 契约见 [substrate-v1-freeze.md](substrate-v1-freeze.md)；当前默认是 light path（edited text + frames + optional claim），不是 lean view/index+parts。
> 状态：已确认并实现（2026-10-31），A+C+D；substrate-only。
> 实现报告：[substrate-s1-view.md](substrate-s1-view.md)。
> 上位：[architecture.md](../architecture.md) §5.3 / §15；[substrate-s0.md](substrate-s0.md) §3.4 / §3.7。
> 本文只定义 substrate 的消费契约；不定义 skill/Writer 的具体写法，不跑模型。

## 0. 已确认的决策

- **不默认一次性注入 full pack**。真实体验里一次性注入过大内容效果不好；默认改为按需消费。
- **A：lean single view**：短/中内容一次给 Writer 的瘦身 view。
- **C：index + parts**：长/大内容按需读文件；先读 index，再读 part。
- **D：full pack = audit sidecar**：full pack 不再作为 Writer 输入；Writer 只读 A/C 产物。
- **B（compact schema）暂不默认**：短 key/数组/短 ID 虽能再省 ~30–50%，但模型理解/绑定未验证；作为实验项，probe 通过后再进默认。
- **不硬截断**：超预算只记 advisory 或分区，不删 claims/context/frames。
- **skill 只作参考**：本地 17 个 skill 是围绕业务拉下来的素材；全文注入属于微调 writing 产出。业务迁移是后话，当前优先 substrate。

## 1. 产物与消费者

| 产物 | 消费者 | 内容 | 预算 |
|---|---|---|---|
| `pack.json` | audit / QA | 全量 claims/evidence/sentences/segments/frames + provenance/selection/coverage/frame_selection/truncation | advisory；不硬删 |
| `writer_view.json` | Writer（短/中） | lean segments：label + claims(id/text/status/scope/evidence) + context + frames(id/caption) + gaps/conflicts(description) | 目标 ≤ ~4.5x 转录文本 chars |
| `writer_index.json` | Writer/agent（大内容第一层） | segment label + claim id/text/status/scope + `part_id` + gaps/conflicts | 目标 ≤ ~1.5x 转录文本 chars |
| `writer_parts/part_XX.json` | Writer/agent（按需） | 一个或多个 lean segments；无全局 gaps/conflicts | 目标 ≤ ~2k chars/part |
| `manifest.json` | 消费者/audit | part 列表、segment/claim 覆盖、chars、oversize、文件路径 | 小 |

- `--writer-out` 写 `writer_view.json`。
- `--writer-bundle-dir` 写 `writer_index.json`、`writer_parts/`、`manifest.json`。
- full pack 仍然由 `--out` 写；它不进入 Writer 上下文。

## 2. lean single view（A）

```json
{
  "schema": "writer-view-v1",
  "segments": [
    {
      "label": "segment label",
      "claims": [
        {
          "claim_id": "c_...",
          "text": "writing-level claim",
          "status": "supported|bounded",
          "scope": "reader-facing scope or empty",
          "evidence": [
            {"evidence_id": "ev_...", "span": [0, 42]},
            {"evidence_id": "ev_...", "quote": "fallback exact quote"}
          ]
        }
      ],
      "context": ["sentence text", "..."],
      "frames": [{"frame_id": "f_...", "caption": "look-here caption (<=80 chars)"}]
    }
  ],
  "gaps": [{"description": "..."}],
  "conflicts": [{"description": "..."}]
}
```

规则：

- **quote → span**：`span` 是 `"".join(context)` 的 `[start, end]` 偏移；消费者用 `"".join(context)[start:end]` 还原精确 quote。
- 只有当 quote 在 context 中**唯一命中**时才写 span；找不到或不唯一时写 `quote` fallback。不得静默丢 quote。
- 不再带 `segment_id`/`kind`/gap severity；segment 顺序就是 pack 顺序。
- frame caption 最多 80 chars；完整 caption 留在 full pack。
- claim/evidence/frame 使用 full IDs（A 不做短 ID 映射）。
- 任何事实都必须能在 full pack 找到；lean view 不新增事实。

## 3. index + parts（C）

### index

```json
{
  "schema": "writer-index-v1",
  "segments": [
    {
      "part_id": "part_01",
      "label": "segment label",
      "claims": [
        {"claim_id": "c_...", "text": "...", "status": "supported", "scope": ""}
      ]
    }
  ],
  "gaps": [{"description": "..."}],
  "conflicts": [{"description": "..."}]
}
```

- index 不含 quote/context/frames；它只用于选择要读哪些 part/claim。
- 每个 segment 有 `part_id`，映射到 `writer_parts/part_XX.json`。

### parts

```json
{
  "schema": "writer-part-v1",
  "part_id": "part_01",
  "segments": [/* lean segment objects, same schema as A */]
}
```

- 默认一个 segment 一个 part；`--writer-part-max-chars` 可把连续 segments 合并到预算内。
- 单个 segment 超预算时保留为 oversize part，标记，不删。
- 全局 gaps/conflicts 只在 index/manifest，不在每个 part 重复。

### manifest

```json
{
  "schema": "writer-bundle-v1",
  "index": "writer_index.json",
  "parts_count": 1,
  "parts": [
    {
      "part_id": "part_01",
      "file": "writer_parts/part_01.json",
      "segment_labels": ["..."],
      "claim_count": 3,
      "chars": 950,
      "oversize": false
    }
  ],
  "segments_total": 10,
  "claims_total": 40,
  "max_chars_per_part": null,
  "oversize_parts": [],
  "note": "segments partitioned; no content dropped"
}
```

## 4. Audit sidecar（D）

- `pack.json` 是唯一 audit 源：provenance/selection/coverage/frame_selection/truncation/rights 等留在 full pack。
- Writer 只读 A/C；不读 full pack。
- Writer output 的 claim/evidence/frame ID 是 full pack 的 ID；audit 可直接回查。
- full pack 可以超 advisory 预算；不得为了 audit 体积删除 writer 内容。

## 5. 预算与测量（advisory）

| 产物 | BV1AC 新 claims | BV17 | 对转录文本 |
|---|---:|---:|---:|
| 转录文本 | 4,726 | 2,071 | 1.0x |
| lean view（A，实测） | 15,861 | 9,753 | 3.36x / 4.71x |
| index（C，实测，full IDs） | 6,007 | 4,339 | 1.27x / 2.10x |
| part（C，实测，中位/最大） | 1,518 / 2,820 | 1,456 / 2,382 | — |
| compact schema（B，未默认） | 10,951 | 6,295 | 2.32x / 3.04x |
| full pack（audit, compact） | 57,763 | 33,946 | 12.22x / 16.39x |

- A 目标 ≤ ~4.5x；BV17 4.71x 略高，advisory。
- index 目标 ≤ ~1.5x；BV17 2.10x 高于目标（full IDs/status/scope），仍约 4.3k chars；B/短 ID 可再压。
- part 目标 ≤ ~2k；部分 segment 2.3–2.8k，oversize 保留并标记，不删。
- 预算超限只报告/分区，不硬删。

## 6. 不变量

1. full pack 的每个 selected claim/evidence/frame 在 A 或 C 的 index+parts 中恰好出现一次（index 只有索引，不重复 quote/context；parts 承载内容）。
2. 每个 span 必须能还原为精确 quote；不能还原时必须有 quote fallback。
3. A/C 不新增事实；只引用 full pack。
4. 不硬截断；超预算 → advisory/oversize part，不删内容。
5. 同输入同 hash；文件 sha 由 trace/receipt 记录。
6. A/C 的 claim/evidence/frame ID 与 full pack 一致；不做短 ID（B 再议）。
7. gaps/conflicts 的 description 在 index；parts 不重复。

## 7. 测试

- span：唯一命中 → span 可还原；找不到/重复 → quote fallback。
- lean view：无 segment_id/kind/severity；caption ≤80；claim/evidence/frame ID 完整。
- index：覆盖全部 segments/claims；无 quote/context/frames；part_id 映射完整。
- bundle：index+parts 覆盖全部 segments/claims；无内容丢失；oversize part 保留；manifest 计数一致。
- 确定性：同 pack 同参数 → 同 bytes；与 full pack 的 ID/quote 一致。
- 尺寸：在 BV1AC/BV17 记录 A/index/part/full 的 chars。

## 8. 未决 / 后置

- B compact schema：短 key/数组/短 ID 的模型理解与绑定未验证；先 probe，再决定。
- 短 ID 映射：如果采用 B，需要确定性映射；当前 A/C 保留 full ID。
- Writer 接线：`one_call_writer` 仍读 full pack；接线 A/C 属于 writing 阶段，需单独确认。
- part 预算按 chars 还是 tokens：当前 chars advisory；有真实 tokenizer 后再校准。
- index 是否要带 claim quote 摘要：当前不带；让 Writer 先选 part，再读 quote。
