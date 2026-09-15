"""V7.1 confounder design (`v71_confounders_v1`). Section 13.

The frozen per-family adjustment plan is REUSED from V7; what V7.1 adds is a generic,
tested treatment of the design matrix so the rank-deficiency surprise that hit V7 at
execution time cannot recur.

What happened in V7: the confounder plan listed `venue` for most families, but within a
fixture the subject's venue is constant by construction, so the venue column was constant,
the design matrix was singular, and the first families to reach adjustment terminated
`CONFOUNDED_UNRESOLVED` until the executor was patched mid-flight. The fix is generic here:
every column is screened before the solve, degenerate columns are DROPPED WITH A NAMED
REASON, and the reason is carried into the evidence rather than silently absorbed.

Two rules the plan must never break:
  * a confounder that the corpus cannot supply is NOT invented -- it is declared unavailable;
  * a variable that is a CONSEQUENCE of the target process is not adjusted for, because
    conditioning on it would remove the very effect being measured.
"""
from __future__ import annotations

from src.research.hypothesis_v7 import analysis_spec as V7A

CONFOUNDERS_VERSION = "v71_confounders_v2"

ALLOWED = tuple(V7A.ALLOWED_CONFOUNDERS)
PLAN = {k: dict(v) for k, v in V7A.CONFOUNDER_PLAN.items()}
DEFAULT_PLAN = dict(V7A.DEFAULT_PLAN)

#: Corpus availability of each allowed confounder. `False` means the variable is NOT
#: constructible from this corpus; it is declared unavailable rather than approximated.
AVAILABLE = {
    "venue": True,
    "competition": True,
    "opponent_strength": True,
    "opponent_profile": True,
    "team_baseline_quality": True,
    "cards": True,
    "season_regime": True,
    "score_state": False,      # no minute-level or running-score resolution in this corpus
    "formation": False,        # not resolvable per prior match
}

#: Variables that are DOWNSTREAM of the process being measured. Adjusting for one removes
#: part of the effect itself (collider / mediator bias), so they are never eligible even when
#: the corpus could supply them.
NEVER_ADJUST = {
    "score_state": ("running score is a consequence of attacking and defensive output, so "
                    "conditioning on it absorbs the very effect under test"),
}

#: Why a column may be dropped before the solve. Named so the evidence distinguishes
#: "unavailable in this corpus" from "degenerate in this design".
DROPPED_CONSTANT = "DROPPED_CONSTANT_COLUMN"
DROPPED_COLLINEAR = "DROPPED_COLLINEAR_COLUMN"
UNAVAILABLE = "UNAVAILABLE_IN_CORPUS"
EXCLUDED_MEDIATOR = "EXCLUDED_AS_MEDIATOR"

# ---- missing-confounder policy (D15) ---------------------------------------------------
#: FROZEN, OUTCOME-BLIND policy for a required confounder that cannot be constructed for a
#: particular observation ROW (e.g. an opponent with no prior match, so its point-in-time
#: strength is genuinely absent -- NOT zero).
#:
#: The class of bug this closes: V7.1's engine coerced a missing point-in-time confounder to
#: `0.0` (`index.pit_mean(...)[0] or 0.0`). A missing historical confounder is not a value of
#: zero -- coercing it fabricates an observation, biases the adjustment, and additionally
#: makes a genuine measured zero indistinguishable from "no data". A NULL is not a ZERO.
#:
#: The rule, applied identically to every family and every arm:
#:   1. only the confounders the frozen family plan REQUIRES are ever constructed;
#:   2. a required confounder that is absent for a row is represented as `None`, never 0;
#:   3. a row with ANY missing required confounder is EXCLUDED from the adjusted design under
#:      the reason `ROW_MISSING_REQUIRED_CONFOUNDER`, and the exclusion is counted;
#:   4. if excluding those rows drops the cell below the frozen support minimum, the cell
#:      fails as `INSUFFICIENT_SUPPORT_AFTER_MISSING_CONFOUNDER` rather than being adjusted on
#:      a fabricated design.
#: Nothing here reads an outcome; the decision is a function of data population only.
MISSING_CONFOUNDER_POLICY = {
    "policy": "EXCLUDE_ROW_NAMED_REASON",
    "null_is_not_zero": True,
    "only_required_confounders_constructed": True,
    "row_exclusion_reason": "ROW_MISSING_REQUIRED_CONFOUNDER",
    "cell_failure_reason": "INSUFFICIENT_SUPPORT_AFTER_MISSING_CONFOUNDER",
    "fabricates_zero_for_missing": False,
    "reads_outcomes": False,
}
ROW_MISSING_REQUIRED_CONFOUNDER = "ROW_MISSING_REQUIRED_CONFOUNDER"
INSUFFICIENT_AFTER_MISSING = "INSUFFICIENT_SUPPORT_AFTER_MISSING_CONFOUNDER"


def plan_for(research_family: str) -> dict:
    """The frozen adjustment plan for a family, with unavailable and mediator variables
    stripped and the reason recorded. Deterministic; identical for every hypothesis in the
    family, so no per-hypothesis tuning is possible."""
    raw = PLAN.get(research_family, DEFAULT_PLAN)
    keep, removed = [], []
    for c in raw["confounders"]:
        if c in NEVER_ADJUST:
            removed.append({"confounder": c, "reason": EXCLUDED_MEDIATOR,
                            "detail": NEVER_ADJUST[c]})
        elif not AVAILABLE.get(c, False):
            removed.append({"confounder": c, "reason": UNAVAILABLE,
                            "detail": "not constructible from this corpus"})
        else:
            keep.append(c)
    return {"research_family": research_family, "strategy": raw["strategy"],
            "confounders": keep, "removed": removed}


def screen_design(columns: dict, *, tol: float = 1e-12) -> dict:
    """Screen a design matrix before solving. Returns kept columns and named drop reasons.

    `columns` maps a column name to its list of values. Constant columns are dropped first
    (they carry no information and make the normal equations singular); an exactly duplicated
    column is then dropped as collinear. Both are reported, never silently absorbed.
    """
    kept, dropped = {}, []
    seen = {}
    for name, values in columns.items():
        vals = [float(v) for v in values]
        if not vals:
            dropped.append({"column": name, "reason": DROPPED_CONSTANT,
                            "detail": "no observations"})
            continue
        lo, hi = min(vals), max(vals)
        if hi - lo <= tol:
            dropped.append({"column": name, "reason": DROPPED_CONSTANT,
                            "detail": f"constant at {lo}"})
            continue
        key = tuple(round(v, 12) for v in vals)
        if key in seen:
            dropped.append({"column": name, "reason": DROPPED_COLLINEAR,
                            "detail": f"identical to {seen[key]}"})
            continue
        seen[key] = name
        kept[name] = vals
    return {"kept": kept, "dropped": dropped,
            "n_kept": len(kept), "n_dropped": len(dropped),
            "identifiable": bool(kept)}


def version_stamp() -> dict:
    return {"confounders_version": CONFOUNDERS_VERSION,
            "plan_source": V7A.ANALYSIS_VERSION,
            "allowed": list(ALLOWED),
            "availability": dict(AVAILABLE),
            "never_adjust": {k: v for k, v in NEVER_ADJUST.items()},
            "families": sorted(PLAN),
            "degenerate_columns_dropped_with_named_reason": True,
            "missing_confounder_policy": MISSING_CONFOUNDER_POLICY,
            "frozen_by_family_no_per_hypothesis_tuning": True}
