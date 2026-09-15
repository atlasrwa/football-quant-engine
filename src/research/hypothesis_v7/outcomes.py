"""V7 predefined outcome classes + primary endpoints (`v7_outcomes_v1`). Phases 18, 19.

Terminal states a canonical hypothesis may reach. Defined BEFORE any effect is measured so no
result is forced into PASS/FAIL when the data cannot support the distinction. The primary
endpoints are a multi-dimensional profile, NOT "percentage that pass".
"""
from __future__ import annotations

OUTCOMES_VERSION = "v7_outcomes_v1"

TERMINAL_STATES = (
    "UNMEASURABLE",              # provider/temporal/field/compiler gate failed
    "INSUFFICIENT_SUPPORT",      # support rules not met
    "TAUTOLOGICAL",              # comparator degenerate
    "CONFOUNDED_UNRESOLVED",     # confounding cannot be reasonably adjusted
    "HISTORICAL_EFFECT_ONLY",    # development-window effect, never confirmed OOS
    "OOS_DIRECTION_UNSTABLE",    # sign flips across folds
    "OOS_NO_EFFECT",             # OOS effect indistinguishable from zero (a VALID result)
    "OOS_FAIL",                  # large in-sample, collapses OOS
    "OOS_SURVIVES",              # direction-stable, FDR-significant, non-trivial OOS
    "CANDIDATE_FEATURE_ELIGIBLE",  # OOS_SURVIVES + deterministic feature spec computable
)

# the primary V7 endpoints (Phase 19). None is "percentage pass" alone.
PRIMARY_ENDPOINTS = (
    "measurability_rate",
    "adequate_support_rate",
    "confounder_survival_rate",
    "oos_survival_rate",
    "effect_direction_stability",
    "fold_stability",
    "competition_stability",
    "shrinkage_behavior",
    "failure_mode_composition",
)

# the headline scientific comparison (Phase 19/20): is the OOS-stable-relationship rate/
# strength of V6.1 hypotheses above a frozen benchmark, and does the RESEARCH arm exceed the
# BASE arm on the matched, verbosity-neutral endpoint?
PRIMARY_SCIENTIFIC_QUESTION = (
    "Do V6.1-qualified hypotheses yield OOS-stable, PIT-safe, measurable relationships at a "
    "rate/strength exceeding the frozen control benchmark, and does the richer-evidence "
    "RESEARCH arm exceed the BASE arm on the matched fixture/family/metric endpoint?")

# legitimate high-attrition outcomes are explicitly acceptable.
ACCEPTABLE_NULL_RESULTS = (
    "most hypotheses UNMEASURABLE",
    "effects shrink toward zero",
    "historical relationships disappear OOS",
    "Base and Research perform similarly",
    "zero candidate features survive",
)


def version_stamp() -> dict:
    return {"outcomes_version": OUTCOMES_VERSION,
            "terminal_states": list(TERMINAL_STATES),
            "primary_endpoints": list(PRIMARY_ENDPOINTS),
            "primary_scientific_question": PRIMARY_SCIENTIFIC_QUESTION,
            "acceptable_null_results": list(ACCEPTABLE_NULL_RESULTS),
            "pass_fail_forced": False,
            "ends_at": "CANDIDATE_FEATURE_ELIGIBLE (no model promotion in V7)"}
