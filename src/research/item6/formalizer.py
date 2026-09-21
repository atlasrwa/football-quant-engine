"""MECHANISM_FORMALIZER_V1  (`item6_formalizer_v1`).

Deterministic triage/compiler layer (PHASE C). Given a validated Mechanism it:
  - validates evidence refs against the fixture's allowed evidence-ref set,
  - extracts the measurable variables and maps them to provider metrics,
  - detects provider-unsafe / future-leakage concepts,
  - runs the baseline-equivalence detector,
  - classifies the mechanism into exactly one F-class,
  - identifies the additive grammar extension required (if any).

F-classes (frozen):
  F0_NOT_GROUNDED                        - no valid evidence ref, or no measurable variable
  F1_BASELINE_EQUIVALENT                 - equivalent to a covered baseline family
  F2_GROUNDED_BUT_NOT_PROVIDER_MEASURABLE- references provider-unsafe/unavailable concept
  F3_MEASURABLE_WITH_EXISTING_GRAMMAR    - novel-ish but expressible by existing grammar
  F4_MEASURABLE_WITH_SAFE_ADDITIVE_GRAMMAR_EXTENSION - novel AND needs a versioned extension
  F5_UNRESOLVED                          - could not be resolved deterministically

Only F3 and F4 may contribute to NOVEL_MEASURABLE_FAMILY_RATE.
NOTE: in practice a genuinely non-baseline-equivalent mechanism almost always needs an
additive extension (F4), because the whole point of R1..R8 is that the existing grammar
already covers everything expressible within it. F3 is reserved for the rare case where a
mechanism is not baseline-equivalent yet maps onto an existing comparator/condition
combination the coverage catalogue did not enumerate.

The formalizer NEVER computes support N, effect size, similarity score, feasibility,
p-value or OOS result. It decides *measurability class* only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .baseline_equivalence import (
    BASELINE_EQUIVALENCE_VERSION,
    classify as classify_equivalence,
    distinct_metrics,
    novelty_signals,
)
from .provider_vocab import (
    FUTURE_LEAKAGE_CONCEPTS,
    PROVIDER_METRICS,
    PROVIDER_UNSAFE_CONCEPTS,
    PROVIDER_VOCAB_VERSION,
    RES_HALF,
    resolution_of,
)
from .schema import Mechanism

FORMALIZER_VERSION = "item6_formalizer_v1"

F0 = "F0_NOT_GROUNDED"
F1 = "F1_BASELINE_EQUIVALENT"
F2 = "F2_GROUNDED_BUT_NOT_PROVIDER_MEASURABLE"
F3 = "F3_MEASURABLE_WITH_EXISTING_GRAMMAR"
F4 = "F4_MEASURABLE_WITH_SAFE_ADDITIVE_GRAMMAR_EXTENSION"
F5 = "F5_UNRESOLVED"

# Map an escape-hatch structural signal to the additive grammar extension it requires.
SIGNAL_TO_EXTENSION: Dict[str, str] = {
    "US_MULTI_METRIC_INTERACTION": "GX_CROSS_METRIC_JOINT",
    "US_TWO_DIM_OPP_PROFILE_INTERSECTION": "GX_TWO_AXIS_PROFILE_INTERSECTION",
    "US_THRESHOLD_NONLINEARITY": "GX_THRESHOLD_CONDITION",
    "US_HALF_STATE_OR_GAME_STATE": "GX_HALF_STATE_INTERACTION",
    "US_CROSS_METRIC_ASYMMETRY": "GX_CROSS_METRIC_ASYMMETRY",
    "US_SEQUENCING_REGIME": "GX_SEQUENCE_REGIME",
}


@dataclass
class FormalizationResult:
    mechanism_id_local: str
    f_class: str
    is_baseline_equivalent: bool
    grounded: bool
    provider_safe: bool
    future_leakage: bool
    distinct_metrics: List[str]
    novelty_signals: List[str]
    required_extension: Optional[str]
    valid_evidence_refs: List[str]
    invalid_evidence_refs: List[str]
    rationale: str
    # convenience: does this survive to a novel measurable family?
    counts_as_novel_measurable: bool = field(default=False)

    def to_dict(self) -> Dict[str, object]:
        d = self.__dict__.copy()
        return d


def _unsafe_concept_hit(m: Mechanism) -> Optional[str]:
    blob = " ".join([
        m.mechanism_statement, m.conditioning_logic, m.expected_relationship_to_test,
        " ".join(m.observable_variables), " ".join(m.provider_requirements),
    ]).lower()
    for c in PROVIDER_UNSAFE_CONCEPTS:
        if c in blob:
            return c
    return None


def _future_leak_hit(m: Mechanism) -> Optional[str]:
    blob = " ".join([
        m.mechanism_statement, m.conditioning_logic, m.expected_relationship_to_test,
        m.why_not_baseline_equivalent, " ".join(m.observable_variables),
    ]).lower()
    for c in FUTURE_LEAKAGE_CONCEPTS:
        if c in blob:
            return c
    return None


def _has_measurable_variable(dm: Sequence[str], m: Mechanism) -> bool:
    if dm:
        return True
    # allow non-metric observable structural variables (venue/competition/formation/scoreline)
    structural = {"venue_home_away", "competition_label", "formation_recorded_prior_match",
                  "prior_match_scoreline"}
    for v in m.observable_variables:
        if v.strip().lower() in structural:
            return True
    return False


def formalize(m: Mechanism, allowed_evidence_refs: Optional[Sequence[str]] = None) -> FormalizationResult:
    """Classify a single mechanism deterministically.

    allowed_evidence_refs: the set of evidence-ref ids that were actually presented to the
    LLM for this fixture. If provided, refs outside it are 'invalid' (fabricated). If None,
    evidence-ref validity is not enforced (stand-in mode) but refs must be non-empty.
    """
    dm = distinct_metrics(m)
    sig = novelty_signals(m)

    # --- evidence grounding ---
    if allowed_evidence_refs is not None:
        allow = set(allowed_evidence_refs)
        valid = [r for r in m.evidence_refs if r in allow]
        invalid = [r for r in m.evidence_refs if r not in allow]
    else:
        valid = list(m.evidence_refs)
        invalid = []

    grounded = bool(valid) and _has_measurable_variable(dm, m)

    # --- provider safety / future leakage (checked before grounding verdict for clarity) ---
    unsafe = _unsafe_concept_hit(m)
    leak = _future_leak_hit(m)
    provider_safe = unsafe is None
    future_leakage = leak is not None

    eq = classify_equivalence(m)

    # --- F-class decision tree (ordered; first match wins) ---
    if future_leakage:
        return FormalizationResult(
            m.mechanism_id_local, F2, eq.is_baseline_equivalent, grounded, provider_safe,
            future_leakage, dm, sig, None, valid, invalid,
            f"Future/leakage concept referenced: '{leak}'. Rejected.",
            counts_as_novel_measurable=False)

    if not provider_safe:
        return FormalizationResult(
            m.mechanism_id_local, F2, eq.is_baseline_equivalent, grounded, provider_safe,
            future_leakage, dm, sig, None, valid, invalid,
            f"Provider-unsafe concept referenced: '{unsafe}'.",
            counts_as_novel_measurable=False)

    if not grounded:
        return FormalizationResult(
            m.mechanism_id_local, F0, eq.is_baseline_equivalent, grounded, provider_safe,
            future_leakage, dm, sig, None, valid, invalid,
            "No valid evidence ref and/or no measurable observable variable.",
            counts_as_novel_measurable=False)

    if eq.is_baseline_equivalent:
        return FormalizationResult(
            m.mechanism_id_local, F1, True, grounded, provider_safe, future_leakage,
            dm, sig, None, valid, invalid,
            f"Baseline-equivalent via {eq.matched_rule} ({eq.matched_family_id}).",
            counts_as_novel_measurable=False)

    # Non-baseline-equivalent AND grounded AND provider-safe.
    # Check that half-state signals are backed by half-resolution provider data.
    if "US_HALF_STATE_OR_GAME_STATE" in sig:
        half_ok = any(resolution_of(x) == RES_HALF for x in dm) or \
            any(resolution_of(v.strip().lower()) == RES_HALF for v in m.observable_variables) or \
            m.data_resolution_required == "half"
        if not half_ok:
            return FormalizationResult(
                m.mechanism_id_local, F2, False, grounded, provider_safe, future_leakage,
                dm, sig, None, valid, invalid,
                "Half/game-state construction not backed by half-resolution provider data.",
                counts_as_novel_measurable=False)

    # Determine required extension from the strongest structural signal.
    # Order matters: prefer the MOST SPECIFIC construct over generic multi-metric so a
    # threshold/half-state/two-axis mechanism is labelled by its defining structure.
    _EXT_PRIORITY = (
        "US_TWO_DIM_OPP_PROFILE_INTERSECTION",
        "US_THRESHOLD_NONLINEARITY",
        "US_HALF_STATE_OR_GAME_STATE",
        "US_SEQUENCING_REGIME",
        "US_CROSS_METRIC_ASYMMETRY",
        "US_MULTI_METRIC_INTERACTION",
    )
    required_ext = None
    for s in _EXT_PRIORITY:
        if s in sig and s in SIGNAL_TO_EXTENSION:
            required_ext = SIGNAL_TO_EXTENSION[s]
            break

    if required_ext is not None:
        return FormalizationResult(
            m.mechanism_id_local, F4, False, grounded, provider_safe, future_leakage,
            dm, sig, required_ext, valid, invalid,
            f"Novel, grounded, provider-safe; needs additive extension {required_ext}.",
            counts_as_novel_measurable=True)

    # Non-baseline-equivalent but no recognized extension needed: expressible with existing
    # grammar in a way the coverage catalogue did not enumerate (rare) -> F3.
    return FormalizationResult(
        m.mechanism_id_local, F3, False, grounded, provider_safe, future_leakage,
        dm, sig, None, valid, invalid,
        "Novel yet expressible with existing grammar (no additive extension required).",
        counts_as_novel_measurable=True)


# ------------------------- semantic deduplication ----------------------------------------
# Deterministic, embedding-free family-signature dedup. Two mechanisms are semantic
# duplicates iff they share the same canonical family signature:
#   (sorted distinct metrics, sorted novelty signals, sorted profile-band tokens)
# This is outcome-blind and reproducible. It does NOT use future outcomes and does not need
# a paid semantic rater. (An optional frozen LLM semantic pass could be added later under a
# separate cost authorization; it is deliberately NOT used here.)

def family_signature(m: Mechanism) -> Tuple:
    dm = tuple(distinct_metrics(m))
    sig = tuple(novelty_signals(m))
    band = tuple(sorted(set(
        t for t in ("high", "mid", "low")
        if t in m.conditioning_logic.lower()
    )))
    return (dm, sig, band)


def deduplicate(mechs: Sequence[Mechanism]) -> Dict[str, object]:
    """Group mechanisms by family signature. Returns dedup report.

    'representatives' = one mechanism per distinct signature (first by local id order).
    'duplicate_rate' = 1 - n_unique / n_total  (0.0 when all distinct).
    """
    groups: Dict[Tuple, List[str]] = {}
    for m in sorted(mechs, key=lambda x: x.mechanism_id_local):
        groups.setdefault(family_signature(m), []).append(m.mechanism_id_local)
    n_total = len(mechs)
    n_unique = len(groups)
    dup_rate = 0.0 if n_total == 0 else round(1.0 - n_unique / n_total, 6)
    return {
        "n_total": n_total,
        "n_unique_signatures": n_unique,
        "duplicate_rate": dup_rate,
        "signature_groups": {str(k): v for k, v in groups.items()},
        "representatives": [v[0] for v in groups.values()],
    }


def version_stamp() -> Dict[str, object]:
    return {
        "formalizer_version": FORMALIZER_VERSION,
        "baseline_equivalence_version": BASELINE_EQUIVALENCE_VERSION,
        "provider_vocab_version": PROVIDER_VOCAB_VERSION,
        "f_classes": [F0, F1, F2, F3, F4, F5],
        "novel_measurable_classes": [F3, F4],
        "dedup_method": "deterministic_family_signature_embedding_free",
        "outcome_aware": False,
        "computes_support_or_effect": False,
    }
