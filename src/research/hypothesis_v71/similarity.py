"""V7.1 similar-opponent engine (`v71_similarity_v1`). Section 11.

The frozen V7 similarity spec (dimensions, scaling, shrinkage, distance, k, tie-break) is
REUSED verbatim -- it was already audited and repaired once, and restating it would let the
two experiments drift. What V7.1 adds is the missing operational half: a PIT-safe function
that actually names the similar-opponent cohort at a target fixture, with every profile built
from strictly-prior observations.

Temporal rule, enforced structurally: for a fixture at T, every profile is built from the
team's matches strictly before T. No full-season aggregate, no future opponent, no scaler
fitted on anything at or after T. `assert_profiles_are_pit` turns that into a raised error.

The LLM never produces a similarity score. Nothing here reads an outcome.
"""
from __future__ import annotations

from src.research.hypothesis_v7 import similarity as V7S

SIMILARITY_VERSION = "v71_similarity_v1"

DIMENSIONS = tuple(V7S.SIMILARITY_DIMENSIONS)
DIMENSION_BINDING = dict(V7S.DIMENSION_BINDING)
DIMENSION_METRIC = dict(V7S.DIMENSION_METRIC)
SCALING = V7S.SCALING
PRIMARY_DISTANCE = V7S.PRIMARY_DISTANCE
K_NEIGHBORS = V7S.K_NEIGHBORS
MIN_PROFILE_HISTORY_MATCHES = V7S.MIN_PROFILE_HISTORY_MATCHES
PROFILE_SHRINKAGE_K = V7S.PROFILE_SHRINKAGE_K
TIE_BREAK = V7S.TIE_BREAK
RESTRICT_SAME_COMPETITION = V7S.RESTRICT_SAME_COMPETITION
MAX_MISSING_DIMS = V7S.MAX_MISSING_DIMS


class SimilarityRefused(Exception):
    """The cohort cannot be formed PIT-safely at this fixture."""


def assert_profiles_are_pit(profile_observation_unixes, reference_unix) -> None:
    """Every observation feeding a profile must strictly precede the target fixture."""
    from src.research.hypothesis_v7 import leakage as V7L
    V7L.assert_no_future_in_profile(profile_observation_unixes, reference_unix)


class SimilarityEngine:
    """PIT-safe k-nearest-opponent cohorts over a `PITIndex`.

    Profiles, the z-scale fit and the competition baseline are ALL rebuilt from the prior
    frontier of each target fixture, cached by (competition, reference position) so a cache
    hit can never serve a profile built at a later reference time.
    """

    def __init__(self, index):
        self.index = index
        self._cache = {}

    # ---- profile construction ----------------------------------------------------------
    def _prior_matches_for(self, team_id, rec_i):
        return [self.index.recs[e[0]]
                for e in self.index.prior_entries(team_id, rec_i)]

    def _profiles_at(self, competition, rec_i):
        key = (competition, rec_i)
        got = self._cache.get(key)
        if got is not None:
            return got
        ref = int(self.index.kick[rec_i])
        teams = {tid for tid, s in self.index.series.items()
                 if any(e[1] < ref and e[2] == competition for e in s)}
        profiles = {}
        for tid in sorted(teams):
            prior = [r for r in self._prior_matches_for(tid, rec_i)
                     if int(r.kickoff_unix) < ref]
            if len(prior) < MIN_PROFILE_HISTORY_MATCHES:
                continue
            assert_profiles_are_pit([int(r.kickoff_unix) for r in prior], ref)
            profiles[tid] = V7S.team_profile(prior, tid)
        if not profiles:
            self._cache[key] = ({}, None, None)
            return self._cache[key]
        baseline = V7S.competition_baseline(list(profiles.values()))
        shrunk = {tid: V7S.shrink_profile(p, baseline, PROFILE_SHRINKAGE_K)
                  for tid, p in profiles.items()}
        fit = V7S.zscore_fit(list(shrunk.values()))
        self._cache[key] = (shrunk, baseline, fit)
        return self._cache[key]

    # ---- the cohort --------------------------------------------------------------------
    def similar_opponent_ids(self, index, opponent_id, rec, rec_i) -> frozenset:
        """The k opponents most similar to `opponent_id`, as at this fixture.

        Deterministic: distances are computed on shrunk z-vectors over the frozen dimensions,
        ties broken by the frozen rule. Refuses rather than guessing when the fixture
        opponent has too little history for a profile.
        """
        profiles, _baseline, fit = self._profiles_at(rec.competition, rec_i)
        if not profiles or str(opponent_id) not in profiles:
            raise SimilarityRefused(
                f"no PIT profile for opponent {opponent_id} at fixture {rec.fixture_id}")
        target, target_missing = V7S.zvector(profiles[str(opponent_id)], fit)
        if target_missing > MAX_MISSING_DIMS:
            raise SimilarityRefused(
                f"opponent {opponent_id} profile is missing {target_missing} dimensions "
                f"(limit {MAX_MISSING_DIMS}); imputing them would distort every distance")
        rows = []
        for tid, p in profiles.items():
            if tid == str(opponent_id):
                continue
            vec, missing = V7S.zvector(p, fit)
            # A profile missing more than the frozen allowance is EXCLUDED, never imputed:
            # an imputed dimension sits at the cohort mean and would make a data-poor team
            # look artificially similar to the average opponent.
            if missing > MAX_MISSING_DIMS:
                continue
            rows.append((V7S.distance(target, vec, PRIMARY_DISTANCE),
                         self._tie_key(tid), tid))
        if len(rows) < K_NEIGHBORS:
            raise SimilarityRefused(
                f"only {len(rows)} comparable opponents with PIT profiles "
                f"(k={K_NEIGHBORS}) at fixture {rec.fixture_id}")
        rows.sort()
        return frozenset(tid for _d, _t, tid in rows[:K_NEIGHBORS])

    def _tie_key(self, team_id):
        s = self.index.series.get(team_id) or []
        return (s[0][1], team_id) if s else (0, team_id)


def version_stamp() -> dict:
    stamp = dict(V7S.version_stamp())
    stamp.update({"similarity_version": SIMILARITY_VERSION,
                  "source_spec": V7S.SIMILARITY_VERSION,
                  "profiles_are_rebuilt_per_target_fixture": True,
                  "scaler_fitted_on_prior_frontier_only": True,
                  "refuses_rather_than_imputes_missing_target_profile": True,
                  "llm_produces_similarity_score": False})
    return stamp
