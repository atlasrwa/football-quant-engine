"""Field-level repeatability + deterministic semantic severity (patch §4, §5).

Phase B measured a single aggregate `rep_d` (fraction of mechanisms whose (level, confidence)
tuple changed between two calls). That hides WHERE and HOW BADLY identical calls disagree
(patch §4). This module replaces it with:

  1. FIELD-LEVEL agreement. For the SAME packet called k times, for each mechanism present in
     >=2 calls, we measure agreement SEPARATELY for:
        - mechanism_presence   (did the mechanism appear at all in each call?)
        - status               (level for team-states / assessment for matchup-states)
        - strength             (the ordinal magnitude of the level/assessment)
        - confidence           (reliability of the assessment)
        - support_ids          (set of supporting evidence ids)
        - counter_ids          (set of counter-evidence ids)
        - unknown_flag         (is the assessment UNKNOWN?)
        - conflicted_flag      (is the assessment CONFLICTED?)
        - limitations          (set of uncertainty_factors / reason codes)

  2. SEMANTIC SEVERITY (patch §5). A deterministic 0-4 ladder over a PAIR of assessments of
     the same mechanism, so a HIGH->MEDIUM_HIGH confidence wobble is NOT treated as severe as
     a SUPPORTED->CONFLICTED reversal:
        0 = identical (status + strength + confidence all equal)
        1 = adjacent ordinal difference (strength differs by exactly 1 OR only confidence
            differs by <=1 step)
        2 = substantial strength difference (strength differs by >=2, same polarity/known)
        3 = status change (a directional/level category change that is not a full reversal;
            e.g. LOW<->HIGH, A_ADVANTAGE<->B_ADVANTAGE)
        4 = SUPPORTED <-> CONFLICTED / UNKNOWN reversal (the model flips between "resolved
            with a directional finding" and "cannot resolve")

Pure, deterministic, no LLM calls, no sklearn. Unit-testable in isolation.
"""
from __future__ import annotations
from collections import defaultdict

from src.research.llm_matchup import ontology as ONT

# Ordinal maps. Level and advantage share a 0..4 magnitude scale so severity is comparable.
LEVEL_ORD = {"VERY_LOW": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "VERY_HIGH": 4}
ADV_ORD = {"STRONG_B_ADVANTAGE": 0, "B_ADVANTAGE": 1, "NEUTRAL": 2,
           "A_ADVANTAGE": 3, "STRONG_A_ADVANTAGE": 4}
CONF_ORD = {"LOW": 0, "MEDIUM_LOW": 1, "MEDIUM": 2, "MEDIUM_HIGH": 3, "HIGH": 4, "UNKNOWN": 0}

# "resolved as uncertain" statuses — flipping between these and a directional status is the
# most severe disagreement (level 4).
UNCERTAIN = {"UNKNOWN", "CONFLICTED"}


def _status(st: dict) -> str:
    return st.get("level") or st.get("assessment")


def _support_ids(st: dict) -> set:
    return set(st.get("evidence_ids", []) or []) | set(st.get("supporting_evidence_ids", []) or [])


def _counter_ids(st: dict) -> set:
    return set(st.get("counter_evidence_ids", []) or [])


def _strength_ord(status: str):
    """Magnitude 0..4 for a directional/level status, or None for uncertain statuses."""
    if status in LEVEL_ORD:
        return LEVEL_ORD[status]
    if status in ADV_ORD:
        return ADV_ORD[status]
    return None  # UNKNOWN / CONFLICTED


def _is_advantage(status: str) -> bool:
    return status in ADV_ORD


def severity(status_a: str, conf_a: str, status_b: str, conf_b: str) -> int:
    """Deterministic 0-4 semantic severity for a pair of assessments (patch §5)."""
    a_unc = status_a in UNCERTAIN
    b_unc = status_b in UNCERTAIN
    # level 4: one side resolved directionally, the other is uncertain (SUPPORTED<->UNKNOWN/
    # CONFLICTED), OR a UNKNOWN<->CONFLICTED flip (both "cannot resolve" but different kind
    # of non-resolution is still a status reversal of the resolved/uncertain contract).
    if a_unc != b_unc:
        return 4
    if a_unc and b_unc:
        # both uncertain: identical -> 0, else UNKNOWN vs CONFLICTED -> 4 (reversal of kind)
        return 0 if status_a == status_b else 4

    # both directional/level: compare magnitude.
    oa, ob = _strength_ord(status_a), _strength_ord(status_b)
    if oa is None or ob is None:  # defensive; shouldn't happen here
        return 3 if status_a != status_b else 0
    dmag = abs(oa - ob)
    # A directional REVERSAL only exists on the ADVANTAGE scale, where NEUTRAL=2 is the
    # centre and the two sides mean "A ahead" vs "B ahead". On the LEVEL scale (VERY_LOW..
    # VERY_HIGH) there is no polarity — a big jump is a large magnitude difference, not a
    # reversal.
    polarity_change = _is_advantage(status_a) and _is_advantage(status_b) \
        and ((oa - 2) * (ob - 2) < 0)
    if status_a == status_b:
        # same status: only confidence may differ.
        dc = abs(CONF_ORD.get(conf_a, 0) - CONF_ORD.get(conf_b, 0))
        return 0 if dc == 0 else 1  # confidence wobble is level 1 at most
    if polarity_change:
        return 3  # directional reversal (A_ADVANTAGE <-> B_ADVANTAGE), not resolved/uncertain
    if dmag >= 2:
        return 2  # substantial strength difference
    # dmag == 1 (adjacent), different status label
    return 1


