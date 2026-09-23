"""ITEM 6 STAGE 2 feature specification (`item6_stage2_feature_spec_v1`).

Turns each FEASIBLE canonical metric instantiation into a fixed, deterministic set of feature
column definitions. The spec is a pure function of the canonical registry: no outcome, no
market, no LLM text, no per-fixture decision. Running it twice on the same registry yields
byte-identical column definitions in the same order.

COLUMN FAMILIES (one generator rule per structural family)
----------------------------------------------------------
SF_THRESHOLD_NONLINEARITY
    Tercile-band indicators on each canonical axis's season-to-date rolling mean, for the home
    and away team. Bands come from the threshold policy (training-fold quantiles); the `low`
    band is the reference level and is omitted to keep the design matrix full rank.
SF_MULTIMETRIC_INTERACTION
    Standardised continuous product of the first two canonical axes' rolling means, per team.
    No hard threshold at all (authorized option E).
SF_HALF_OR_GAME_STATE_INTERACTION
    Second-half SHARE of the metric (2h / (fh + 2h)) as a rolling mean, standardised, per team
    -- defined only for half-capable metrics. This is the point-in-time-safe half-state
    construction: it is computed from COMPLETED prior matches only.
SF_TWO_AXIS_OPPONENT_PROFILE_INTERSECTION
    Band-intersection indicators for the opponent's two-axis profile, resolved through the
    similarity policy (with its support-driven shrinkage and abstain-on-missing rule).

Every column carries the canonical_key that motivated it, so each Stage-2 feature is traceable
to the Stage-1 mechanisms it came from.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

FEATURE_SPEC_VERSION = "item6_stage2_feature_spec_v1"

WINDOW_STD = "STD"          # season-to-date (champion's MIN_CURRENT_SEASON_MATCHES rule)
WINDOW_W5 = "W5"
PERIOD_FULL = "FULL_MATCH"

TEAM_SLOTS = ("h", "a")     # home, away -- mirrors the champion's naming

KIND_BAND_DUMMY = "BAND_DUMMY"
KIND_STD_PRODUCT = "STANDARDIZED_PRODUCT"
KIND_HALF_SHARE = "HALF_SECOND_HALF_SHARE"
KIND_PROFILE_DUMMY = "PROFILE_BAND_DUMMY"

#: Caps keep the M1 universe bounded and declared BEFORE any outcome is seen.
MAX_AXES_PER_INSTANTIATION = 3
NON_REFERENCE_BANDS = ("mid", "high")     # 'low' is the omitted reference level


def stat_key(metric: str, perspective: str, period: str, window: str) -> str:
    return f"{metric}.{perspective}.{period}.{window}"


def _axes(inst: Dict) -> List[Dict[str, str]]:
    return list(inst["canonical_metrics"])[:MAX_AXES_PER_INSTANTIATION]


def columns_for_instantiation(inst: Dict) -> List[Dict[str, object]]:
    """Deterministic column definitions for one canonical metric instantiation."""
    sf = inst["structural_family"]
    key = inst["canonical_key"]
    cols: List[Dict[str, object]] = []

    if sf == "SF_THRESHOLD_NONLINEARITY":
        for ax in _axes(inst):
            sk = stat_key(ax["metric"], ax["perspective"], PERIOD_FULL, WINDOW_STD)
            for slot in TEAM_SLOTS:
                for band in NON_REFERENCE_BANDS:
                    cols.append({
                        "name": f"i6_{slot}_{ax['metric']}_{ax['perspective'].lower()}_band_{band}",
                        "kind": KIND_BAND_DUMMY, "team_slot": slot, "stat_key": sk,
                        "band": band, "canonical_key": key, "structural_family": sf,
                    })

    elif sf == "SF_MULTIMETRIC_INTERACTION":
        ax = _axes(inst)
        if len(ax) >= 2:
            a, b = ax[0], ax[1]
            ska = stat_key(a["metric"], a["perspective"], PERIOD_FULL, WINDOW_STD)
            skb = stat_key(b["metric"], b["perspective"], PERIOD_FULL, WINDOW_STD)
            for slot in TEAM_SLOTS:
                cols.append({
                    "name": f"i6_{slot}_{a['metric']}_{a['perspective'].lower()}"
                            f"_X_{b['metric']}_{b['perspective'].lower()}",
                    "kind": KIND_STD_PRODUCT, "team_slot": slot,
                    "stat_key_a": ska, "stat_key_b": skb,
                    "canonical_key": key, "structural_family": sf,
                })

    elif sf == "SF_HALF_OR_GAME_STATE_INTERACTION":
        from src.research.item6.stage2 import provider_measurability as PM
        for ax in _axes(inst):
            if not PM.is_half_capable(ax["metric"]):
                continue
            for slot in TEAM_SLOTS:
                cols.append({
                    "name": f"i6_{slot}_{ax['metric']}_{ax['perspective'].lower()}_2h_share",
                    "kind": KIND_HALF_SHARE, "team_slot": slot,
                    "metric": ax["metric"], "perspective": ax["perspective"],
                    "canonical_key": key, "structural_family": sf,
                })

    elif sf == "SF_TWO_AXIS_OPPONENT_PROFILE_INTERSECTION":
        ax = _axes(inst)
        if len(ax) >= 2:
            a, b = ax[0], ax[1]
            axis_keys = [
                stat_key(a["metric"], a["perspective"], PERIOD_FULL, WINDOW_STD),
                stat_key(b["metric"], b["perspective"], PERIOD_FULL, WINDOW_STD),
            ]
            for slot in TEAM_SLOTS:
                for band in NON_REFERENCE_BANDS:
                    cols.append({
                        "name": f"i6_{slot}_oppprof_{a['metric']}_{b['metric']}_{band}",
                        "kind": KIND_PROFILE_DUMMY, "team_slot": slot,
                        "axis_stat_keys": axis_keys, "band": band,
                        "canonical_key": key, "structural_family": sf,
                    })
    return cols


def build_feature_spec(canonical_registry: Dict) -> Dict[str, object]:
    """Full Stage-2 LLM-derived feature universe. Column order is deterministic."""
    cols: List[Dict[str, object]] = []
    seen = set()
    for inst in canonical_registry["metric_instantiations"]:
        for c in columns_for_instantiation(inst):
            if c["name"] in seen:          # identical column from two instantiations
                continue
            seen.add(c["name"])
            cols.append(c)
    cols.sort(key=lambda c: str(c["name"]))

    required_stats = sorted({
        s for c in cols for s in (
            [c.get("stat_key")] if c.get("stat_key") else
            [c.get("stat_key_a"), c.get("stat_key_b")] if c.get("stat_key_a") else
            list(c.get("axis_stat_keys") or [])
        ) if s
    })
    by_family: Dict[str, int] = {}
    for c in cols:
        by_family[str(c["structural_family"])] = by_family.get(str(c["structural_family"]), 0) + 1

    return {
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "n_columns": len(cols),
        "n_columns_by_structural_family": dict(sorted(by_family.items())),
        "required_rolling_statistics": required_stats,
        "n_required_rolling_statistics": len(required_stats),
        "columns": cols,
        "max_axes_per_instantiation": MAX_AXES_PER_INSTANTIATION,
        "reference_band_omitted": "low",
        "reads_outcomes": False,
        "llm_numeric_thresholds_used": False,
    }


def version_stamp() -> Dict[str, object]:
    return {
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "kinds": [KIND_BAND_DUMMY, KIND_STD_PRODUCT, KIND_HALF_SHARE, KIND_PROFILE_DUMMY],
        "deterministic_column_order": True,
        "reads_outcomes": False,
    }
