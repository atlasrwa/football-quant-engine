"""Repeatability hardening study runner (patch §6, §7).

Selects a deterministic stratified HARDENING_CONTROL_SET, builds the NEUTRALIZED runtime
packet for each fixture, runs k=3 identical hardened calls per packet, and measures
FIELD-LEVEL agreement + semantic severity (repeatability.py). It then DIAGNOSES where the
instability comes from (patch §7) BEFORE any aggregation is applied (aggregation is a separate
study, §31-§33): it attributes each unstable mechanism to the most likely cause using packet
signals (small-N, high shrinkage, provider disagreement, formation-conditioned, ontology
overlap) rather than blindly majority-voting.

Writes (research/llm_matchup/out/hardening/):
  * repeatability_field_level.csv   — one row per (fixture, mechanism_key) with field flags.
  * repeatability_severity.csv      — one row per (fixture, mechanism_key) with severity + cause.
  * repeatability_summary.json      — headline stats + per-stratum stability + diagnosis.
  * hardened_call_manifest.csv      — one row per call (provenance, tokens, cost, cache).
  * llm_states_hardening.jsonl      — every call's validated state (or reject metadata).

Run: .venv/bin/python -m src.research.llm_matchup.hardening.run_repeatability [N] [K]
"""
from __future__ import annotations
import os, sys, csv, json, time

from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup.hardening import sampling as SMP
from src.research.llm_matchup.hardening import neutralize as NZ
from src.research.llm_matchup.hardening import adapter_v3 as A3
from src.research.llm_matchup.hardening import repeatability as REP
from src.research.llm_matchup.hardening import feature_matrix as FM
from src.research.llm_matchup.hardening import versions_v2 as V2

OUT = "/home/ubuntu/research/llm_matchup/out/hardening"

CALL_MANIFEST_HEADER = [
    "study", "fixture_id", "competition", "packet_hash", "call_index", "status",
    "generation_id", "schema_version", "prompt_version", "packet_schema_version",
    "resolved_model_id", "input_tokens", "output_tokens", "latency_s", "cost_usd",
    "cache_hit", "reject_field", "reject_reason", "created_unix",
]


