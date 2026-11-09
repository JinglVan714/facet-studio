# Run report — 20261108T095810Z_BV1brgs6mE7a_wechat_article

- created_at: `2026-11-08T10:11:14.811984+00:00`
- video: `BV1brgs6mE7a`
- form: `wechat_article`
- status: `typeset`
- review: `missing`
- contract passed (machine checks): `True`
- manual acceptance: `False` (review=missing)

## Workflow stages

| stage | status | duration_ms | tokens | error |
|---|---|---:|---:|---|
| intake | succeeded | 0 | 0 |  |
| plan | succeeded | 37340 | 3276 |  |
| approval | auto_approved | 0 | 0 |  |
| write | succeeded | 37837 | 20722 |  |
| typeset | succeeded | 7 | 0 |  |
| review | auto_accepted | 0 | 0 |  |

## LLM calls

- count: 7
- total tokens: 32363
- by stage: {'BV1brgs6mE7a:wechat_article_svg_spec': 1, 'bundle_plan': 1, 'visual_audit': 4, 'write_wechat_article': 1}

## Contract checks

| check | passed | detail |
|---|---|---|
| status_healthy | True | status=typeset |
| reader_artifact | True | reader_html=<project>\runs\product_v1\20261108T095810Z_BV1brgs6mE7a_wechat_article\wechat_article\reader.html |
| manual_acceptance | False | review=missing |
| figures | True | figures=1, missing=[], missing_on_disk=[] |
| body_chars | True | output_chars=1720, bounds=0-∞ |
| fact_keywords | True | missing=[] |
| forbidden_keywords | True | present=[] |
| trajectory_stages | True | stages=['intake', 'plan', 'approval', 'write', 'typeset', 'review'] |
| trajectory_order | True | ordered=['intake', 'plan', 'approval', 'write', 'typeset', 'review'] |
| trajectory_no_editor | True | forbidden=[] |
| trajectory_failures | True | failed_stages=[], errors=[] |
| trajectory_hitl | True | review_status=auto_accepted |
| trajectory_usage | True | plan_tokens=3276, write_tokens=20722 |
| usage_present | True | tokens=23998, latency_ms=48338 |
| wechat_artifact | True | html=True, main=True, h1_in_main=False, images=1 |

## Grounding candidates

- status: `typeset`
- flags: 4

| kind | value | context |
|---|---|---|
| quote_not_in_content | `从零做一个东西` |  |
| entity_not_in_content | `Pro` |  |
| entity_not_in_content | `Web` |  |
| scope_term_not_in_content | `一定` |  |

## Notes

Developer run report. Contract/trajectory checks are process checks; grounding flags are candidates, not a hallucination rate. No writing quality score; human acceptance remains the only publish gate.
