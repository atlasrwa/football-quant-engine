"""V7.1 recency / non-stationarity contract (`v71_recency_v1`). Section 12.

Football teams are not stationary across seasons: squads, managers and tactical regimes turn
over. Any profile that pools three seasons with equal weight silently asserts they are one
population.

This module makes the weighting EXPLICIT and FROZEN, and it reuses the frozen V7 decay and
shrinkage primitives rather than restating them, so the two experiments cannot drift.

Frozen rules:
  * decay half-lives are a small PREREGISTERED FAMILY, never a searched grid, and BOTH members
    are always reported -- the estimator may never select the better-looking one;
  * every recent-window estimate is shrunk toward a longer-run prior, so a W5 estimate is
    never treated as truth;
  * hyperparameters are constants fixed before any confirmatory effect, so there is nothing to
    fit on the fresh sample. `assert_not_fitted` makes that checkable rather than promised.
"""
from __future__ import annotations

from src.research.hypothesis_v7 import pit as V7PIT

RECENCY_VERSION = "v71_recency_v1"

#: Reused verbatim from the frozen V7 point-in-time engine.
HALFLIVES_DAYS = tuple(V7PIT.TIME_DECAY_HALFLIVES_DAYS)
SHRINKAGE_PRIOR = V7PIT.SHRINKAGE_PRIOR
SHRINKAGE_STRENGTH_K = V7PIT.SHRINKAGE_STRENGTH_K

#: A short window is an ESTIMATE, not a fact. Every windowed cohort is shrunk toward the
#: competition-environment prior with the same k as any other cohort, so W5 carries no
#: privileged status.
WINDOWS_ARE_SHRUNK = True

#: Cross-season contribution is governed by decay ALONE -- there is no separate season weight,
#: and no season is dropped. Stated so a reader knows multi-season pooling is deliberate and
#: down-weighted rather than accidental and flat.
CROSS_SEASON_POLICY = ("prior seasons contribute through time decay only; no season is "
                       "excluded and no additional season weight is applied")

#: Regime variables (manager, formation) are NOT used: this corpus cannot resolve them per
#: prior match. Named here so their absence is a declared limitation, not an oversight.
REGIME_VARIABLES_UNAVAILABLE = ("manager", "formation", "lineup")


class Recency:
    """One frozen half-life. The estimator iterates the whole family; it never picks one."""

    def __init__(self, halflife_days: float):
        if halflife_days not in HALFLIVES_DAYS:
            raise ValueError(f"half-life {halflife_days} is outside the frozen family "
                             f"{HALFLIVES_DAYS}; V7.1 does not search windows")
        self.halflife_days = float(halflife_days)

    def weight(self, obs_unix: int, ref_unix: int) -> float:
        """Decay weight of an observation, PIT-checked: an observation at or after the
        reference time has no weight because it may not exist at prediction time."""
        if int(obs_unix) >= int(ref_unix):
            raise ValueError(f"observation {obs_unix} is not strictly before {ref_unix}")
        return V7PIT.time_decay_weight(int(obs_unix), int(ref_unix), self.halflife_days)

    def shrink(self, mean, n, prior_mean):
        return V7PIT.shrink_estimate(mean, n, prior_mean, SHRINKAGE_STRENGTH_K)


class UniformRecency(Recency):
    """The un-decayed member. Weight 1 for every strictly-prior observation."""

    def __init__(self):
        self.halflife_days = None

    def weight(self, obs_unix: int, ref_unix: int) -> float:
        if int(obs_unix) >= int(ref_unix):
            raise ValueError(f"observation {obs_unix} is not strictly before {ref_unix}")
        return 1.0


def family():
    """The frozen decay family, in frozen order. Both members are always evaluated."""
    return tuple(Recency(h) for h in HALFLIVES_DAYS)


def assert_not_fitted(fit_observation_unixes, train_end_unix) -> None:
    """Hyperparameters are constants, so nothing may be fitted at all -- least of all on data
    at or after a fold's training boundary. Delegates to the frozen V7 leakage guard."""
    from src.research.hypothesis_v7 import leakage as V7L
    V7L.assert_hyperparams_fit_past_only(fit_observation_unixes, train_end_unix)


def version_stamp() -> dict:
    return {"recency_version": RECENCY_VERSION,
            "halflives_days": list(HALFLIVES_DAYS),
            "family_is_preregistered_not_searched": True,
            "both_members_always_reported": True,
            "shrinkage_prior": SHRINKAGE_PRIOR,
            "shrinkage_strength_k": SHRINKAGE_STRENGTH_K,
            "windows_are_shrunk": WINDOWS_ARE_SHRUNK,
            "cross_season_policy": CROSS_SEASON_POLICY,
            "regime_variables_unavailable": list(REGIME_VARIABLES_UNAVAILABLE),
            "hyperparameters_are_constants": True,
            "source": V7PIT.PIT_VERSION}