def _diagnose_cause(mech_key: str, packet: dict, field_row: dict) -> str:
    """Attribute an unstable mechanism to the most likely instability source (patch §7).
    Deterministic priority order; returns STABLE when worst_severity<=1."""
    if field_row["worst_severity"] <= 1:
        return "STABLE"
    mech = mech_key.split(":", 1)[1]
    # gather packet signals for evidence allowed to this mechanism
    from src.research.llm_matchup import ontology as ONT
    allow = ONT.allowed_metric_prefixes(mech) if mech in ONT.MECHANISMS else []
    rel_ns = []
    provs = set()
    is_formation = mech.startswith("FORMATION")
    for e in packet["evidence"]:
        m = e.get("metric", "")
        if any(m == a or m.startswith(a) or a in m for a in allow):
            rel_ns.append(e.get("sample_n") or 0)
            provs.add(e.get("source_provider"))
    small_n = bool(rel_ns) and (sorted(rel_ns)[len(rel_ns) // 2] <= 4)
    multi_prov = len({p for p in provs if p in ("thestatsapi", "footystats")}) >= 2

    if not field_row["presence_stable"]:
        return "PRESENCE_INSTABILITY"          # mechanism appears/disappears across calls
    if field_row["worst_severity"] == 4:
        return "RESOLVED_VS_UNCERTAIN_FLIP"     # SUPPORTED<->UNKNOWN/CONFLICTED
    if small_n:
        return "SMALL_SAMPLE_AMBIGUITY"
    if multi_prov:
        return "PROVIDER_DISAGREEMENT"
    if is_formation:
        return "FORMATION_CONDITIONING_AMBIGUITY"
    return "ONTOLOGY_BOUNDARY_OR_MODEL_NOISE"   # residual: ambiguous ontology or inference noise


def run(n: int = 40, k: int = None, max_scan: int = 200, use_cache: bool = True):
    k = k or V2.REPEATABILITY_CALLS
    os.makedirs(OUT, exist_ok=True)
    ctx = H.HarnessContext(enrich_halves=False)
    picks = SMP.select_stratified(ctx, n=n, max_scan=max_scan)
    print(f"repeatability: selected {len(picks)} stratified fixtures, k={k} calls each")

    field_rows_all, sev_rows_all, call_rows, states_out = [], [], [], []
    feature_rows_all = []
    per_stratum = {}   # stratum -> [semantically_stable bool per mechanism]
    cause_counts = {}
    total_cost = 0.0

    for pi, p in enumerate(picks):
        cand = p.candidate
        real_pkt = ctx.build_packet(cand, include_formation=True, projected=True)
        packet = NZ.neutralize_packet(real_pkt)   # runtime default: neutral identifiers
        # persist the raw input feature matrix for this packet (patch §18) — the neutralized
        # packet is what Sonnet actually saw, so the surrogate is tested on the true inputs.
        feature_rows_all.extend(FM.extract_feature_rows(packet))
        results = A3.analyze_k(packet, k=k, use_cache=use_cache)
        states = []
        for r in results:
            m = r.manifest
            cost = A3.estimate_cost_usd(m.get("input_tokens"), m.get("output_tokens"))
            total_cost += cost
            call_rows.append({
                "study": "repeatability", "fixture_id": p.fixture_id, "competition": p.competition,
                "packet_hash": packet["packet_hash"], "call_index": m.get("call_index"),
                "status": r.status, "generation_id": m.get("generation_id"),
                "schema_version": m.get("schema_version"), "prompt_version": m.get("prompt_version"),
                "packet_schema_version": m.get("packet_schema_version"),
                "resolved_model_id": m.get("resolved_model_id"),
                "input_tokens": m.get("input_tokens"), "output_tokens": m.get("output_tokens"),
                "latency_s": m.get("latency_s"), "cost_usd": cost, "cache_hit": m.get("cache_hit"),
                "reject_field": m.get("reject_field"), "reject_reason": m.get("reject_reason"),
                "created_unix": int(time.time()),
            })
            states_out.append({"study": "repeatability", "fixture_id": p.fixture_id,
                               "call_index": m.get("call_index"), "status": r.status,
                               "state": r.state, "manifest": m})
            states.append(r.state if r.status == "OK" else None)

        ok_states = [s for s in states if s]
        if len(ok_states) < 2:
            statuses = [r.status for r in results]
            print(f"  [{pi+1}/{len(picks)}] {p.fixture_id}: <2 OK calls ({statuses}); skipping field analysis")
            continue
        field_rows = REP.field_level_agreement(states)
        for fr in field_rows:
            cause = _diagnose_cause(fr["mechanism_key"], packet, fr)
            cause_counts[cause] = cause_counts.get(cause, 0) + 1
            base = {"fixture_id": p.fixture_id, "competition": p.competition,
                    "strata": "|".join(sorted(p.strata))}
            field_rows_all.append({**base, **fr})
            sev_rows_all.append({**base, "mechanism_key": fr["mechanism_key"],
                                 "worst_severity": fr["worst_severity"],
                                 "presence_stable": fr["presence_stable"],
                                 "status_agree": fr["status_agree"],
                                 "instability_cause": cause,
                                 "statuses": fr["statuses"], "confidences": fr["confidences"]})
            for s in p.strata:
                per_stratum.setdefault(s, []).append(fr["worst_severity"] <= 1)

        summ = REP.summarize(field_rows)
        print(f"  [{pi+1}/{len(picks)}] {p.fixture_id} [{','.join(sorted(p.strata))[:40]}] "
              f"sem_stable={summ['semantically_stable_frac']} severe={summ['severe_disagreement_frac']}")

    # write artifacts
    _write_csv(os.path.join(OUT, "repeatability_field_level.csv"), field_rows_all)
    _write_csv(os.path.join(OUT, "repeatability_severity.csv"), sev_rows_all)
    _append_csv(os.path.join(OUT, "hardened_call_manifest.csv"), call_rows, CALL_MANIFEST_HEADER)
    with open(os.path.join(OUT, "llm_states_hardening.jsonl"), "a") as f:
        for s in states_out:
            f.write(json.dumps(s, default=str) + "\n")

    # persist the raw input feature matrix for the surrogate ladder (patch §18)
    if feature_rows_all:
        FM.write_feature_matrix(feature_rows_all)

    overall = REP.summarize(field_rows_all) if field_rows_all else {}
    stratum_stability = {s: round(sum(v) / len(v), 4) for s, v in sorted(per_stratum.items())}
    n_calls = len(call_rows)
    n_ok = sum(1 for c in call_rows if c["status"] == "OK")
    summary = {
        "study": "repeatability", "generation_id": V2.GENERATION_ID,
        "n_fixtures": len(picks), "k_calls": k, "n_calls": n_calls, "n_ok_calls": n_ok,
        "n_mechanism_keys": len(field_rows_all),
        "overall": overall,
        "per_stratum_semantic_stability": stratum_stability,
        "instability_cause_counts": cause_counts,
        "cost": {"total_usd": round(total_cost, 4),
                 "usd_per_fixture": round(total_cost / max(len(picks), 1), 4),
                 "usd_per_call": round(total_cost / max(n_calls, 1), 4)},
        "strata_coverage": SMP.strata_coverage(picks),
        "created_unix": int(time.time()),
    }
    json.dump(summary, open(os.path.join(OUT, "repeatability_summary.json"), "w"),
              indent=2, default=str)
    print(json.dumps({k2: summary[k2] for k2 in
                      ("n_fixtures", "n_calls", "n_ok_calls", "overall",
                       "instability_cause_counts", "cost")}, indent=2, default=str))
    return summary


def _write_csv(path, rows):
    if not rows:
        open(path, "w").close()
        return
    cols = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _append_csv(path, rows, header):
    exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in header})


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    k = int(sys.argv[2]) if len(sys.argv) > 2 else None
    run(n=n, k=k)
