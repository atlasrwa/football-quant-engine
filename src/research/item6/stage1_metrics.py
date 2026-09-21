"""STAGE 1 endpoint computation + frozen gate  (`item6_stage1_metrics_v1`).

Aggregates per-fixture formalization/dedup output into the frozen Stage-1 endpoints and
applies the preregistered HARD PASS/FAIL gate. Endpoints are computed, the gate decides;
neither reads any OOS outcome (Stage-1 is OOS-blind by construction).

Within-fixture dependence is handled explicitly: the primary novel-measurable-family
endpoint is aggregated at the FIXTURE level (fraction of fixtures producing >=1 novel
measurable family) as well as at the mechanism level, and the gate uses the fixture-level
denominator for its primary threshold so K correlated mechanisms in one fixture are not
counted as K independent successes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from .formalizer import F0, F1, F2, F3, F4, F5, FormalizationResult

STAGE1_METRICS_VERSION = "item6_stage1_metrics_v1"


@dataclass
class FixtureOutcome:
    fixture_id: str
    abstained: bool
    formalizations: List[FormalizationResult]
    duplicate_rate: float           # within-fixture, from dedup report
    # cross-fixture dedup is applied separately at corpus level


@dataclass
class Stage1Endpoints:
    n_fixtures: int
    n_fixtures_abstained: int
    n_mechanisms_total: int
    baseline_equivalent_rate: float
    semantic_duplicate_rate: float
    novel_measurable_family_rate: float          # fixture-level primary
    novel_measurable_family_rate_mech: float     # mechanism-level secondary
    multivariable_interaction_rate: float
    new_family_count: int
    grounding_pass_rate: float
    falsifiability_pass_rate: float
    formalization_survival_rate: float
    abstention_rate: float
    f_class_counts: Dict[str, int]
    extension_family_ids: List[str]

    def to_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()


def _rate(num: int, den: int) -> float:
    return 0.0 if den == 0 else round(num / den, 6)


def compute_endpoints(
    outcomes: Sequence[FixtureOutcome],
    corpus_duplicate_rate: float,
    corpus_new_family_ids: Sequence[str],
) -> Stage1Endpoints:
    """corpus_duplicate_rate: the SEMANTIC_DUPLICATE_RATE unit = mean WITHIN-fixture duplicate
        rate (fraction of a fixture's K mechanisms that share a family signature with an
        earlier one in the same fixture), averaged over non-abstaining fixtures. This is the
        scale-stable definition that handles within-fixture dependence and matches the prior
        small-corpus audit's notion of "the generator keeps proposing the same concept".
    corpus_new_family_ids: distinct NOVEL family signatures accepted across the whole corpus.
    """
    n_fix = len(outcomes)
    n_abst = sum(1 for o in outcomes if o.abstained)
    all_f: List[FormalizationResult] = [f for o in outcomes for f in o.formalizations]
    n_mech = len(all_f)

    fc: Dict[str, int] = {k: 0 for k in (F0, F1, F2, F3, F4, F5)}
    for f in all_f:
        fc[f.f_class] = fc.get(f.f_class, 0) + 1

    n_baseline_eq = sum(1 for f in all_f if f.is_baseline_equivalent)
    n_novel_meas = sum(1 for f in all_f if f.counts_as_novel_measurable)
    n_grounded = sum(1 for f in all_f if f.grounded)
    n_interaction = sum(1 for f in all_f if len(f.distinct_metrics) >= 2
                        or "US_TWO_DIM_OPP_PROFILE_INTERSECTION" in f.novelty_signals)
    # falsifiability proxy (structural): a mechanism is falsifiable if it is grounded,
    # provider-safe, not future-leaking, and states a directional relationship (non-F0/F2).
    n_falsifiable = sum(1 for f in all_f
                        if f.grounded and f.provider_safe and not f.future_leakage
                        and f.f_class not in (F0, F2))
    # survival: fraction of NON-baseline-equivalent, grounded mechanisms whose value survives
    # formalization (i.e. lands in F3/F4 rather than collapsing to F0/F1/F2/F5).
    non_be_grounded = [f for f in all_f if (not f.is_baseline_equivalent) and f.grounded]
    n_survive = sum(1 for f in non_be_grounded if f.counts_as_novel_measurable)

    # fixture-level primary: fraction of NON-abstaining fixtures with >=1 novel measurable family
    non_abst = [o for o in outcomes if not o.abstained]
    n_fix_with_novel = sum(1 for o in non_abst
                           if any(f.counts_as_novel_measurable for f in o.formalizations))

    return Stage1Endpoints(
        n_fixtures=n_fix,
        n_fixtures_abstained=n_abst,
        n_mechanisms_total=n_mech,
        baseline_equivalent_rate=_rate(n_baseline_eq, n_mech),
        semantic_duplicate_rate=round(corpus_duplicate_rate, 6),
        novel_measurable_family_rate=_rate(n_fix_with_novel, len(non_abst)),
        novel_measurable_family_rate_mech=_rate(n_novel_meas, n_mech),
        multivariable_interaction_rate=_rate(n_interaction, n_mech),
        new_family_count=len(set(corpus_new_family_ids)),
        grounding_pass_rate=_rate(n_grounded, n_mech),
        falsifiability_pass_rate=_rate(n_falsifiable, n_mech),
        formalization_survival_rate=_rate(n_survive, len(non_be_grounded)),
        abstention_rate=_rate(n_abst, n_fix),
        f_class_counts=fc,
        extension_family_ids=sorted({f.required_extension for f in all_f if f.required_extension}),
    )


def version_stamp() -> Dict[str, object]:
    return {
        "stage1_metrics_version": STAGE1_METRICS_VERSION,
        "primary_novel_family_denominator": "non_abstaining_fixtures",
        "handles_within_fixture_dependence": True,
        "reads_oos": False,
    }