def _collect(states_per_call: list[dict]) -> dict:
    """Index states by mechanism key across calls. key = 'side:mechanism'."""
    by_key = defaultdict(dict)  # key -> {call_index -> state}
    for ci, state in enumerate(states_per_call):
        if not state:
            continue
        for side in ("team_a_states", "team_b_states", "matchup_states"):
            for st in state.get(side, []):
                key = f"{side}:{st['mechanism']}"
                by_key[key][ci] = st
    return by_key


def field_level_agreement(states_per_call: list[dict]) -> list[dict]:
    """Per-mechanism field-level agreement across k calls. One row per mechanism key that
    appears in >=1 call. Returns rows with agreement flags + worst pairwise severity."""
    k = len(states_per_call)
    by_key = _collect(states_per_call)
    rows = []
    for key, calls in sorted(by_key.items()):
        present = sorted(calls.keys())
        n_present = len(present)
        statuses = [_status(calls[c]) for c in present]
        confs = [calls[c].get("confidence") for c in present]
        supports = [_support_ids(calls[c]) for c in present]
        counters = [_counter_ids(calls[c]) for c in present]
        limits = [frozenset(calls[c].get("uncertainty_factors", []) or []) for c in present]
        searches = [calls[c].get("counter_evidence_search") for c in present]

        # worst pairwise semantic severity across all present-call pairs
        worst_sev = 0
        for i in range(n_present):
            for j in range(i + 1, n_present):
                worst_sev = max(worst_sev,
                                severity(statuses[i], confs[i], statuses[j], confs[j]))

        rows.append({
            "mechanism_key": key,
            "k_calls": k,
            "n_present": n_present,
            "presence_stable": n_present == k,
            "status_agree": len(set(statuses)) == 1,
            "strength_agree": len(set(_strength_ord(s) for s in statuses)) == 1,
            "confidence_agree": len(set(confs)) == 1,
            "support_ids_agree": all(supports[0] == s for s in supports),
            "counter_ids_agree": all(counters[0] == c for c in counters),
            "unknown_agree": len(set(s == "UNKNOWN" for s in statuses)) == 1,
            "conflicted_agree": len(set(s == "CONFLICTED" for s in statuses)) == 1,
            "limitations_agree": all(limits[0] == l for l in limits),
            "counter_search_agree": len(set(searches)) == 1,
            "worst_severity": worst_sev,
            "statuses": "|".join(str(s) for s in statuses),
            "confidences": "|".join(str(c) for c in confs),
        })
    return rows


def summarize(field_rows: list[dict]) -> dict:
    """Aggregate field-level rows into headline repeatability statistics (patch §4)."""
    n = len(field_rows) or 1
    def frac(flag):
        return round(sum(1 for r in field_rows if r[flag]) / n, 4)
    sev_hist = defaultdict(int)
    for r in field_rows:
        sev_hist[r["worst_severity"]] += 1
    return {
        "n_mechanism_keys": len(field_rows),
        "presence_stable_frac": frac("presence_stable"),
        "status_agree_frac": frac("status_agree"),
        "strength_agree_frac": frac("strength_agree"),
        "confidence_agree_frac": frac("confidence_agree"),
        "support_ids_agree_frac": frac("support_ids_agree"),
        "counter_ids_agree_frac": frac("counter_ids_agree"),
        "unknown_agree_frac": frac("unknown_agree"),
        "conflicted_agree_frac": frac("conflicted_agree"),
        "limitations_agree_frac": frac("limitations_agree"),
        # severity distribution: how many mechanisms had worst severity 0..4.
        "severity_hist": {str(s): sev_hist.get(s, 0) for s in range(5)},
        # a mechanism is "semantically stable" if worst severity <= 1 (identical or a mere
        # adjacent/confidence wobble). Severe (>=3) means status/reversal disagreement.
        "semantically_stable_frac": round(
            sum(1 for r in field_rows if r["worst_severity"] <= 1) / n, 4),
        "severe_disagreement_frac": round(
            sum(1 for r in field_rows if r["worst_severity"] >= 3) / n, 4),
    }
