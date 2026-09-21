"""ARM G-D — deterministic hypothesis-family generator  (`item6_control_gd_v1`).

The Stage-1 control. Produces family proposals from ONLY the existing enumerated baseline
grammar (baseline_coverage), given the same evidence universe (the fixture's supported
metrics + profile axes). It is a genuine, NOT-deliberately-weakened enumerator: it emits the
strongest structural proposals the baseline grammar can express, including its two covered
arity-2 interactions.

Its purpose is the comparison denominator: ARM G-L (upgraded LLM) is only credited with
research-space EXPANSION for families that fall OUTSIDE ARM G-D's covered space. By
construction, every G-D proposal formalizes to F1 (baseline-equivalent), because G-D only
draws from the covered grammar. That is the point — it establishes the covered space the
LLM must exceed, not a rhetorical strawman.

Deterministic: same fixture context -> byte-identical proposals (sorted enumeration, no
randomness). Reads no outcome.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from .baseline_coverage import (
    BASELINE_COMPARATORS,
    BASELINE_PROFILE_AXES,
)
from .schema import Mechanism

CONTROL_GD_VERSION = "item6_control_gd_v1"


def generate_families(
    fixture_id: str,
    supported_metrics: Sequence[str],
    k: int,
) -> List[Mechanism]:
    """Emit up to k baseline-grammar family proposals as Mechanism objects (so they pass
    through the identical formalization pipeline as ARM G-L). Deterministic ordering.

    The proposals span the covered structural families: univariate profile split, venue
    contrast, recent-vs-longrun, similar-opponent cohort, and the covered venue x profile
    interaction. Each is a legitimate baseline research question — just inside the grammar.
    """
    metrics = sorted(set(supported_metrics))
    axes = list(BASELINE_PROFILE_AXES)
    proposals: List[Mechanism] = []

    templates = [
        # (suffix, statement, conditioning, relationship, variables, why)
        ("uni_profile",
         "Whether the subject's {m0} differs when facing opponents in a given band on {ax0}, "
         "versus the subject's own baseline.",
         "Condition on one opponent-profile band ({ax0}: HIGH/MID/LOW).",
         "The conditioned mean deviates from the unconditioned subject baseline.",
         ["{m0}"], "Single metric, single opponent-profile band."),
        ("venue_contrast",
         "Whether the subject's {m0} differs at home versus away, relative to a venue baseline.",
         "Condition on subject home/away venue only.",
         "Home and away conditioned means differ.",
         ["{m0}", "venue_home_away"], "Pure venue split on one metric."),
        ("recent_long",
         "Whether the subject's recent-window {m0} deviates from its long-run level.",
         "Compare recent window (W5/W10) against ALL_PRIOR for one metric.",
         "Recent-window mean differs from long-run mean.",
         ["{m0}"], "Recent-vs-long-run on one metric (form)."),
        ("similar_cohort",
         "Whether the subject's {m0} versus opponents similar to the fixture opponent differs "
         "from its overall baseline.",
         "Restrict to a deterministically-computed similar-opponent cohort.",
         "Cohort mean differs from overall subject baseline.",
         ["{m0}"], "Existing similarity comparator, one metric."),
        ("venue_x_profile",
         "Whether the subject's {m0} against a given opponent-profile band on {ax0} differs "
         "specifically at home versus away.",
         "Condition jointly on venue AND one opponent-profile band on {ax0} (covered arity-2).",
         "The venue x profile conditioned mean deviates from baseline.",
         ["{m0}", "venue_home_away"], "The covered venue x single-profile interaction."),
    ]

    idx = 0
    for t_i, (suffix, stmt, cond, rel, varsub, why) in enumerate(templates):
        m0 = metrics[t_i % len(metrics)] if metrics else "shots_on_target"
        ax0 = axes[t_i % len(axes)]
        variables = [v.format(m0=m0, ax0=ax0) for v in varsub]
        comparator = BASELINE_COMPARATORS[t_i % len(BASELINE_COMPARATORS)]
        proposals.append(Mechanism(
            mechanism_id_local=f"GD_{fixture_id}_{suffix}",
            mechanism_statement=stmt.format(m0=m0, ax0=ax0),
            observable_variables=variables,
            conditioning_logic=cond.format(m0=m0, ax0=ax0) + f" (comparator {comparator}).",
            expected_relationship_to_test=rel.format(m0=m0, ax0=ax0),
            why_not_baseline_equivalent=(
                "This is a baseline family proposal (control arm); it is expected to be "
                "baseline-equivalent."),
            evidence_refs=[f"ev_{fixture_id}_{m0}_summary"],
            data_resolution_required="match",
            provider_requirements=[m0],
            self_overlap_with=[],
        ))
        idx += 1
        if idx >= k:
            break
    return proposals[:k]


def version_stamp() -> Dict[str, object]:
    return {
        "control_gd_version": CONTROL_GD_VERSION,
        "draws_from": "baseline_grammar_only",
        "deliberately_weakened": False,
        "deterministic": True,
        "reads_outcomes": False,
    }
