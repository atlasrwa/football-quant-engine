# Fixture Evidence Packet (`fixture_evidence_packet_v1`)

The bounded, deterministic factual universe handed to the LLM (brief §9, §10). Every numeric
value originates from Python; the LLM computes nothing. Built by
`evidence.EvidencePacketBuilder.build(target_record)`.

## Top-level structure
```
{
  "packet_schema_version", "cohort_policy_version",
  "fixture": {fixture_id, home, away, competition, season, kickoff_unix},
  "information_cutoff_unix",              # == kickoff_unix
  "competition_context": {tags},
  "team_a": {name, venue:"home", style_tags[], evidence_ids[]},
  "team_b": {name, venue:"away", style_tags[], evidence_ids[]},
  "league_environment": {evidence_ids[]},
  "evidence": [ EvidenceItem, ... ],      # the only citable facts
  "unsupported_context": {formation_status, injury_status, neutral_venue},
  "data_quality": {n_evidence, n_pit_safe, n_unavailable},
  "provider_provenance": {...},
  "packet_hash"                            # sha256 over the packet minus this field
}
```

## EvidenceItem (every value carries provenance — brief §10)
```
{
  "id",                       # stable, deterministic (e.g. A_ATK_crosses_for_<h6>)
  "metric",                   # e.g. crosses_for, corners_against, crosses_2h_shift, league_corners_env
  "value",                    # shrunk PIT estimate, or null if UNAVAILABLE
  "sample_n",
  "scope": {team, opponent, venue, side, competition, season, [period]},
  "reliability": LOW|MEDIUM|HIGH,     # by sample size
  "shrinkage_level": DIRECT|SHRUNK,
  "evidence_level": VENUE_OVERALL|ALL_VENUES|COMPETITION_PRIOR|...,
  "source_provider": thestatsapi|derived,
  "source_field",
  "cutoff_unix",              # == fixture kickoff
  "temporal_status": PIT_SAFE|UNAVAILABLE,
  "max_source_time_unix"
}
```

## Evidence families emitted per fixture
- **Attack (for):** crosses, total_shots, shots_on_target, shots_inside_box, touches_in_box,
  corners, possession, throw_ins, final_third_entries.
- **Defense (against / actions):** crosses_against, total_shots_against, shots_inside_box_against,
  touches_in_box_against, corners_against, blocked_shots, clearances, interceptions.
- **Discipline:** fouls_for, tackles_for, yellow_cards_for, fouls_against.
- **Second-half shift:** `{crosses,total_shots,corners,possession}_2h_shift` (2H mean − 1H mean),
  from raw TheStatsAPI half splits. Score-state caveat: flagged, not yet conditioned (see below).
- **League environment:** `league_{corners,total_shots,fouls,yellow_cards}_env` (prior-match mean total).

## Cohort hierarchy & shrinkage (brief §12, §41)
v1 uses a two-tier venue hierarchy with empirical-Bayes partial pooling: a venue-conditioned
child cohort is shrunk toward the team's overall-season parent mean with weight `n/(n+6)`.
Deeper tiers (exact-opponent → formation → tactical-cluster → venue → all-venues → competition)
are defined in the ontology's `EVIDENCE_LEVELS` and are the documented v2 expansion; formation
tiers are inert while formation is UNKNOWN.

## Determinism & safety
- `packet_hash` is stable across rebuilds (tested).
- Reads only prior same-season matches for team state; prior competition matches for league env;
  never the target or the future (tested: `test_llm_matchup_evidence_pit.py`).
- Missing data → `value:null`, `temporal_status:UNAVAILABLE` — never fabricated.
