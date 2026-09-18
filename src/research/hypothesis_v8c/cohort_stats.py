"""V8C shared cohort primitives (`v8c_cohort_stats_v1`).

Exists so the PRE-T process never has to import a SCORER.

The P0 outcome seal is process separation: `select_freeze.py` must be able to assert that no
scoring module is loaded in its interpreter. That assertion is only meaningful if the pre-T
classifier does not itself pull one in -- and it used to, because it needed
`_weighted_variance`, `ZERO_VARIANCE_FLOOR` and `unique_opponents_of_cohort` from the scorer
module.

Those are not scoring functions. Every one of them is a property of the PRE-T COHORT:

    weighted_mean / weighted_variance   moments of the cohort's own prior observations
    unique_opponents_of_cohort          a diversity count over strictly-prior entries
    ZERO_VARIANCE_FLOOR                 the dispersion floor, a cohort property

None of them touches the target's observed value. Hoisting them here lets both the pre-T
classifier and the post-T scorer import the SAME implementations while keeping the scorer --
the only module that reads a target outcome -- out of the pre-T process entirely.

Values are imported from the frozen V8B.2 scorer where they exist there, so nothing drifts.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

COHORT_STATS_VERSION = "v8c_cohort_stats_v1"

#: The frozen V8B.2 dispersion floor, stated LITERALLY rather than imported.
#:
#: Importing it from `hypothesis_v8b2.scorer` would load a scoring module into the pre-T
#: interpreter and silently defeat the P0 seal assertion this module exists to make possible.
#: The no-drift guarantee is preserved by a TEST -- `test_outcome_seal.py::
#: test_zero_variance_floor_matches_frozen_scorer` asserts this value equals
#: `hypothesis_v8b2.scorer.ZERO_VARIANCE_FLOOR` -- so a change upstream fails the suite rather
#: than diverging quietly.
ZERO_VARIANCE_FLOOR = 1e-18

#: Terminal scoring statuses. Named here so the pre-T consistency invariant can reference them
#: without importing a scorer.
SCORE_OK = "SCORE_OK"
SCORE_REFUSED = "SCORE_REFUSED"
SCORE_INSUFFICIENT_SUPPORT = "SCORE_INSUFFICIENT_SUPPORT"
SCORE_UNDEFINED = "SCORE_UNDEFINED"
TERMINAL_STATUSES = (SCORE_OK, SCORE_REFUSED, SCORE_INSUFFICIENT_SUPPORT, SCORE_UNDEFINED)

#: The exact refusal string emitted when the target's own observation is unavailable. The ONE
#: post-T state a PRE_T_EVALUABLE hypothesis may legitimately reach besides SCORE_OK.
OBSERVED_UNAVAILABLE_REASON = "observed value or environment mean unavailable"


def weighted_mean(values, weights):
    tw = sum(weights)
    if tw <= 0:
        return None
    return sum(v * w for v, w in zip(values, weights)) / tw


def weighted_variance(values, weights):
    tw = sum(weights)
    if tw <= 0:
        return None
    mean = weighted_mean(values, weights)
    return sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / tw


def unique_opponents_of_cohort(ir, index, rec_i, cohort_fixtures) -> int:
    """Distinct canonical opponent identities contributing to the fixture-level cohort.

    Walks only `prior_entries`, which is strictly-before by construction, so this is PIT-safe
    and carries no target observation.
    """
    rec = index.recs[rec_i]
    subject_id = str(rec.home_id) if ir.subject == "HOME_TEAM" else str(rec.away_id)
    role = ir.cohort.entity_role
    if role == "SUBJECT":
        entity_id = subject_id
    elif role == "FIXTURE_OPPONENT":
        entity_id = str(rec.away_id) if str(rec.home_id) == subject_id else str(rec.home_id)
    else:
        return 0
    want = set(str(f) for f in (cohort_fixtures or ()))
    if not want:
        return 0
    opponents = set()
    for e in index.prior_entries(entity_id, rec_i):
        rec_idx, _kick, _comp, _is_home, opponent_id = e
        if str(index.recs[rec_idx].fixture_id) not in want:
            continue
        if opponent_id is None:
            continue
        oid = str(opponent_id)
        if oid == str(entity_id):
            continue
        opponents.add(oid)
    return len(opponents)


def version_stamp() -> dict:
    return {"cohort_stats_version": COHORT_STATS_VERSION,
            "purpose": "let the PRE-T process avoid importing any scorer module",
            "all_quantities_are_cohort_properties": True,
            "reads_target_outcome": False,
            "zero_variance_floor": ZERO_VARIANCE_FLOOR,
            "terminal_statuses": list(TERMINAL_STATUSES)}
