"""V8C sealed-947 structural preflight -- OUTCOME-BLIND, PARALLEL.

The 947 sealed fixtures are NEVER scored and their target observations are NEVER read. Every
read goes through `TargetBlindIndex`, whose audit log is aggregated into the artifact, so
SEALED_947_OUTCOMES_VIEWED=false is a MECHANICAL result rather than a claim.

Per sealed fixture, using strictly pre-T information only:
    admissible universe size
    PRE_T_EVALUABLE universe size + the pre-T attrition ledger
    metrics represented / mechanism (comparator) types represented / research families
    LIVE search addressability (live_reachability.audit_fixture -- the bounded 6-call protocol)
    full R action-space coverage + SET-LEVEL distinct-R feasibility up to MAX_SELECTIONS
    H feasibility
    PILOT_ELIGIBLE, matching V8C_FRESH_PILOT_POPULATION_RULE.md section 2 EXACTLY

No Sonnet calls. No scoring. No CHAMPION write.

REPAIRED FOR GATE A (Phase 8). NOT RUN IN THAT MISSION -- running it needs explicit
authorisation, because it touches the sealed reserve's structural surface.

Three things were obsolete and are now fixed:

  1. `UNI.reachability_report` measured THEORETICAL reachability by paginating one unfiltered
     query to exhaustion. Under the live protocol the model gets 6 calls and a 50-result page,
     so that overstated S's action space. Replaced by `live_reachability.audit_fixture`, which
     asks whether each candidate's own canonical structural query surfaces it on the FIRST page.
  2. Distinct-R feasibility was probed on `fu.evaluable[:K_MIN]` -- the first four candidates as
     a proxy. The experiment matches a SET of up to MAX_SELECTIONS simultaneously, where no
     control may be reused and none may be another S pick. Replaced by
     `control_coverage.audit_fixture`, which computes full single-candidate coverage and
     SET-LEVEL feasibility by maximum bipartite matching.
  3. `PILOT_ELIGIBLE` omitted the frozen rule's `live_search_addressable` conjunct. It now
     reproduces section 2 term for term, and `PILOT_RULE_CONJUNCTS` states those terms in code
     so a reviewer can diff them against the document.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)

OUT = f"{ENG}/V8C_SEALED947_STRUCTURAL_PREFLIGHT.json"
SHARD_DIR = f"{ENG}/out/v8c_preflight_shards"

#: PILOT_ELIGIBLE threshold, DERIVED operationally (V8C_END_TO_END_CONTRACT.md section 3):
#: S needs a genuine choice (>=2), R needs a distinct control (+1), H needs to rank rather
#: than restate S's pick (+1). Not tuned to yield a fixture count.
K_MIN = 4

#: V8C_FRESH_PILOT_POPULATION_RULE.md section 2, term for term. A fixture is PILOT_ELIGIBLE
#: iff ALL of these hold on pre-T structural information only. No term reads a target outcome,
#: an effect, a score, a direction or a p-value.
PILOT_RULE_CONJUNCTS = (
    "pre_t_evaluable_candidates >= K_MIN",
    "distinct_R_feasible",
    "H_feasible",
    "live_search_addressable",
    "fixture_in_frozen_947_reserve",
)
PILOT_RULE_DOC = "V8C_FRESH_PILOT_POPULATION_RULE.md"
PILOT_RULE_VERSION = "v8c_pilot_rule_v1"

#: Set-level R feasibility is evaluated up to the frozen submission cap, not at K_MIN.
MAX_SELECTIONS = 8

_G = {}


def _init():
    from src.research.hypothesis_v71 import similarity as SIM
    from src.research.hypothesis_v8c import harness as H
    cap, index, _ = H.build(check_champion=False)
    _G["cap"], _G["index"] = cap, index
    _G["sim"] = SIM.SimilarityEngine(index)


def _one(fid):
    from src.research.hypothesis_v8c import blind_index as BI
    from src.research.hypothesis_v8c import control_coverage as CC
    from src.research.hypothesis_v8c import controls as CTL
    from src.research.hypothesis_v8c import live_reachability as LIVE
    from src.research.hypothesis_v8c import pit_context as PC
    from src.research.hypothesis_v8c import universe as UNI
    cap, index = _G["cap"], _G["index"]
    pos = index.pos_of_fixture.get(fid)
    if pos is None:
        return {"fixture_id": fid, "status": "NOT_IN_INDEX"}

    sealed = BI.TargetBlindIndex(index, [pos])          # the target's own stats are unreadable
    ctx = PC.build_pit_context(sealed, pos)
    fu = UNI.build_fixture_universe(sealed, pos, ctx=ctx, capability=cap, fixture_id=fid)

    # LIVE addressability under the real bounded protocol -- NOT the old unlimited-pagination
    # `reachability_report`, which measured a search budget the model does not have.
    reach = LIVE.audit_fixture(fu)
    live_addressable = reach["n_live_unreachable"] == 0

    # FULL R action-space coverage, plus SET-LEVEL feasibility at the frozen submission cap.
    # No first-four proxy.
    cov = CC.audit_fixture(fu, k=MAX_SELECTIONS)
    r_single = cov["R_SINGLE_CANDIDATE_COVERAGE"]
    r_set_k8 = cov["R_SET_LEVEL_K8_FEASIBLE"]

    # The rule's `distinct_R_feasible` term: a control exists for every member of a
    # simultaneously-submitted set, at the size the protocol actually permits.
    k_probe = min(MAX_SELECTIONS, fu.n_evaluable)
    probe = [CTL.shape_of(c) for c in fu.evaluable[:k_probe]]
    r_feasible = bool(r_set_k8) if probe else False
    r_tiers = {}
    if probe:
        r_tiers = CTL.blind_selections_for_fixture(probe, fu)["tiers"]
    h_out = CTL.heuristic_selections_for_fixture(len(probe), fu) if probe else None
    h_feasible = bool(h_out and h_out["n_selected"] == len(probe))

    audit = sealed.audit_report()
    return {
        "fixture_id": fid, "status": "OK",
        "competition": index.recs[pos].competition,
        "kickoff_unix": int(index.kick[pos]),
        "ledger": fu.ledger(),
        "n_admissible": fu.n_admissible,
        "n_pre_t_evaluable": fu.n_evaluable,
        "n_metrics_represented": len({c["target_metrics"][0] for c in fu.evaluable}),
        "n_mechanism_types_represented": len({c["comparator"] for c in fu.evaluable}),
        "n_research_families_represented": len({c["research_family"] for c in fu.evaluable}),
        "research_family_counts": fu.research_family_counts(),
        "live_search_unreachable_count": reach["n_live_unreachable"],
        "live_search_addressable": bool(live_addressable),
        "live_reachability_version": reach["live_reachability_version"],
        "R_SINGLE_CANDIDATE_COVERAGE": r_single,
        "R_SET_LEVEL_K8_FEASIBLE": bool(r_set_k8),
        "distinct_r_feasible": bool(r_feasible), "r_tiers": r_tiers,
        "h_feasible": bool(h_feasible),
        # section 2, term for term. The in-reserve term is guaranteed by the caller, which
        # iterates `sealed_947_ids()`, and is restated here so the record is self-describing.
        "pilot_eligible": bool(fu.n_evaluable >= K_MIN and r_feasible and h_feasible
                               and live_addressable),
        "pilot_rule_version": PILOT_RULE_VERSION,
        "pilot_rule_conjuncts": list(PILOT_RULE_CONJUNCTS),
        "fixture_in_frozen_947_reserve": True,
        "blind_audit": {"blocked_target_reads": audit["blocked_target_reads"],
                        "blocked_vals_reads": audit["blocked_vals_reads"],
                        "sanitized_record_reads": audit["sanitized_record_reads"],
                        "served_target_reads": audit["served_target_reads"],
                        "target_outcomes_viewed": audit["target_outcomes_viewed"]},
    }


#: The 3 T2 infrastructure canaries, read from their own provenance artifacts rather than
#: hardcoded: these fixtures were used to validate transport and the search cap, so they are
#: infrastructure-exposed and are NOT part of the clean sealed reserve.
#:     1000 manifest - 50 outcome-exposed pilot - 3 canaries = 947
T2_CANARY_PROVENANCE = "V8B1_CANARY_RESULTS.json"


def t2_canary_ids() -> set:
    d = json.load(open(f"{ENG}/{T2_CANARY_PROVENANCE}"))
    ids = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("fixture_id", "fixture_ids"):
                    ids.extend(v if isinstance(v, list) else [v])
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(d)
    return {str(x) for x in ids if str(x).startswith("mt_")}


def sealed_947_ids():
    man = json.load(open(f"{ENG}/V8B1_FIXTURE_MANIFEST.json"))["fixtures"]
    exposed = set(json.load(open(f"{ENG}/V8B1_PILOT50_SELECTION_FREEZE.json"))
                  ["pilot_fixture_ids_ordered"])
    canaries = t2_canary_ids()
    rows = sorted(man, key=lambda f: (int(f["kickoff_unix"]), str(f["fixture_id"])))
    out = [f["fixture_id"] for f in rows
           if f["fixture_id"] not in exposed and f["fixture_id"] not in canaries]
    assert len(out) == 947, (
        f"sealed reserve is {len(out)}, expected 947 "
        f"(manifest {len(man)} - exposed {len(exposed)} - canaries {len(canaries)})")
    return out


def main():
    from src.research.hypothesis_v8c import harness as H
    champ = H.assert_champion_unchanged()
    ids = sealed_947_ids()
    print(f"[preflight] sealed fixtures = {len(ids)}", flush=True)
    os.makedirs(SHARD_DIR, exist_ok=True)

    t0 = time.time()
    rows = []
    with mp.Pool(processes=4, initializer=_init) as pool:
        for n, r in enumerate(pool.imap(_one, ids, chunksize=4), 1):
            rows.append(r)
            if n % 20 == 0 or n == len(ids):
                el = time.time() - t0
                print(f"[preflight] {n}/{len(ids)}  {el:.0f}s  "
                      f"eta {el / n * (len(ids) - n):.0f}s", flush=True)
                with open(f"{SHARD_DIR}/partial.json", "w") as f:
                    json.dump({"n_done": n, "rows": rows}, f, default=str)

    ok = [r for r in rows if r["status"] == "OK"]
    ev = sorted(r["n_pre_t_evaluable"] for r in ok)

    def pct(p):
        return ev[min(len(ev) - 1, int(p * len(ev)))] if ev else None

    by_comp = {}
    for r in ok:
        by_comp.setdefault(r["competition"], []).append(r)

    report = {
        "preflight_version": "v8c_sealed947_structural_preflight_v1",
        "evidence_class": "SEALED_STRUCTURAL_PREFLIGHT",
        "reads_target_observations": False,
        "sealed_947_outcomes_viewed": any(
            r.get("blind_audit", {}).get("target_outcomes_viewed") for r in ok),
        "new_sonnet_calls": 0,
        "k_min": K_MIN,
        "k_min_derivation": ("S needs >=2 for a genuine choice, R needs one more for a "
                             "distinct control, H needs one more to rank rather than restate "
                             "S's pick; not tuned to a fixture count"),
        "n_fixtures": len(ok),
        "zero_evaluable": sum(1 for r in ok if r["n_pre_t_evaluable"] == 0),
        "ge1_evaluable": sum(1 for r in ok if r["n_pre_t_evaluable"] >= 1),
        "ge5_evaluable": sum(1 for r in ok if r["n_pre_t_evaluable"] >= 5),
        "ge10_evaluable": sum(1 for r in ok if r["n_pre_t_evaluable"] >= 10),
        "evaluable_p10": pct(0.10), "evaluable_p50": pct(0.50), "evaluable_p90": pct(0.90),
        "evaluable_min": ev[0] if ev else None, "evaluable_max": ev[-1] if ev else None,
        "distinct_r_feasible": sum(1 for r in ok if r["distinct_r_feasible"]),
        "h_feasible": sum(1 for r in ok if r["h_feasible"]),
        "both_controls_feasible": sum(1 for r in ok
                                      if r["distinct_r_feasible"] and r["h_feasible"]),
        "pilot_eligible": sum(1 for r in ok if r["pilot_eligible"]),
        "total_unreachable_candidates": sum(r["unreachable_candidate_count"] for r in ok),
        "by_competition": {c: {"n": len(rs),
                               "pilot_eligible": sum(1 for r in rs if r["pilot_eligible"]),
                               "median_evaluable": sorted(
                                   x["n_pre_t_evaluable"] for x in rs)[len(rs) // 2]}
                           for c, rs in sorted(by_comp.items())},
        "champion_sha256": champ,
        "champion_unchanged": H.champion_unchanged(),
        "elapsed_s": round(time.time() - t0, 1),
        "per_fixture": rows,
    }
    with open(OUT, "w") as f:
        json.dump(report, f, indent=1, default=str)
    for k in ("n_fixtures", "zero_evaluable", "ge1_evaluable", "ge5_evaluable",
              "ge10_evaluable", "evaluable_p10", "evaluable_p50", "evaluable_p90",
              "distinct_r_feasible", "h_feasible", "both_controls_feasible",
              "pilot_eligible", "total_unreachable_candidates",
              "sealed_947_outcomes_viewed"):
        print(f"[preflight] {k} = {report[k]}")
    print(f"[preflight] wrote {OUT}")


if __name__ == "__main__":
    main()
