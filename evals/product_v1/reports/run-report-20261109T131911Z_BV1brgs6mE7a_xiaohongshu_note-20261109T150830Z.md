# Run report — 20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note

- created_at: `2026-11-09T15:08:30.280620+00:00`
- video: `BV1brgs6mE7a`
- form: `xiaohongshu_note`
- status: `approved`
- review: `approved`
- contract passed (machine checks): `True`
- manual acceptance: `True` (review=approved)

## Workflow stages

| stage | status | duration_ms | tokens | error |
|---|---|---:|---:|---|
| intake | succeeded | 0 | 0 |  |
| plan | succeeded | 32251 | 2719 |  |
| approval | auto_approved | 0 | 0 |  |
| write | succeeded | 13181 | 6203 |  |
| typeset | succeeded | 5723 | 0 |  |
| review | approved | 0 | 0 |  |

## LLM calls

- count: 6
- total tokens: 15862
- by stage: {'bundle_plan': 1, 'visual_audit': 4, 'write_xiaohongshu_note': 1}

## Contract checks

| check | passed | detail |
|---|---|---|
| status_healthy | True | status=approved |
| reader_artifact | True | reader_html=<project>\runs\product_v1\20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note\xiaohongshu_note\reader.html |
| manual_acceptance | True | review=approved |
| figures | True | figures=0, missing=[], missing_on_disk=[] |
| body_chars | True | output_chars=793, bounds=0-∞ |
| fact_keywords | True | missing=[] |
| forbidden_keywords | True | present=[] |
| trajectory_stages | True | stages=['intake', 'plan', 'approval', 'write', 'typeset', 'review'] |
| trajectory_order | True | ordered=['intake', 'plan', 'approval', 'write', 'typeset', 'review'] |
| trajectory_no_editor | True | forbidden=[] |
| trajectory_failures | True | failed_stages=[], errors=[] |
| trajectory_hitl | True | review_status=approved |
| trajectory_usage | True | plan_tokens=2719, write_tokens=6203 |
| usage_present | True | tokens=15862 (plan+write+visual_audit), latency_ms=21344 (plan+write) |
| xhs_artifact | True | cards=1, dims_1080x1440=True, copy_ui=True |

## Grounding candidates

- status: `approved`
- flags: 2

| kind | value | context |
|---|---|---|
| entity_not_in_content | `AIAgent` |  |
| entity_not_in_content | `Web` |  |

## Notes

Developer run report. Contract/trajectory checks are process checks; grounding flags are candidates, not a hallucination rate. No writing quality score; human acceptance remains the only publish gate.
