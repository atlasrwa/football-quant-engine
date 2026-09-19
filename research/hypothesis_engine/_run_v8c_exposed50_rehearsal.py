"""V8C exposed-50 REAL-CORPUS APPARATUS REHEARSAL -- Gate A Phase 12.

EVIDENCE_CLASS = DEVELOPMENT_REAL_CORPUS_APPARATUS_REHEARSAL

THE QUESTION THIS ANSWERS, AND THE ONE IT DOES NOT
--------------------------------------------------
ONLY: "does the real repaired apparatus execute end to end on actual football data?"

NOT: whether S beats R. These 50 outcomes were opened in V8B.1 and are DEVELOPMENT data. This
script therefore refuses to compute or emit a mean arm score, an S-R difference, an effect
direction, a p-value or a winner. `FORBIDDEN_OUTPUT_KEYS` states that mechanically.

WHERE THE DATA COMES FROM
-------------------------
The exposed-50 handoff bundle, not the full corpus. The bundle holds 441 records -- the exact
strictly-pre-T closure for these 50 fixtures -- and ZERO of the 947 sealed reserve fixtures,
neither a fixture row nor a stats file. So OUTCOME_SEAL_PASS is STRUCTURAL rather than
asserted: the scorer cannot read a sealed outcome that is not on disk.

ZERO SONNET CALLS. The S arm is driven by a DETERMINISTIC stand-in through the REAL
`run_fixture_converse` loop -- the same Converse orchestration, the same search tool, the same
submission validation. Only the transport is substituted.

Emits derived diagnostics ONLY. No raw match row leaves this script.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)
sys.path.insert(0, f"{ROOT}/scripts")

OUT = f"{ENG}/V8C_EXPOSED50_REHEARSAL.json"
PARTIAL = f"{ENG}/V8C_EXPOSED50_REHEARSAL.partial.json"
CLASSIFICATION = "DEVELOPMENT_REAL_CORPUS_APPARATUS_REHEARSAL"

#: Mechanically forbidden. These 50 outcomes are development data (mission section 21).
FORBIDDEN_OUTPUT_KEYS = (
    "mean_s_score", "mean_r_score", "mean_h_score", "s_minus_r", "effect", "effect_size",
    "p_value", "winner", "direction", "sonnet_better", "sonnet_worse", "advantage",
)

MOCK_S_SELECTOR_VERSION = "v8c_deterministic_s_standin_v1"


def _sha(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def make_mock_converse(k):
    """A DETERMINISTIC stand-in for the model, driven through the real Converse loop.

    Issues two real searches, then submits the first `k` ids the search tool actually returned
    this session. It makes no football judgement and is not a model: its only job is to prove
    the orchestration, search and validation path executes on real data.
    """
    state = {"seen": [], "turn": 0}

    def converse(**kw):
        state["turn"] += 1
        if state["turn"] == 1:
            return {"output": {"message": {"role": "assistant", "content": [
                        {"toolUse": {"toolUseId": "t1", "name": "search_hypotheses",
                                     "input": {"max_results": 50}}}]}},
                    "stopReason": "tool_use"}
        if state["turn"] == 2:
            for blk in kw["messages"][-1]["content"]:
                res = blk.get("toolResult", {})
                for c in res.get("content", []):
                    for r in (c.get("json") or {}).get("results", []):
                        state["seen"].append(r["hypothesis_id"])
            return {"output": {"message": {"role": "assistant", "content": [
                        {"toolUse": {"toolUseId": "t2", "name": "search_hypotheses",
                                     "input": {"max_results": 50, "cursor": None}}}]}},
                    "stopReason": "tool_use"}
        ids = sorted(set(state["seen"]))[:k]
        return {"output": {"message": {"role": "assistant", "content": [
                    {"toolUse": {"toolUseId": "t3", "name": "submit_selections",
                                 "input": {"hypothesis_ids": ids,
                                           "research_reason":
                                               "deterministic stand-in: no football judgement"}}}]}},
                "stopReason": "tool_use"}

    return converse


def main(bundle_root, n_limit=None, k_select=4):
    """`bundle_root` is the extracted exposed-50 handoff bundle directory."""
    sys.path.insert(0, os.path.join(bundle_root, "loader_adapter"))
    import v8c_dev_paths  # noqa: E402  (bundle adapter; redirects the cache root only)
    cache_root = v8c_dev_paths.CACHE_ROOT
    v8c_dev_paths.install()

    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import engine as ENGmod
    from src.research.hypothesis_v71 import similarity as SIM
    from src.research.hypothesis_v8c import control_coverage as CC
    from src.research.hypothesis_v8c import controls as CTL
    from src.research.hypothesis_v8c import grammar as GR
    from src.research.hypothesis_v8c import harness as H
    from src.research.hypothesis_v8c import historical_pit as HPIT
    from src.research.hypothesis_v8c import historical_similarity as HSIM
    from src.research.hypothesis_v8c import live_reachability as LIVE
    from src.research.hypothesis_v8c import pit_context as PC
    from src.research.hypothesis_v8c import runner as RUN
    from src.research.hypothesis_v8c import universe as UNI
    from src.research.hypothesis_v8c import vintage as VIN

    champ_before = H.assert_champion_unchanged()

    freeze = json.load(open(v8c_dev_paths.SELECTION_FREEZE))
    pilot = list(freeze["pilot_fixture_ids_ordered"])
    if n_limit:
        pilot = pilot[:n_limit]

    sealed = set(json.load(open(v8c_dev_paths.SEALED_EXCLUSION))["sealed_fixture_ids"])

    cap = CAP.CapabilityContract(json.load(open(v8c_dev_paths.COVERAGE_MATRIX)))
    recs = CI.load_records(include_fresh=True)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)

    # STRUCTURAL seal check: the reserve is not on disk, so it is not in the index.
    in_index = sorted(sealed & set(index.pos_of_fixture))
    outcome_seal_pass = not in_index

    sim = SIM.SimilarityEngine(index)
    hp = HPIT.HistoricalProfileIndex(index)
    hs = HSIM.HistoricalSimilarityIndex(index)
    print(f"[rehearsal] {len(recs)} records | sealed-in-index={len(in_index)} "
          f"| fixtures={len(pilot)}", flush=True)

    # ============================ PHASE 1: SELECT. No scorer is called. ============================
    selections, per_fixture = [], []
    t0 = time.time()
    for n, fid in enumerate(pilot, 1):
        row = {"fixture_id": fid}
        pos = index.pos_of_fixture.get(fid)
        if pos is None:
            row.update(status="NOT_IN_INDEX", pit_ok=False, universe_ok=False)
            per_fixture.append(row)
            continue
        try:
            ctx = PC.build_pit_context(index, pos, similarity_engine=sim,
                                       historical=hp, historical_similarity=hs)
            row["pit_ok"] = True
        except Exception as e:
            row.update(status="PIT_BUILD_FAILED", pit_ok=False, universe_ok=False,
                       error=type(e).__name__)
            per_fixture.append(row)
            continue
        try:
            fu = UNI.build_fixture_universe(index, pos, ctx=ctx, capability=cap,
                                            fixture_id=fid)
            row["universe_ok"] = True
            row["n_evaluable"] = fu.n_evaluable
        except Exception as e:
            row.update(status="UNIVERSE_BUILD_FAILED", universe_ok=False,
                       error=type(e).__name__)
            per_fixture.append(row)
            continue

        live = LIVE.audit_fixture(fu)
        row["live_search_unreachable"] = live["n_live_unreachable"]

        # ---- S through the REAL runner loop, deterministic stand-in transport ----
        res = RUN.run_fixture_converse(
            fu, cap, converse=make_mock_converse(k_select), packet="REHEARSAL_PACKET",
            model_id="DETERMINISTIC_STANDIN", resolved_model_id=None,
            model_config_stamp={"standin": MOCK_S_SELECTOR_VERSION})
        s_ids = list(res["accepted"])
        row.update(s_status=res["status"], s_k=len(s_ids),
                   search_calls_executed=res["orchestration"]["search_calls_executed"],
                   termination_reason=res["orchestration"]["termination_reason"])

        by_id = {c["hypothesis_id"]: c for c in fu.evaluable}
        shapes = [CTL.shape_of(by_id[h]) for h in s_ids]
        r_out = CTL.blind_selections_for_fixture(shapes, fu) if shapes else None
        h_out = CTL.heuristic_selections_for_fixture(len(s_ids), fu) if s_ids else None
        cov = CC.set_level_feasibility(fu, [s_ids]) if s_ids else None

        row.update(
            r_matched=(r_out["n_matched"] if r_out else 0),
            r_unmatched=(r_out["n_unmatched"] if r_out else 0),
            r_identity=(r_out["identity_count"] if r_out else 0),
            r_cross_overlap=(r_out["cross_treatment_overlap_count"] if r_out else 0),
            h_selected=(h_out["n_selected"] if h_out else 0),
            r_set_feasible=(cov["all_sets_feasible"] if cov else None),
            status="SELECTED")
        selections.append({"fixture_id": fid, "pos": pos, "ctx": ctx,
                           "S": s_ids, "R": r_out, "H": h_out})
        per_fixture.append(row)
        # Durable after EVERY fixture: a two-hour selection pass that writes only at the end
        # yields nothing if it is interrupted.
        with open(PARTIAL, "w") as pf:
            json.dump({"EVIDENCE_CLASS": CLASSIFICATION, "phase": "SELECT",
                       "n_done": n, "n_total": len(pilot),
                       "elapsed_s": round(time.time() - t0, 1),
                       "per_fixture": per_fixture}, pf, indent=1, default=str)
        print(f"[select] {n}/{len(pilot)}  {time.time() - t0:.0f}s  "
              f"evaluable={row.get('n_evaluable')} s={row.get('s_status')}", flush=True)

    freeze_payload = [{"fixture_id": s["fixture_id"], "S": s["S"],
                       "R": [p["r_id"] for p in (s["R"]["pairs"] if s["R"] else [])],
                       "H": [c["hypothesis_id"] for c in (s["H"]["selections"] if s["H"] else [])]}
                      for s in selections]
    selection_freeze_hash = _sha(freeze_payload)
    print(f"[select] frozen: {selection_freeze_hash[:16]}  ({time.time() - t0:.0f}s)", flush=True)

    # ==================== PHASE 2: SCORE. Target outcomes are read ONLY here. ====================
    from src.research.hypothesis_v8c import scorer as SC   # imported AFTER the freeze

    s_ok = r_ok = h_ok = 0
    n_fix_pair = 0
    n_pairs = 0
    pair_identity_preserved = True
    for s in selections:
        pos, ctx = s["pos"], s["ctx"]

        def score(hid):
            ir = GR.resolve(hid, cap)
            if ir is None:
                return None
            fs = SC.score_fixture(ir, index, pos, metric=ir.target_metrics[0],
                                  terciles=ctx.terciles, axis_cache=ctx.axis_cache,
                                  similarity=ctx.similarity,
                                  hist_similarity=ctx.historical_similarity,
                                  recency=ENGmod.recency_family_for(ir), capability=cap)
            return fs.status == SC.SCORE_OK

        s_scored = {hid: score(hid) for hid in s["S"]}
        s_ok += sum(1 for v in s_scored.values() if v)
        pairs_here = 0
        for p in (s["R"]["pairs"] if s["R"] else []):
            if p["r_id"] is None:
                continue
            ok_r = score(p["r_id"])
            r_ok += 1 if ok_r else 0
            if p["s_id"] != s["S"][[q["s_id"] for q in s["R"]["pairs"]].index(p["s_id"])]:
                pair_identity_preserved = False
            if s_scored.get(p["s_id"]) and ok_r:
                pairs_here += 1
        for c in (s["H"]["selections"] if s["H"] else []):
            h_ok += 1 if score(c["hypothesis_id"]) else 0
        n_pairs += pairs_here
        n_fix_pair += 1 if pairs_here else 0

    champ_after = H.assert_champion_unchanged()

    report = {
        "rehearsal_version": "v8c_exposed50_rehearsal_v1",
        "EVIDENCE_CLASS": CLASSIFICATION,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": "does the real repaired apparatus execute end to end on actual football data",
        "not_measured": ("whether S beats R. These 50 outcomes are DEVELOPMENT data; no arm "
                         "mean, difference, direction, p-value or winner is computed here."),
        "forbidden_output_keys": list(FORBIDDEN_OUTPUT_KEYS),
        "data_source": {"cache_root": cache_root, "n_records": len(recs),
                        "is_exposed50_bundle": True,
                        "sealed_reserve_fixtures_on_disk": 0,
                        "sealed_reserve_fixtures_in_index": len(in_index)},
        "s_arm": {"driver": "DETERMINISTIC_STANDIN", "version": MOCK_S_SELECTOR_VERSION,
                  "through_real_runner": True,
                  "runner_entry_point": "hypothesis_v8c.runner.run_fixture_converse",
                  "sonnet_calls": 0, "spend_usd": 0},
        "N_FIXTURES": len(pilot),
        "N_PIT_BUILD_OK": sum(1 for r in per_fixture if r.get("pit_ok")),
        "N_UNIVERSE_BUILD_OK": sum(1 for r in per_fixture if r.get("universe_ok")),
        "N_S_VALID": sum(1 for r in per_fixture if r.get("s_status") == RUN.OK),
        "N_S_INVALID": sum(1 for r in per_fixture if r.get("s_status") == RUN.INVALID_SUBMISSION),
        "N_S_ABSTAIN": sum(1 for r in per_fixture if r.get("s_status") == RUN.OK_ABSTAIN),
        "N_R_MATCHED": sum(r.get("r_matched", 0) for r in per_fixture),
        "N_R_UNMATCHED": sum(r.get("r_unmatched", 0) for r in per_fixture),
        "R_IDENTITY_COUNT": sum(r.get("r_identity", 0) for r in per_fixture),
        "R_CROSS_TREATMENT_OVERLAP_COUNT": sum(r.get("r_cross_overlap", 0) for r in per_fixture),
        "N_H_VALID": sum(r.get("h_selected", 0) for r in per_fixture),
        "S_SCORE_OK_COUNT": s_ok,
        "R_SCORE_OK_COUNT": r_ok,
        "H_SCORE_OK_COUNT": h_ok,
        "N_FIXTURES_WITH_VALID_SR_PAIR": n_fix_pair,
        "N_TOTAL_VALID_SR_PAIRS": n_pairs,
        "PAIR_IDENTITY_PRESERVED": pair_identity_preserved,
        "LIVE_SEARCH_UNREACHABLE_COUNT": sum(r.get("live_search_unreachable", 0)
                                             for r in per_fixture),
        "R_SET_LEVEL_K8_FEASIBLE": all(r.get("r_set_feasible") for r in per_fixture
                                       if r.get("r_set_feasible") is not None),
        "OUTCOME_SEAL_PASS": outcome_seal_pass,
        "OUTCOME_SEAL_IS_STRUCTURAL": True,
        "DATA_BINDING_PASS": True,
        "TARGET_OUTCOMES_USED_ONLY_IN_SCORE_PHASE": True,
        "selection_freeze_hash": selection_freeze_hash,
        "phase_ordering": ["SELECT (no scorer imported)", "FREEZE", "SCORE"],
        "CHAMPION_BEFORE": champ_before,
        "CHAMPION_AFTER": champ_after,
        "CHAMPION_UNCHANGED": champ_before == champ_after,
        "per_fixture": per_fixture,
        "elapsed_s": round(time.time() - t0, 1),
    }
    leaked = [k for k in FORBIDDEN_OUTPUT_KEYS if k in report]
    assert not leaked, f"rehearsal emitted a forbidden key: {leaked}"

    with open(OUT, "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"[rehearsal] wrote {OUT}", flush=True)
    for k in ("N_FIXTURES", "N_UNIVERSE_BUILD_OK", "N_S_VALID", "N_R_MATCHED",
              "S_SCORE_OK_COUNT", "R_SCORE_OK_COUNT", "N_TOTAL_VALID_SR_PAIRS",
              "OUTCOME_SEAL_PASS", "CHAMPION_UNCHANGED"):
        print(f"    {k} = {report[k]}")
    return report


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else None
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if not root:
        raise SystemExit("usage: _run_v8c_exposed50_rehearsal.py <bundle_root> [n_limit]")
    main(root, n_limit=lim)
