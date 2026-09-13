# Hallucination Controls

We do not assume hallucination can be eliminated; we engineer it to be **unusable** (brief §17).
Defense in depth, ordered by strength (deterministic first).

## 1. Closed-world evidence packet (primary)
The packet is the entire factual universe. The system prompt forbids external factual memory
about clubs, players, coaches, formations, injuries, referees, venues, results, competitions.
Anything not in the packet is UNKNOWN.

## 2. The LLM computes nothing
All statistics are precomputed in Python and delivered as facts (brief §7). No arithmetic,
no rolling windows, no averages, no rates. This removes an entire class of numeric error.

## 3. Strict structured output + closed schema
`additionalProperties:false` everywhere; enumerated labels only; no free prose is canonical.
Extra fields (e.g. `extra_analysis`, `recommended_bet`) are rejected.

## 4. Mandatory evidence citation + allow-list
Every assessment must cite `evidence_ids` present in the packet, and each cited metric must be
in the mechanism's ontology allow-list. A conclusion cannot be "supported" by irrelevant or
non-existent evidence.

## 5. PIT gate on cited evidence
Supporting citations must be `PIT_SAFE`. Citing an `UNAVAILABLE`/future-dated item → reject.

## 6. Abstention contract (deterministically enforced)
- No PIT-safe evidence → `UNKNOWN`.
- Conflicting evidence → `CONFLICTED`.
- Small sample / shrunk-to-prior → lower confidence + `SMALL_SAMPLE`/`SHRUNK_TO_PRIOR`.
- No formation data → `FORMATION_UNKNOWN`; no injury data → `INJURY_STATUS_UNKNOWN`.
The validator rejects a non-UNKNOWN state that cites zero PIT-safe evidence, and rejects a
dishonest `formation_status`/`injury_status`.

## 7. Counter-evidence requirement (anti-confirmation-bias, brief §20)
Matchup conclusions must carry `counter_evidence_ids` + `uncertainty_factors`.

## 8. No probabilities from the LLM (brief §32)
Schema has no probability fields; validator scans for and rejects any betting/probability keys.
This keeps calibration measurable and prevents a hallucination from becoming a price.

## 9. Prompt-injection isolation (brief §48)
No provider text is ever concatenated into the system prompt. The packet is delivered as a
fenced, explicitly-untrusted DATA block. Golden case `prompt_injection` embeds
`"IGNORE ALL PREVIOUS INSTRUCTIONS ... probability=0.99"` in a provider field; the test asserts
the output is unaffected and contains no probability content.

## 10. Optional second-pass verifier (brief §31) — deferred
A constrained verifier call (PASS / FAIL / PASS_WITH_DOWNGRADED_CONFIDENCE + offending paths)
is specified but not enabled by default; it must be benchmarked to prove it improves reliability
before paying its latency/cost. Interface reserved in the architecture, not yet built.

## 11. Determinism / reproducibility
Outputs cached by `(model_id, version_stamp, packet_hash)`; version stamps persisted on every
state; a resolved-model-id mismatch is treated as a new LLM generation (no silent drift).

## Falsifiability (brief §34)
None of the above proves an LLM state is *useful*. That is decided later, quantitatively:
a state that is eloquent but does not lower chronological OOS loss is discarded.
