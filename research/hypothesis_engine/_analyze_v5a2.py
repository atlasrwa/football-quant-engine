"""Run the FROZEN V5A.2 evaluator exactly once over the completed immutable response set.

ZERO SPEND. This is a DRIVER. Every scoring rule, threshold, classifier and gate lives in
`v5a2_evaluator.py`, which was hashed and frozen BEFORE the first paid call. Nothing here
defines, adjusts or reweights a metric.

WRITTEN AND HASHED BEFORE THE FIRST PAID CALL
---------------------------------------------
The frozen evaluator supplies the metrics and the gates, but an aggregation layer still has
to decide WHICH calls feed WHICH gate. Deciding that after seeing 38 responses is exactly
the degree of freedom a preregistration exists to remove, so the choices are made here, in
advance, and the file is hashed alongside the preregistered modules.

THE FOUR PRE-COMMITTED AGGREGATION CHOICES
------------------------------------------
A1. VALID_MODEL_RESPONSE means: `score_response` parsed the tool payload, validator_v4
    accepted the whole response, and no apparatus defect was recorded. Concretely
    `parsed and whole_response_failure is None and failure_class is None`. Everything else
    partitions into the four named non-valid classes (see `classify_outcome`), which is the
    taxonomy the authorization requires be kept separate.

A2. The paired comparison uses PRIMARY calls only (`rep == 0`), mirroring V5A.1's
    `replicate == 0`. A fixture contributes a pair only when BOTH arms produced a VALID
    primary response -- the evaluator's own gate text is "fixtures have a valid response in
    BOTH arms", so the set fed to `verdict()` and the count fed to `evaluability()` are the
    same set. A pair where one side never produced hypotheses is not a measurement of the
    other side.

A3. `min_valid_responses_per_arm` counts VALID responses among the 10 PRIMARY calls of that
    arm (max 10, gate 8). Counting the repeats too would make a gate of 8 nearly
    unfailable against 19 calls per arm and would stop measuring what it was chosen to
    measure.

A4. Repeatability groups and the self-noise floor use EVERY charged call in a
    (fixture, arm) group, scoring a whole-response failure as its true
    `grounded_accepted_n` of 0 -- V5A.1's convention, kept. An invalid response is a real
    outcome of an identical repeated call, so it belongs in the run-to-run variability of
    the metric. This can only INFLATE the floor, i.e. make PASS harder. Discipline deltas
    are likewise pooled over ALL primary calls, not the valid ones, so a research-arm
    failure counts against the research arm rather than vanishing from its average.

A2 narrows and A3 narrows; A4 keeps the inherited, conservative reading. None of the four
was chosen to make any particular verdict more likely, and all four were fixed at $0.00.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import validator_v4 as V4
from src.research.hypothesis_oos import v5a2_evaluator as EV

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a2"
RUN = f"{OUT}/execution"

RATE_KEYS = ["grounded_acceptance_rate", "valid_evidence_reference_rate",
             "fabricated_evidence_rate", "compilability", "unsupported_dimension_rate",
             "firewall_clean_rate", "meaningful_conditionality",
             "meaningful_interaction_rate", "redundancy_rate", "baseline_diversity",
             "metric_family_diversity", "evidence_specificity", "abstention_rate",
             "grounded_abstention_rate"]
USE_KEYS = list(EV.AVAILABILITY_DIMENSIONS)

#: Whole-response failures that are the MODEL violating the numerical firewall, kept apart
#: from schema invalidity because the authorization requires the distinction.
FIREWALL_FAILURES = ("NUMERICAL_AUTHORITY_VIOLATION", "LATENT_GRADING_VIOLATION")
#: Whole-response failures that are the MODEL using evidence the packet did not expose.
AVAILABILITY_FAILURES = ("UNSUPPORTED_CONTEXT_SOURCE", "UNSUPPORTED_DIMENSION",
                         "UNAVAILABLE_AXIS")


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def is_valid(s: dict) -> bool:
    """A1. The single definition of VALID_MODEL_RESPONSE used everywhere below."""
    return bool(s["parsed"]) and s["whole_response_failure"] is None \
        and s["failure_class"] is None


def classify_outcome(s: dict) -> str:
    """The authorization's five-way taxonomy, applied to one CHARGED call.

    (INFRASTRUCTURE_FAILURE also covers transport failures, which are never charged and are
    counted separately from this function.)
    """
    if s["failure_class"] == V4.INFRASTRUCTURE_CONTRACT_FAILURE:
        return "INFRASTRUCTURE_FAILURE"
    wrf = s["whole_response_failure"]
    if wrf is None:
        return "VALID_MODEL_RESPONSE"
    if wrf in FIREWALL_FAILURES:
        return "MODEL_FIREWALL_VIOLATION"
    if wrf in AVAILABILITY_FAILURES:
        return "MODEL_AVAILABILITY_VIOLATION"
    return "MODEL_SCHEMA_INVALID"


def expand_calls(prereg) -> list:
    """The driver's call order, reproduced so seq -> (arm, fixture, rep) is exact."""
    calls = []
    for c in prereg["request_manifest"]["calls"]:
        for rep in range(c["n_calls"]):
            calls.append({"arm": c["arm"], "fixture_id": c["fixture_id"], "rep": rep})
    return calls


