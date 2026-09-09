"""Evaluation-only bridge: provider policy -> champion feature interface (Phase 6).

Reconstructs FootyStats-schema match dicts (the EXACT per-team keys the champion
``build_prior_only_features`` reads) where the per-side FEATURE stats
(shots, possession, fouls) are sourced from a chosen PROVIDER POLICY, while
holding everything else identical across arms:
    same fixtures, same chronology, same target outcome, same model architecture,
    same hyperparameters, same walk-forward window.
Only the provider/reconciliation input policy varies.

Provider policies (reusing the merged PR #3 reconciler, never max):
    FOOTYSTATS_ONLY, THESTATSAPI_ONLY, PREFERRED_PROVIDER_WITH_FALLBACK,
    VALIDATED_BLEND.

Provider-quality isolation: by default only the OVERLAPPING feature stats are
provider-sourced. The FootyStats-only extras (dangerous_attacks, attacks) are
controlled by an explicit flag so a provider-quality comparison is not
contaminated by an additional-feature effect. Two modes:
    include_fs_only_features=False  -> pure provider-quality comparison
                                       (shots/possession/fouls only, same feature
                                       set for every arm)
    include_fs_only_features=True   -> realistic FootyStats champion feature set
                                       (adds dangerous_attacks/attacks, which only
                                       FootyStats supplies) -- used for the
                                       additional-feature ablation, NOT the
                                       head-to-head provider-quality claim.

This module NEVER modifies the champion. It only builds input dicts and calls
the existing feature builder + model.
"""

from __future__ import annotations

from typing import Optional

from src.research.experiments.provider_comparison.dataset import PairedFixture, SideStats
from src.research.observation.model import MISSING, ObservationKey, ProviderObservation
from src.research.reconciliation import Reconciler, ReconciliationPolicy
from src.research.thestatsapi import ids as _ids

FOOTYSTATS = "footystats"
THESTATSAPI = "thestatsapi"

# The per-side feature stats that BOTH providers supply (provider-quality set).
_OVERLAP_SIDE_FIELDS = ("shots", "possession", "fouls")


def _team_int_id(canonical_tm: str) -> int:
    """Stable INTEGER team id for the champion (which casts ids to int).

    The canonical team id here is the TheStatsAPI 'tm_XXXX' ref (identity is by
    provider id, not name). The champion's count-regression team-effects encoder
    requires int-castable ids, so we use the numeric suffix. This is a pure
    representation detail of the eval bridge and does not affect identity: the
    same canonical team always maps to the same integer.
    """
    try:
        return _ids.parse_team_id(canonical_tm)
    except _ids.ProviderIdError:
        # Deterministic fallback: stable hash of the ref.
        return abs(hash(canonical_tm)) % (10 ** 9)


def _obs(source: str, provider_id: str, value: Optional[float]) -> ProviderObservation:
    """Wrap a per-side value as a ProviderObservation (MISSING if absent)."""
    return ProviderObservation(
        key=ObservationKey("side", "stat"),
        source=source,
        provider_entity_id=provider_id,
        value=(MISSING if value is None else value),
        observed_at=0,  # intra-record; PIT handled at fixture level, not here
    )


def _reconcile_value(
    reconciler: Reconciler,
    fs_val: Optional[float],
    tsa_val: Optional[float],
) -> Optional[float]:
    """Apply the reconciliation policy to one per-side stat, returning the value.

    Absent (None) inputs are represented as MISSING observations (not 0), so the
    reconciler's NULL != MISSING and never-max rules apply. Returns None when the
    policy selects nothing.
    """
    inputs = {}
    if fs_val is not None:
        inputs[FOOTYSTATS] = _obs(FOOTYSTATS, "fs", fs_val)
    if tsa_val is not None:
        inputs[THESTATSAPI] = _obs(THESTATSAPI, "tsa", tsa_val)
    if not inputs:
        # Represent true absence on both sides.
        inputs = {FOOTYSTATS: _obs(FOOTYSTATS, "fs", None)}
    result = reconciler.reconcile("stat", inputs)
    v = result.value
    return None if v is MISSING else v


