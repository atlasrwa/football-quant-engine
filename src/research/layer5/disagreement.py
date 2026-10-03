"""QFE V2 Layer 5 deterministic disagreement / abstention policy.

No outcomes are accepted by this module. It compares frozen p_model values and
Layer 4 support metadata with a preregistered market comparator.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Iterable, Optional

from src.research.layer5.market_surface import MarketPoint, MarketSurface
from src.research.layer5.protocol import protocol_active


@dataclass(frozen=True, slots=True)
class ModelMarketPoint:
    line: float
    p_model_over: float
    dynamic_supported: bool
    calibration_bin_unique_fixtures: int
    reliability_ci_low: Optional[float]
    reliability_ci_high: Optional[float]
    ood_flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DisagreementDecision:
    eligible: bool
    reason: Optional[str]
    evidence_class: Optional[str]
    side: Optional[str]
    line: Optional[float]
    p_model_side: Optional[float]
    p_market_side: Optional[float]
    absolute_gap: Optional[float]
    reliability_penalty: Optional[float]
    reliability_adjusted_gap: Optional[float]
    corroborating_lines: tuple[float, ...]
    mean_signed_over_gap: Optional[float]
    mean_absolute_gap: Optional[float]
    same_sign_fraction: Optional[float]


def _reject(reason: str) -> DisagreementDecision:
    return DisagreementDecision(
        eligible=False,
        reason=reason,
        evidence_class=None,
        side=None,
        line=None,
        p_model_side=None,
        p_market_side=None,
        absolute_gap=None,
        reliability_penalty=None,
        reliability_adjusted_gap=None,
        corroborating_lines=(),
        mean_signed_over_gap=None,
        mean_absolute_gap=None,
        same_sign_fraction=None,
    )


def _support_reason(model: ModelMarketPoint) -> Optional[str]:
    p = protocol_active()["model_support_gate"]
    if p["dynamic_support_required"] and not model.dynamic_supported:
        return "MODEL_DYNAMIC_SUPPORT_INSUFFICIENT"
    if model.calibration_bin_unique_fixtures < p["calibration_bin_min_unique_fixtures"]:
        return "MODEL_CALIBRATION_REGION_UNSUPPORTED"
    if model.reliability_ci_low is None or model.reliability_ci_high is None:
        return "MODEL_CALIBRATION_REGION_UNSUPPORTED"
    if model.ood_flags:
        if any("component" in flag.lower() or "gap" in flag.lower() for flag in model.ood_flags):
            return "MODEL_COMPONENT_DISPERSION_OOD"
        return "MODEL_OOD"
    return None


def _reliability_penalty(model: ModelMarketPoint) -> float:
    assert model.reliability_ci_low is not None
    assert model.reliability_ci_high is not None
    return max(abs(model.reliability_ci_low), abs(model.reliability_ci_high))


def _devig_stable(model_p_over: float, market: MarketPoint) -> bool:
    p = protocol_active()["no_vig"]["sensitivity"]
    primary_gap = model_p_over - market.p_over_clean
    shin_gap = model_p_over - market.p_over_shin
    # A direction change across de-vig methods is unstable unless both gaps are
    # numerically zero.
    if primary_gap * shin_gap < 0:
        return False
    return abs(abs(primary_gap) - abs(shin_gap)) <= p["selected_side_gap_abs_difference_max"] + 1e-12


def evaluate_single_line(
    market: MarketSurface,
    model: ModelMarketPoint,
) -> DisagreementDecision:
    protocol = protocol_active()
    if not market.is_ok or len(market.points) != 1:
        return _reject(market.reason or "TARGET_UNSUPPORTED")
    point = market.points[0]
    if abs(point.line - model.line) > 1e-9:
        return _reject("TARGET_UNSUPPORTED")
    reason = _support_reason(model)
    if reason:
        return _reject(reason)
    if not _devig_stable(model.p_model_over, point):
        return _reject("DEVIG_SENSITIVITY_UNSTABLE")

    signed_gap = model.p_model_over - point.p_over_clean
    gap = abs(signed_gap)
    dp = protocol["disagreement_policy"]
    if gap < dp["minimum_selected_line_absolute_gap"]:
        return _reject("DISAGREEMENT_TOO_SMALL")
    penalty = _reliability_penalty(model)
    adjusted = gap - penalty
    if adjusted < protocol["model_support_gate"]["minimum_reliability_adjusted_gap"]:
        return _reject("RELIABILITY_ADJUSTED_GAP_TOO_SMALL")
    side = "OVER" if signed_gap > 0 else "UNDER"
    p_model_side = model.p_model_over if side == "OVER" else 1.0 - model.p_model_over
    p_market_side = point.p_over_clean if side == "OVER" else 1.0 - point.p_over_clean
    return DisagreementDecision(
        eligible=True,
        reason=None,
        evidence_class=dp["single_line_evidence_class"],
        side=side,
        line=model.line,
        p_model_side=p_model_side,
        p_market_side=p_market_side,
        absolute_gap=gap,
        reliability_penalty=penalty,
        reliability_adjusted_gap=adjusted,
        corroborating_lines=(model.line,),
        mean_signed_over_gap=signed_gap,
        mean_absolute_gap=gap,
        same_sign_fraction=1.0,
    )


def _contiguous_runs(rows: list[tuple[MarketPoint, ModelMarketPoint, float]]) -> list[list[tuple[MarketPoint, ModelMarketPoint, float]]]:
    if not rows:
        return []
    rows = sorted(rows, key=lambda r: r[0].line)
    out = [[rows[0]]]
    for row in rows[1:]:
        prev = out[-1][-1]
        same_direction = (row[2] > 0) == (prev[2] > 0)
        adjacent = abs(row[0].line - prev[0].line - 1.0) <= 1e-9
        if same_direction and adjacent:
            out[-1].append(row)
        else:
            out.append([row])
    return out


def evaluate_surface(
    market: MarketSurface,
    models: Iterable[ModelMarketPoint],
) -> DisagreementDecision:
    if not market.is_ok:
        return _reject(market.reason or "TARGET_UNSUPPORTED")
    protocol = protocol_active()
    dp = protocol["disagreement_policy"]
    support = protocol["model_support_gate"]
    model_by_line = {m.line: m for m in models}
    paired: list[tuple[MarketPoint, ModelMarketPoint, float]] = []
    for point in market.points:
        model = model_by_line.get(point.line)
        if model is None:
            continue
        reason = _support_reason(model)
        if reason:
            continue
        if not _devig_stable(model.p_model_over, point):
            continue
        paired.append((point, model, model.p_model_over - point.p_over_clean))

    if len(paired) < dp["surface_min_adjacent_corroborating_lines"]:
        return _reject("MODEL_CALIBRATION_REGION_UNSUPPORTED")

    strong_positive = any(g >= dp["minimum_selected_line_absolute_gap"] for _, _, g in paired)
    strong_negative = any(g <= -dp["minimum_selected_line_absolute_gap"] for _, _, g in paired)
    if strong_positive and strong_negative and dp["surface_opposite_strong_gap_forbidden"]:
        return _reject("CROSS_LINE_DIRECTION_CONFLICT")

    supporting = [
        row for row in paired
        if abs(row[2]) >= dp["surface_supporting_line_absolute_gap"]
    ]
    eligible_runs = []
    for run in _contiguous_runs(supporting):
        if len(run) < dp["surface_min_adjacent_corroborating_lines"]:
            continue
        if max(abs(row[2]) for row in run) < dp["minimum_selected_line_absolute_gap"]:
            continue
        signed_mean = mean(row[2] for row in run)
        if abs(signed_mean) < dp["surface_min_mean_signed_gap_in_corroborating_run"]:
            continue
        eligible_runs.append(run)
    if not eligible_runs:
        return _reject("CROSS_LINE_NOT_CORROBORATED")

    def market_side_probability(row):
        point, _, gap = row
        return point.p_over_clean if gap > 0 else 1.0 - point.p_over_clean

    def run_key(run):
        centrality = min(abs(market_side_probability(row) - 0.5) for row in run)
        return (centrality, run[0][0].line)

    chosen_run = min(eligible_runs, key=run_key)
    run_median = median([row[0].line for row in chosen_run])
    strong_in_run = [
        row for row in chosen_run
        if abs(row[2]) >= dp["minimum_selected_line_absolute_gap"]
    ]
    if not strong_in_run:
        # Defensive assertion: eligible-run construction above should make this
        # unreachable, but never emit a sub-threshold selected line.
        return _reject("DISAGREEMENT_TOO_SMALL")
    selected = min(
        strong_in_run,
        key=lambda row: (
            abs(market_side_probability(row) - 0.5),
            abs(row[0].line - run_median),
            row[0].line,
        ),
    )
    point, model, signed_gap = selected
    gap = abs(signed_gap)
    penalty = _reliability_penalty(model)
    adjusted = gap - penalty
    if adjusted < support["minimum_reliability_adjusted_gap"]:
        return _reject("RELIABILITY_ADJUSTED_GAP_TOO_SMALL")

    side = "OVER" if signed_gap > 0 else "UNDER"
    p_model_side = model.p_model_over if side == "OVER" else 1.0 - model.p_model_over
    p_market_side = point.p_over_clean if side == "OVER" else 1.0 - point.p_over_clean
    all_gaps = [gap_ for _, _, gap_ in paired]
    sign = 1 if signed_gap > 0 else -1
    same_sign = sum((g > 0) == (sign > 0) for g in all_gaps) / len(all_gaps)
    return DisagreementDecision(
        eligible=True,
        reason=None,
        evidence_class=dp["surface_evidence_class"],
        side=side,
        line=point.line,
        p_model_side=p_model_side,
        p_market_side=p_market_side,
        absolute_gap=gap,
        reliability_penalty=penalty,
        reliability_adjusted_gap=adjusted,
        corroborating_lines=tuple(row[0].line for row in chosen_run),
        mean_signed_over_gap=mean(all_gaps),
        mean_absolute_gap=mean(abs(g) for g in all_gaps),
        same_sign_fraction=same_sign,
    )
