"""V8B.2 fixture-level support classifier (`v8b2_fixture_support_v1`).

Fixes the P1 evaluation-semantic defect exposed by V8B.1 Pilot-50: the frozen V8B.1 fixture
scorer called V7.1's `classify_support(..., unique_teams=1, ...)`, but the reused V7.1 gate
required `unique_teams >= 6`. Since a fixture-level cohort is, by construction, ONE subject
team's own prior matches, `unique_teams == 1` ALWAYS, so `SCORE_OK` was structurally
unreachable.

Root-cause translation (traced, effect-blind -- see V8B2_SUPPORT_SPEC.md):
  V7.1 `MIN_UNIQUE_TEAMS = 6` was documented at src/research/hypothesis_v7/pit.py:23 as
  "distinct teams/opponents contributing" -- a DIVERSITY floor guarding against a cohort
  dominated by a handful of counterpart identities. In V7.1 the pooled cohort spanned many
  SUBJECT teams, so distinct-subject-teams was that diversity. At the fixture level the pooled
  identity that varies is the OPPONENT the subject faced, so the direct semantic analogue is
  `unique_opponents`. The threshold's PURPOSE (>=6 distinct contributing identities) transfers
  directly; the number 6 was a diversity floor, never tied to any effect. Hence
  `MIN_UNIQUE_OPPONENTS = 6`.

The statistical unit is made EXPLICIT in the names so this mismatch cannot silently recur:
there is deliberately NO field named `unique_teams` anywhere in this module.

All other valid support semantics are RETAINED unchanged, imported from the frozen V7.1 pit:
  MIN_RAW_N (20), MIN_UNIQUE_FIXTURES (15), MIN_EFFECTIVE_N (10.0),
  MAX_WEIGHT_CONCENTRATION (0.25). `unique_opponents` is a DIVERSITY COUNT, kept SEPARATE from
  `effective_n` (a weighted pseudo-count) -- the gate protects against two distinct
  pathologies and never combines them into one score.

ZERO SPEND. Reads no CHAMPION, no effect, no target outcome. Effect-independent by design.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.research.hypothesis_v7 import pit as V7PIT

FIXTURE_SUPPORT_VERSION = "v8b2_fixture_support_v1"

# ---- thresholds ------------------------------------------------------------------------
# Retained UNCHANGED from the frozen V7.1 pit (same numeric contract, same source of truth):
MIN_RAW_N = V7PIT.MIN_RAW_N                              # 20
MIN_UNIQUE_FIXTURES = V7PIT.MIN_UNIQUE_FIXTURES          # 15
MIN_EFFECTIVE_N = V7PIT.MIN_EFFECTIVE_N                  # 10.0
MAX_WEIGHT_CONCENTRATION = V7PIT.MAX_WEIGHT_CONCENTRATION  # 0.25
# The ONE corrected threshold: the fixture-level analogue of the V7.1 team-diversity floor.
# Direct semantic translation of MIN_UNIQUE_TEAMS=6 (see module docstring). Effect-blind.
MIN_UNIQUE_OPPONENTS = 6

# Reuse the frozen status vocabulary so downstream code paths are unchanged.
SUPPORT_ADEQUATE = V7PIT.SUPPORT_ADEQUATE
SUPPORT_LOW = V7PIT.SUPPORT_LOW
SUPPORT_CONCENTRATED = V7PIT.SUPPORT_CONCENTRATED
SUPPORT_NOT_EVALUABLE = V7PIT.SUPPORT_NOT_EVALUABLE


@dataclass(frozen=True)
class FixtureSupport:
    """Explicit fixture-level support object. The statistical unit is named so it cannot be
    confused with the pooled/fold unit: the diversity field is `unique_opponents`, NEVER
    `unique_teams`."""
    status: str
    raw_n: int
    unique_fixtures: int
    unique_opponents: int
    effective_n: float
    weight_concentration: float
    failures: tuple  # tuple of {"field","have","need"|"limit"} -- ONLY actual failing predicates


def classify_fixture_support(*, raw_n: int, unique_fixtures: int, unique_opponents: int,
                             effective_n: float, max_weight_share: float) -> FixtureSupport:
    """Classify a fixture-level cohort's support against the frozen thresholds.

    Reports ONLY the predicates that actually FAILED (each as an explicit
    {field, have, need|limit} record) -- never a disjunctive string that lists thresholds that
    passed. Effect-independent.
    """
    failures = []

    if raw_n == 0:
        # No observations at all: not evaluable (kept distinct from LOW support).
        return FixtureSupport(status=SUPPORT_NOT_EVALUABLE, raw_n=raw_n,
                              unique_fixtures=unique_fixtures, unique_opponents=unique_opponents,
                              effective_n=round(effective_n, 4),
                              weight_concentration=round(max_weight_share, 4),
                              failures=({"field": "raw_n", "have": 0, "need": MIN_RAW_N},))

    if raw_n < MIN_RAW_N:
        failures.append({"field": "raw_n", "have": raw_n, "need": MIN_RAW_N})
    if unique_fixtures < MIN_UNIQUE_FIXTURES:
        failures.append({"field": "unique_fixtures", "have": unique_fixtures,
                         "need": MIN_UNIQUE_FIXTURES})
    if unique_opponents < MIN_UNIQUE_OPPONENTS:
        failures.append({"field": "unique_opponents", "have": unique_opponents,
                         "need": MIN_UNIQUE_OPPONENTS})
    if effective_n < MIN_EFFECTIVE_N:
        failures.append({"field": "effective_n", "have": round(effective_n, 4),
                         "need": MIN_EFFECTIVE_N})

    concentrated = max_weight_share > MAX_WEIGHT_CONCENTRATION
    if concentrated:
        failures.append({"field": "weight_concentration", "have": round(max_weight_share, 4),
                         "limit": MAX_WEIGHT_CONCENTRATION})

    if not failures:
        status = SUPPORT_ADEQUATE
    elif concentrated and len(failures) == 1:
        # Only pathology is weight concentration -> distinct named status (mirrors V7.1).
        status = SUPPORT_CONCENTRATED
    else:
        status = SUPPORT_LOW

    return FixtureSupport(status=status, raw_n=raw_n, unique_fixtures=unique_fixtures,
                          unique_opponents=unique_opponents, effective_n=round(effective_n, 4),
                          weight_concentration=round(max_weight_share, 4),
                          failures=tuple(failures))


def version_stamp() -> dict:
    return {"fixture_support_version": FIXTURE_SUPPORT_VERSION,
            "statistical_unit": "one subject team, one target fixture, one conditioned "
                                "historical cohort",
            "diversity_field": "unique_opponents",
            "no_unique_teams_field": True,
            "thresholds": {"min_raw_n": MIN_RAW_N, "min_unique_fixtures": MIN_UNIQUE_FIXTURES,
                           "min_unique_opponents": MIN_UNIQUE_OPPONENTS,
                           "min_effective_n": MIN_EFFECTIVE_N,
                           "max_weight_concentration": MAX_WEIGHT_CONCENTRATION},
            "retained_from_v7_pit": ["min_raw_n", "min_unique_fixtures", "min_effective_n",
                                     "max_weight_concentration"],
            "corrected": {"was": "unique_teams>=6 (V7.1 pooled-cohort unit, always 1 at "
                                 "fixture level -> SCORE_OK unreachable)",
                          "now": "unique_opponents>=6 (fixture-level diversity analogue)"},
            "reads_outcomes": False, "effect_independent": True}
