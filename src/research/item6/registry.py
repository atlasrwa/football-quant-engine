"""NOVEL_HYPOTHESIS_FAMILY_REGISTRY_V1  (`item6_novel_family_registry_v1`).

Builds the versioned registry of accepted novel families from the corpus of F3/F4
formalizations. Each accepted family gets:
  family_id, semantic_description, required_measurable_variables, conditioning_dimensions,
  temporal_resolution_requirement, provider_requirements, formalization_rule,
  existing_grammar_supported (bool), required_additive_extension (or null).

NO predictive result belongs in this registry (frozen invariant). It records STRUCTURE and
provenance only. The registry is what gets FROZEN if Stage 1 passes, and is the sole input
surface Stage 2 may draw novel families from.

Family identity is the deterministic family_signature (metrics, novelty signals, bands) used
by the dedup layer, so the registry is stable and reproducible.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from .formalizer import F3, F4, FormalizationResult
from .schema import Mechanism

NOVEL_FAMILY_REGISTRY_VERSION = "item6_novel_family_registry_v1"

# forbidden keys that must never appear in a registry entry (no predictive result).
_FORBIDDEN_REGISTRY_KEYS = (
    "effect", "p_value", "pvalue", "oos", "survives", "score", "probability",
    "brier", "log_loss", "coefficient", "edge", "ev",
)


def _band_dims(m: Mechanism) -> List[str]:
    cl = m.conditioning_logic.lower()
    dims: List[str] = []
    if any(w in cl for w in ("home", "away", "venue")):
        dims.append("historical_venue_conditioning")
    if any(w in cl for w in ("profile", "high", "mid", "low", "tercile", "band")):
        dims.append("opponent_profile")
    if "competition" in cl or "same-competition" in cl:
        dims.append("competition")
    if any(w in cl for w in ("half", "game state", "scoreline", "leading", "trailing")):
        dims.append("match_state")
    if any(w in cl for w in ("threshold", "above", "below", "exceed")):
        dims.append("threshold")
    return sorted(set(dims))


def build_registry(
    accepted: Sequence[Tuple[Mechanism, FormalizationResult]],
) -> Dict[str, object]:
    """accepted: (mechanism, formalization) pairs that are F3/F4 and counts_as_novel_measurable.
    Returns a registry dict grouping by family signature; one canonical entry per family.
    """
    from .formalizer import family_signature

    groups: Dict[Tuple, List[Tuple[Mechanism, FormalizationResult]]] = {}
    for m, f in sorted(accepted, key=lambda x: x[0].mechanism_id_local):
        if f.f_class not in (F3, F4) or not f.counts_as_novel_measurable:
            continue
        groups.setdefault(family_signature(m), []).append((m, f))

    families: List[Dict[str, object]] = []
    for i, (sig, members) in enumerate(sorted(groups.items(), key=lambda kv: str(kv[0]))):
        m0, f0 = members[0]
        entry = {
            "family_id": f"NF_{i:03d}",
            "family_signature": str(sig),
            "semantic_description": m0.mechanism_statement,
            "required_measurable_variables": sorted(set(f0.distinct_metrics)
                                                     or m0.observable_variables),
            "conditioning_dimensions": _band_dims(m0),
            "temporal_resolution_requirement": m0.data_resolution_required,
            "provider_requirements": sorted(set(
                v for mm, _ in members for v in mm.provider_requirements)),
            "formalization_rule": f0.f_class,
            "existing_grammar_supported": f0.f_class == F3,
            "required_additive_extension": f0.required_extension,
            "novelty_signals": f0.novelty_signals,
            "member_mechanism_ids": [mm.mechanism_id_local for mm, _ in members],
            "n_members": len(members),
        }
        # invariant: no predictive result key
        for k in entry:
            assert not any(fb in k.lower() for fb in _FORBIDDEN_REGISTRY_KEYS), \
                f"registry entry key '{k}' resembles a predictive-result field"
        families.append(entry)

    return {
        "registry_version": NOVEL_FAMILY_REGISTRY_VERSION,
        "n_families": len(families),
        "families": families,
        "contains_predictive_result": False,
    }


def version_stamp() -> Dict[str, object]:
    return {
        "novel_family_registry_version": NOVEL_FAMILY_REGISTRY_VERSION,
        "records_predictive_result": False,
        "family_identity": "deterministic_family_signature",
    }
