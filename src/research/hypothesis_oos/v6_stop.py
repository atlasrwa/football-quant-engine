"""Stop rules, gated on evidence DIVERSITY (`v6_stop_v1`). §7, §8.

    "No model-behavior rate stop may become eligible until a minimum evidence base is
     reached. ... This is not to make the experiment finish. It is to prevent one fixture
     from representing the entire treatment."

WHAT V5A.2'S RULE ACTUALLY MEASURED
------------------------------------
`v5a2_evaluator.classify_stop` guarded its rate rule on a CALL COUNT alone:

    if n_calls >= MIN_CALLS_BEFORE_RATE_STOP:        # 6
        rate = n_model_schema_invalid / n_calls
        if rate > MODEL_SCHEMA_INVALID_RATE_STOP:    # 0.30

6 calls is a diversity claim only if the first 6 calls are diverse, and under the
fixture-major order they were all one fixture. The rule fired at 2/6, and the 2 were the
only two research-arm calls in the run, both on that one fixture. It halted a ten-fixture
experiment on n=1 fixture.

A count is not a sample. So V6 gates every model-behaviour rate rule on three conditions at
once, ALL of which must hold before the rule is even evaluated:

    >= MIN_STOP_FIXTURES distinct fixtures observed
    >= MIN_STOP_VALID_CALLS_PER_ARM non-fatal calls in EACH arm
    >= MIN_CALLS_BEFORE_RATE_STOP calls charged

`v6_schedule.freeze_assertions` then proves the frozen sequence REACHES that eligibility
without any fixture dominating the prefix, and refuses to freeze a sequence that does not.
The two halves have to agree: an eligibility rule the schedule cannot satisfy would either
never fire or fire on a prefix that is not diverse.

PER-CATEGORY NUMERATORS (§8)
-----------------------------
V5A.2 had ONE model rate rule whose numerator was `failure_class == MODEL_SCHEMA_INVALID`,
a field `validator_v4` also stamps on firewall violations. The rule that fired was named
for schema invalidity and fired on zero schema-invalid responses.

V6 has one rule per category, each reading its OWN count from the §8 enum, and each
naming the category in its rule id. A halt now says what halted it.

RATES ARE PER HYPOTHESIS, NOT PER RESPONSE
-------------------------------------------
Under hypothesis-level adjudication a response is no longer pass/fail, so a
"response-invalid rate" has nothing to count. The model-behaviour rules therefore run on
the hypothesis denominator -- the thing that is now actually adjudicated. The one exception
is RESPONSE_PARSE_FATAL, which is a response-level event by definition and keeps a
response-level rule.

ZERO SPEND.
"""
from __future__ import annotations

from src.research.hypothesis_oos import v6_classes as K

STOP_VERSION = "v6_stop_v1"

# ----------------------------------------------------------------------------------------
# ELIGIBILITY (§7). No model-behaviour rate rule is evaluated until all three hold.
# ----------------------------------------------------------------------------------------
#: §7's floor is 3 distinct fixtures. Taken as-is: the frozen sequence reaches 3 fixtures at
#: call 6, and raising it further would delay every rate protection for no gain in
#: diversity that the "no fixture dominates" assertion does not already provide.
MIN_STOP_FIXTURES = 3
#: §7's floor is 2 valid calls from each arm. Taken as-is.
MIN_STOP_VALID_CALLS_PER_ARM = 2
#: Carried forward from V5A.2 unchanged, now as one condition of three rather than the only
#: one. Under the V6 round-robin, call 6 is fixture 3's pair -- so the three conditions
#: become satisfiable at the same call, by construction rather than by coincidence.
MIN_CALLS_BEFORE_RATE_STOP = 6

