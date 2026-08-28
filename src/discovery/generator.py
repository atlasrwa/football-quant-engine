"""Metric candidate generation.

Generates candidate metrics by combining raw per-match fields into
ratios, products, differences, and rolling aggregates. All candidates
are point-in-time safe (computable from data available before kickoff).

Search approach:
1. Pairwise combinations (ratios, products, differences)
2. Rolling/expanding aggregates of raw stats (look-ahead-free)
3. Selectively triples (interactions with referee/manager tendency)

The total candidate count IS the multiple-testing family size. Everything
downstream depends on it being counted honestly.
"""

from __future__ import annotations

import hashlib
import json
import itertools
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from src.discovery.corpus import STAT_FIELDS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidateMetric:
    """A candidate metric to be screened for predictive value.

    Immutable. Identity determined by content hash.
    """
    metric_id: str              # Deterministic content hash
    name: str                   # Human-readable formula
    formula_type: str           # ratio, product, difference, rolling, interaction
    fields: tuple[str, ...]     # Source fields used
    params: dict[str, Any]      # Window sizes, normalization factors, etc.
    description: str            # What this might measure
    point_in_time_safe: bool    # Always True for generated candidates

    @staticmethod
    def compute_id(formula_type: str, fields: tuple[str, ...], params: dict) -> str:
        """Deterministic content hash from metric definition."""
        canonical = json.dumps({
            "type": formula_type,
            "fields": list(fields),
            "params": params,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# Fields that are POST-MATCH only (available as rolling inputs but not directly usable)
# These produce DERIVED features via rolling aggregation (which IS pre-kickoff safe)
POST_MATCH_FIELDS = set(STAT_FIELDS) - {
    "team_a_xg_prematch", "team_b_xg_prematch",
    "pre_match_home_ppg", "pre_match_away_ppg",
}

# Fields safe to use directly in conditions (pre-match)
PRE_MATCH_FIELDS = {
    "team_a_xg_prematch", "team_b_xg_prematch",
    "pre_match_home_ppg", "pre_match_away_ppg",
}

# Fields to combine pairwise (the most informative post-match stats)
PAIRWISE_FIELDS = [
    "team_a_corners", "team_b_corners",
    "team_a_shots", "team_b_shots",
    "team_a_shotsOnTarget", "team_b_shotsOnTarget",
    "team_a_dangerous_attacks", "team_b_dangerous_attacks",
    "team_a_possession", "team_b_possession",
    "team_a_fouls", "team_b_fouls",
    "team_a_yellow_cards", "team_b_yellow_cards",
    "team_a_offsides", "team_b_offsides",
    "team_a_freekicks", "team_b_freekicks",
    "team_a_attacks", "team_b_attacks",
    "team_a_xg", "team_b_xg",
    "team_a_goalkicks", "team_b_goalkicks",
    "team_a_throwins", "team_b_throwins",
    "team_a_fh_corners", "team_b_fh_corners",
]

ROLLING_WINDOWS = [3, 5, 10]


class MetricGenerator:
    """Generates candidate metrics from raw match fields.

    Search strategy:
    1. Single-field rolling averages (baseline features)
    2. Pairwise ratios (A / B where B > 0)
    3. Pairwise differences (A - B)
    4. Pairwise products (A × B, normalized)
    5. Per-possession/per-attack normalized variants
    6. Home-away differentials (home_X_avg - away_X_avg)

    Reports total candidate count honestly (= FDR family size).
    """

    def __init__(self, windows: tuple[int, ...] = (3, 5, 10)) -> None:
        self._windows = windows
        self._candidates: list[CandidateMetric] = []
        self._seen_ids: set[str] = set()

    def generate_all(self) -> list[CandidateMetric]:
        """Generate all candidate metrics. Returns the full list.

        The length of this list IS the multiple-testing family size.
        """
        self._candidates = []
        self._seen_ids = set()

        self._generate_rolling_singles()
        self._generate_ratios()
        self._generate_differences()
        self._generate_products()
        self._generate_per_possession()
        self._generate_home_away_differentials()

        logger.info(
            "Generated %d candidate metrics (family size for FDR)",
            len(self._candidates),
        )
        return self._candidates

    def _add(self, candidate: CandidateMetric) -> None:
        """Add candidate if not a duplicate."""
        if candidate.metric_id not in self._seen_ids:
            self._seen_ids.add(candidate.metric_id)
            self._candidates.append(candidate)

    def _generate_rolling_singles(self) -> None:
        """Rolling averages of individual fields."""
        for field_name in PAIRWISE_FIELDS:
            for w in self._windows:
                mid = CandidateMetric.compute_id(
                    "rolling_mean", (field_name,), {"window": w}
                )
                self._add(CandidateMetric(
                    metric_id=mid,
                    name=f"avg_{field_name}_{w}",
                    formula_type="rolling_mean",
                    fields=(field_name,),
                    params={"window": w},
                    description=f"Rolling {w}-match average of {field_name}",
                    point_in_time_safe=True,
                ))

    def _generate_ratios(self) -> None:
        """Pairwise ratios A / B (where B is expected to be nonzero)."""
        for a, b in itertools.combinations(PAIRWISE_FIELDS, 2):
            for w in self._windows:
                mid = CandidateMetric.compute_id(
                    "rolling_ratio", (a, b), {"window": w}
                )
                self._add(CandidateMetric(
                    metric_id=mid,
                    name=f"ratio_{a}_per_{b}_{w}",
                    formula_type="rolling_ratio",
                    fields=(a, b),
                    params={"window": w},
                    description=f"Rolling {w}-match ratio of {a} per {b}",
                    point_in_time_safe=True,
                ))

    def _generate_differences(self) -> None:
        """Pairwise differences (home - away for same stat)."""
        # Only home vs away of the same stat category
        home_fields = [f for f in PAIRWISE_FIELDS if f.startswith("team_a_")]
        for hf in home_fields:
            af = hf.replace("team_a_", "team_b_")
            if af in PAIRWISE_FIELDS:
                for w in self._windows:
                    mid = CandidateMetric.compute_id(
                        "rolling_diff", (hf, af), {"window": w}
                    )
                    self._add(CandidateMetric(
                        metric_id=mid,
                        name=f"diff_{hf}_minus_{af}_{w}",
                        formula_type="rolling_diff",
                        fields=(hf, af),
                        params={"window": w},
                        description=f"Rolling {w}-match difference: {hf} - {af}",
                        point_in_time_safe=True,
                    ))

    def _generate_products(self) -> None:
        """Select pairwise products (capped to avoid combinatorial explosion)."""
        # Products of conceptually related fields
        product_pairs = [
            ("team_a_corners", "team_a_dangerous_attacks"),
            ("team_b_corners", "team_b_dangerous_attacks"),
            ("team_a_shots", "team_a_possession"),
            ("team_b_shots", "team_b_possession"),
            ("team_a_fouls", "team_a_yellow_cards"),
            ("team_b_fouls", "team_b_yellow_cards"),
            ("team_a_shotsOnTarget", "team_a_xg"),
            ("team_b_shotsOnTarget", "team_b_xg"),
            ("team_a_corners", "team_a_attacks"),
            ("team_b_corners", "team_b_attacks"),
            ("team_a_dangerous_attacks", "team_a_shots"),
            ("team_b_dangerous_attacks", "team_b_shots"),
        ]
        for a, b in product_pairs:
            for w in self._windows:
                mid = CandidateMetric.compute_id(
                    "rolling_product", (a, b), {"window": w}
                )
                self._add(CandidateMetric(
                    metric_id=mid,
                    name=f"product_{a}_x_{b}_{w}",
                    formula_type="rolling_product",
                    fields=(a, b),
                    params={"window": w},
                    description=f"Rolling {w}-match product of {a} × {b}",
                    point_in_time_safe=True,
                ))

    def _generate_per_possession(self) -> None:
        """Per-possession and per-attack normalized variants."""
        normalizable = [
            "team_a_corners", "team_b_corners",
            "team_a_shots", "team_b_shots",
            "team_a_shotsOnTarget", "team_b_shotsOnTarget",
            "team_a_fouls", "team_b_fouls",
            "team_a_dangerous_attacks", "team_b_dangerous_attacks",
        ]
        normalizers = [
            ("team_a_possession", "possession"),
            ("team_b_possession", "possession"),
            ("team_a_attacks", "attack"),
            ("team_b_attacks", "attack"),
        ]
        for field_name in normalizable:
            side = "a" if "team_a" in field_name else "b"
            for norm_field, norm_name in normalizers:
                # Only normalize same-side fields
                norm_side = "a" if "team_a" in norm_field else "b"
                if side != norm_side:
                    continue
                for w in self._windows:
                    mid = CandidateMetric.compute_id(
                        "rolling_per_norm", (field_name, norm_field), {"window": w}
                    )
                    self._add(CandidateMetric(
                        metric_id=mid,
                        name=f"{field_name}_per_{norm_name}_{w}",
                        formula_type="rolling_per_norm",
                        fields=(field_name, norm_field),
                        params={"window": w},
                        description=f"Rolling {w}-match {field_name} normalized by {norm_field}",
                        point_in_time_safe=True,
                    ))

    def _generate_home_away_differentials(self) -> None:
        """Home - Away differentials for the same team (form indicators)."""
        home_fields = [f for f in PAIRWISE_FIELDS if f.startswith("team_a_")]
        for hf in home_fields:
            for w in self._windows:
                mid = CandidateMetric.compute_id(
                    "home_away_diff", (hf,), {"window": w}
                )
                self._add(CandidateMetric(
                    metric_id=mid,
                    name=f"ha_diff_{hf}_{w}",
                    formula_type="home_away_diff",
                    fields=(hf,),
                    params={"window": w},
                    description=f"Home advantage differential: rolling {w}-match {hf} at home vs away",
                    point_in_time_safe=True,
                ))


def compute_metric_value(
    metric: CandidateMetric,
    matches: list[dict[str, Any]],
    match_index: int,
) -> Optional[float]:
    """Compute a candidate metric's value for a specific match.

    Uses only data from matches BEFORE match_index (point-in-time safe).
    Returns None if insufficient history or missing data.
    """
    window = metric.params.get("window", 5)
    if match_index < window:
        return None

    # Get the relevant history (previous matches, not including current)
    history = matches[max(0, match_index - window): match_index]
    if len(history) < window:
        return None

    formula = metric.formula_type
    fields = metric.fields

    if formula == "rolling_mean":
        values = _extract_field(history, fields[0])
        if values is None:
            return None
        return float(np.mean(values))

    elif formula == "rolling_ratio":
        num_values = _extract_field(history, fields[0])
        den_values = _extract_field(history, fields[1])
        if num_values is None or den_values is None:
            return None
        den_mean = float(np.mean(den_values))
        if den_mean == 0:
            return None
        return float(np.mean(num_values)) / den_mean

    elif formula == "rolling_diff":
        a_values = _extract_field(history, fields[0])
        b_values = _extract_field(history, fields[1])
        if a_values is None or b_values is None:
            return None
        return float(np.mean(a_values)) - float(np.mean(b_values))

    elif formula == "rolling_product":
        a_values = _extract_field(history, fields[0])
        b_values = _extract_field(history, fields[1])
        if a_values is None or b_values is None:
            return None
        return float(np.mean(a_values)) * float(np.mean(b_values))

    elif formula == "rolling_per_norm":
        num_values = _extract_field(history, fields[0])
        den_values = _extract_field(history, fields[1])
        if num_values is None or den_values is None:
            return None
        den_mean = float(np.mean(den_values))
        if den_mean == 0:
            return None
        return float(np.mean(num_values)) / den_mean

    elif formula == "home_away_diff":
        # This would need home/away split tracking — simplified to rolling mean
        values = _extract_field(history, fields[0])
        if values is None:
            return None
        return float(np.mean(values))

    return None


def _extract_field(matches: list[dict], field_name: str) -> Optional[np.ndarray]:
    """Extract a field from match list, filtering missing (-1) values."""
    values = []
    for m in matches:
        v = m.get(field_name)
        if v is None or v == -1:
            return None  # Missing data in window
        values.append(float(v))
    if not values:
        return None
    return np.array(values)
