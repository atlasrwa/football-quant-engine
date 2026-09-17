"""Executes the preregistered V8B.1 50-fixture operational tranche under runner v3.

HARD INVARIANTS enforced per fixture; ANY violation -> immediate STOP (raise TrancheStop,
persist partial telemetry, do NOT continue the 50). Inspects OPERATIONAL telemetry only:
never reads a target outcome, never inspects football/hypothesis quality, never tunes.

Selections are frozen into a sealed store. Target outcomes remain sealed.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT)

TRANCHE_MANIFEST = f"{ROOT}/research/hypothesis_engine/V8B1_TRANCHE_50_MANIFEST.json"
OUT_TELEMETRY = f"{ROOT}/research/hypothesis_engine/V8B1_TRANCHE_50_TELEMETRY.json"
OUT_SELECTIONS = f"{ROOT}/research/hypothesis_engine/V8B1_TRANCHE_50_SELECTIONS.json"

CHAMPION_ARTIFACT = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

PRICE_INPUT_PER_1K = 0.003
PRICE_OUTPUT_PER_1K = 0.015

VALID_TERMINAL = {"OK", "OK_ABSTAIN"}


class TrancheStop(Exception):
    pass


def _sha(path):
    with open(f"{ROOT}/{path}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _cost(i, o):
    return round((i or 0) / 1000.0 * PRICE_INPUT_PER_1K + (o or 0) / 1000.0 * PRICE_OUTPUT_PER_1K, 6)


def _check_invariants(fid, res, seen_ids):
    """Return list of invariant violations for one fixture result (empty => clean)."""
    m = res.manifest
    v = []
    # 1. fixture identity: the runner's manifest fixture must be exactly the preregistered one
    if m.get("fixture_id") != fid:
        v.append(f"IDENTITY: manifest fixture_id={m.get('fixture_id')!r} != preregistered {fid!r}")
    # 2. no duplicate execution
    if fid in seen_ids:
        v.append(f"DUPLICATE: fixture {fid} executed more than once")
    # 3. search cap
    sc = m.get("search_calls")
    if sc is None:
        v.append("ACCOUNTING: search_calls missing")
    elif sc > 6:
        v.append(f"CAP_BREACH: search_calls={sc} > 6")
    # 4. max_search_calls / max_tool_turns frozen
    if m.get("max_search_calls") != 6:
        v.append(f"CONFIG_DRIFT: max_search_calls={m.get('max_search_calls')} != 6")
    if m.get("max_tool_turns") != 7:
        v.append(f"CONFIG_DRIFT: max_tool_turns={m.get('max_tool_turns')} != 7")
    # 5. complete accounting on any terminal-with-usage path
    if res.status in VALID_TERMINAL:
        u = m.get("usage") or {}
        for k in ("inputTokens", "outputTokens", "totalTokens"):
            if u.get(k) is None:
                v.append(f"ACCOUNTING: usage.{k} missing on {res.status}")
        for k in ("converse_calls", "search_calls", "latency_s"):
            if m.get(k) is None:
                v.append(f"ACCOUNTING: {k} missing on {res.status}")
    return v


def main():
    tm = json.load(open(TRANCHE_MANIFEST))
    fixture_ids = tm["fixture_ids_ordered"]
    assert len(fixture_ids) == 50 and len(set(fixture_ids)) == 50

    # pre-run scientific + champion + tranche-manifest integrity (read-only)
    fm = json.load(open(f"{ROOT}/research/hypothesis_engine/V8B1_FREEZE_MANIFEST.json"))
    drift = [p for p, h in fm["artifact_hashes"].items() if _sha(p) != h]
    if drift:
        raise TrancheStop(f"scientific artifact drift before run: {drift}")
    if _sha(CHAMPION_ARTIFACT) != CHAMPION_EXPECTED:
        raise TrancheStop("CHAMPION changed before run")
    live_tm_hash = hashlib.sha256(json.dumps(
        {k: v for k, v in tm.items() if k != "tranche_manifest_hash"},
        sort_keys=True, default=str).encode()).hexdigest()
    if live_tm_hash != tm["tranche_manifest_hash"]:
        raise TrancheStop("tranche manifest hash mismatch (tampered)")

    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import execution as EX
    from src.research.hypothesis_v71 import recency as REC
    from src.research.hypothesis_v8b1 import packet as PK
    from src.research.hypothesis_v8b1 import prompt as PR
    from src.research.hypothesis_v8b1 import runner as RN

    model_id = tm["model_id"]
    region = tm["region"]
    config_stamp = tm["config_stamp"]
    assert model_id == "us.anthropic.claude-sonnet-4-6"
    assert RN.MAX_SEARCH_CALLS == 6 and RN.version_stamp()["search_budget_is_true_execution_cap"]

    cap = CAP.CapabilityContract(
        json.load(open(f"{ROOT}/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json")))
    recs = CI.load_records(include_fresh=True)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)
    ctx = EX.build_context(index)
    recency_family = tuple(REC.family()) + (REC.UniformRecency(),)

    telemetry = []
    selections_store = []
    seen_ids = set()
    t_start = time.time()

    for i, fid in enumerate(fixture_ids):
        pos = index.pos_of_fixture.get(fid)
        if pos is None:
            # not-in-index is a hard provenance failure for a preregistered fixture
            _persist(telemetry, selections_store, tm, live_tm_hash, stopped=True,
                     stop_reason=f"FIXTURE_NOT_IN_INDEX: {fid}")
            raise TrancheStop(f"preregistered fixture {fid} not in live index")

        packet = PK.build_packet(index, pos, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                                 recency_family)
        # outcome-blindness invariant on the packet
        if packet.get("reads_target_outcome") is not False:
            _persist(telemetry, selections_store, tm, live_tm_hash, stopped=True,
                     stop_reason=f"OUTCOME_LEAKAGE: packet reads_target_outcome for {fid}")
            raise TrancheStop(f"packet for {fid} not outcome-blind")

        print(f"[tranche] {i+1}/50 fixture {fid} packet={packet['packet_hash'][:12]}", flush=True)
        res = RN.run_fixture(packet, cap, model_id=model_id, region=region,
                             config_stamp=config_stamp, use_cache=True)

        violations = _check_invariants(fid, res, seen_ids)
        seen_ids.add(fid)

        m = res.manifest
        rec = {
            "order": i, "fixture_id": fid, "packet_hash": packet["packet_hash"],
            "status": res.status,
            "termination_reason": m.get("termination_reason"),
            "converse_calls": m.get("converse_calls"),
            "search_calls": m.get("search_calls"),
            "usage": m.get("usage"),
            "latency_s": m.get("latency_s"),
            "cache_hit": m.get("cache_hit"),
            "n_final_selections": len(res.final_selections),
            "call_state": m.get("call_state"),
            "error": m.get("error"),
            "cost_usd": _cost((m.get("usage") or {}).get("inputTokens"),
                              (m.get("usage") or {}).get("outputTokens")),
            "invariant_violations": violations,
        }
        telemetry.append(rec)
        # sealed selections store: store only fixture id + selection hypothesis_ids + trace
        # (NO target outcome is ever read or stored).
        selections_store.append({
            "fixture_id": fid, "status": res.status,
            "final_selections": res.final_selections,
            "research_trace": res.research_trace,
            "packet_hash": packet["packet_hash"],
        })
        print(f"    -> {res.status} reason={m.get('termination_reason')} "
              f"search={m.get('search_calls')} conv={m.get('converse_calls')} "
              f"sel={len(res.final_selections)} cost=${rec['cost_usd']}", flush=True)

        if violations:
            _persist(telemetry, selections_store, tm, live_tm_hash, stopped=True,
                     stop_reason=f"INVARIANT_VIOLATION at {fid}: {violations}")
            raise TrancheStop(f"hard invariant violation at {fid}: {violations}")

    # post-run integrity re-check
    drift = [p for p, h in fm["artifact_hashes"].items() if _sha(p) != h]
    champ_ok = _sha(CHAMPION_ARTIFACT) == CHAMPION_EXPECTED
    _persist(telemetry, selections_store, tm, live_tm_hash, stopped=False,
             stop_reason=None, post_drift=drift, post_champion_ok=champ_ok,
             wall_s=round(time.time() - t_start, 1))
    print(f"\n[tranche] complete: {len(telemetry)} fixtures. post-drift={drift} "
          f"champion_ok={champ_ok}")


def _persist(telemetry, selections, tm, live_tm_hash, *, stopped, stop_reason,
             post_drift=None, post_champion_ok=None, wall_s=None):
    payload = {
        "tranche_manifest_hash": tm["tranche_manifest_hash"],
        "tranche_manifest_hash_recomputed": live_tm_hash,
        "n_planned": len(tm["fixture_ids_ordered"]),
        "n_executed": len(telemetry),
        "stopped_early": stopped,
        "stop_reason": stop_reason,
        "post_run_scientific_drift": post_drift,
        "post_run_champion_ok": post_champion_ok,
        "wall_clock_s": wall_s,
        "model_id": tm["model_id"],
        "results": telemetry,
        "target_outcomes_viewed": False,
    }
    with open(OUT_TELEMETRY, "w") as f:
        json.dump(payload, f, indent=1, default=str)
    with open(OUT_SELECTIONS, "w") as f:
        json.dump({"tranche_manifest_hash": tm["tranche_manifest_hash"],
                   "target_outcomes_sealed": True,
                   "selections": selections}, f, indent=1, default=str)


if __name__ == "__main__":
    try:
        main()
    except TrancheStop as e:
        print(f"\n*** TRANCHE STOPPED: {e} ***", flush=True)
        sys.exit(3)
