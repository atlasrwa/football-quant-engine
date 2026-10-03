"""Preregistered QFE V2 Layer 3.1 market-event coverage protocol.

This protocol is frozen before any Layer 3.1 multi-line scoring is computed.
It evaluates probability quality implied by the already-frozen corner side
count distributions. It contains no bookmaker odds and may read DEVELOPMENT
OOF outcomes only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.research.dataset.manifest import sha256_json
from src.research.evaluation.chronology import EvaluationPartition

LAYER31_PROTOCOL_VERSION = "qfe-layer3.1-market-event-coverage-v1"
FROZEN_ON = "2026-10-02"
SIDE_LINES = (2.5, 3.5, 4.5, 5.5, 6.5, 7.5)
TOTAL_LINES = (7.5, 8.5, 9.5, 10.5, 11.5, 12.5)
ROLES = ("home", "away")
CANDIDATES = ("dynamic_poisson", "dynamic_side_nb2")
PRIMARY_METRICS = ("binary_log_loss", "brier")
BLOCKING_UNIT = "UTC_CALENDAR_WEEK"
BOOTSTRAP_REPLICATES = 4000
BOOTSTRAP_SEED = 20261002


@dataclass(frozen=True, slots=True)
class Layer31Protocol:
    version: str = LAYER31_PROTOCOL_VERSION
    frozen_on: str = FROZEN_ON
    source_partition: str = EvaluationPartition.DEVELOPMENT.value
    calibration_outcomes_allowed: bool = False
    protected_outcomes_allowed: bool = False
    market_odds_allowed: bool = False
    side_roles: tuple[str, ...] = ROLES
    side_lines: tuple[float, ...] = SIDE_LINES
    total_lines: tuple[float, ...] = TOTAL_LINES
    candidates: tuple[str, ...] = CANDIDATES
    primary_metrics: tuple[str, ...] = PRIMARY_METRICS
    block_unit: str = BLOCKING_UNIT
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES
    bootstrap_seed: int = BOOTSTRAP_SEED

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "frozen_on": self.frozen_on,
            "source_partition": self.source_partition,
            "calibration_outcomes_allowed": self.calibration_outcomes_allowed,
            "protected_outcomes_allowed": self.protected_outcomes_allowed,
            "market_odds_allowed": self.market_odds_allowed,
            "side_roles": list(self.side_roles),
            "side_lines": list(self.side_lines),
            "total_lines": list(self.total_lines),
            "candidates": list(self.candidates),
            "primary_metrics": list(self.primary_metrics),
            "block_unit": self.block_unit,
            "bootstrap_replicates": self.bootstrap_replicates,
            "bootstrap_seed": self.bootstrap_seed,
            "hypotheses": {
                "SIDE_CORNERS": {
                    "population": "all eligible DEVELOPMENT OOF fixture-role-line cells for HOME and AWAY",
                    "aggregation": "pool all preregistered roles and lines; each eligible fixture-role-line cell contributes once",
                    "primary_comparison": "dynamic_side_nb2 minus dynamic_poisson using paired loss differences",
                    "promotion_gate": "mean improvement > 0 and 95% weekly-block CI lower bound > 0 for BOTH binary Log Loss and Brier",
                    "role_guard": "HOME and AWAY pooled role Log Loss must not have a 95% CI upper bound < 0 (material degradation)",
                    "line_results": "diagnostic only; no single line may determine promotion",
                },
                "TOTAL_CORNERS": {
                    "population": "all eligible DEVELOPMENT OOF fixture-line cells for match totals",
                    "aggregation": "pool all preregistered total lines; each eligible fixture-line cell contributes once",
                    "primary_comparison": "convolution of side-NB2 distributions minus Poisson total distribution",
                    "promotion_gate": "mean improvement > 0 and 95% weekly-block CI lower bound > 0 for BOTH binary Log Loss and Brier",
                    "line_results": "diagnostic only; no single line may determine promotion",
                },
            },
            "multiplicity_policy": (
                "No best-line search. Two preregistered primary hypotheses only: SIDE_CORNERS and TOTAL_CORNERS. "
                "Role/line/competition slices are diagnostics and cannot promote a candidate by themselves."
            ),
            "missingness_policy": "Missing corner outcomes are excluded, never imputed. Both candidate probabilities must exist for a paired cell.",
            "coherence_policy": "Candidate probabilities must be monotone across increasing over lines within each fixture/role or fixture/total ladder; violation blocks evidence.",
            "scientific_boundary": "Layer 3.1 may decide component eligibility for Layer 4. It is not calibration, market comparison, protected evaluation, or commercial evidence.",
        }

    @property
    def protocol_hash(self) -> str:
        return sha256_json(self.to_dict())


def protocol_v1() -> Layer31Protocol:
    return Layer31Protocol()
