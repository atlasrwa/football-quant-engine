# B2 — Corners-First Capped Pilot

Runs ONLY after B0 and B1 pass. Generates the frozen-stack Sonnet **state dataset** for the
corners market. **B2 does not modify the quant model** (brief §36) — predictive evaluation
is Phase C. B2 inspects: schema validity, stability, mechanism diversity, formation/behavior
sensitivity, evidence fidelity, unknown/conflict rates, cost, latency.

## Scope guards
- **CORNERS ONLY.** Not a full historical backfill.
- **Hard cap ≤ 300 fixtures** (brief §23). Default live run capped smaller for cost/latency.
- Frozen stack: `football_ontology_v2`, `football_state_schema_v2`, `sonnet_prompt_v2`,
  `fixture_evidence_packet_v2`, `formation_policy_v1`, `formation_family_v1`. The stack is
  **not** tuned after seeing B2 results.

## Deterministic selection policy (`deterministic_stratified_v1`, brief §24)

No randomness. Fixture IDs and rationale are persisted to `out/b2_selection.json`
**before any Sonnet call**. Selection walks the football-state space via round-robin across
sorted strata (within-stratum ordered by kickoff), so no single stratum dominates and the
sample is not cherry-picked to flatter Sonnet.

Strata dimensions:
- competition
- season bucket
- venue corner environment (`LOW/MID/HIGH_CORNER` from league corner env)
- formation family (team A projected)
- formation-family matchup (A family × B family)
- history reliability (`LOW/MED/HIGH_HISTORY` from min prior-match count)

### Selection manifest (persisted before results)
- policy: `deterministic_stratified_v1`, market: `corners`
- candidates: **726**, strata: **134**, selected: **120**
- `selection_hash`: `4c322004380882cf...` (sha256 of the ordered selected fixture-id list)

The manifest also records, per selected fixture, its stratum and the A/B projected formation
+ family, so the coverage of the football-state space is auditable.

## Formation handling in B2 (leakage-safe)
Each B2 packet attaches a **PROJECTED** `FormationInput` for the target (mode of the team's
prior resolved formations, PIT-safe — never the target's own resolved formation), plus a
distribution over prior formations for the formation-uncertain view. Historical cohorts are
conditioned on the resolved formation those source matches actually played. No target-match
resolved-formation leakage (enforced by `assert_not_target_resolved` and
`tests/research/test_formation_leakage.py`).

## Raw evidence surfaced (brief §26), corners-relevant
corners FOR/AGAINST; crosses FOR/AGAINST (+ 2H shift); shots / SoT / blocked shots; shots in
box; touches in box; possession; clearances; throw-ins; final-third entries; venue;
competition corner environment; formation-conditioned behavior (`fc_*`), formation delta
(`formation_delta_*`), hierarchical formation × opponent-formation matchup (`fmx_*`) with tier
summary + sample sizes + reliability; behavioral style tags; provider provenance.

## Corner mechanisms compiled (brief §27)
`WIDE_PRESSURE_MATCHUP`, `BOX_PRESSURE_MATCHUP`, `CORNER_MECHANISM_MATCHUP`,
`SET_PIECE_GENERATION`, `CROSS_ALLOWANCE`, `CLEARANCE_DEPENDENCE`, `CORNER_CONCESSION`,
`SECOND_HALF_PRESSURE_SHIFT`, plus the formation family: `FORMATION_BEHAVIOR_FIT`,
`FORMATION_WIDTH_INTERACTION`, `FORMATION_BOX_INTERACTION`,
`FORMATION_VS_OPP_DEFENSIVE_PROFILE`, `FORMATION_TRANSITION_STATE`. Formation interaction is
**evidence-based** (brief §28): a formation × opponent-formation mechanism is only supported
by measured `fmx_*` behavior, never by a nominal-label stereotype.

## Second-half safeguard (brief §29)
Resolved formation may help explain 2H behavioral shifts, but **score-state remains
unavailable**. The observed 2H shift is surfaced as evidence, but its interpretation as an
inherent tactical trait stays confidence-discounted (`SCORE_STATE_CONFOUND`). This safeguard
is unchanged from Phase A.

## Outputs
- `out/b2_selection.json` — selection manifest (written before calls).
- `out/llm_states_b2.jsonl` — per-fixture validated Sonnet state + provenance.
- `out/phase_b_calls.csv` — per-call identity/metrics (phase=B2).
- `out/b2_summary.json` — aggregate metrics.

## Live-run note
Each live Sonnet call takes ≈ 45 s and the packet is ≈ 28k input tokens. The full 120-fixture
live run is cost/latency-bound in this environment; the harness (`run_b2_corners.py`) runs the
full frozen-stack dataset when executed with a real budget. A representative live subset was
executed to validate the B2 path end-to-end; see `b2_summary.json` for the actual counts and
`PHASE_B_AUDIT.md` for interpretation. The deterministic selection is fully persisted
regardless of how many calls are ultimately executed, so the dataset can be completed later
without re-selection.
