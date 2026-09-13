"""Controlled sample-and-aggregate over k calls (patch §31, §32, §33).

Only after DIAGNOSING instability (repeatability.py) do we consider aggregation. This module
aggregates k identical-input calls into ONE state per mechanism DETERMINISTICALLY, and it
PRESERVES disagreement rather than hiding it (patch §32):

  * status:      if all k agree -> that status. If they disagree, we do NOT silently
                 majority-vote to a confident directional state. Instead:
                   - if the disagreement is only an adjacent ordinal / confidence wobble
                     (max pairwise severity <= 1): take the modal status but DOWNGRADE
                     reliability one step;
                   - if the disagreement is severe (severity >= 2, i.e. substantial strength,
                     directional reversal, or resolved<->uncertain flip): aggregate_status =
                     UNSTABLE and reliability = LOW.
  * confidence:  min (most conservative) confidence across calls, further downgraded on wobble.
  * support_ids / counter_ids: INTERSECTION across calls (only evidence every call agreed on).
  * LLM_INTERPRETATION_STABILITY: a separate metadata field (3/3 same -> STABLE;
    2/3 -> WEAK; all-different -> UNSTABLE). This is NOT an event probability (patch §33) —
    it is a property of the measurement instrument.

Deterministic, pure, no LLM calls. `aggregate_fixture` returns an aggregate state object
plus per-mechanism stability metadata. We also compare single-call vs k-call stability so the
report can decide whether aggregation is worth the cost (patch §31).
"""
from __future__ import annotations
from collections import Counter, defaultdict

from src.research.llm_matchup.hardening import repeatability as REP

CONF_ORDER = ["UNKNOWN", "LOW", "MEDIUM_LOW", "MEDIUM", "MEDIUM_HIGH", "HIGH"]
CONF_RANK = {c: i for i, c in enumerate(["LOW", "MEDIUM_LOW", "MEDIUM", "MEDIUM_HIGH", "HIGH"])}


def _min_confidence(confs: list[str]) -> str:
    ranked = [c for c in confs if c in CONF_RANK]
    if not ranked:
        return "LOW"
    return min(ranked, key=lambda c: CONF_RANK[c])


def _downgrade(conf: str, steps: int = 1) -> str:
    order = ["LOW", "MEDIUM_LOW", "MEDIUM", "MEDIUM_HIGH", "HIGH"]
    if conf not in order:
        return "LOW"
    return order[max(0, order.index(conf) - steps)]


def _worst_severity(states: list[dict]) -> int:
    worst = 0
    for i in range(len(states)):
        for j in range(i + 1, len(states)):
            si, ci = states[i]["status"], states[i]["confidence"]
            sj, cj = states[j]["status"], states[j]["confidence"]
            worst = max(worst, REP.severity(si, ci, sj, cj))
    return worst


def _stability_label(n_present: int, k: int, worst_sev: int) -> str:
    if n_present < k:
        return "UNSTABLE"          # mechanism appeared/disappeared
    if worst_sev == 0:
        return "STABLE"
    if worst_sev <= 1:
        return "WEAK"              # minor wobble
    return "UNSTABLE"


def aggregate_fixture(states_per_call: list[dict]) -> dict:
    """Aggregate k call states into one, preserving disagreement (patch §32, §33)."""
    k = len(states_per_call)
    by_key = defaultdict(list)  # 'side:mechanism' -> list of {status, confidence, support, counter, item}
    for st in states_per_call:
        if not st:
            continue
        for side in ("team_a_states", "team_b_states", "matchup_states"):
            for it in st.get(side, []):
                key = f"{side}:{it['mechanism']}"
                by_key[key].append({
                    "status": it.get("level") or it.get("assessment"),
                    "confidence": it.get("confidence"),
                    "support": set(it.get("evidence_ids", []) or it.get("supporting_evidence_ids", []) or []),
                    "counter": set(it.get("counter_evidence_ids", []) or []),
                    "side": side, "mechanism": it["mechanism"],
                })

    agg_states = {"team_a_states": [], "team_b_states": [], "matchup_states": []}
    meta = []
    for key, calls in sorted(by_key.items()):
        n_present = len(calls)
        statuses = [c["status"] for c in calls]
        worst_sev = _worst_severity(calls)
        stability = _stability_label(n_present, k, worst_sev)
        modal_status = Counter(statuses).most_common(1)[0][0]
        min_conf = _min_confidence([c["confidence"] for c in calls])

        if n_present == k and worst_sev == 0:
            agg_status, agg_conf = modal_status, min_conf
        elif worst_sev <= 1 and n_present == k:
            agg_status, agg_conf = modal_status, _downgrade(min_conf, 1)  # wobble -> downgrade
        else:
            agg_status, agg_conf = "UNSTABLE", "LOW"                      # severe -> preserve as UNSTABLE

        side = calls[0]["side"]
        mech = calls[0]["mechanism"]
        support = set.intersection(*[c["support"] for c in calls]) if calls else set()
        counter = set.intersection(*[c["counter"] for c in calls]) if calls else set()
        agg_states[side].append({
            "mechanism": mech, "aggregate_status": agg_status, "aggregate_confidence": agg_conf,
            "llm_interpretation_stability": stability,
            "support_ids_intersection": sorted(support), "counter_ids_intersection": sorted(counter),
            "n_present": n_present, "k": k, "worst_severity": worst_sev,
        })
        meta.append({"mechanism_key": key, "stability": stability, "worst_severity": worst_sev,
                     "aggregate_status": agg_status, "n_present": n_present, "k": k})
    return {"aggregate_states": agg_states, "meta": meta}


def compare_single_vs_aggregate(fixtures_states: dict) -> dict:
    """Compare single-call stability vs k-call aggregate stability across fixtures (patch §31).

    fixtures_states: {fixture_id -> list_of_k_states}. For each fixture we compute the aggregate
    and count how many mechanisms end up STABLE / WEAK / UNSTABLE. We also report how many
    mechanisms a naive single call (call 0) would have presented as confident directional
    states that the aggregate correctly demotes to UNSTABLE (the value aggregation adds)."""
    total = Counter()
    demoted = 0
    n_mech = 0
    for fx, states in fixtures_states.items():
        agg = aggregate_fixture(states)
        for m in agg["meta"]:
            total[m["stability"]] += 1
            n_mech += 1
            if m["aggregate_status"] == "UNSTABLE":
                demoted += 1
    return {
        "n_mechanisms": n_mech,
        "stability_counts": dict(total),
        "n_demoted_to_unstable": demoted,
        "frac_stable": round(total.get("STABLE", 0) / max(n_mech, 1), 4),
        "frac_unstable": round(total.get("UNSTABLE", 0) / max(n_mech, 1), 4),
    }
