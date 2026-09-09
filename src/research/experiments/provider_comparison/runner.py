"""Experiment orchestrator (Phases 12-15).

Runs the full provider comparison and emits a machine-readable report:
- per-arm metrics for each market (CORNERS_TOTAL, CARDS_TOTAL)
- paired block-bootstrap of each provider arm vs the FootyStats baseline
- model vs de-vigged market benchmark (pre-match) on common fixtures
- provider value decomposition (replacement / coverage / new-feature)
- per-market verdicts: PROMOTE_CANDIDATE / KEEP_BASELINE / INSUFFICIENT_EVIDENCE / REJECT

Deterministic: fixed seeds throughout. Champion code is never modified.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.research.experiments.provider_comparison.bootstrap import paired_block_bootstrap
from src.research.experiments.provider_comparison.coverage import build_coverage_report
from src.research.experiments.provider_comparison.dataset import (
    DatasetBuildReport,
    PairedFixture,
    build_epl_paired_dataset,
)
from src.research.experiments.provider_comparison.fields import OVERLAPPING_CONCEPTS
from src.research.experiments.provider_comparison.identity_setup import (
    load_high_confidence_team_registry,
)
from src.research.experiments.provider_comparison.market import build_market_benchmarks_by_fs_id
from src.research.experiments.provider_comparison.metrics import brier_losses, compute_metrics
from src.research.experiments.provider_comparison.pit import VINTAGE_SUPPORT
from src.research.experiments.provider_comparison.walkforward import (
    MARKET_SPECS,
    Prediction,
    run_walk_forward,
)

BASELINE_POLICY = "footystats_only"
PROVIDER_ARMS = ["footystats_only", "thestatsapi_only", "preferred_fallback", "validated_blend"]
MARKETS = ["CORNERS_TOTAL", "CARDS_TOTAL"]

# Verdict thresholds (deliberately conservative).
_MEANINGFUL_BSS = 0.0          # must at least beat climatology to be interesting
_DIRECTION_CONF = 0.95         # P(direction) needed to call an improvement credible
_CALIB_SLOPE_FLOOR = 0.5       # material calibration degradation guard


@dataclass
class Verdict:
    market: str
    comparison: str            # e.g. "thestatsapi_only vs footystats_only"
    classification: str        # PROMOTE_CANDIDATE / KEEP_BASELINE / INSUFFICIENT_EVIDENCE / REJECT
    rationale: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "market": self.market, "comparison": self.comparison,
            "classification": self.classification, "rationale": self.rationale,
            "evidence": self.evidence,
        }


def _predictions_metrics(preds: list[Prediction], policy: str, market: str) -> dict:
    probs = [p.prob_over for p in preds]
    outs = [p.outcome_over for p in preds]
    return compute_metrics(probs, outs, policy=policy, market=market, line=None).to_dict()


def _market_vs_model(preds: list[Prediction], market_bench: dict, market: str) -> Optional[dict]:
    """Paired model-vs-market Brier on fixtures/lines where market odds exist.

    Returns model & market Brier on the common set + a paired bootstrap of the
    (model - market) difference. Market odds are the benchmark only.
    """
    model_probs, market_probs, outs = [], [], []
    m_preds_a, m_preds_b = [], []
    for p in preds:
        key = (p.fixture_key, market, p.line)
        mb = market_bench.get(key)
        if mb is None or mb.prob_over is None:
            continue
        model_probs.append(p.prob_over)
        market_probs.append(mb.prob_over)
        outs.append(p.outcome_over)
        m_preds_a.append(p)
        # synthetic Prediction for the market arm (same key/outcome)
        m_preds_b.append(Prediction(
            fixture_key=p.fixture_key, kickoff_unix=p.kickoff_unix, market=market,
            line=p.line, prob_over=mb.prob_over, outcome_over=p.outcome_over,
            league=p.league, season=p.season,
        ))
    if not model_probs:
        return None
    n = len(model_probs)
    model_brier = sum(brier_losses(model_probs, outs)) / n
    market_brier = sum(brier_losses(market_probs, outs)) / n
    bs = paired_block_bootstrap(m_preds_a, m_preds_b, arm_a="model", arm_b="market",
                                metric="brier", n_boot=1500)
    return {
        "n_line_preds": n,
        "model_brier": round(model_brier, 4),
        "market_brier": round(market_brier, 4),
        "paired_model_minus_market": bs.to_dict(),
    }


def _classify(market: str, arm: str, arm_metrics: dict, baseline_metrics: dict,
              bootstrap_vs_baseline: dict) -> Verdict:
    """Apply the conservative promotion criteria to one provider arm vs baseline."""
    comparison = f"{arm} vs {BASELINE_POLICY}"
    diff = bootstrap_vs_baseline.get("observed_diff_a_minus_b")  # arm - baseline; <0 = arm better
    ci_low = bootstrap_vs_baseline.get("ci95_low")
    ci_high = bootstrap_vs_baseline.get("ci95_high")
    prob_arm_better = bootstrap_vs_baseline.get("prob_a_better")
    n = bootstrap_vs_baseline.get("n_fixtures", 0)
    arm_bss = arm_metrics.get("bss_vs_base_rate")
    arm_slope = arm_metrics.get("calibration_slope")

    ev = {
        "arm_brier": arm_metrics.get("brier"),
        "baseline_brier": baseline_metrics.get("brier"),
        "paired_diff_arm_minus_baseline": diff,
        "ci95": [ci_low, ci_high],
        "prob_arm_better": prob_arm_better,
        "arm_bss_vs_climatology": arm_bss,
        "arm_calibration_slope": arm_slope,
        "n_fixtures": n,
    }

    if arm == BASELINE_POLICY:
        return Verdict(market, comparison, "KEEP_BASELINE",
                       "This arm IS the baseline.", ev)

    # Degenerate: arm produced byte-identical predictions to the baseline (e.g.
    # PREFERRED_PROVIDER_WITH_FALLBACK when the preferred provider has complete
    # coverage, so fallback never fires). Label this precisely rather than
    # calling it "insufficient evidence".
    if (diff == 0.0 and ci_low == 0.0 and ci_high == 0.0):
        return Verdict(market, comparison, "KEEP_BASELINE",
                       "Arm is identical to the FootyStats baseline on this set "
                       "(no fallback fired; complete FootyStats coverage), so there "
                       "is nothing to promote.", ev)

    # Guard: material calibration degradation.
    if arm_slope is not None and arm_slope < _CALIB_SLOPE_FLOOR:
        return Verdict(market, comparison, "REJECT",
                       f"Calibration slope {arm_slope} below floor {_CALIB_SLOPE_FLOOR}.", ev)

    # CI spanning zero => cannot distinguish from baseline.
    if ci_low is None or ci_high is None or n < 50:
        return Verdict(market, comparison, "INSUFFICIENT_EVIDENCE",
                       "Too few paired fixtures for a credible interval.", ev)
    if ci_low <= 0.0 <= ci_high:
        return Verdict(market, comparison, "INSUFFICIENT_EVIDENCE",
                       "Paired 95% CI for the metric difference spans zero; the arm is "
                       "not distinguishable from the FootyStats baseline.", ev)

    # Direction credible AND arm better (diff<0) AND beats climatology.
    if diff is not None and diff < 0 and prob_arm_better is not None \
            and prob_arm_better >= _DIRECTION_CONF and (arm_bss or 0) > _MEANINGFUL_BSS:
        return Verdict(market, comparison, "PROMOTE_CANDIDATE",
                       "Arm improves on the baseline with a 95% CI excluding zero, "
                       "credible direction, and positive skill vs climatology. "
                       "Single-league (EPL) only -> candidate, not a promotion.", ev)

    # Arm worse with credible direction.
    if diff is not None and diff > 0 and (1 - (prob_arm_better or 0)) >= _DIRECTION_CONF:
        return Verdict(market, comparison, "KEEP_BASELINE",
                       "Baseline is credibly at least as good as this arm.", ev)

    return Verdict(market, comparison, "INSUFFICIENT_EVIDENCE",
                   "No credible directional improvement over baseline.", ev)


@dataclass
class ExperimentReport:
    baseline_sha: str
    pit_support: dict
    identity: dict
    dataset: dict
    coverage: dict
    per_market: dict = field(default_factory=dict)
    verdicts: list = field(default_factory=list)
    value_decomposition: dict = field(default_factory=dict)
    limitations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "experiment": "provider_comparison",
            "baseline_sha": self.baseline_sha,
            "evaluation_only": True,
            "champion_modified": False,
            "pit_support": self.pit_support,
            "identity": self.identity,
            "dataset": self.dataset,
            "coverage": self.coverage,
            "per_market": self.per_market,
            "verdicts": self.verdicts,
            "value_decomposition": self.value_decomposition,
            "limitations": self.limitations,
        }


def run_experiment(
    *,
    baseline_sha: str = "9854363",
    arm: str = "pooled",
    seed: int = 12345,
) -> ExperimentReport:
    """Run the full experiment deterministically and return the report."""
    reg, idrep, name_to_tm = load_high_confidence_team_registry(
        min_confidence=0.9, leagues=["England Premier League"]
    )
    paired, dsrep = build_epl_paired_dataset(name_to_tm["England Premier League"])
    concepts = [c.concept for c in OVERLAPPING_CONCEPTS]
    cov = build_coverage_report(paired, concepts, league="EPL")
    market_bench = build_market_benchmarks_by_fs_id({f.fs_match_id for f in paired})

    report = ExperimentReport(
        baseline_sha=baseline_sha,
        pit_support=VINTAGE_SUPPORT.to_dict(),
        identity=idrep.to_dict(),
        dataset=dsrep.to_dict(),
        coverage=cov.to_dict(),
    )

    for market in MARKETS:
        runs = {a: run_walk_forward(paired, policy=a, market=market, arm=arm) for a in PROVIDER_ARMS}
        baseline_preds = runs[BASELINE_POLICY].predictions
        baseline_metrics = _predictions_metrics(baseline_preds, BASELINE_POLICY, market)

        market_block = {
            "arms": {},
            "vs_baseline_paired": {},
            "model_vs_market": {},
        }
        for a in PROVIDER_ARMS:
            preds = runs[a].predictions
            market_block["arms"][a] = _predictions_metrics(preds, a, market)
            if a != BASELINE_POLICY:
                bs = paired_block_bootstrap(
                    preds, baseline_preds, arm_a=a, arm_b=BASELINE_POLICY,
                    metric="brier", n_boot=1500, seed=seed,
                )
                market_block["vs_baseline_paired"][a] = bs.to_dict()
                report.verdicts.append(
                    _classify(market, a, market_block["arms"][a], baseline_metrics, bs.to_dict()).to_dict()
                )
            mvm = _market_vs_model(preds, market_bench, market)
            if mvm is not None:
                market_block["model_vs_market"][a] = mvm
        report.per_market[market] = market_block

    # Provider value decomposition (Phase 12), hypothesis-driven and narrow.
    report.value_decomposition = _value_decomposition(paired, arm=arm, seed=seed)

    report.limitations = [
        "Single league (EPL) and two seasons; not robust across leagues/seasons.",
        "Stat observations carry no capture timestamp -> EARLY/LATE vintages "
        "UNSUPPORTED; evaluated on the fixture-date walk-forward only.",
        "Genuine closing/CLV UNSUPPORTED (timestamped odds do not overlap fixtures "
        "with stats); market benchmark is pre-match de-vigged odds only.",
        "Providers agree on goals/corners/cards/SoT/possession; provider choice can "
        "only move results via shots/xg, which the corners/cards champion uses only "
        "through shots. Effect sizes are therefore expected to be small.",
        "Team identity uses high-confidence (>=0.9) maps only; 2 EPL teams excluded.",
    ]
    return report


def _value_decomposition(paired: list[PairedFixture], *, arm: str, seed: int) -> dict:
    """Replacement vs coverage vs new-feature value (narrow ablation).

    - replacement: thestatsapi_only vs footystats_only on the OVERLAP feature set
      (shots/possession/fouls) -> does swapping the provider's measurement help?
    - coverage: fallback fill rate (how often preferred_fallback used TheStatsAPI
      because FootyStats was missing). On EPL FootyStats coverage is ~100%, so
      coverage value is expected ~0 here (reported, not assumed).
    - new_feature: footystats_only WITH vs WITHOUT the FootyStats-only extras
      (dangerous_attacks/attacks). This isolates additional-feature value, which
      is NOT a provider-accuracy claim.
    """
    out: dict = {}
    # Coverage: how many fixtures would need fallback (FootyStats missing the
    # overlap stats). Count fixtures where any overlap side value is None in FS.
    need_fallback = 0
    for f in paired:
        fs = f.fs_side
        if fs is None:
            need_fallback += 1
            continue
        if any(getattr(fs, f"{s}_{side}") is None
               for s in ("shots", "possession", "fouls") for side in ("home", "away")):
            need_fallback += 1
    out["coverage_value"] = {
        "fixtures": len(paired),
        "fixtures_needing_fallback_from_footystats": need_fallback,
        "fallback_rate": round(need_fallback / len(paired), 4) if paired else None,
        "note": "Low/zero fallback rate => coverage value of TheStatsAPI is minimal on this set.",
    }

    # New-feature value: FS-only with vs without extras, corners market.
    base = run_walk_forward(paired, policy="footystats_only", market="CORNERS_TOTAL",
                            arm=arm, include_fs_only_features=False)
    ext = run_walk_forward(paired, policy="footystats_only", market="CORNERS_TOTAL",
                           arm=arm, include_fs_only_features=True)
    bs = paired_block_bootstrap(ext.predictions, base.predictions,
                                arm_a="with_fs_only_features", arm_b="overlap_only",
                                metric="brier", n_boot=1500, seed=seed)
    out["new_feature_value_corners"] = {
        "description": "FootyStats-only extras (dangerous_attacks/attacks) added to overlap set.",
        "paired_with_minus_without": bs.to_dict(),
    }
    return out
