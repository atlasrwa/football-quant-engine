# Direct ChatGPT Pilot — Local Export Handoff

Goal: produce ONE strictly pre-kickoff rich context packet so ChatGPT can generate hypotheses directly. This is an exploratory process test only.

## Selection

Using the locally configured project providers/data:

1. Enumerate upcoming fixtures.
2. Keep fixtures whose target kickoff is in the future at export time.
3. Require both teams to have at least 10 completed prior TheStatsAPI matches with non-empty rich stats.
4. Select the earliest eligible fixture, tie-break by provider fixture id.
5. Record the selection rule and fixture id. Do not select based on market, outcome expectation or interesting-looking stats.

If no upcoming fixture satisfies coverage, use a historical fixture selected deterministically by fixture id and hide its result and all target-match post-match fields from the exporter and operator-facing packet.

## Phase A — TheStatsAPI rich packet

For the first direct test, TheStatsAPI may stand alone as the rich provider. Do not block the pilot on a cross-provider fixture join.

For each team, from completed matches strictly before target kickoff, export:

### Aggregate evidence
For each populated canonical ResearchMatch rich field:
- ALL_PRIOR FOR
- ALL_PRIOR AGAINST where meaningful
- RECENT_5 FOR
- RECENT_5 AGAINST
- RECENT_10 FOR
- RECENT_10 AGAINST
- venue-conditioned ALL_PRIOR where sample exists

Candidate rich dimensions already implemented include:
- shots / shots_on_target
- shots_inside_box / shots_outside_box / blocked_shots
- big_chances
- possession
- corners
- fouls / cards
- touches_in_box
- final_third_entries
- fouled_in_final_third
- accurate_crosses
- accurate_long_balls
- aerial_duel_pct
- ground_duel_pct
- tackles / tackles_won_pct
- interceptions
- clearances
- saves / high_claims

Do not include npxG in this pilot.

Each evidence item must carry:
- evidence_ref
- provider=thestatsapi
- canonical_concept
- exact provider/canonical source field
- team_role
- perspective
- period
- window
- venue_scope
- value
- sample_n
- cutoff_unix
- normalization version if available

### Raw recent behavior

Also include the last 10 completed prior matches per team with the same rich raw fields where populated.

Every raw row must include:
- provider match id
- kickoff
- venue
- opponent name/id
- provider=thestatsapi
- populated raw metrics only

The raw rows exist so the LLM can inspect combinations and asymmetries rather than seeing only means.

## Phase B — optional FootyStats sidecar

If the target teams have an EXPLICIT, reviewed cross-provider identity mapping, append FootyStats evidence as separately labelled evidence items.

Do NOT fuzzy-join teams or fixtures automatically.

The canonical registry supports TEAM/FIXTURE mappings, but the currently committed loader automatically seeds competition mappings only. Therefore a missing explicit team/fixture mapping is not permission to guess.

Do NOT blend same-named provider fields in the LLM packet.

## Prohibited packet content

Do not export:
- target result
- target post-match stats
- market close
- settlement
- p_model
- model probabilities
- future lineup/injury data
- future match observations
- deterministic feature performance/OOS results

## Validation

Before handing the JSON to ChatGPT assert:

- target_outcome_included=false
- every contributing history match kickoff < target kickoff
- every evidence_ref unique
- every numeric evidence item traceable to a real provider field
- no invented zeros for null/missing
- no npxG
- no odds/market data
- no p_model
- no future observation
- packet validates against DUAL_PROVIDER_PACKET_CONTRACT_V1.json conceptually

## Deliverable

Write one JSON file, suggested path:

research/dual_provider_llm/out/direct_pilot/PILOT_FIXTURE_PACKET_V1.json

Also print:
- selected fixture id
- kickoff
- home/away
- number of TheStatsAPI prior matches per team
- populated rich concepts
- packet SHA256
- leakage checks

Do NOT commit provider credentials or raw secrets.

Then paste the packet into ChatGPT together with DIRECT_LLM_HYPOTHESIS_PROMPT_V1.md.

No model fit and no outcome evaluation in this pilot.
