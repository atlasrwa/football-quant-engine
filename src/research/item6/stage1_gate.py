"""STAGE1_GATE_V1  (`item6_stage1_gate_v1`).

The frozen, preregistered HARD PASS/FAIL gate for Stage 1. Thresholds are set BEFORE any
live generation and BEFORE any output is seen. They are derived from the prior-corpus audit
used as a HISTORICAL REFERENCE (not as an outcome to optimize against), and are chosen to
require MATERIALLY BETTER generation than the prior corpus — not merely non-zero novelty.

Prior-corpus reference metrics (researcher knowledge, from the audit summarized in the
Item 6 mission and the V3 final report):
  - semantic duplicate rate               ~0.80
  - mirror-like / baseline-equivalent      ~0.51 (77/150 mirror; 46/150 one repeated concept)
  - novel hypothesis FAMILIES              0
  - genuine >1-dimension joint conditions  0
  - meaningful two-condition hypotheses    ~1/112 (0.009) in V3
  - nonlinearities / thresholds            0
  - half-state / game-state constructions  0

PRIMARY gates (all must pass):
  P1 BASELINE_EQUIVALENT_RATE       <= 0.60   (below prior ~0.51+ mirror-dominance regime once
                                               the *full* corpus of 5 mechanisms/fixture is
                                               scored; a generator still emitting mostly
                                               baseline-equivalent ideas fails)
  P2 SEMANTIC_DUPLICATE_RATE        <= 0.50   (materially below prior ~0.80)
  P3 NOVEL_MEASURABLE_FAMILY_RATE   >= 0.30   (>=30% of non-abstaining FIXTURES yield >=1 novel
                                               measurable family; prior = 0)
  P4 NEW_FAMILY_COUNT               >= 3      (>=3 DISTINCT novel families corpus-wide; prior = 0)
  P5 MULTIVARIABLE_INTERACTION_RATE >= 0.20   (materially >0; prior ~0.009)
  P6 FORMALIZATION_SURVIVAL_RATE    >= 0.50   (>=half of non-baseline-equivalent grounded ideas
                                               keep their value through formalization)

DIAGNOSTIC gates (reported, NOT pass/fail-determining):
  D_GROUNDING_PASS_RATE             >= 0.90
  D_FALSIFIABILITY_PASS_RATE        >= 0.80
  D_ABSTENTION_RATE                 reported (high abstention is itself informative)

Rationale for thresholds being demanding but achievable:
  The experiment must be able to FAIL even if some prose sounds excellent. A generator that
  merely rephrases mirrors will fail P1/P2/P3/P4/P5. A generator that produces one brilliant
  anecdote but is otherwise baseline will fail P3/P4 (which require repeatable, corpus-wide
  expansion). Thresholds are NOT set to the prior audit values + epsilon; they demand a
  regime change, which is what "research-space expansion" means.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .stage1_metrics import Stage1Endpoints

STAGE1_GATE_VERSION = "item6_stage1_gate_v1"

# Frozen thresholds (do not edit after freeze).
BASELINE_EQUIVALENT_RATE_MAX = 0.60
SEMANTIC_DUPLICATE_RATE_MAX = 0.50
NOVEL_MEASURABLE_FAMILY_RATE_MIN = 0.30
NEW_FAMILY_COUNT_MIN = 3
MULTIVARIABLE_INTERACTION_RATE_MIN = 0.20
FORMALIZATION_SURVIVAL_RATE_MIN = 0.50

# Diagnostic (reported, non-gating)
GROUNDING_PASS_RATE_MIN = 0.90
FALSIFIABILITY_PASS_RATE_MIN = 0.80

PRIOR_CORPUS_REFERENCE = {
    "semantic_duplicate_rate": 0.80,
    "baseline_equivalent_rate_like": 0.51,
    "novel_family_count": 0,
    "meaningful_two_condition_rate": 0.009,
    "multivariable_interaction_rate": 0.009,
    "nonlinearity_count": 0,
    "half_state_count": 0,
}


@dataclass
class GateResult:
    passed: bool
    primary_checks: Dict[str, Dict[str, object]]     # name -> {value, threshold, op, pass}
    diagnostic_checks: Dict[str, Dict[str, object]]
    failed_primary: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "passed": self.passed,
            "primary_checks": self.primary_checks,
            "diagnostic_checks": self.diagnostic_checks,
            "failed_primary": self.failed_primary,
        }


def _chk(value, threshold, op) -> Dict[str, object]:
    if op == "<=":
        ok = value <= threshold
    elif op == ">=":
        ok = value >= threshold
    else:  # pragma: no cover
        raise ValueError(op)
    return {"value": value, "threshold": threshold, "op": op, "pass": bool(ok)}


def evaluate_gate(ep: Stage1Endpoints) -> GateResult:
    primary = {
        "BASELINE_EQUIVALENT_RATE": _chk(ep.baseline_equivalent_rate, BASELINE_EQUIVALENT_RATE_MAX, "<="),
        "SEMANTIC_DUPLICATE_RATE": _chk(ep.semantic_duplicate_rate, SEMANTIC_DUPLICATE_RATE_MAX, "<="),
        "NOVEL_MEASURABLE_FAMILY_RATE": _chk(ep.novel_measurable_family_rate, NOVEL_MEASURABLE_FAMILY_RATE_MIN, ">="),
        "NEW_FAMILY_COUNT": _chk(ep.new_family_count, NEW_FAMILY_COUNT_MIN, ">="),
        "MULTIVARIABLE_INTERACTION_RATE": _chk(ep.multivariable_interaction_rate, MULTIVARIABLE_INTERACTION_RATE_MIN, ">="),
        "FORMALIZATION_SURVIVAL_RATE": _chk(ep.formalization_survival_rate, FORMALIZATION_SURVIVAL_RATE_MIN, ">="),
    }
    diagnostic = {
        "GROUNDING_PASS_RATE": _chk(ep.grounding_pass_rate, GROUNDING_PASS_RATE_MIN, ">="),
        "FALSIFIABILITY_PASS_RATE": _chk(ep.falsifiability_pass_rate, FALSIFIABILITY_PASS_RATE_MIN, ">="),
        "ABSTENTION_RATE": {"value": ep.abstention_rate, "threshold": None, "op": "report", "pass": True},
    }
    failed = [k for k, v in primary.items() if not v["pass"]]
    return GateResult(passed=(len(failed) == 0),
                      primary_checks=primary,
                      diagnostic_checks=diagnostic,
                      failed_primary=failed)


def version_stamp() -> Dict[str, object]:
    return {
        "stage1_gate_version": STAGE1_GATE_VERSION,
        "primary_thresholds": {
            "BASELINE_EQUIVALENT_RATE_MAX": BASELINE_EQUIVALENT_RATE_MAX,
            "SEMANTIC_DUPLICATE_RATE_MAX": SEMANTIC_DUPLICATE_RATE_MAX,
            "NOVEL_MEASURABLE_FAMILY_RATE_MIN": NOVEL_MEASURABLE_FAMILY_RATE_MIN,
            "NEW_FAMILY_COUNT_MIN": NEW_FAMILY_COUNT_MIN,
            "MULTIVARIABLE_INTERACTION_RATE_MIN": MULTIVARIABLE_INTERACTION_RATE_MIN,
            "FORMALIZATION_SURVIVAL_RATE_MIN": FORMALIZATION_SURVIVAL_RATE_MIN,
        },
        "diagnostic_thresholds": {
            "GROUNDING_PASS_RATE_MIN": GROUNDING_PASS_RATE_MIN,
            "FALSIFIABILITY_PASS_RATE_MIN": FALSIFIABILITY_PASS_RATE_MIN,
        },
        "prior_corpus_reference": PRIOR_CORPUS_REFERENCE,
        "reads_oos": False,
    }
