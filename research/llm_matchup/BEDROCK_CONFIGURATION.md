# Bedrock Configuration

## Model
- **Default model id:** `anthropic.claude-3-5-sonnet-20241022-v2:0` (pinned concrete
  version, not a moving alias — brief §25). Override via `BEDROCK_MODEL_ID` env var.
- **Region default:** `us-east-1` (override `AWS_REGION`).
- The **resolved** model id returned by Bedrock is recorded per call in the call manifest
  (`resolved_model_id`), so a silent underlying model change is detectable and treated as a
  new LLM generation.

## API
- **Bedrock Runtime `Converse`** for provider-stable interface.
- **Structured output via strict tool schema:** a single tool `emit_football_state` whose
  `inputSchema.json` is `football_state_schema_v1`, with `toolChoice` forcing that tool.
  This is the portable structured-output path across Claude models on Bedrock. If a deployed
  model additionally supports response-format JSON-schema validation, it can be layered on;
  our deterministic validator is the source of truth regardless.
- **Inference config:** `temperature=0.0, topP=1.0, maxTokens=4096`. Temperature≈0 does not
  guarantee determinism → outputs are cached by `(model_id, version_stamp, packet_hash)`.

## Caching
- Cache dir: `research/llm_matchup/out/cache/<sha256(model|versions|packet_hash)>.json`.
- Cache stores the validated state (or the rejection) plus the provenance manifest. Identical
  analysis requests reuse the cached validated result.

## IAM boundary (least privilege — brief §28)
The analysis runtime role should be limited to:
- `bedrock:InvokeModel` / `bedrock:Converse` on the **one approved model/inference-profile ARN** only;
- read of the approved research evidence inputs;
- write of the approved research output/cache prefix.
It must NOT have: repository mutation, deployment, secret enumeration, unrelated S3, or any
canonical/prospective ledger write. Credentials are never printed or committed. (This repo
contains no IAM changes; this section documents the required boundary for the operator.)

## Guardrails (defense-in-depth — brief §29)
Amazon Bedrock Guardrails *contextual grounding* may be attached to flag ungrounded output.
It is **supplementary**; primary correctness comes from the closed evidence packet, strict
schema, evidence-id validation, and deterministic recomputation.

## Failure modes (brief §61)
| Condition | Result |
|---|---|
| boto3/creds absent, client error | `LLM_STATE_UNAVAILABLE` |
| network/timeout/throttle on invoke | `LLM_STATE_UNAVAILABLE` |
| schema/evidence/PIT/ontology violation | `LLM_STATE_REJECTED` |
| insufficient evidence for a mechanism | mechanism level = `UNKNOWN` |
The quant pipeline operates without LLM states; LLM failure degrades gracefully, never breaks.

## Offline research mode
When boto3/creds are absent (current sandbox), `analyze_matchup` returns
`LLM_STATE_UNAVAILABLE` and makes no network call. No LLM output is fabricated. The `stub`
producer is used **only** in the test suite to exercise the contract.
