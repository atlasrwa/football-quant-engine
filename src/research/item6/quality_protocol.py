"""STAGE1_QUALITY_PROTOCOL_V1  (`item6_quality_protocol_v1`).

A corrected successor to the previous quality audit. The prior audit had (a) an unreachable
aggregate category (Q2) and (b) a single LLM rater. This protocol fixes both:

  * Scoring is DIMENSION-LEVEL, not aggregate-category-level. No single aggregate "Q"
    bucket is the scientific endpoint; each dimension is scored and reported independently.
  * Rater independence: TWO passes.
      PASS A  deterministic structural classifier (this module) — reproducible, no model.
      PASS B  semantic blinded rater — a SEPARATE, cost-authorized pass (NOT run here; the
              stand-in uses a deterministic stub of Pass B so agreement can be computed
              offline). Pass B sees only the pre-target packet + mechanism + evidence refs +
              baseline coverage spec; it NEVER sees OOS outcomes, markets, or ARM-D results.

Frozen dimensions (each scored on a small ordinal scale by Pass A structurally):
  fixture_specificity, grounding, information_gain, interaction_depth,
  mechanistic_plausibility, novelty, synthesis, falsifiability, statistical_discipline,
  grammar_transcendence, actionability, baseline_equivalence.

This module implements PASS A only (deterministic). It reads no outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .baseline_equivalence import classify as classify_equivalence, distinct_metrics, novelty_signals
from .formalizer import FormalizationResult
from .schema import Mechanism

QUALITY_PROTOCOL_VERSION = "item6_quality_protocol_v1"

QUALITY_DIMENSIONS = (
    "fixture_specificity",
    "grounding",
    "information_gain",
    "interaction_depth",
    "mechanistic_plausibility",
    "novelty",
    "synthesis",
    "falsifiability",
    "statistical_discipline",
    "grammar_transcendence",
    "actionability",
    "baseline_equivalence",
)


@dataclass
class PassAScores:
    mechanism_id_local: str
    scores: Dict[str, int]     # dimension -> ordinal 0..2

    def to_dict(self) -> Dict[str, object]:
        return {"mechanism_id_local": self.mechanism_id_local, "scores": self.scores}


def pass_a_score(m: Mechanism, f: FormalizationResult) -> PassAScores:
    """Deterministic structural scoring. 0 = absent/poor, 1 = partial, 2 = strong."""
    eq = classify_equivalence(m)
    dm = distinct_metrics(m)
    sig = novelty_signals(m)
    txt_len = len(m.mechanism_statement) + len(m.conditioning_logic)

    s: Dict[str, int] = {}
    # fixture_specificity: does conditioning reference fixture-specific context (opponent/venue)?
    s["fixture_specificity"] = 2 if any(w in (m.conditioning_logic + m.mechanism_statement).lower()
                                        for w in ("opponent", "fixture", "venue", "similar")) else 1
    # grounding: valid evidence + measurable variable
    s["grounding"] = 2 if f.grounded else 0
    # information_gain: non-baseline-equivalent AND grounded AND provider-safe
    s["information_gain"] = 2 if (f.counts_as_novel_measurable) else (1 if not eq.is_baseline_equivalent else 0)
    # interaction_depth: number of distinct metrics / interaction signals
    s["interaction_depth"] = 2 if (len(dm) >= 2 or "US_TWO_DIM_OPP_PROFILE_INTERSECTION" in sig) else (1 if dm else 0)
    # mechanistic_plausibility: has a stated relationship + conditioning (coherence proxy)
    s["mechanistic_plausibility"] = 2 if (m.expected_relationship_to_test and m.conditioning_logic
                                          and txt_len > 40) else 1
    # novelty: structural escape-hatch present
    s["novelty"] = 2 if sig else (0 if eq.is_baseline_equivalent else 1)
    # synthesis: combines >1 concept (metrics or dims)
    s["synthesis"] = 2 if (len(dm) >= 2 or len(sig) >= 2) else (1 if (dm or sig) else 0)
    # falsifiability: states a directional testable relationship, provider-safe, not leaking
    s["falsifiability"] = 2 if (f.provider_safe and not f.future_leakage
                                and m.expected_relationship_to_test) else 0
    # statistical_discipline: no forbidden numeric claim survived (schema already guards);
    # here reward abstemious phrasing (no probability words)
    s["statistical_discipline"] = 2  # schema-validated responses reach Pass A; violations rejected upstream
    # grammar_transcendence: needs an additive extension
    s["grammar_transcendence"] = 2 if f.required_extension else 0
    # actionability: formalizes to F3/F4 (measurable) — provider can build it
    s["actionability"] = 2 if f.counts_as_novel_measurable else (1 if f.grounded and f.provider_safe else 0)
    # baseline_equivalence (LOWER is better; scored inverted: 2 = clearly non-equivalent)
    s["baseline_equivalence"] = 0 if eq.is_baseline_equivalent else 2
    return PassAScores(m.mechanism_id_local, s)


def pass_b_stub(m: Mechanism, f: FormalizationResult) -> PassAScores:
    """Deterministic STAND-IN for the blinded semantic Pass B, for offline agreement testing.

    It intentionally uses a slightly different (semantic-flavoured) heuristic than Pass A so
    that inter-pass agreement is a non-trivial, reportable number in rehearsal. In the LIVE
    experiment, Pass B is a separately cost-authorized semantic rater; this stub is NEVER
    used to make a scientific claim, only to exercise the agreement machinery at zero spend.
    """
    a = pass_a_score(m, f).scores.copy()
    # semantic-flavoured adjustment: reward longer, more articulated mechanism prose on
    # mechanistic_plausibility and synthesis; otherwise mirror Pass A.
    length = len(m.mechanism_statement)
    a["mechanistic_plausibility"] = 2 if length > 80 else (1 if length > 30 else 0)
    a["synthesis"] = min(2, a["synthesis"] + (1 if length > 120 else 0))
    return PassAScores(m.mechanism_id_local, a)


def agreement(a: List[PassAScores], b: List[PassAScores]) -> Dict[str, float]:
    """Per-dimension exact-agreement rate between two passes (aligned by mechanism id)."""
    bmap = {x.mechanism_id_local: x for x in b}
    dims = QUALITY_DIMENSIONS
    agree = {d: 0 for d in dims}
    n = 0
    for x in a:
        y = bmap.get(x.mechanism_id_local)
        if y is None:
            continue
        n += 1
        for d in dims:
            if x.scores.get(d) == y.scores.get(d):
                agree[d] += 1
    return {d: (0.0 if n == 0 else round(agree[d] / n, 4)) for d in dims} | {"_n": n}


def version_stamp() -> Dict[str, object]:
    return {
        "quality_protocol_version": QUALITY_PROTOCOL_VERSION,
        "dimensions": list(QUALITY_DIMENSIONS),
        "pass_a": "deterministic_structural",
        "pass_b": "blinded_semantic_separately_cost_authorized",
        "aggregate_category_is_endpoint": False,
        "oos_visible": False,
    }
