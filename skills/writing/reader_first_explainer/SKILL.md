---
name: reader-first-explainer
description: Use when turning a video's evidence pack into a continuous reader-first explainer article (one central question, one mechanism/argument chain, one demo or an explicit no-demo boundary, terms explained at first use, a synthesis conclusion), not a chapter-by-chapter lecture note or a coverage dump.
version: 0.1.0
---

# Reader-first explainer

You are one author writing for a smart reader who wants to understand the content, not a summary of the video. The reader should finish the article able to answer the central question, retell the mechanism in their own words, and say what the evidence does not cover.

The content is the subject. The source (video, speaker, frame) is context, not the main character.

## Inputs

- `request`: central question, reader before/after, required/forbidden information.
- `evidence_pack`: contextual evidence units grouped by segment/beat; each claim has an ID, exact quotes, timecodes, frame candidates, gaps/conflicts.
- `output_contract`: format, language, citation display, media policy. Length is advisory.

Use only IDs and quotes present in `evidence_pack`. Do not add facts, numbers, names, speakers, citations, or frames from outside the pack.

## Method

1. **Find the one thing.** State the central question and the single explanatory target: the mechanism, process, or tradeoff the reader must understand. Do not turn the article into a list of everything in the video.
2. **Build one chain.** Write a short `reader_path` and a `mechanism_or_steps` header. Each step needs evidence; if the evidence only gives an observation, say so and write a reader-facing boundary instead of inventing a cause.
3. **Choose one demo.** Prefer `real_frame` only when a frame candidate actually shows the operation/result/claim. Otherwise use `text_experiment` or `no_demo`; never imply a demo that the evidence does not contain.
4. **Explain terms at first use.** Define in reader language; do not use a harder term to define a term. Use the first section where the term is needed.
5. **Make the conclusion a synthesis.** Add one new connection, judgment, or decision. Do not recap each section; do not add a new causal claim that the body did not support.
6. **Boundary only when it changes the reader's judgment or action.** Say what can be concluded from this evidence, not a list of what the evidence lacks. If the evidence is insufficient, shrink the claim.

## Evidence discipline

- A grounded span must carry `claim_ids`, `evidence_ids`, and an exact `quote` from one of those evidence items. `quote` is the evidence quote used for binding/audit; it does **not** need to appear verbatim in `text` when you paraphrase. If you directly quote in the prose, the quoted text must match `quote` exactly.
- The quote must be a continuous substring of the evidence's `quote`/`raw_content`; numbers in the span must appear in the bound evidence.
- Editorial spans carry no claim/evidence/quote; they may organize, limit, synthesize, or point to a demo. They must not introduce new facts or causal mechanisms.
- Establish the source/demo relation once (opening or demo section). After that, write about the mechanism/objects; use "the video/speaker" only when distinguishing an opinion from a fact, or pointing to a specific demo.
- Reader text has no internal IDs, citation keys, timecodes, or audit language. Timecodes/citations belong in audit/citations, not the article.

## Output

Return one JSON object; the code will wrap provenance/hash. Keep content fields only.

```json
{
  "plan_header": {
    "title": "specific, honest, not inflated",
    "controlling_idea": "one sentence",
    "reader_path": ["..."],
    "sections": [
      {"section_id": "sec_1", "role": "opening|mechanism|demo|terms|conclusion", "goal": "..."}
    ],
    "mechanism_or_steps": [
      {"step_id": "ms_1", "premise": "...", "operation": "...", "result": "...", "why": "..."}
    ],
    "demo_choice": {
      "representation": "real_frame|text_experiment|no_demo",
      "frame_id": "f_... or null",
      "reason": "..."
    }
  },
  "sections": [
    {
      "section_id": "sec_1",
      "heading": "reader-visible heading",
      "paragraphs": [
        {
          "spans": [
            {
              "text": "continuous prose",
              "role": "grounded|editorial",
              "claim_ids": ["c_..."],
              "evidence_ids": ["ev_..."],
              "quote": "exact evidence quote used for binding/audit (may be paraphrased in text); null if not quoting",
              "scope_note": "reader-facing scope or empty"
            }
          ]
        }
      ]
    }
  ],
  "media_choices": [
    {"frame_id": "f_...", "section_id": "sec_2", "caption": "one look-here sentence"}
  ],
  "self_review": {
    "central_question_answered": true,
    "mechanism_retellable": true,
    "conclusion_is_synthesis": true,
    "source_attribution_natural": true,
    "boundary_is_reader_facing": true,
    "risks": ["..."],
    "uncertain_claims": ["..."],
    "coverage_gaps": ["..."]
  }
}
```

## Self-review before returning

Ask, not scan a word list:

1. Does the opening create the reader's question, and does the article answer it?
2. Is there one mechanism/argument chain, or a pile of sections?
3. Does the conclusion add a synthesis/decision, or just repeat the sections?
4. Is the source attribution doing real work, or is "the video/speaker" the default subject?
5. Is each boundary a reader-facing limit, or a list of what the evidence lacks?
6. Is every grounded span bound to evidence, and every editorial span free of new facts?
7. Is any action/observation/number repeated when one mention would do?
8. Is the caption a "look here" cue, not a summary of the body?

If a check fails, revise that part before returning. Do not add rules or words just to pass; write the clearest version.

## Examples

Read [examples.md](examples.md) for annotated good/bad pairs (source attribution, boundary, conclusion, caption, repetition).

## Attribution

See [SOURCES.md](SOURCES.md). This skill is a v3 composition informed by existing skills; it is not a verbatim copy of any single source.
