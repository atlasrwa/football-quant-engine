"""ITEM6_MECHANISM_SCHEMA_V1  (`item6_mechanism_schema_v1`).

Structured-output contract for the LLM's mechanism-discovery response. The response is a
two-phase object:

  PHASE A  mechanism discovery  -> a list of proposed mechanisms (or explicit abstention)
  PHASE B  research specification -> per-mechanism measurable-relationship description

PHASE C (deterministic formalization) is NOT part of this schema — code owns it.

Hard structural prohibitions (enforced by validate_response, tested):
  * NO numerical prediction of any kind: probability, effect magnitude, confidence,
    novelty score, quality score, expected edge/EV, odds, stake, p-value, similarity score.
  * NO field asking the model to grade or rank its own novelty numerically.

Controlled free text is permitted ONLY in the semantic fields (mechanism_statement,
conditioning_logic, expected_relationship_to_test, why_not_baseline_equivalent). The
observable concepts referenced live in `observable_variables` and are bounded/auditable
downstream by the formalizer against provider_vocab.

This module validates STRUCTURE. It does not judge measurability, novelty or grounding —
those are the formalizer's and the quality protocol's job.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

MECHANISM_SCHEMA_VERSION = "item6_mechanism_schema_v1"

# Number of distinct mechanisms requested per fixture. Chosen scientifically (see
# STAGE1_POWER_AND_COST): K=5 gives enough within-fixture draws to estimate a per-fixture
# novel-family rate while keeping output-token cost bounded and abstention meaningful.
K_MECHANISMS_PER_FIXTURE = 5

# Fields that must NEVER appear anywhere in a mechanism object or the response (numeric
# authority / latent grading firewall). Matched case-insensitively as dict keys AND as
# substrings of any stringified value token, per the D7/D8 zero-tolerance lesson from V3.
FORBIDDEN_KEYS: Tuple[str, ...] = (
    "probability", "p_model", "prob", "effect", "effect_size", "magnitude",
    "confidence", "novelty_score", "novelty_probability", "quality_score",
    "expected_value", "ev", "edge", "odds", "stake", "p_value", "pvalue",
    "similarity_score", "distance", "score", "prediction", "predicted_prob",
    "coefficient", "weight", "expected_predictive_value",
)

REQUIRED_MECHANISM_FIELDS: Tuple[str, ...] = (
    "mechanism_id_local",
    "mechanism_statement",
    "observable_variables",
    "conditioning_logic",
    "expected_relationship_to_test",
    "why_not_baseline_equivalent",
    "evidence_refs",
    "data_resolution_required",
    "provider_requirements",
    "self_overlap_with",  # descriptive self-novelty check; deterministic dedup is authoritative
)

ABSTENTION_TOKEN = "NO_NOVEL_GROUNDED_MECHANISM"

# Direction words are ALLOWED (qualitative relationship). Numeric magnitudes are NOT.
# We reject any bare numeric that looks like a probability/percentage/effect claim inside
# a semantic field. Integers referring to windows/axes/counts of matches are tolerated only
# in the structured non-semantic fields.
_NUMERIC_CLAIM_RE = re.compile(
    r"(?<![\w])(\d+(\.\d+)?\s?%|0?\.\d+\s*(probability|prob|chance|odds)|"
    r"p\s*[=<>]\s*0?\.\d+|effect\s*(size)?\s*[=:]\s*-?\d)",
    re.IGNORECASE,
)


@dataclass
class Mechanism:
    mechanism_id_local: str
    mechanism_statement: str
    observable_variables: List[str]
    conditioning_logic: str
    expected_relationship_to_test: str
    why_not_baseline_equivalent: str
    evidence_refs: List[str]
    data_resolution_required: str          # "match" | "half"
    provider_requirements: List[str]
    self_overlap_with: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mechanism_id_local": self.mechanism_id_local,
            "mechanism_statement": self.mechanism_statement,
            "observable_variables": list(self.observable_variables),
            "conditioning_logic": self.conditioning_logic,
            "expected_relationship_to_test": self.expected_relationship_to_test,
            "why_not_baseline_equivalent": self.why_not_baseline_equivalent,
            "evidence_refs": list(self.evidence_refs),
            "data_resolution_required": self.data_resolution_required,
            "provider_requirements": list(self.provider_requirements),
            "self_overlap_with": list(self.self_overlap_with),
        }


@dataclass
class ValidationResult:
    ok: bool
    is_abstention: bool
    mechanisms: List[Mechanism]
    errors: List[str]


def _iter_strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v)


def _contains_forbidden_key(obj: Any) -> List[str]:
    hits: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            for fk in FORBIDDEN_KEYS:
                # exact key or key token boundary match (avoid 'scoreline' matching 'score')
                if kl == fk or re.search(rf"(^|[_\W]){re.escape(fk)}([_\W]|$)", kl):
                    hits.append(f"forbidden_key:{k}")
            hits.extend(_contains_forbidden_key(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            hits.extend(_contains_forbidden_key(v))
    return hits


def _semantic_numeric_claim(text: str) -> bool:
    return bool(_NUMERIC_CLAIM_RE.search(text or ""))


def validate_response(payload: Dict[str, Any]) -> ValidationResult:
    """Validate a raw LLM response object against the mechanism schema.

    Expected shape:
      {"fixture_id": "...", "mechanisms": [ {...}, ... ]}
    or an abstention:
      {"fixture_id": "...", "abstention": "NO_NOVEL_GROUNDED_MECHANISM", "mechanisms": []}
    """
    errors: List[str] = []

    if not isinstance(payload, dict):
        return ValidationResult(False, False, [], ["response_not_object"])

    # Firewall: forbidden numeric-authority keys anywhere.
    fk_hits = _contains_forbidden_key(payload)
    if fk_hits:
        errors.extend(sorted(set(fk_hits)))

    abstention = payload.get("abstention")
    raw_mechs = payload.get("mechanisms", [])
    is_abstention = abstention == ABSTENTION_TOKEN and (not raw_mechs)

    if abstention is not None and abstention != ABSTENTION_TOKEN:
        errors.append(f"bad_abstention_token:{abstention}")

    mechanisms: List[Mechanism] = []
    if not is_abstention:
        if not isinstance(raw_mechs, list) or len(raw_mechs) == 0:
            errors.append("no_mechanisms_and_no_abstention")
        for i, m in enumerate(raw_mechs):
            if not isinstance(m, dict):
                errors.append(f"mechanism[{i}]_not_object")
                continue
            missing = [f for f in REQUIRED_MECHANISM_FIELDS if f not in m]
            if missing:
                errors.append(f"mechanism[{i}]_missing:{','.join(missing)}")
                continue
            if not isinstance(m["observable_variables"], list) or not m["observable_variables"]:
                errors.append(f"mechanism[{i}]_observable_variables_empty")
            if not isinstance(m["evidence_refs"], list) or not m["evidence_refs"]:
                errors.append(f"mechanism[{i}]_evidence_refs_empty")
            if m.get("data_resolution_required") not in ("match", "half"):
                errors.append(f"mechanism[{i}]_bad_resolution")
            # semantic numeric-claim guard
            for sem in ("mechanism_statement", "conditioning_logic",
                        "expected_relationship_to_test", "why_not_baseline_equivalent"):
                if _semantic_numeric_claim(str(m.get(sem, ""))):
                    errors.append(f"mechanism[{i}]_numeric_claim_in:{sem}")
            try:
                mechanisms.append(Mechanism(
                    mechanism_id_local=str(m["mechanism_id_local"]),
                    mechanism_statement=str(m["mechanism_statement"]),
                    observable_variables=[str(v) for v in m["observable_variables"]],
                    conditioning_logic=str(m["conditioning_logic"]),
                    expected_relationship_to_test=str(m["expected_relationship_to_test"]),
                    why_not_baseline_equivalent=str(m["why_not_baseline_equivalent"]),
                    evidence_refs=[str(v) for v in m["evidence_refs"]],
                    data_resolution_required=str(m["data_resolution_required"]),
                    provider_requirements=[str(v) for v in m["provider_requirements"]],
                    self_overlap_with=[str(v) for v in m.get("self_overlap_with", [])],
                ))
            except Exception as e:  # noqa: BLE001
                errors.append(f"mechanism[{i}]_parse_error:{e}")

    return ValidationResult(
        ok=(len(errors) == 0),
        is_abstention=is_abstention,
        mechanisms=mechanisms,
        errors=errors,
    )


def version_stamp() -> Dict[str, object]:
    return {
        "mechanism_schema_version": MECHANISM_SCHEMA_VERSION,
        "k_mechanisms_per_fixture": K_MECHANISMS_PER_FIXTURE,
        "n_required_fields": len(REQUIRED_MECHANISM_FIELDS),
        "n_forbidden_keys": len(FORBIDDEN_KEYS),
        "abstention_token": ABSTENTION_TOKEN,
        "reads_outcomes": False,
        "asks_llm_for_numbers": False,
    }