# ----------------------------------------------------------------------------------------
# THRESHOLDS. Per category, on the hypothesis denominator.
#
# 0.30 is V5A.2's threshold, carried forward unchanged for the discipline categories. It was
# fixed before V5A.1 ran and is therefore not reachable by anything V5A.1 or V5A.2 revealed,
# which is the property that makes carrying it forward legitimate rather than convenient.
#
# It is applied SEPARATELY per category rather than to a pooled failure rate. Pooling would
# be strictly stricter -- any two categories at 0.2 each would halt a run neither of them
# condemns -- and V6 expects a substantial availability-violation rate in the BASE arm by
# construction (its packet exposes zero conditionable terms, and §18 says to record that
# rather than to treat it as pathology).
# ----------------------------------------------------------------------------------------
FIREWALL_VIOLATION_RATE_STOP = 0.30
NUMERIC_CONTRACT_VIOLATION_RATE_STOP = 0.30
GROUNDING_VIOLATION_RATE_STOP = 0.30
SCHEMA_INVALID_RATE_STOP = 0.30
#: Response-level, and the only rule that is: a fatal response yields no hypotheses, so
#: there is no hypothesis denominator for it to have.
RESPONSE_PARSE_FATAL_RATE_STOP = 0.30

#: DELIBERATELY ABSENT: an availability-violation stop rule. The base arm's packet declares
#: zero conditionable terms, so every conditioned hypothesis is inadmissible there by
#: construction -- V5A.2 observed 6, 12, 5, 12 of 12 across four base calls. A rate rule on
#: that category would halt the run on the arm definition §2 preserves, not on model
#: behaviour. The category is COUNTED and reported (§20) and enters the discipline deltas;
#: it just does not stop the run.
AVAILABILITY_VIOLATION_HAS_STOP_RULE = False

#: Our own defects. Expected to be ZERO; the first one halts rather than being averaged in.
INFRASTRUCTURE_FAILURE_STOP_N = 1
CONSECUTIVE_TRANSPORT_FAILURE_STOP_N = 3

CLASS_RATE_RULES = (
    ("V6_STOP_MODEL_FIREWALL_VIOLATION_RATE", K.MODEL_FIREWALL_VIOLATION,
     FIREWALL_VIOLATION_RATE_STOP),
    ("V6_STOP_MODEL_NUMERIC_CONTRACT_VIOLATION_RATE", K.MODEL_NUMERIC_CONTRACT_VIOLATION,
     NUMERIC_CONTRACT_VIOLATION_RATE_STOP),
    ("V6_STOP_MODEL_GROUNDING_VIOLATION_RATE", K.MODEL_GROUNDING_VIOLATION,
     GROUNDING_VIOLATION_RATE_STOP),
    ("V6_STOP_MODEL_SCHEMA_INVALID_RATE", K.MODEL_SCHEMA_INVALID,
     SCHEMA_INVALID_RATE_STOP),
)


def eligibility(n_calls_charged: int, fixtures_observed, valid_calls_per_arm: dict) -> dict:
    """Are the §7 minimums met? Returns the decision AND why, always."""
    fixtures = sorted(set(fixtures_observed or ()))
    per_arm = dict(valid_calls_per_arm or {})
    unmet = []
    if len(fixtures) < MIN_STOP_FIXTURES:
        unmet.append(f"only {len(fixtures)} distinct fixture(s) observed; "
                     f"need {MIN_STOP_FIXTURES}")
    for arm in ("base", "research"):
        if per_arm.get(arm, 0) < MIN_STOP_VALID_CALLS_PER_ARM:
            unmet.append(f"{arm} arm has {per_arm.get(arm, 0)} valid call(s); "
                         f"need {MIN_STOP_VALID_CALLS_PER_ARM}")
    if n_calls_charged < MIN_CALLS_BEFORE_RATE_STOP:
        unmet.append(f"{n_calls_charged} call(s) charged; "
                     f"need {MIN_CALLS_BEFORE_RATE_STOP}")
    return {"eligible": not unmet, "unmet": unmet,
            "n_calls_charged": n_calls_charged,
            "n_distinct_fixtures": len(fixtures), "fixtures": fixtures,
            "valid_calls_per_arm": per_arm,
            "minimums": {"distinct_fixtures": MIN_STOP_FIXTURES,
                         "valid_calls_per_arm": MIN_STOP_VALID_CALLS_PER_ARM,
                         "calls_charged": MIN_CALLS_BEFORE_RATE_STOP}}


