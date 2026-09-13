# Phase B — Live Sonnet Football Evidence Pilot (Plan)

Senior Quant + Senior LLM Engineering mandate. This document is the controlling plan for
the Phase-B controlled live-Bedrock research pilot. It builds on the completed Phase-A
architecture under `src/research/llm_matchup/`, `research/llm_matchup/`, and
`tests/research/`.

## 0. What Phase B is (and is not)

Phase B answers ONE question:

> Can Claude Sonnet, operating over closed structured football evidence, produce stable,
> faithful, evidence-backed matchup states that represent genuine football interactions
> **beyond** what the deterministic contextual feature layer already expresses?

Phase B is **not**: a production integration, a historical full backfill, a champion
replacement, a prediction publication system, or a prompt-tuning free-for-all.

## 1. Preserved safety boundaries

Not modified in Phase B: champion model, champion artifact, production forecast path,
prospective canonical evidence, publication logic, Telegram output, production gates. All
work is research-only under the three Phase directories. No destructive git operations.

Starting state (documented at session start):
- branch `feat/model-oos-benchmark`, HEAD `224aef608f501496a06a7231401ee5706486890f`.
- `research/llm_matchup/` and `src/research/llm_matchup/` were untracked (Phase A
  uncommitted). Numerous pre-existing operational modifications left untouched.

## 2. Formation policy correction

The Phase-A `FORMATION_UNKNOWN` treatment was too restrictive. Phase B replaces it with
the two-concept model in `FORMATION_RESOLUTION_POLICY.md`:
`RESOLVED_FORMATION` (historical resolution) vs `PREMATCH_FORMATION` (forecast input),
with a hard leakage rule. Formation is now a football-resolution variable, but never a
stereotype.

## 3. Frozen stack for the pilot

Phase B freezes a versioned stack (see `versions.py`):

| Artifact          | Version                       |
|-------------------|-------------------------------|
| ontology          | `football_ontology_v2`        |
| state schema      | `football_state_schema_v2`    |
| prompt            | `sonnet_prompt_v2`            |
| cohort policy     | `cohort_policy_v1`            |
| packet schema     | `fixture_evidence_packet_v2`  |
| formation policy  | `formation_policy_v1`         |
| formation family  | `formation_family_v1`         |

Any change required after B1 bumps to a new explicit version, then the stack is frozen
before B2 (brief §25). B2 states are generated from the frozen stack and are not tuned
after seeing predictive results (that is Phase C).

## 4. Gate sequence

### B0 — Live Bedrock smoke (5–10 fixtures) — ENGINEERING VALIDATION ONLY
Harness: `src/research/llm_matchup/run_b0_smoke.py`. Verifies a real Converse request
works, the structured tool schema is accepted, model identity is recorded, the validator
accepts legitimate responses and fails closed on invalid ones, packet hashing/caching
works, retries are safe, AWS exceptions map to `LLM_STATE_UNAVAILABLE`, no credentials are
logged, no prose/probabilities/predictions leak. No predictive tuning. Results in
`BEDROCK_LIVE_SMOKE.md`.

### B1 — Adversarial football interpretation (30–50 fixtures)
Harness: `src/research/llm_matchup/run_b1_adversarial.py`. Deliberately difficult cases
(formation stable/unstable, sparse exact cohorts, family-stronger-than-exact, behavior
contradicting nominal formation, 2H shifts, provider disagreement, FOR/AGAINST and
home/away traps). Evaluates interpretation fidelity, not predictive performance. Includes:
- **matchup swap test** (metamorphic A-vs-B → B-vs-A with orientation corrected);
- **formation-removal ablation** (full vs behavior-minus-formation);
- **formation-label shuffle control** (behavior unchanged, labels shuffled — output must
  not change dramatically);
- **behavior-vs-formation** parroting / ignoring tests.
Results in `B1_ADVERSARIAL_RESULTS.md`.

### B2 — Corners-first capped pilot (≤300 fixtures)
Harness: `src/research/llm_matchup/run_b2_corners.py`. CORNERS ONLY, no full backfill,
deterministic stratified selection (see `B2_CORNERS_PILOT.md`). Fixture IDs and selection
rationale persisted BEFORE reviewing Sonnet results. B2 output is an LLM state dataset; it
does NOT modify the quant model. Inspect schema validity, stability, mechanism diversity,
formation/behavior sensitivity, evidence fidelity, unknown/conflict rates, cost, latency.

