# writing_v3

v3 P0 prototypes. No v2 writing-chain imports.

Pipeline:

1. `transcript.py` — ASR units → sentences → passages (deterministic).
2. `claim_extract.py` — passages → writing-level claims (1 model call/video).
3. `evidence_pack.py` / `pack_from_claims.py` — claims → EvidencePack (deterministic, coverage-aware).
4. `one_call_writer.py` — pack + skill + request → reader (1 Writer call).
5. `trace.py` — trace.jsonl + stage_receipts (inputs/outputs/hashes/counts/decisions/samples).

Commands (from project root; Python 3.11):

```bash
# 1) units -> sentences/passages
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m lunograph.writing_v3.transcript \
  --units data/<video>/substrate/units.jsonl \
  --contract data/<video>/substrate/contract.json \
  --out-dir runs/v3_poc/<video>_transcript

# 2) passages -> claims (one model call)
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m lunograph.writing_v3.claim_extract \
  --passages runs/v3_poc/<video>_transcript/passages.json \
  --out-dir runs/v3_poc/<video>_claims

# 3) claims -> EvidencePack
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m lunograph.writing_v3.pack_from_claims \
  --claims runs/v3_poc/<video>_claims/claims.json \
  --passages runs/v3_poc/<video>_transcript/passages.json \
  --sentences runs/v3_poc/<video>_transcript/sentences.json \
  --snapshot runs/<substrate_run>/evidence_snapshot.json \
  --outline runs/<substrate_run>/temporal_outline.json \
  --knowledge runs/<substrate_run>/knowledge_snapshot.json \
  --request docs/v3/examples/<video>_request.json \
  --contract data/<video>/substrate/contract.json \
  --video-id <video> \
  --out runs/v3_poc/<video>_pack.json

# 4) one Writer
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m lunograph.writing_v3.one_call_writer \
  --pack runs/v3_poc/<video>_pack.json \
  --skill-dir skills/writing/reader_first_explainer \
  --request docs/v3/examples/<video>_request.json \
  --out-dir runs/v3_poc/<video>_one_call
```

P0 evidence: `docs/v3/03-p0-one-call.md`; samples `docs/v3/examples/`.
