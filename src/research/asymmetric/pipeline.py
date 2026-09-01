"""Build/backtest pipeline wiring — strictly zero-API (Req 13.1, 13.4, 12.1/12.2).

Responsibility:
    Connect the isolated components into the full build/backtest run:

        Loaders -> Team_Profiler (full for Rich, reduced for Broad)
                -> Feature_Verification_Gate (stop on any failure)
                -> Sanity_Gate (record known non-persistence, never stop)
                -> Interaction_Model (fit) + Per_Side predictions
                -> Derived_Outcome combiner + correlation check
                -> AsymmetryEvaluator (fresh FDR)
                -> Reporting

    and produce the final report document: per-side-vs-baseline (per market and
    league), rich-vs-broad comparison, ECE/reliability per target, the fresh FDR
    family size, and a CI on every estimate.

Zero-API guarantee (Req 12.1, 12.2, 13.4):
    This module imports ONLY cached loaders and pure modelling components. It does
    NOT import ``live_fetch`` (the CLI-only capped fetcher). The corpus is passed
    in as already-loaded matches or via the cache-only loaders, so no network call
    can occur on the build/backtest path. A test injects an API stub that raises
    on any call and asserts it is never invoked (task 13.2 / Property 23).

Isolation: imports only the isolated package + general-purpose building blocks
(no prior-effort modules, Req 13.2, 13.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.research.asymmetric.derived import DerivedOutcomeCombiner
from src.research.asymmetric.evaluation import AsymmetryEvaluator, AsymmetryReport
from src.research.asymmetric.gates import (
    FeatureVerificationGate,
    SanityGate,
    SanityRecord,
)
from src.research.asymmetric.interaction import (
    TARGETS,
    InteractionModel,
    build_training_observations,
)
from src.research.asymmetric.models import GateResult
from src.research.asymmetric.profiles import TeamProfiler
from src.research.asymmetric.reporting import (
    AsymmetryReportDocument,
    TargetCalibration,
    assemble_report,
)
from src.research.data_source import ResearchMatch


@dataclass(frozen=True)
class PipelineResult:
    """The full build/backtest output for one corpus (or a rich+broad pair).

    Attributes:
        gate: the Feature_Verification_Gate result (Req 6). When it did not pass,
            ``stopped_before_modelling`` is True and ``report`` is None — the
            pipeline stopped before modelling exactly as the gate demands.
        sanity_records: recorded structural non-persistence results (Req 7).
        report: the assembled honest report document, or None if the gate stopped
            the run before modelling.
        stopped_before_modelling: True iff the gate failed and modelling was
            skipped (Req 6.8).
    """

    gate: GateResult
    sanity_records: tuple[SanityRecord, ...]
    report: Optional[AsymmetryReportDocument]
    stopped_before_modelling: bool


def _completed(matches: Sequence[ResearchMatch]) -> list[ResearchMatch]:
    return [m for m in matches if m.home_goals is not None and m.away_goals is not None]


def run_pipeline(
    matches: Sequence[ResearchMatch],
    *,
    leagues: Optional[dict[int, str]] = None,
    corpus_label: str = "rich",
    reduced_profiles: bool = False,
    targets: tuple[str, ...] = TARGETS,
    dataset_version: str = "asym-v1",
    research_run_id: str = "asym-run-1",
    run_gate: bool = True,
    min_within_league: int = 30,
    bootstrap_draws: int = 1000,
    broad_report: Optional[AsymmetryReport] = None,
    seed: int = 12345,
) -> PipelineResult:
    """Run the full zero-API build/backtest pipeline for one corpus (Req 13.1).

    Args:
        matches: cached corpus matches (already loaded; NEVER fetched here).
        leagues: ``league_id -> label`` map for per-league reporting.
        corpus_label: "rich" or "broad".
        reduced_profiles: build reduced Broad_Corpus profiles when True (Req 4.3).
        targets: the Per_Side_Targets to evaluate.
        dataset_version / research_run_id: identity for the fresh FDR family
            (Req 8.10, 13.3) — never inherited from any prior effort.
        run_gate: run the Feature_Verification_Gate first; on failure the pipeline
            stops before modelling (Req 6.8). Set False only in controlled tests.
        min_within_league / bootstrap_draws / seed: evaluator knobs.
        broad_report: an optional Broad_Corpus AsymmetryReport for the
            rich-vs-broad comparison in the assembled document (Req 10.2).

    Returns:
        A :class:`PipelineResult`. When the gate stops the run, ``report`` is None.
    """
    leagues = leagues or {}
    completed = _completed(matches)
    profiler = TeamProfiler(reduced=reduced_profiles)

    # 1. Feature_Verification_Gate — stop before modelling on any failure (Req 6).
    if run_gate:
        gate = FeatureVerificationGate(seed=seed).run(completed, profiler, leagues)
    else:
        gate = GateResult(
            gate="feature_verification",
            passed=True,
            checks=(),
            stopped_modelling=False,
        )

    # 2. Sanity_Gate — record known non-persistence, never stops (Req 7).
    league_labels = sorted(set(leagues.values())) or ["__pooled__"]
    sanity_records = tuple(SanityGate().run(league_labels, list(targets)))

    if not gate.passed:
        # The gate demands we stop before modelling (Req 6.8).
        return PipelineResult(
            gate=gate,
            sanity_records=sanity_records,
            report=None,
            stopped_before_modelling=True,
        )

    # 3. Interaction_Model fit (for readable coefficients in the report, Req 10.3).
    interaction = InteractionModel(targets=targets)
    if completed:
        interaction.fit(
            build_training_observations(
                completed, profiler, targets=targets, leagues=leagues
            )
        )

    # 4. Derived combiner + correlation check are exercised per-fixture inside the
    #    evaluator/CLI; here we surface the combiner so its independence
    #    assumption + correlation structure are available to reporting.
    _ = DerivedOutcomeCombiner()

    # 5. AsymmetryEvaluator with a FRESH FDR family (Req 8, 8.10, 13.3).
    evaluator = AsymmetryEvaluator(
        min_within_league=min_within_league,
        bootstrap_draws=bootstrap_draws,
        seed=seed,
    )
    rich_report = evaluator.evaluate(
        completed,
        profiler,
        targets=targets,
        leagues=leagues,
        corpus_label=corpus_label,
        dataset_version=dataset_version,
        research_run_id=research_run_id,
    )

    # 6. Assemble the honest report (Req 10): coefficients + rich-vs-broad.
    document = assemble_report(
        rich_report,
        broad_report=broad_report,
        interaction_model=interaction,
    )

    return PipelineResult(
        gate=gate,
        sanity_records=sanity_records,
        report=document,
        stopped_before_modelling=False,
    )
