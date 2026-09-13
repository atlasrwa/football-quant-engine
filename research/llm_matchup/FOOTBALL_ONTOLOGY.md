# Football Ontology (`football_ontology_v1`)

Finite, versioned taxonomy the LLM is confined to (brief §14–§16). The LLM may only emit
mechanism ids, level/advantage enums and confidence enums from this ontology; it may not
invent concepts fixture-by-fixture. Machine-readable: `out/ontology.json`,
`out/ontology_mechanisms.csv`.

## Enumerated value sets
- **LEVELS** (team-state): `VERY_LOW, LOW, MEDIUM, HIGH, VERY_HIGH, UNKNOWN`.
- **ADVANTAGE_LEVELS** (matchup): `STRONG_B_ADVANTAGE, B_ADVANTAGE, NEUTRAL, A_ADVANTAGE, STRONG_A_ADVANTAGE, UNKNOWN, CONFLICTED`.
- **CONFIDENCE:** `LOW, MEDIUM_LOW, MEDIUM, MEDIUM_HIGH, HIGH, UNKNOWN`.
- **EVIDENCE_LEVELS** (preferred cohort tier): `EXACT_OPPONENT, EXACT_FORMATION, FORMATION_FAMILY, TACTICAL_CLUSTER, VENUE_OVERALL, ALL_VENUES, COMPETITION_PRIOR, NONE`.
- **UNCERTAINTY_FACTORS:** `SMALL_SAMPLE, SHRUNK_TO_PRIOR, PROVIDER_DISAGREEMENT, FORMATION_UNKNOWN, SCORE_STATE_CONFOUND, COLD_START, SINGLE_PROVIDER, WIDE_COHORT_ONLY`.

## Mechanisms (24)
Each mechanism declares the **evidence metric families it is allowed to cite**; the validator
rejects any conclusion citing evidence outside that allow-list, so a mechanism cannot be
"justified" by irrelevant numbers.

### Attack (team-state)
`WIDTH_PRESSURE, TERRITORIAL_PRESSURE, BOX_PRESSURE, SHOT_VOLUME, SHOT_QUALITY,
SET_PIECE_GENERATION, SECOND_HALF_ESCALATION`

### Defense (team-state)
`SHOT_SUPPRESSION, BOX_PROTECTION, CROSS_ALLOWANCE, CLEARANCE_DEPENDENCE,
CORNER_CONCESSION, SAVE_ENVIRONMENT`

### Discipline (team-state)
`CONTACT_INTENSITY, FOUL_TENDENCY, BOOKING_CONVERSION, FOUL_DRAWING`

### Matchup / interaction (direction MATCH, advantage-framed)
`WIDE_PRESSURE_MATCHUP, BOX_PRESSURE_MATCHUP, SHOT_CREATION_MATCHUP,
CORNER_MECHANISM_MATCHUP, CONTACT_MATCHUP, SECOND_HALF_PRESSURE_SHIFT, TEMPO_EXPECTATION`

## Context flags (closed-world honesty)
- `formation_status`: `KNOWN_PIT_SAFE | FORMATION_UNKNOWN`
- `injury_status`: `KNOWN_PIT_SAFE | INJURY_STATUS_UNKNOWN`
- `neutral_venue`: `TRUE | FALSE | UNKNOWN`
- `score_state_conditioning`: `APPLIED | UNAVAILABLE`
- `provider_agreement`: `AGREE | DISAGREE | SINGLE_PROVIDER | UNKNOWN`

## Style clusters are data-driven, not model-invented (brief §13, §42)
Opponent style tags (`HIGH_POSSESSION, LOW_BLOCK_OR_DIRECT, HIGH_WIDTH, HIGH_BOX_ENTRY,
SHOT_HEAVY, BALANCED, STYLE_UNKNOWN`) are computed deterministically from a team's own prior
standardized behavioral profile vs the competition mean. The LLM may *interpret/label* an
existing cluster; it never derives style from club names. This is a coarse v1; a PCA/mixture
clustering is a documented future upgrade.

## Formation is not style (brief §5)
`football_ontology_v1` intentionally represents **behavior** (width, territory, box entry,
shot profile, contact) rather than formation strings. Formation is currently
`FORMATION_UNKNOWN` (see TEMPORAL_SAFETY.md), so behavioral mechanisms carry the load.

## Versioning
Any change to mechanisms, enums, or allow-lists creates `football_ontology_v2`; historical
LLM states are never silently regenerated (brief §26). The ontology sha256 is recorded in
`prompt_manifest.json` and every call manifest.
