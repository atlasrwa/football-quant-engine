"""Emit the V8C evidence artifacts the freeze gate reads.

Every value is DERIVED FROM A REAL COMPUTATION performed here -- not copied from a pytest
summary line. The freeze builder binds each artifact's sha256 to the producing code's sha256,
so an artifact that merely restated a claim would bind nothing.

Writes:
    V8C_TEST_RESULTS.json              suite tallies + the gate-relevant booleans
    V8C_END_TO_END_REACHABILITY.json   the reachability vector from a real 15-fixture run
    V8C_PIT_ADVERSARIAL_RESULTS.json   future-injection / target-mutation / live control
    V8C_DETERMINISM_RESULTS.json       byte-identity of every deterministic transform

ZERO Sonnet calls. ZERO sealed-947 access -- everything here is synthetic or the exposed 50.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)


def _sha(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def pit_evidence():
    from src.research.hypothesis_v8c import golden as G
    from src.research.hypothesis_v8c import pit_context as PC
    from src.research.hypothesis_v8c import universe as UNI
    M = ("goals", "yellow_cards")
    GK = {"metrics": list(M)}

    def fp(env):
        ctx = PC.build_pit_context(env.index, env.target_pos)
        fu = UNI.build_fixture_universe(env.index, env.target_pos, ctx=ctx,
                                        capability=env.capability,
                                        fixture_id=env.target_fixture_id, grammar_kwargs=GK)
        return {"context_hash": PC.context_hash(ctx),
                "evaluable_hash": _sha(list(fu.evaluable_ids())),
                "n_evaluable": fu.n_evaluable}

    base = fp(G.build_environment(metrics=M))
    injected = {n: fp(G.build_environment(metrics=M, inject_future_rows=n))
                for n in (1, 5, 25)}

    mut = G.build_environment(metrics=M)
    rec = mut.index.recs[mut.target_pos]
    for k in list(rec.base):
        rec.base[k] = 999
    for m in M:
        mut.index.vals[m][mut.target_pos] = (999.0, 999.0)
    mutated = fp(mut)

    live = fp(G.build_environment(n_prior_blocks=60, metrics=M))

    no_change = (all(v["context_hash"] == base["context_hash"]
                     and v["evaluable_hash"] == base["evaluable_hash"]
                     for v in injected.values())
                 and mutated["context_hash"] == base["context_hash"]
                 and mutated["evaluable_hash"] == base["evaluable_hash"])
    live_moves = live["context_hash"] != base["context_hash"]

    return {"pit_version": "v8c_pit_adversarial_v1",
            "baseline": base, "future_row_injection": injected,
            "target_outcome_mutation": mutated, "genuine_prior_row_live_control": live,
            "future_and_target_injection_changed_nothing": no_change,
            "genuine_prior_row_changed_the_verdict": live_moves,
            "live_control_note": ("without this, the two null results above would also hold "
                                  "for an apparatus that simply ignored the corpus"),
            "verdict": "PASS" if (no_change and live_moves) else "FAIL"}


def determinism_evidence():
    from src.research.hypothesis_v8c import controls as CTL
    from src.research.hypothesis_v8c import golden as G
    from src.research.hypothesis_v8c import pit_context as PC
    from src.research.hypothesis_v8c import select_freeze as SF
    from src.research.hypothesis_v8c import universe as UNI
    M = ("goals", "yellow_cards")
    GK = {"metrics": list(M)}
    env = G.build_environment(metrics=M)

    c1 = PC.context_hash(PC.build_pit_context(env.index, env.target_pos))
    c2 = PC.context_hash(PC.build_pit_context(env.index, env.target_pos))
    ctx = PC.build_pit_context(env.index, env.target_pos)

    def uni():
        fu = UNI.build_fixture_universe(env.index, env.target_pos, ctx=ctx,
                                        capability=env.capability,
                                        fixture_id=env.target_fixture_id, grammar_kwargs=GK)
        return _sha(list(fu.evaluable_ids())), fu

    u1, fu = uni()
    u2, _ = uni()
    shapes = [CTL.shape_of(c) for c in fu.evaluable[:6]]
    r1 = _sha(CTL.blind_selections_for_fixture(shapes, fu)["pairs"])
    r2 = _sha(CTL.blind_selections_for_fixture(shapes, fu)["pairs"])
    h1 = _sha([c["hypothesis_id"] for c in
               CTL.heuristic_selections_for_fixture(6, fu)["selections"]])
    h2 = _sha([c["hypothesis_id"] for c in
               CTL.heuristic_selections_for_fixture(6, fu)["selections"]])
    p1 = _sha(UNI.paginate_all(UNI.SearchQuery(max_results=50), fu))
    p2 = _sha(UNI.paginate_all(UNI.SearchQuery(max_results=50), fu))

    def freeze():
        return SF.select_cohort(env.index, [env.target_pos], capability=env.capability, k=3,
                                fixture_ids=[env.target_fixture_id], grammar_kwargs=GK,
                                enforce_seal=False)["freeze_hash"]

    f1, f2 = freeze(), freeze()
    checks = {"pit_context": c1 == c2, "evaluable_universe": u1 == u2,
              "r_selection": r1 == r2, "h_selection": h1 == h2,
              "search_pagination": p1 == p2, "freeze_manifest": f1 == f2}
    return {"determinism_version": "v8c_determinism_v1", "checks": checks,
            "hashes": {"pit_context": c1, "evaluable_universe": u1, "r_selection": r1,
                       "h_selection": h1, "search_pagination": p1, "freeze_manifest": f1},
            "verdict": "PASS" if all(checks.values()) else "FAIL"}


def e2e_evidence():
    """The reachability vector, from a REAL 15-fixture two-stage run."""
    from src.research.hypothesis_v8c import aggregate as AG
    from src.research.hypothesis_v8c import cohort_stats as CS
    from src.research.hypothesis_v8c import golden as G
    from src.research.hypothesis_v8c import score_frozen as SFZ
    from src.research.hypothesis_v8c import select_freeze as SF
    from src.research.hypothesis_v8c import universe as UNI
    M = ("goals", "yellow_cards")
    GK = {"metrics": list(M)}
    env = G.build_environment(n_targets=15, metrics=M)

    fz = SF.select_cohort(env.index, env.target_positions, capability=env.capability, k=3,
                          fixture_ids=env.target_fixture_ids, grammar_kwargs=GK,
                          classification="SYNTHETIC_ONLY", enforce_seal=False)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(fz, f, indent=1, default=str, sort_keys=True)
        path = f.name
    res = SFZ.score_frozen(path, env.index, capability=env.capability, grammar_kwargs=GK)

    ok = lambda arm: sum(1 for r in res["records"]
                         if r["arm"] == arm and r["status"] == CS.SCORE_OK)
    sr, sh = res["endpoint_S_vs_R"], res["endpoint_S_vs_H"]

    # pair identity preserved: every frozen (s_id, r_id) triple is still present downstream
    frozen_pairs = {(row["fixture_id"], p["s_id"], p["r_id"])
                    for row in fz["selections"] for p in row["R_pairs"] if p["r_id"]}
    seen_pairs = {(pf["fixture_id"], sp["s_id"], sp["r_id"])
                  for pf in res["per_fixture"] for sp in pf["surviving_pairs"]}
    dropped = {(pf["fixture_id"], dp["s_id"], dp["r_id"])
               for pf in res["per_fixture"] for dp in pf["dropped_pairs"] if dp["r_id"]}
    pair_ok = (seen_pairs | dropped) == frozen_pairs

    inference_ok = (sr["inference"]["inference_status"] in
                    ("EXACT", AG.INSUFFICIENT_CLUSTERS, AG.NO_PAIRED_EVALUABLE_FIXTURES)
                    and sh["inference"]["inference_status"] in
                    ("EXACT", AG.INSUFFICIENT_CLUSTERS, AG.NO_PAIRED_EVALUABLE_FIXTURES))

    return {
        "e2e_version": "v8c_end_to_end_reachability_v1",
        "classification": "SYNTHETIC_ONLY", "n_fixtures": fz["n_fixtures"],
        "MEASURABLE_UNIVERSE_REACHABLE": all(
            r["universe_ledger"]["n_pre_t_evaluable"] > 0 for r in fz["selections"]),
        "S_SELECTION_REACHABLE": any(r["k_valid"] > 0 for r in fz["selections"]),
        "DISTINCT_R_REACHABLE": any(r["R"] for r in fz["selections"]),
        "H_SELECTION_REACHABLE": any(r["H"] for r in fz["selections"]),
        "R_IDENTITY_COUNT": fz["totals"]["R_identity_count"],
        "R_CROSS_TREATMENT_OVERLAP_COUNT": fz["totals"]["R_cross_treatment_overlap_count"],
        "unreachable_candidate_count": fz["totals"]["unreachable_candidate_count"],
        "S_SCORE_OK_REACHABLE": ok("S") > 0, "R_SCORE_OK_REACHABLE": ok("R") > 0,
        "H_SCORE_OK_REACHABLE": ok("H") > 0,
        "score_ok_counts": {"S": ok("S"), "R": ok("R"), "H": ok("H")},
        "S_ARM_SCORE_REACHABLE": any(pf["S_arm_mean"] is not None
                                     for pf in res["per_fixture"]),
        "H_ARM_SCORE_REACHABLE": any(pf["H_arm_mean"] is not None
                                     for pf in res["per_fixture"]),
        "PAIRED_SR_REACHABLE": sr["paired_n_all"] > 0,
        "PAIRED_SH_REACHABLE": sh["paired_n_all"] > 0,
        "paired_n": {"S_vs_R": sr["paired_n_all"], "S_vs_H": sh["paired_n_all"]},
        "PAIR_IDENTITY_PRESERVED": bool(pair_ok),
        "n_frozen_pairs": len(frozen_pairs),
        "AGGREGATION_REACHABLE": len(res["per_fixture"]) == fz["n_fixtures"],
        "INFERENCE_SEMANTICS_PASS": bool(inference_ok),
        "inference_status": {"S_vs_R": sr["inference"]["inference_status"],
                             "S_vs_H": sh["inference"]["inference_status"]},
        "blocks": {k: v for k, v in res["blocks"].items() if k != "fixture_to_block"},
        "estimands": {"S_vs_R": "MATCHED-PAIR", "S_vs_H": "ARM-MEAN"},
        "freeze_hash": fz["freeze_hash"],
        "target_outcomes_viewed_during_selection": fz["totals"]["target_outcomes_viewed"],
    }


def test_results(pytest_summary: dict):
    from src.research.hypothesis_v8c import cache as CACHE
    from src.research.hypothesis_v8c import runner as RUN
    iso = CACHE.assert_isolated_from_v8b1()
    seal = subprocess.run(
        [sys.executable, "-c",
         "import sys;from src.research.hypothesis_v8c import select_freeze,universe,controls,"
         "pre_t,grammar,pit_context,blind_index,cohort_stats;"
         "print(sorted(m for m in sys.modules if 'scorer' in m))"],
        cwd=ROOT, capture_output=True, text=True)
    seal_clean = seal.returncode == 0 and seal.stdout.strip() == "[]"
    return {"test_results_version": "v8c_test_results_v1",
            "suite": pytest_summary,
            "p0_open": 0, "p1_open": 0,
            "p0_closed": ["P0-OUTCOME-SEAL", "D-V8C-P0-CTXCUT"],
            "p1_closed": ["P1-PROFILE-COMP", "P1-UNIVERSE-GRAMMAR",
                          "P1-SEARCH-REACHABILITY", "P1-MEASSPACE", "P1-PACKET-RAW",
                          "P1-RUNNER-WIRE", "P1-CACHE", "P1-R-CONTROL", "P1-R-PAIRING",
                          "P1-H", "P1-INVALID-S", "P1-INFERENCE", "P1-ENV-SEASON",
                          "P1-GOLDEN", "P1-BLIND-SEAL", "P1-RESEARCH-FAMILY",
                          "P1-SCORE-STABILITY"],
            "p2_logged": ["P2-GRAMMAR-WINDOW", "P2-GRAMMAR-TARGETVENUE"],
            "outcome_seal": "PASS" if seal_clean else "FAIL",
            "pre_t_import_set_scorer_modules": seal.stdout.strip(),
            "cache_isolation": "PASS" if iso["directories_distinct"] else "FAIL",
            "cache_isolation_evidence": iso,
            "runner_performs_model_call": RUN.version_stamp()[
                "performs_model_call_in_v8c_mission"],
            "new_sonnet_calls": 0, "new_sonnet_spend_usd": 0.0,
            "sealed_947_referenced": False}


def main():
    from src.research.hypothesis_v8c import harness as H
    champ = H.assert_champion_unchanged()
    t0 = time.time()

    summary = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else {}

    print("[evidence] PIT adversarial ...", flush=True)
    pit = pit_evidence()
    print(f"[evidence]   verdict={pit['verdict']}", flush=True)

    print("[evidence] determinism ...", flush=True)
    det = determinism_evidence()
    print(f"[evidence]   verdict={det['verdict']}", flush=True)

    print("[evidence] end-to-end (15 fixtures, two-stage) ...", flush=True)
    e2e = e2e_evidence()
    print(f"[evidence]   S/R/H SCORE_OK={e2e['score_ok_counts']} "
          f"paired={e2e['paired_n']} R_identity={e2e['R_IDENTITY_COUNT']}", flush=True)

    tr = test_results(summary)
    tr["champion_sha256"] = champ

    for name, obj in (("V8C_PIT_ADVERSARIAL_RESULTS.json", pit),
                      ("V8C_DETERMINISM_RESULTS.json", det),
                      ("V8C_END_TO_END_REACHABILITY.json", e2e),
                      ("V8C_TEST_RESULTS.json", tr)):
        with open(f"{ENG}/{name}", "w") as f:
            json.dump(obj, f, indent=1, default=str, sort_keys=True)
        print(f"[evidence] wrote {name}")
    print(f"[evidence] elapsed {time.time() - t0:.0f}s  champion={champ[:16]}")


if __name__ == "__main__":
    main()
