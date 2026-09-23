# Direct LLM Rich-Context Pilot V1

Status: RESEARCH ONLY. This pilot is additive and does not modify Item 6, Stage 2, CHAMPION, p_model, calibration, market comparison, or production.

## Scientific purpose

Test a narrower question before launching another full experiment:

> Does an LLM generate more genuinely data-grounded, football-specific and testable hypotheses when it sees a richer provider-native behavioral packet rather than the reduced FootyStats Item 6 packet?

This pilot does **not** test predictive value. It must not read target outcomes, closing lines, settlement, OOS performance, or any Item 6 Stage 2 result.

## Why this pilot exists

The frozen Item 6 evidence materializer was intentionally FootyStats-only. Its own provider policy states that it performs no cross-provider merge. The repository's TheStatsAPI normalizer already exposes richer per-side post-match observables including:

- blocked shots;
- shots inside / outside box;
- big chances;
- touches in penalty area;
- final-third entries;
- fouled in final third;
- accurate crosses;
- accurate long balls;
- aerial and ground duel percentages;
- tackles and tackles-won percentage;
- interceptions;
- clearances;
- saves;
- high claims.

Many Stage 1 ideas were therefore outside the actual Item 6 packet even though the project already has a provider that can represent those concepts.

## Provider policy for V1

**Do not merge FootyStats and TheStatsAPI match records.**

V1 uses a **TheStatsAPI-native packet end-to-end** for the target fixture and its historical context. This avoids inventing cross-provider team/fixture identity or treating similarly named fields as equivalent.

A FootyStats packet may be generated separately as a comparison arm only when the target fixture has an explicit frozen provider crosswalk. No fuzzy join may be used inside the experiment.

## Point-in-time contract

For target kickoff T:

- historical observations must come only from matches completed before T;
- target-match statistics are forbidden;
- same/later kickoff observations are forbidden;
- market prices are forbidden;
- closing lines are forbidden;
- post-target lineup/injury information is forbidden;
- target outcomes are forbidden.

The packet may include only provider-native historical behavior and neutral fixture identity/context available at T.

## Packet construction

The packet should expose actual behavioral evidence, not a global vocabulary.

For each team, include provider-supported historical cells where coverage exists:

- attack FOR;
- defensive concession AGAINST;
- ALL_PRIOR;
- RECENT_5 as a descriptive slice, never treated as truth;
- HOME/AWAY context where sample exists;
- full-match resolution;
- half/state resolution only where TheStatsAPI genuinely supplies it.

Every evidence cell must include:

- evidence_ref;
- provider = thestatsapi;
- canonical metric name used by this pilot;
- raw normalized ResearchMatch field(s);
- team_role = TEAM_A or TEAM_B;
- perspective = FOR or AGAINST;
- period;
- venue_scope;
- window;
- value;
- sample_n;
- cutoff_unix;
- semantic/provenance note.

Do not rank evidence cells by value, model salience, outcome association, or market information.

### Critical vocabulary rule

The model-visible metric vocabulary is derived **only from evidence cells actually present in this packet**.

A metric name that exists globally in the repository but has no evidence cell in this fixture packet is invisible to the LLM.

The LLM may not introduce it from football world knowledge.

## Direct-LLM treatment

Use the prompt below directly with a frontier reasoning model. No search tools, no web, no external football facts, and no model access to outcomes.

Generate exactly 5 candidate hypotheses unless the packet is too weak, in which case abstention is allowed.

### Prompt

You are the hypothesis/context layer of a quantitative football research system.

You are NOT the predictor.

Your job is to inspect the supplied pre-fixture evidence packet and propose what a deterministic statistical engine should measure historically.

Hard rules:

1. Use ONLY observables that have an evidence_ref in this packet.
2. Every hypothesis must cite the evidence_refs that motivated it.
3. Do not estimate a probability, advantage, effect size, odds, EV, stake, expected result, or matchup score.
4. Do not assert that a relationship is true. Phrase it as a falsifiable historical question.
5. Do not invent numeric cutoffs. If nonlinearity is plausible, ask the deterministic engine to test training-derived quantiles/splines/thresholds.
6. Do not infer injuries, tactics, lineups, manager intentions, formation switches, or event timing not represented in the packet.
7. Prefer mechanisms involving interactions, opponent profiles, venue/context, asymmetric attack-vs-defense relationships, and supported half/state effects over simple one-variable restatements.
8. Recent windows are noisy context. Do not treat RECENT_5 as ground truth; use ALL_PRIOR/sample size to contextualize it.
9. Similarity must be computed by the deterministic engine. You may state which measured dimensions should define an opponent profile, but never invent a similarity score.
10. A mechanism is useful even if later measurement finds an effect of zero.

For each hypothesis return:

- hypothesis_id
- research_question
- mechanism_rationale
- evidence_refs
- variables_to_measure
- conditioning_context
- deterministic_measurement_plan
- key_confounders
- required_resolution
- novelty_tags
- abstain_reason (null unless abstaining)

Generate exactly 5 unless evidence is insufficient.

## Pilot sample

Start small: 3 fresh fixtures, selected deterministically without inspecting their outcomes.

For each fixture preserve:

1. packet JSON;
2. packet hash;
3. exact prompt version;
4. raw LLM response;
5. response hash.

Do not score predictive outcomes.

## Pilot evaluation

The pilot is diagnostic, not confirmatory.

Measure only process quality:

- invalid evidence-ref rate;
- out-of-packet metric rate;
- unsupported-provider concept rate;
- simple-baseline-equivalent rate;
- multimetric interaction rate;
- richer-metric utilization rate;
- duplicate/signature rate across the 3 fixtures;
- number of hypotheses requiring genuinely richer TheStatsAPI dimensions;
- abstention rate.

The most important expected invariants are:

OUT_OF_PACKET_METRIC_RATE = 0

INVALID_EVIDENCE_REF_RATE = 0

LLM_PROBABILITIES_EMITTED = 0

LLM_NUMERIC_EFFECTS_EMITTED = 0

## What would count as an encouraging pilot?

Not predictive success.

An encouraging pilot means the richer packet causes the model to form grounded questions that could not have been formed from the reduced Item 6 packet, while staying inside the actual evidence provided.

Examples of dimensions that may create genuinely new mechanisms if present in the packet:

- accurate crosses x opponent clearances / aerial-duel profile;
- touches in box x opponent blocks / tackles;
- final-third entries x opponent interception profile;
- shot-location mix x defensive block behavior;
- long-ball / aerial-duel interaction;
- goalkeeper claim/save profile x crossing/box-entry behavior.

These are examples of **structure only**. They are not claims that any effect exists.

## What this pilot must NOT become

Do not:

- refit Item 6;
- alter the Item 6 failure;
- select a winning Stage 2 family;
- inspect OOS outcomes;
- use the LLM as a predictor;
- create p_model;
- use market data;
- modify CHAMPION.

If this pilot is promising, the next step is a fresh preregistered experiment using a new cohort and a provider-safe measurement substrate.

## Governing principle

LLM proposes what to measure.

Provider-native evidence constrains what it may talk about.

Deterministic analysis measures it.

Only future OOS/prospective evidence can determine whether it predicts.