## 5. Live Bedrock identity recording (brief §15, §25)

Every call persists: AWS region, Bedrock model id / inference profile, resolved model
info where available, prompt version, schema version, ontology version, formation-policy
version, evidence packet hash, inference parameters. Recorded per call in
`out/phase_b_calls.csv` and per-call cache manifests. No silent Sonnet drift.

## 6. Metrics (B0/B1/B2)

`phase_b_calls.csv` and the report docs capture: calls attempted/successful, Bedrock
failures, schema-valid %, validator rejection %, invalid evidence-ID %, orientation
error %, unsupported inference %, UNKNOWN %, CONFLICTED %, repeatability,
formation-sensitive %, formation-stereotype failures, label-shuffle failures,
behavior-vs-formation disagreement cases, input/output tokens, latency, cost, cache-hit
rate.

## 7. Success / failure criteria

**Success (B0/B1/B2):** very high schema compliance; zero accepted fake evidence
references; zero accepted future-target leakage; very low unsupported inference; correct
A/B and FOR/AGAINST orientation; appropriate UNKNOWN/CONFLICTED behavior; stable outputs;
measurable response to matchup structure; meaningful use of formation-conditioned
evidence; no systematic formation stereotyping; manageable cost/latency. Predictive
improvement is NOT required in B0/B1.

**Failure (stop before Phase C):** Sonnet invents facts; relies on club-name stereotypes;
formation labels dominate measured behavior; outputs unstable; small-N overstated;
counter-evidence ignored; schema frequently fails; cost unreasonable; matchup swap tests
fail; label-shuffle reveals stereotype dependence. Fix architecture rather than scaling
calls.

## 8. Two scientific questions (do not conflate) (brief §34)

- **RESOLUTION:** Does knowing the historical formation help organize football mechanisms?
  (Expected: likely yes.)
- **FORECAST:** Can we know/estimate tomorrow's formation accurately enough before kickoff
  to improve prediction? (Open empirical question — Phase C.)

## 9. Phase C handoff — target-fixture formation scenarios (brief §13, §45)

Phase B does NOT build a formation predictor. It recommends how Phase C should handle the
target-fixture formation in an inference-realistic way:

- **Scenario 1 — ANNOUNCED-formation model:** evaluate only when historically timestamped
  pre-match formation can be reconstructed. Not possible with this data source (no
  timestamp), so this is prospective-only later.
- **Scenario 2 — PROJECTED-formation model:** project formation from pre-cutoff info only
  (team's previous formations, venue, competition, recent lineup structures). Never uses
  target-match resolved formation. A deterministic baseline projector (mode of prior
  resolved formations) is exercised in the harnesses but NOT productionised.
- **Scenario 3 — FORMATION-UNCERTAIN model:** pass a distribution over plausible formations
  (`FormationInput.distribution`) and marginalise / generate weighted states. Likely
  superior to pretending formation is certain.

Phase B makes recommendations; it does not overbuild.

## 10. Two-stage future model (documented, not built) (brief §35)

```
historical resolved formations
   -> formation transition model
   -> P(formation | pre-match information)
   -> formation-conditioned football states
   -> marginalized matchup state
```

Represents formation uncertainty rather than asserting a single certain formation.

## 11. Deliverables

Docs: this plan, `BEDROCK_LIVE_SMOKE.md`, `FORMATION_RESOLUTION_POLICY.md`,
`FORMATION_FAMILY_V1.json`, `FORMATION_BEHAVIOR_ANALYSIS.md`,
`B1_ADVERSARIAL_RESULTS.md`, `B2_CORNERS_PILOT.md`, `PHASE_B_AUDIT.md`.
Machine-readable (under `out/`): `phase_b_calls.csv`, `formation_profiles.csv`,
`formation_matchups.csv`, `llm_states_b1.jsonl`, `llm_states_b2.jsonl`,
`formation_ablation.csv`, `formation_shuffle_control.csv`, `repeatability_results.csv`.

## 12. Phase-C recommendation gate

At the end of Phase B, recommend exactly one of: `PROCEED_TO_PHASE_C`,
`REVISE_LLM_LAYER`, or `LLM_NOT_ADDING_MEANINGFUL_REPRESENTATION`. See `PHASE_B_AUDIT.md`.
Because live Bedrock access depends on the environment, if credentials are unavailable the
harnesses fail closed (`LLM_STATE_UNAVAILABLE`) and the recommendation is conditioned on
the offline structural evidence plus whatever live calls succeeded.
