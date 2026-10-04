"""Layer 5 market-surface diagnostics.

These diagnostics are outcome-blind. They compare the frozen standalone QFE
probability ladder with the cleaned, same-bookmaker market ladder. They do not
change p_model, select a bookmaker, choose a line, or determine eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable, Optional

from src.research.layer5.disagreement import ModelMarketPoint
from src.research.layer5.market_surface import MarketSurface


@dataclass(frozen=True, slots=True)
class SurfaceDiagnostics:
    paired_lines: tuple[float, ...]
    mean_signed_over_probability_gap: float
    mean_absolute_probability_gap: float
    dominant_direction: str
    same_sign_fraction: float
    market_median_crossing_line: Optional[float]
    qfe_median_crossing_line: Optional[float]
    median_crossing_displacement: Optional[float]
    maximum_local_gap_diagnostic_only: float
    maximum_local_gap_line: float
    maximum_local_signed_gap: float


def _validate_probability(value: float) -> float:
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    return value


def _median_crossing_line(
    lines: list[float],
    probabilities: list[float],
) -> Optional[float]:
    """Return the line where a non-increasing OVER CDF crosses 0.50.

    Linear interpolation is used only between adjacent registered lines. If
    0.50 lies outside the observed ladder support, return None rather than
    extrapolating an invented median.
    """
    if len(lines) != len(probabilities) or not lines:
        raise ValueError("lines/probabilities must be non-empty and aligned")
    if any(lines[i + 1] <= lines[i] for i in range(len(lines) - 1)):
        raise ValueError("lines must be strictly increasing")
    probs = [_validate_probability(p) for p in probabilities]
    if any(probs[i + 1] > probs[i] + 1e-12 for i in range(len(probs) - 1)):
        raise ValueError("probability ladder must be non-increasing")

    for line, probability in zip(lines, probs, strict=True):
        if abs(probability - 0.5) <= 1e-12:
            return float(line)

    for i in range(len(lines) - 1):
        p0, p1 = probs[i], probs[i + 1]
        if p0 > 0.5 > p1:
            fraction = (0.5 - p0) / (p1 - p0)
            return float(lines[i] + fraction * (lines[i + 1] - lines[i]))
    return None


def compute_surface_diagnostics(
    market: MarketSurface,
    models: Iterable[ModelMarketPoint],
) -> SurfaceDiagnostics:
    """Compute preregistered QFE-CDF versus market-CDF diagnostics.

    Only exactly paired registered lines are used. Missing QFE lines are not
    imputed and no tail extrapolation is performed.
    """
    if not market.is_ok:
        raise ValueError(f"market surface is not usable: {market.reason}")

    model_by_line: dict[float, ModelMarketPoint] = {}
    for model in models:
        line = float(model.line)
        if line in model_by_line:
            raise ValueError(f"duplicate QFE model line: {line}")
        _validate_probability(model.p_model_over)
        model_by_line[line] = model

    paired = [
        (point, model_by_line[float(point.line)])
        for point in market.points
        if float(point.line) in model_by_line
    ]
    paired.sort(key=lambda row: row[0].line)
    if not paired:
        raise ValueError("no paired QFE/market lines")

    lines = [float(point.line) for point, _ in paired]
    market_probs = [_validate_probability(point.p_over_clean) for point, _ in paired]
    qfe_probs = [_validate_probability(model.p_model_over) for _, model in paired]

    if any(market_probs[i + 1] > market_probs[i] + 1e-12 for i in range(len(market_probs) - 1)):
        raise ValueError("cleaned market ladder must be non-increasing")
    if any(qfe_probs[i + 1] > qfe_probs[i] + 1e-12 for i in range(len(qfe_probs) - 1)):
        raise ValueError("QFE probability ladder must be non-increasing")

    gaps = [qfe - market_p for qfe, market_p in zip(qfe_probs, market_probs, strict=True)]
    signed_mean = mean(gaps)
    nonzero = [gap for gap in gaps if abs(gap) > 1e-15]
    if not nonzero:
        dominant = "NONE"
        same_sign_fraction = 1.0
    else:
        positive = sum(gap > 0 for gap in nonzero)
        negative = len(nonzero) - positive
        dominant = "OVER" if positive >= negative else "UNDER"
        same_sign_fraction = max(positive, negative) / len(nonzero)

    market_crossing = _median_crossing_line(lines, market_probs)
    qfe_crossing = _median_crossing_line(lines, qfe_probs)
    displacement = (
        qfe_crossing - market_crossing
        if qfe_crossing is not None and market_crossing is not None
        else None
    )

    max_index = min(
        range(len(gaps)),
        key=lambda i: (-abs(gaps[i]), lines[i]),
    )

    return SurfaceDiagnostics(
        paired_lines=tuple(lines),
        mean_signed_over_probability_gap=float(signed_mean),
        mean_absolute_probability_gap=float(mean(abs(gap) for gap in gaps)),
        dominant_direction=dominant,
        same_sign_fraction=float(same_sign_fraction),
        market_median_crossing_line=market_crossing,
        qfe_median_crossing_line=qfe_crossing,
        median_crossing_displacement=displacement,
        maximum_local_gap_diagnostic_only=float(abs(gaps[max_index])),
        maximum_local_gap_line=float(lines[max_index]),
        maximum_local_signed_gap=float(gaps[max_index]),
    )
