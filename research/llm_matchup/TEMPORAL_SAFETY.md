# Temporal Safety (Point-in-Time Integrity)

Every evidence value satisfies `source information time < fixture kickoff` and the
information cutoff equals kickoff. The LLM only sees the packet; it cannot reach past the
cutoff. Fail closed when safety cannot be proven (brief §8, §10, §36).

## Deterministic guarantees (tested)
`tests/research/test_llm_matchup_evidence_pit.py`:
- **No target/future leakage:** team-state cohorts read only prior same-season matches; the
  target's own (and future) values are never included (verified with an injected 99-corner
  target that must not appear).
- **League environment prior-only:** competition baselines use only matches before kickoff.
- **Cold start fails closed:** a team with `< MIN_HISTORY (4)` prior matches yields
  `value:null / temporal_status:UNAVAILABLE`, never a fabricated number.
- **Orientation:** FOR vs AGAINST and home/away are correctly assigned.
- **Deterministic packet hash** across rebuilds.

## Half-splits (1H/2H)
Sourced from the raw TheStatsAPI `/stats` payload (`first_half`/`second_half` cells), which
the normal adapter drops. They are **realized in-match** for *prior* fixtures and used only as
prior-match rolling inputs — never for the target — so they remain PIT-safe.

## Score-state confound (brief §36) — explicitly flagged, not yet resolved
Second-half pressure (e.g. `crosses_2h_shift`) can be trailing-game behavior, not stable style.
`football_ontology_v1` therefore:
- exposes `SCORE_STATE_CONFOUND` as an uncertainty factor, and
- sets `context_flags.score_state_conditioning = UNAVAILABLE` in v1.
The raw payload does **not** carry per-interval running score by minute in the cached `/stats`
object (only half/regulation aggregate scores in the fixture object), so leading/level/trailing
half conditioning is a documented **v2 requirement** pending an interval score-state source.
Until then, 2H-shift mechanisms must be reported at reduced confidence with the confound flag.

## Formation — classified `FORMATION_UNKNOWN` (honest blocker)
Cached lineups (`lineups_mt_*.json`) contain `formation` and `confirmed:true` but **no
announcement timestamp**. A "confirmed" lineup is typically the final XI; we cannot prove it was
known before kickoff. Per strict PIT rules we **do not** use formation as pre-match knowledge.
Behavioral style clusters (derived from prior realized play) carry the tactical signal instead.
To unlock formation safely we would need a lineup **announcement timestamp** proving pre-kickoff
availability. See UNAVAILABLE_CONTEXT.md.

## Injuries / weather
Not available from the audited providers → `INJURY_STATUS_UNKNOWN`; weather out of scope.
Never inferred from omission.

## Neutral venue
The fixture object carries an explicit `is_neutral` field, so neutral venue can be represented
honestly (not inferred from names/geography). v1 packet sets it `UNKNOWN` pending wiring of that
field into the builder (a small, safe v1.1 addition).
