# LLM Regression Policy

Any change to prompt / ontology / schema / model / evidence packet must run a fixed
regression suite before it is considered (brief §49). No prompt change ships because it
"looks better".

## What must be regression-checked
| Dimension | Check |
|---|---|
| Schema validity | golden cases still validate; closed-schema still rejects extras |
| Abstention behavior | UNKNOWN/CONFLICTED emitted when evidence absent/conflicting |
| Evidence fidelity | every cited id exists, is PIT-safe, allowed for mechanism |
| Orientation | fixture-id / cutoff match; FOR vs AGAINST correct |
| Injection inertness | malicious data field has no effect |
| Label stability | on a fixed pilot sample, label agreement vs previous version tracked |
| Latency / token cost | recorded per call in `llm_call_manifest.csv` |

## Versioning discipline (brief §26, §50)
- A prompt change → `matchup_analyst_prompt_v2`; ontology change → `football_ontology_v2`; etc.
- Historical LLM states are **not** regenerated in place; a new version produces a new,
  separately-persisted feature generation for scientific reproducibility.
- A **model** change (even a Sonnet minor version) is treated as a new predictive component:
  re-run golden cases, regenerate a historical sample, measure label agreement and OOS effect
  before adoption. The `resolved_model_id` recorded per call makes silent drift detectable.

## Phase-A status
The deterministic half of the regression suite (schema, abstention, evidence fidelity,
orientation, injection) is implemented and green (26 tests). The **model-dependent** half
(label agreement across versions, latency/cost, OOS) activates in Phase B/C once Bedrock access
exists; `llm_call_manifest.csv` and `llm_state_features.csv` are headed and ready to receive it.
