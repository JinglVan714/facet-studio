# Run report — 20261108T041238Z_BV1ixpd6GENc_wechat_article

- created_at: `2026-11-08T04:16:08.139479+00:00`
- video: `BV1ixpd6GENc`
- form: `wechat_article`
- status: `typeset`
- review: `missing`
- contract passed (machine checks): `True`
- manual acceptance: `False` (review=missing)

## Workflow stages

| stage | status | duration_ms | tokens | error |
|---|---|---:|---:|---|
| intake | succeeded | 0 | 0 |  |
| plan | succeeded | 18342 | 5664 |  |
| approval | auto_approved | 0 | 0 |  |
| write | succeeded | 74916 | 25849 |  |
| typeset | succeeded | 10 | 0 |  |
| review | auto_accepted | 0 | 0 |  |

## LLM calls

- count: 2
- total tokens: 31513
- by stage: {'bundle_plan': 1, 'write_wechat_article': 1}

## Contract checks

| check | passed | detail |
|---|---|---|
| status_healthy | True | status=typeset |
| reader_artifact | True | reader_html=<project>\runs\product_v1\20261108T041238Z_BV1ixpd6GENc_wechat_article\wechat_article\reader.html |
| manual_acceptance | False | review=missing |
| figures | True | figures=2, missing=[], missing_on_disk=[] |
| body_chars | True | output_chars=1876, bounds=0-∞ |
| fact_keywords | True | missing=[] |
| forbidden_keywords | True | present=[] |
| trajectory_stages | True | stages=['intake', 'plan', 'approval', 'write', 'typeset', 'review'] |
| trajectory_order | True | ordered=['intake', 'plan', 'approval', 'write', 'typeset', 'review'] |
| trajectory_no_editor | True | forbidden=[] |
| trajectory_failures | True | failed_stages=[], errors=[] |
| trajectory_hitl | True | review_status=auto_accepted |
| trajectory_usage | True | plan_tokens=5664, write_tokens=25849 |
| usage_present | True | tokens=31513, latency_ms=92738 |
| wechat_artifact | True | html=True, main=True, h1_in_main=False, images=2 |

## Grounding candidates

- status: `typeset`
- flags: 0


## Notes

Developer run report. Contract/trajectory checks are process checks; grounding flags are candidates, not a hallucination rate. No writing quality score; human acceptance remains the only publish gate.
