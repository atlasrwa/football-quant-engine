# Dual-Provider LLM Context Pilot V1

Status: exploratory research only. No Stage-2 reopening. No CHAMPION changes. No outcome evaluation.

## Why this exists

Item 6 Stage 2 validly failed on the feature universe it tested, but the Stage-1 evidence packet was deliberately FootyStats-only. The current codebase already exposes richer TheStatsAPI fields on `ResearchMatch`, including `accurate_crosses`, `blocked_shots`, `touches_in_box`, `final_third_entries`, tackles, interceptions, clearances, duel percentages, saves and related fields.

This pilot asks a different question:

> Does a frontier LLM generate more football-specific, data-grounded, falsifiable hypotheses when it sees a richer provider-bound behavioral packet instead of a narrow aggregate packet plus a global metric vocabulary?

It does NOT ask whether those hypotheses improve prediction.

## Firewall

The LLM MUST NOT produce:
- probabilities;
- p_model;
- odds;
- EV/edge;
- stakes;
- numerical effect sizes;
- matchup-strength scores;
- hand-written predictive thresholds.

The LLM proposes what the deterministic engine should measure.

## Provider discipline

1. FootyStats and TheStatsAPI observations remain provider-labelled.
2. Similarly named fields are NOT assumed equivalent.
3. Do not average/blend providers unless an existing deterministic reconciliation policy has validated that concept.
4. A hypothesis may cite a provider-specific field directly.
5. Every variable used in a hypothesis must cite an evidence_ref actually present in the packet.
6. No global vocabulary escape hatch. If a metric has no evidence_ref, the LLM cannot use it.
7. TheStatsAPI npxG remains excluded unless a separate provider-safe experiment explicitly authorizes it.

## Better context representation

Each fixture packet should contain two complementary representations, both strictly pre-kickoff:

### A. Raw recent behavior
For each team, include a bounded sequence of prior completed matches (for example the most recent 10-12) with provider-labelled raw observables where available.

The purpose is to let the LLM see:
- recurring combinations;
- asymmetry;
- opponent-dependent behavior;
- venue changes;
- recent-vs-longer-run divergence;
- possible football mechanisms hidden by means.

### B. Deterministic aggregate context
For each provider/metric/team perspective, include value-neutral aggregates such as:
- all-prior;
- venue;
- recent 5;
- recent 10 where supported;
- FOR and AGAINST;
- half-level only where genuinely available;
- sample_n and coverage.

Do not rank or salience-sort fields by outcome or effect.

## Rich TheStatsAPI dimensions currently represented in canonical ResearchMatch

Examples already implemented in the repository:
- shots_inside_box;
- shots_outside_box;
- blocked_shots;
- big_chances;
- touches_in_box;
- final_third_entries;
- fouled_in_final_third;
- accurate_crosses;
- accurate_long_balls;
- aerial_duel_pct;
- ground_duel_pct;
- tackles;
- tackles_won_pct;
- interceptions;
- clearances;
- saves;
- high_claims.

These fields must still pass real historical coverage and point-in-time checks before downstream measurement.

## Direct ChatGPT pilot

The first test should be small and exploratory:

1. Pick 1-3 fixtures whose kickoff has not occurred at packet construction time, OR historical fixtures with the target outcome strictly withheld.
2. Build a packet under `DUAL_PROVIDER_PACKET_CONTRACT_V1.json`.
3. Do not include target outcome, target-match post-match statistics, market close, settlement or p_model.
4. Paste the packet together with `DIRECT_LLM_HYPOTHESIS_PROMPT_V1.md` into ChatGPT.
5. Save the raw LLM response byte-for-byte.
6. Deterministically audit:
   - evidence_ref validity;
   - provider provenance;
   - variables actually present in packet;
   - falsifiability;
   - whether the mechanism is baseline-equivalent;
   - whether it uses richer TheStatsAPI evidence;
   - whether it proposes a genuinely football-specific interaction rather than generic thresholding.
7. Do not fit a model or inspect outcomes in this pilot.

## What success looks like

This exploratory pilot is useful if the LLM:
- grounds every variable in actual evidence refs;
- makes substantial use of rich provider-specific observations;
- proposes mechanisms that depend on observed team behavior, not generic football priors;
- identifies deterministic similarity dimensions or conditional relationships worth testing;
- avoids invented metrics and numerical claims.

This is not evidence of predictive value.

## Relationship to Item 6

Item 6 remains frozen and failed Stage 2.

Nothing in this pilot may alter Item 6 artifacts, thresholds, results or interpretation.

If this process appears materially better, the next scientific step is a NEW preregistered experiment on a fresh cohort, not an Item 6 rerun.