def classify_stop(*, n_calls_charged: int, fixtures_observed, valid_calls_per_arm: dict,
                  class_counts: dict, n_hypotheses_adjudicated: int,
                  n_responses_fatal: int, n_infrastructure_failures: int,
                  n_consecutive_transport_failures: int,
                  spend_usd: float, ceiling_usd: float) -> dict:
    """Every stop rule, evaluated together. Returns the decision and the full audit trail.

    APPARATUS rules are evaluated ALWAYS and are NOT diversity-gated: our own defect does
    not become more real with more fixtures, and the correct response to the first one is
    to halt at once. Only MODEL-behaviour rate rules wait for §7's evidence base.
    """
    fired: list = []
    evaluated: list = []

    if n_infrastructure_failures >= INFRASTRUCTURE_FAILURE_STOP_N:
        fired.append({"rule": "V6_STOP_INFRASTRUCTURE_FAILURE", "class": "APPARATUS",
                      "detail": f"{n_infrastructure_failures} apparatus failure(s); "
                                f"expected 0"})
    if n_consecutive_transport_failures >= CONSECUTIVE_TRANSPORT_FAILURE_STOP_N:
        fired.append({"rule": "V6_STOP_TRANSPORT", "class": "APPARATUS",
                      "detail": f"{n_consecutive_transport_failures} consecutive transport "
                                f"failures"})
    if spend_usd > ceiling_usd:
        fired.append({"rule": "V6_STOP_COST_CEILING", "class": "APPARATUS",
                      "detail": f"${spend_usd:.4f} > ${ceiling_usd:.4f}"})

    elig = eligibility(n_calls_charged, fixtures_observed, valid_calls_per_arm)
    if elig["eligible"]:
        for rule_id, cls, threshold in CLASS_RATE_RULES:
            n = (class_counts or {}).get(cls, 0)
            denom = n_hypotheses_adjudicated
            rate = (n / denom) if denom else 0.0
            evaluated.append({"rule": rule_id, "class": cls, "n": n, "denominator": denom,
                              "rate": round(rate, 6), "threshold": threshold})
            if denom and rate > threshold:
                fired.append({"rule": rule_id, "class": "MODEL",
                              "detail": f"{cls}: {n}/{denom} = {rate:.3f} > {threshold}"})
        r = (n_responses_fatal / n_calls_charged) if n_calls_charged else 0.0
        evaluated.append({"rule": "V6_STOP_RESPONSE_PARSE_FATAL_RATE",
                          "class": K.RESPONSE_PARSE_FATAL, "n": n_responses_fatal,
                          "denominator": n_calls_charged, "rate": round(r, 6),
                          "threshold": RESPONSE_PARSE_FATAL_RATE_STOP})
        if n_calls_charged and r > RESPONSE_PARSE_FATAL_RATE_STOP:
            fired.append({"rule": "V6_STOP_RESPONSE_PARSE_FATAL_RATE", "class": "MODEL",
                          "detail": f"{n_responses_fatal}/{n_calls_charged} = {r:.3f} > "
                                    f"{RESPONSE_PARSE_FATAL_RATE_STOP}"})

    return {"fired": fired, "stop": bool(fired), "eligibility": elig,
            "rules_evaluated": evaluated,
            "model_rules_gated": not elig["eligible"]}


def version_stamp() -> dict:
    return {"stop_version": STOP_VERSION,
            "min_stop_fixtures": MIN_STOP_FIXTURES,
            "min_stop_valid_calls_per_arm": MIN_STOP_VALID_CALLS_PER_ARM,
            "min_calls_before_rate_stop": MIN_CALLS_BEFORE_RATE_STOP,
            "class_rate_rules": [{"rule": r, "class": c, "threshold": t}
                                 for r, c, t in CLASS_RATE_RULES],
            "response_parse_fatal_rate_stop": RESPONSE_PARSE_FATAL_RATE_STOP,
            "availability_violation_has_stop_rule": AVAILABILITY_VIOLATION_HAS_STOP_RULE,
            "infrastructure_failure_stop_n": INFRASTRUCTURE_FAILURE_STOP_N,
            "consecutive_transport_failure_stop_n": CONSECUTIVE_TRANSPORT_FAILURE_STOP_N,
            "model_rate_rules_are_diversity_gated": True,
            "apparatus_rules_are_diversity_gated": False,
            "rate_denominator": "hypotheses adjudicated (response-level only for "
                                "RESPONSE_PARSE_FATAL)"}
