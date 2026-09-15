"""V7 point-in-time engine + support rules (`v7_pit_v1`). Phases 5, 9, 10, 26.

Every historical observation for fixture t is constructed as if measured at t's own
prediction timestamp: only fixtures STRICTLY BEFORE t (by kickoff_unix) may inform team
profiles, opponent similarity, cohorts, and conditions. The target/outcome is fixture t's own
observed statistic. This rule applies recursively across folds.

Support rules (raw N, effective N, concentration, dependence) are FROZEN here, before any
effect is examined. Recency is handled by preregistered time-decay/shrinkage families, never
by searching windows for the best result.

ZERO SPEND. Reads only the local historical corpus. NO CHAMPION, NO p_model, NO effects.
"""
from __future__ import annotations

import math

PIT_VERSION = "v7_pit_v1"

# ---- support thresholds (Phase 9), frozen BEFORE effect examination -------------------
MIN_RAW_N = 20                 # historical observations backing a cohort/effect
MIN_UNIQUE_FIXTURES = 15       # distinct fixtures (not just repeated rows)
MIN_UNIQUE_TEAMS = 6           # distinct teams/opponents contributing
MIN_EFFECTIVE_N = 10.0         # Kish effective N after similarity/decay weighting
MAX_WEIGHT_CONCENTRATION = 0.25  # no single observation may hold >25% of total weight
MIN_COMPETITION_COVERAGE = 1   # at least one competition (documented if restricted)

# ---- recency / shrinkage family (Phase 10), frozen; NOT searched for best -------------
TIME_DECAY_HALFLIVES_DAYS = (180, 365)   # a small preregistered family, not a grid search
SHRINKAGE_PRIOR = "TEAM_COMPETITION_BASELINE"
SHRINKAGE_STRENGTH_K = 10.0    # pseudo-observations pulling toward the baseline prior

SUPPORT_ADEQUATE = "ADEQUATE_SUPPORT"
SUPPORT_LOW = "LOW_SUPPORT"
SUPPORT_CONCENTRATED = "CONCENTRATED_SUPPORT"
SUPPORT_UNSTABLE = "UNSTABLE_SUPPORT"
SUPPORT_NOT_EVALUABLE = "NOT_EVALUABLE"


def prior_fixtures(index, target_rec):
    """Fixtures STRICTLY before target_rec.kickoff_unix. The PIT frontier."""
    cut = int(target_rec.kickoff_unix)
    return [r for r in index.records if int(r.kickoff_unix) < cut]


def prior_for_team(index, target_rec, team_id):
    """PIT-safe prior matches involving a team, strictly before the target fixture."""
    cut = int(target_rec.kickoff_unix)
    out = []
    for r in index.records:
        if int(r.kickoff_unix) >= cut:
            continue
        if r.home_id == team_id or r.away_id == team_id:
            out.append(r)
    return out


def kish_effective_n(weights) -> float:
    """Kish effective sample size: (sum w)^2 / sum(w^2). 0 for empty/degenerate."""
    w = [float(x) for x in weights if x is not None and x > 0]
    if not w:
        return 0.0
    s1 = sum(w)
    s2 = sum(x * x for x in w)
    return (s1 * s1) / s2 if s2 > 0 else 0.0


def weight_concentration(weights) -> float:
    """Max single-observation share of total weight (0..1)."""
    w = [float(x) for x in weights if x is not None and x > 0]
    if not w:
        return 1.0
    return max(w) / sum(w)


def time_decay_weight(obs_unix, ref_unix, halflife_days) -> float:
    """Exponential time-decay weight for a PIT observation. obs must precede ref."""
    if obs_unix >= ref_unix:
        return 0.0     # future or same-time observation contributes nothing (PIT guard)
    age_days = (ref_unix - obs_unix) / 86400.0
    return 0.5 ** (age_days / float(halflife_days))


def shrink_estimate(cohort_mean, cohort_n, prior_mean, k=SHRINKAGE_STRENGTH_K) -> float:
    """James-Stein-style partial pooling toward a baseline prior. Deterministic."""
    if cohort_n <= 0:
        return prior_mean
    return (cohort_n * cohort_mean + k * prior_mean) / (cohort_n + k)


def classify_support(*, raw_n, unique_fixtures, unique_teams, effective_n,
                     concentration, n_competitions) -> dict:
    """Classify cohort support against the FROZEN thresholds. Effect-independent."""
    reasons = []
    status = SUPPORT_ADEQUATE
    if raw_n < MIN_RAW_N or unique_fixtures < MIN_UNIQUE_FIXTURES or \
            unique_teams < MIN_UNIQUE_TEAMS:
        status = SUPPORT_LOW
        reasons.append(f"raw_n={raw_n}(<{MIN_RAW_N}) or unique_fixtures={unique_fixtures}"
                       f"(<{MIN_UNIQUE_FIXTURES}) or unique_teams={unique_teams}"
                       f"(<{MIN_UNIQUE_TEAMS})")
    if effective_n < MIN_EFFECTIVE_N:
        status = SUPPORT_LOW if status == SUPPORT_ADEQUATE else status
        reasons.append(f"effective_n={effective_n:.2f}(<{MIN_EFFECTIVE_N})")
    if concentration > MAX_WEIGHT_CONCENTRATION:
        status = SUPPORT_CONCENTRATED
        reasons.append(f"weight_concentration={concentration:.3f}"
                       f"(>{MAX_WEIGHT_CONCENTRATION})")
    if raw_n == 0:
        status = SUPPORT_NOT_EVALUABLE
        reasons.append("no observations")
    return {"status": status, "raw_n": raw_n, "unique_fixtures": unique_fixtures,
            "unique_teams": unique_teams, "effective_n": round(effective_n, 4),
            "weight_concentration": round(concentration, 4),
            "n_competitions": n_competitions, "reasons": reasons or ["adequate"]}


def version_stamp() -> dict:
    return {"pit_version": PIT_VERSION,
            "pit_rule": "team profiles/similarity/cohorts use ONLY fixtures strictly before "
                        "the target kickoff_unix; target is the fixture's own observed stat",
            "min_raw_n": MIN_RAW_N, "min_unique_fixtures": MIN_UNIQUE_FIXTURES,
            "min_unique_teams": MIN_UNIQUE_TEAMS, "min_effective_n": MIN_EFFECTIVE_N,
            "max_weight_concentration": MAX_WEIGHT_CONCENTRATION,
            "time_decay_halflives_days": list(TIME_DECAY_HALFLIVES_DAYS),
            "shrinkage_prior": SHRINKAGE_PRIOR, "shrinkage_k": SHRINKAGE_STRENGTH_K,
            "thresholds_frozen_before_effects": True,
            "clustering": "team/fixture clustering + block bootstrap required for uncertainty"}
