# Formation Resolution Policy (`formation_policy_v1`)

Phase B introduces the architectural correction that **formation is now a
football-resolution variable**. Formation is no longer discarded merely because a
trustworthy historical announcement timestamp is unavailable.

This document defines the **two-concept formation model** and the **hard leakage rule**
that keeps them separate. It is the authoritative reference for the code in
`src/research/llm_matchup/formation.py`, `formation_evidence.py`, and `evidence_v2.py`.

---

## 1. Two concepts, never conflated

### A. `RESOLVED_FORMATION`

> The formation recorded for how a team **actually lined up / played** in a **completed
> historical match**.

Examples: `4-2-3-1`, `4-3-3`, `3-4-2-1`.

**Source:** cached lineup payloads `data/thestatsapi/championship/lineups_mt_<id>.json`,
each carrying `confirmed: true`, `home.formation`, `away.formation`. There is **no
announcement timestamp** anywhere in this data source.

**Permitted uses (historical resolution):**
- historical behavioral analysis
- formation-conditioned cohort construction
- learning what statistical/tactical state accompanies a formation
- resolving team style
- opponent-conditioned behavior
- learning formation families
- learning formation × formation mechanisms
- building historical tactical archetypes

The lack of a trustworthy announcement timestamp does **not** invalidate these uses,
because they describe **completed** matches, not the future.

Represented in code by `formation.ResolvedFormation` (`source_type="RESOLVED"`,
`has_announcement_timestamp=False`).

### B. `PREMATCH_FORMATION`

> Formation information legitimately available or projected **before** the fixture being
> predicted.

May eventually originate from: official announced lineup, timestamped lineup feed,
reliable pre-match provider data, deterministic formation projection, or a separate
formation prediction model.

`PREMATCH_FORMATION` is the **only** formation that may enter an actual forward
prediction.

Represented in code by `formation.FormationInput` with `source_type ∈ {ANNOUNCED,
PROJECTED, UNKNOWN}` and an optional `distribution` for the formation-uncertain case.

**These two concepts MUST NEVER be silently conflated.** `FormationInput` cannot carry
`source_type="RESOLVED"`; `formation.assert_not_target_resolved()` enforces this.

---

## 2. Hard leakage rule

For a **target fixture**:

| Match role                         | Formation evidence allowed                        |
|------------------------------------|---------------------------------------------------|
| historical source matches (`kickoff < target cutoff`) | **RESOLVED formation allowed** (conditioning key) |
| the target fixture itself          | **only PREMATCH formation / projection** — never the target's own final recorded formation |

Forbidden (leakage):

```
target fixture final recorded formation  ->  target prediction   (in chronological OOS)
```

Enforcement:
- `evidence_v2.EvidencePacketBuilderV2.build()` never reads the target's resolved
  formation. It conditions **historical cohorts** on the resolved formation those source
  matches used, and attaches only a `FormationInput` for the target.
- The default `FormationInput` for the target in Phase B is `UNKNOWN` (honest, since no
  pre-match formation source is proven for history).
- `validator.validate()` enforces that the output's `context_flags.prematch_formation_status`
  matches the packet's declared `formation_context.prematch_status`, so the LLM cannot
  silently upgrade an unknown target formation into a known one.
- The leakage guard is covered by tests in `tests/research/test_formation_leakage.py`.

---

## 3. Formation is part of football resolution, not a stereotype

The historical engine learns:

```
TEAM + VENUE + RESOLVED_FORMATION + OPPONENT_RESOLVED_FORMATION + ACTUAL_BEHAVIOR
```

A family label (`FORMATION_FAMILY_V1.json`) is a **conditioning key only**. It carries no
behavioral assumption. We never assume `4-3-3 = high width` or `3-5-2 = defensive`.
Instead we measure:

```
formation  ->  observed behavior under that formation (fc_* evidence, formation_delta_*)
```

Two teams with the same nominal formation can have completely different measured states.
The Phase-B prompt (`sonnet_prompt_v2`) instructs the model to respond to the **measured
behavior**, not the label. The label-shuffle control (§21 of the brief) tests that the
model is not over-relying on the label.

---

## 4. Formation availability classification (four separate questions)

Reducing everything to `formation available = false` loses information. Phase B reports
four independent axes (see `PHASE_B_AUDIT.md` for the final values):

| Axis                              | Meaning                                                        |
|-----------------------------------|----------------------------------------------------------------|
| **HISTORICAL RESOLUTION**         | Do we know what formation was actually played historically?    |
| **HISTORICAL PREMATCH AVAILABILITY** | Can we prove the formation was known *before* those historical kickoffs? |
| **FORWARD ANNOUNCED**             | Can we ingest an official announced pre-match formation today?  |
| **FORWARD PROJECTED**             | Can we project a pre-match formation from prior information?     |

For this dataset:
- HISTORICAL RESOLUTION = **AVAILABLE** (1001 lineup matches; 21 formations; all overlap
  the corpus).
- HISTORICAL PREMATCH AVAILABILITY = **UNPROVEN** (no announcement timestamp exists).
- FORWARD ANNOUNCED = **NOT_IMPLEMENTED** (interface designed via `FormationInput`, no live
  feed wired).
- FORWARD PROJECTED = **NOT_IMPLEMENTED** (interface designed; no projection model built;
  recommendations in `PHASE_B_PLAN.md` §Phase-C scenarios).

---

## 5. Data coverage note (important caveat)

Although 1001 matches carry resolved formation, they are scattered across teams and
seasons. Consequently **exact-formation cohorts per team are typically tiny** (often
`n = 1`). The hierarchical ladder in `formation_evidence.formation_matchup()` therefore
degrades most matchup estimates to the `VENUE_OVERALL` / `FAMILY` tiers. This is by design
(a tiny exact cohort must not masquerade as strong evidence) and is a central empirical
finding for Phase C planning. See `FORMATION_BEHAVIOR_ANALYSIS.md`.