_POLICY_MAP = {
    "footystats_only": ReconciliationPolicy.FOOTYSTATS_ONLY,
    "thestatsapi_only": ReconciliationPolicy.THESTATSAPI_ONLY,
    "preferred_fallback": ReconciliationPolicy.PREFERRED_PROVIDER_WITH_FALLBACK,
    "validated_blend": ReconciliationPolicy.VALIDATED_BLEND,
}


def make_reconciler(policy_name: str) -> Reconciler:
    """Build a reconciler for a named policy (tolerances tuned per Phase 3).

    VALIDATED_BLEND uses a per-stat relative tolerance; the shots concept
    genuinely disagrees (Phase 3), so a strict tolerance will (correctly) refuse
    to blend there and the arm will fall back to a single provider's value only
    where the providers agree.
    """
    pol = _POLICY_MAP[policy_name]
    if pol == ReconciliationPolicy.PREFERRED_PROVIDER_WITH_FALLBACK:
        return Reconciler(pol, preferred=FOOTYSTATS)
    if pol == ReconciliationPolicy.VALIDATED_BLEND:
        # 15% relative agreement required to blend; else no value (arm skips).
        return Reconciler(pol, blend_rel_tolerance=0.15)
    return Reconciler(pol)


def _side_value(side: Optional[SideStats], stat: str, home: bool) -> Optional[float]:
    if side is None:
        return None
    attr = f"{stat}_{'home' if home else 'away'}"
    return getattr(side, attr, None)


def build_champion_match_dict(
    fx: PairedFixture,
    reconciler: Reconciler,
    *,
    include_fs_only_features: bool,
) -> Optional[dict]:
    """Build ONE FootyStats-schema match dict for the champion, per policy.

    Returns None if the required overlapping feature stats cannot be sourced
    under the policy for BOTH sides (so common-support can exclude it). Outcome
    fields use the provider-agreed realized outcome.
    """
    # Reconcile each overlapping per-side feature stat under the policy.
    md: dict = {
        "homeID": _team_int_id(fx.canonical_home_tm),
        "awayID": _team_int_id(fx.canonical_away_tm),
        "date_unix": fx.kickoff_unix,
        "status": "complete",
    }
    for stat in _OVERLAP_SIDE_FIELDS:
        for home in (True, False):
            fs_v = _side_value(fx.fs_side, stat, home)
            tsa_v = _side_value(fx.tsa_side, stat, home)
            val = _reconcile_value(reconciler, fs_v, tsa_v)
            key = f"team_{'a' if home else 'b'}_{stat}"
            md[key] = val

    # FootyStats-only extra features (additional-feature ablation only).
    if include_fs_only_features:
        md["team_a_dangerous_attacks"] = fx.fs_dangerous_attacks_home
        md["team_b_dangerous_attacks"] = fx.fs_dangerous_attacks_away
        md["team_a_attacks"] = fx.fs_attacks_home
        md["team_b_attacks"] = fx.fs_attacks_away
    # else: leave absent -> champion feature builder treats as None (neutral prior)

    # Outcome components (provider-agreed ground truth) for the target labels.
    md["totalCornerCount"] = fx.outcome_total_corners
    # cards target is recomputed by the champion from these components:
    if fx.fs_side is not None:
        md["team_a_yellow_cards"] = fx.fs_side.yellow_home
        md["team_b_yellow_cards"] = fx.fs_side.yellow_away
        md["team_a_red_cards"] = fx.fs_side.red_home
        md["team_b_red_cards"] = fx.fs_side.red_away
    md["homeGoalCount"] = fx.fs_side.goals_home if fx.fs_side else None
    md["awayGoalCount"] = fx.fs_side.goals_away if fx.fs_side else None
    return md


def build_provider_matches(
    fixtures: list[PairedFixture],
    policy_name: str,
    *,
    include_fs_only_features: bool = False,
) -> list[dict]:
    """Build the full chronological list of champion match dicts for a policy."""
    reconciler = make_reconciler(policy_name)
    out = []
    for fx in sorted(fixtures, key=lambda f: f.kickoff_unix):
        md = build_champion_match_dict(
            fx, reconciler, include_fs_only_features=include_fs_only_features
        )
        if md is not None:
            out.append(md)
    return out