def main() -> int:
    frz = json.load(open(f"{OUT}/EVALUATOR_FREEZE.json"))
    cur = _sha(f"{ROOT}/src/research/hypothesis_oos/v5a2_evaluator.py")
    if cur != frz["evaluator_sha256"]:
        print("EVALUATOR DRIFT: refusing to score.", cur, "!=", frz["evaluator_sha256"])
        return 2

    prereg = json.load(open(f"{OUT}/PREREGISTRATION.json"))
    packets = {"base": json.load(open(f"{OUT}/packets_base.json")),
               "research": json.load(open(f"{OUT}/packets_research.json"))}
    summary = json.load(open(f"{RUN}/execution_summary.json"))
    calls = expand_calls(prereg)

    log = [json.loads(l) for l in open(f"{RUN}/execution_log.jsonl")]
    by_seq = {r["seq"]: r for r in log}
    transport_failures = [r for r in log if r.get("outcome") == "TRANSPORT_FAILURE"]

    scored = []
    for seq in sorted(by_seq):
        rec = by_seq[seq]
        if rec.get("outcome") == "TRANSPORT_FAILURE":
            continue
        c = calls[seq - 1]
        pk = packets[c["arm"]][c["fixture_id"]]
        raw = json.load(open(f"{RUN}/raw/{seq:03d}.json"))
        s = EV.score_response(raw.get("payload"), pk)
        row = {"seq": seq, "fixture_id": c["fixture_id"], "arm": c["arm"],
               "rep": c["rep"],
               "input_tokens": rec.get("input_tokens"),
               "output_tokens": rec.get("output_tokens"),
               "outcome": classify_outcome(s), "valid": is_valid(s),
               **s, **EV.rates(s)}
        scored.append(row)

    # ---- A2: paired comparison, primaries only, valid in BOTH arms -------------------
    primary = {(x["fixture_id"], x["arm"]): x for x in scored if x["rep"] == 0}
    paired, unpaired = [], []
    for f in sorted({k[0] for k in primary}):
        a, b = primary.get((f, "base")), primary.get((f, "research"))
        if not a or not b or not a["valid"] or not b["valid"]:
            unpaired.append({"fixture_id": f,
                             "base": a["outcome"] if a else "NOT_CALLED",
                             "research": b["outcome"] if b else "NOT_CALLED"})
            continue
        row = {"fixture_id": f, "base": a[EV.PRIMARY_METRIC],
               "research": b[EV.PRIMARY_METRIC],
               "diff": b[EV.PRIMARY_METRIC] - a[EV.PRIMARY_METRIC]}
        for k in RATE_KEYS:
            row[f"{k}__base"] = round(a[k], 4)
            row[f"{k}__research"] = round(b[k], 4)
            row[f"{k}__delta"] = round(b[k] - a[k], 4)
        for k in USE_KEYS:
            row[f"{k}__base"] = a.get(k, 0)
            row[f"{k}__base_available"] = a.get(f"{k}_available", False)
            row[f"{k}__research"] = b.get(k, 0)
            row[f"{k}__research_available"] = b.get(f"{k}_available", False)
        paired.append(row)

    # ---- A4: self-noise over every charged call in a repeat group --------------------
    groups = {}
    for x in scored:
        groups.setdefault((x["fixture_id"], x["arm"]), []).append(x)
    repeat_groups = [{"fixture_id": f, "arm": a,
                      "values": [y[EV.PRIMARY_METRIC]
                                 for y in sorted(v, key=lambda z: z["rep"])]}
                     for (f, a), v in sorted(groups.items()) if len(v) > 1]
    noise = EV.self_noise_floor(repeat_groups)
    n_groups = {arm: sum(1 for g in repeat_groups if g["arm"] == arm)
                for arm in ("base", "research")}

    # ---- A4: discipline deltas pooled over ALL primary calls -------------------------
    def pooled(arm, key):
        vals = [x[key] for x in scored if x["arm"] == arm and x["rep"] == 0]
        return statistics.fmean(vals) if vals else 0.0

    disc = {
        "compilability_delta": round(pooled("research", "compilability")
                                     - pooled("base", "compilability"), 4),
        "firewall_clean_delta": round(pooled("research", "firewall_clean_rate")
                                      - pooled("base", "firewall_clean_rate"), 4),
        "fabricated_evidence_delta": round(pooled("research", "fabricated_evidence_rate")
                                           - pooled("base", "fabricated_evidence_rate"), 4),
        "unsupported_dimension_delta": round(
            pooled("research", "unsupported_dimension_rate")
            - pooled("base", "unsupported_dimension_rate"), 4),
    }

    # ---- A3: evaluability, then the frozen two-status verdict ------------------------
    n_valid = {arm: sum(1 for x in scored
                        if x["arm"] == arm and x["rep"] == 0 and x["valid"])
               for arm in ("base", "research")}
    ev = EV.evaluability(len(paired), n_valid["base"], n_valid["research"],
                         n_groups["base"], n_groups["research"])
    final = EV.final_verdict(summary["execution_status"], ev, paired,
                             noise["floor_used"], disc)

    outcome_counts = {}
    for x in scored:
        outcome_counts[x["outcome"]] = outcome_counts.get(x["outcome"], 0) + 1

    pooled_rates = {arm: {k: round(pooled(arm, k), 4) for k in RATE_KEYS}
                    for arm in ("base", "research")}
    pooled_use = {arm: {k: round(statistics.fmean(
        [x[k] for x in scored if x["arm"] == arm and x["rep"] == 0] or [0]), 4)
        for k in USE_KEYS} for arm in ("base", "research")}

    results = {
        "evaluator": EV.version_stamp(),
        "evaluator_sha256": cur,
        "evaluator_frozen_before_first_paid_call": True,
        "analyzer_sha256": _sha(__file__),
        "aggregation_choices": {"A1": "VALID = parsed and no whole-response failure and "
                                      "no apparatus defect",
                                "A2": "paired = primaries (rep 0) valid in BOTH arms",
                                "A3": "valid-per-arm counted over the 10 primaries only",
                                "A4": "repeat groups and discipline deltas use every "
                                      "charged call; failures score 0"},
        "transport": summary["transport"],
        "n_charged": summary["transport"]["n_charged"],
        "n_transport_failures": len(transport_failures),
        "transport_failures": [{"seq": r["seq"], "error": r.get("error")}
                               for r in transport_failures],
        "actual_cost_usd": summary["transport"]["spend_usd"],
        "stop": summary["stop"],
        "execution_status": summary["execution_status"],
        "environment": summary.get("environment"),
        "outcome_counts": outcome_counts,
        "n_model_schema_invalid": summary["n_model_schema_invalid"],
        "n_infrastructure_contract_failures":
            summary["n_infrastructure_contract_failures"],
        "per_call": scored,
        "paired_by_fixture": paired,
        "unpaired_fixtures": unpaired,
        "pooled_rates": pooled_rates,
        "pooled_availability_use": pooled_use,
        "discipline_deltas": disc,
        "self_noise": noise,
        "n_valid_primaries": n_valid,
        "n_repeat_groups": n_groups,
        "evaluability": ev,
        "final": final,
    }
    json.dump(results, open(f"{RUN}/evaluation_results.json", "w"), indent=1,
              sort_keys=False, default=str)

    print(f"charged={results['n_charged']} transport_fail={len(transport_failures)} "
          f"cost=${results['actual_cost_usd']}")
    print(f"outcomes: {outcome_counts}")
    print(f"valid primaries: {n_valid}  repeat groups: {n_groups}  paired: {len(paired)}")
    print(f"self-noise pooled_sd={noise['pooled_sd']} floor={noise['floor_used']}")
    print(f"discipline deltas: {disc}")
    print(f"\n{'FIXTURE':16}{'base':>6}{'res':>6}{'diff':>7}")
    for p in paired:
        print(f"{p['fixture_id']:16}{p['base']:6}{p['research']:6}{p['diff']:+7}")
    print(f"\nEXECUTION_STATUS   = {final['execution_status']}")
    print(f"SCIENTIFIC_STATUS  = {final['scientific_status']}")
    print(f"SCIENTIFIC_VERDICT = {final['scientific_verdict']}")
    print(f"REASON: {final['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
