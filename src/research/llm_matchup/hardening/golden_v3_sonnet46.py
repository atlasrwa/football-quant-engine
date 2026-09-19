"""LLM_MATCHUP_V3_SONNET46 golden batch harness -- the Sonnet 4.6 arm.

FULLY SEPARATE from the Sonnet 4.5 arm. This module owns its own:
    out/v3_sonnet46/golden_v3_sonnet46_fixture_manifest.json   (manifest)
    out/v3_sonnet46/golden_v3_sonnet46_execution_ledger.json   (execution ledger)
    out/v3_sonnet46/golden_v3_sonnet46_states.jsonl            (structured states)
    out/v3_sonnet46/golden_v3_sonnet46_summary.json            (summary)
    out/v3_sonnet46/cache/                                     (LLM response cache namespace)

It NEVER reads or writes anything under out/hardening_v3/ except to READ the frozen 4.5
fixture manifest, from which it copies the fixture id list VERBATIM. That read is the whole
point: the two arms must analyse the SAME 20 fixtures, so the selection is inherited rather
than resampled. `build_or_load_manifest` refuses to proceed unless the resulting
fixture_manifest_hash equals the frozen 4.5 one.

WHAT IS SHARED WITH THE 4.5 ARM (deliberately, by reference -- never re-implemented):
  * evidence packet construction      phaseb_harness.HarnessContext.build_packet
  * fixture selection                 sampling.select_stratified (same n / max_scan)
  * neutralization                    neutralize_v3.neutralize_for_llm_v2
  * prompt / output schema / ontology  prompt_v4 / schema_v3 / ontology
  * validator                         validator_v3 (via adapter_v4)
  * error classification              resume_golden_v3.classify_bedrock_error
WHAT DIFFERS: the Bedrock model identity (versions_v3_sonnet46) and the artifact namespace.

The deterministic evidence packets ARE reused (identical inputs => identical hashes, which we
assert against the 4.5 states file). The LLM RESPONSE CACHE is NOT reused: adapter_v4's cache
key binds the resolved model id, and this module points the adapter at a different cache_dir,
so a 4.5 response can never be served as a 4.6 observation.
"""
from __future__ import annotations
import json
import os
import statistics
import time

from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup.hardening import sampling as SMP
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3
from src.research.llm_matchup.hardening import golden_manifest as GM
from src.research.llm_matchup.hardening import audit_prespend as AP
from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening import resume_golden_v3 as RG
from src.research.llm_matchup.hardening import versions_v3 as V45
from src.research.llm_matchup.hardening import versions_v3_sonnet46 as V46
from src.research.llm_matchup.hardening import prompt_v4 as PR4
from src.research.llm_matchup.hardening import schema_v3 as SCH3
from src.research.llm_matchup.hardening import formation_structure as FS
from src.research.llm_matchup import ontology as ONT

# --- the 4.6 arm's OWN namespace ----------------------------------------------------------
OUT = "/home/ubuntu/research/llm_matchup/out/v3_sonnet46"
CACHE_DIR = os.path.join(OUT, "cache")
MANIFEST_PATH = os.path.join(OUT, "golden_v3_sonnet46_fixture_manifest.json")
LEDGER_PATH = os.path.join(OUT, "golden_v3_sonnet46_execution_ledger.json")
STATES_PATH = os.path.join(OUT, "golden_v3_sonnet46_states.jsonl")
SUMMARY_PATH = os.path.join(OUT, "golden_v3_sonnet46_summary.json")
PRESPEND_AUDIT_PATH = os.path.join(OUT, "golden_v3_sonnet46_prespend_audit.json")

# --- the 4.5 arm's frozen manifest (READ-ONLY; the source of the fixture selection) --------
SONNET45_MANIFEST_PATH = GM.MANIFEST_PATH
SONNET45_STATES_PATH = "/home/ubuntu/research/llm_matchup/out/hardening_v3/golden_v3_states.jsonl"


def content_hashes() -> dict:
    """The shared scientific content hashes, recorded per fixture (mandate SS11)."""
    import hashlib
    return {
        "prompt_hash": PR4.prompt_content_hash(),
        "schema_hash": SCH3.schema_content_hash(),
        "ontology_hash": hashlib.sha256(
            json.dumps(ONT.to_dict(), sort_keys=True, default=str).encode()).hexdigest(),
        "neutralization_hash": GM._sha256_file(GM.NEUTRALIZE_MODULE_PATH),
        "formation_structure_hash": FS.structure_content_hash(),
    }


# ------------------------------------------------------------------ manifest
def build_or_load_manifest() -> dict:
    """Create (or load) the 4.6 manifest, inheriting the 4.5 fixture selection VERBATIM.

    Fails closed if the frozen 4.5 manifest is missing or if the inherited fixture list does
    not reproduce the 4.5 fixture_manifest_hash -- i.e. we can prove we are testing the same
    fixtures, not an easier resample.
    """
    frozen45 = GM.load_manifest(SONNET45_MANIFEST_PATH)
    if frozen45 is None:
        raise RuntimeError(f"frozen Sonnet 4.5 manifest not found at {SONNET45_MANIFEST_PATH}; "
                           "refusing to invent a fixture selection")
    if frozen45.get("generation_id") != V45.GENERATION_ID:
        raise RuntimeError(f"expected 4.5 manifest generation_id={V45.GENERATION_ID!r}, "
                           f"got {frozen45.get('generation_id')!r}")

    fixture_ids = list(frozen45["fixture_ids"])
    sp = frozen45["generation_fingerprint"]["sampling_params"]
    n, max_scan = sp["n"], sp["max_scan"]

    existing = GM.load_manifest(MANIFEST_PATH)
    if existing is not None:
        if existing["fixture_manifest_hash"] != frozen45["fixture_manifest_hash"]:
            raise RuntimeError("existing 4.6 manifest does not match the frozen 4.5 fixture "
                               "selection; refusing to continue")
        return existing

    m46 = GM.build_manifest(
        fixture_ids, n=n, max_scan=max_scan, gen=V46,
        note=("Sonnet 4.6 arm (LLM_MATCHUP_V3_SONNET46). Fixture ids are INHERITED VERBATIM "
              "from the frozen Sonnet 4.5 manifest at "
              f"{SONNET45_MANIFEST_PATH} (fixture_manifest_hash "
              f"{frozen45['fixture_manifest_hash']}); NOT resampled, NOT reordered, NOT "
              "reselected. The only intended difference vs the 4.5 generation fingerprint is "
              "bedrock_model_id + generation_id."))
    if m46["fixture_manifest_hash"] != frozen45["fixture_manifest_hash"]:
        raise RuntimeError(
            f"inherited fixture list hashed to {m46['fixture_manifest_hash']} but the frozen "
            f"4.5 manifest says {frozen45['fixture_manifest_hash']}")
    m46["inherited_from"] = {
        "path": SONNET45_MANIFEST_PATH,
        "generation_id": frozen45["generation_id"],
        "fixture_manifest_hash": frozen45["fixture_manifest_hash"],
    }
    os.makedirs(OUT, exist_ok=True)
    status = GM.save_manifest_if_absent(m46, MANIFEST_PATH)
    m46["_save_status"] = status
    return m46


def manifest_vs_45_fingerprint_diff() -> dict:
    """Machine-checkable proof that ONLY model id + generation_id differ (mandate SS5, SS29.3)."""
    frozen45 = GM.load_manifest(SONNET45_MANIFEST_PATH)
    sp = frozen45["generation_fingerprint"]["sampling_params"]
    cur46 = GM.current_generation_fingerprint(n=sp["n"], max_scan=sp["max_scan"], gen=V46)
    f45 = frozen45["generation_fingerprint"]
    differing = {}
    for k in sorted(set(f45) | set(cur46)):
        if k == "sampling_params":
            continue
        if f45.get(k) != cur46.get(k):
            differing[k] = {"sonnet45_frozen": f45.get(k), "sonnet46_current": cur46.get(k)}
    return {
        "differing_fields": sorted(differing),
        "detail": differing,
        "identical_fields": sorted(k for k in f45 if k != "sampling_params"
                                   and f45.get(k) == cur46.get(k)),
    }


# ------------------------------------------------------------------ ledger
def load_ledger() -> dict:
    if os.path.exists(LEDGER_PATH):
        return json.load(open(LEDGER_PATH))
    return {"study": "golden_v3_sonnet46_execution_ledger",
            "generation_id": V46.GENERATION_ID,
            "model_id": V46.DEFAULT_BEDROCK_MODEL_ID,
            "fixtures": {}}


def save_ledger(ledger: dict) -> None:
    os.makedirs(OUT, exist_ok=True)
    tmp = LEDGER_PATH + ".tmp"
    json.dump(ledger, open(tmp, "w"), indent=2, default=str)
    os.replace(tmp, LEDGER_PATH)


# ------------------------------------------------------------------ state metrics
def state_metrics(state: dict | None) -> dict:
    """Objective, non-subjective structural metrics (mandate SS13). No 'smartness score'."""
    if not state:
        return {}
    a = state.get("team_a_states", []) or []
    b = state.get("team_b_states", []) or []
    m = state.get("matchup_states", []) or []
    team_items = a + b
    all_items = team_items + m

    def support_ids(it):
        return list(it.get("evidence_ids", []) or []) + \
               list(it.get("supporting_evidence_ids", []) or [])

    n_unknown = sum(1 for it in all_items
                    if (it.get("level") or it.get("assessment")) == "UNKNOWN")
    n_conflicted = sum(1 for it in all_items
                       if (it.get("level") or it.get("assessment")) == "CONFLICTED")
    n_unsupported = sum(1 for it in all_items if len(support_ids(it)) == 0)
    n_search_performed = sum(1 for it in all_items
                             if it.get("counter_evidence_search") == "PERFORMED")
    n_with_counter = sum(1 for it in all_items if (it.get("counter_evidence_ids") or []))
    support_counts = [len(support_ids(it)) for it in all_items]
    counter_counts = [len(it.get("counter_evidence_ids") or []) for it in all_items]

    # Redundant mechanism = the SAME mechanism id emitted more than once within the SAME
    # collection. Objectively definable; no judgement involved.
    def redundant(items):
        seen, dupes = set(), 0
        for it in items:
            mid = it.get("mechanism")
            if mid in seen:
                dupes += 1
            seen.add(mid)
        return dupes

    return {
        "n_team_a_states": len(a), "n_team_b_states": len(b), "n_matchup_states": len(m),
        "n_mechanisms_total": len(all_items),
        "n_distinct_mechanisms": len({it.get("mechanism") for it in all_items}),
        "n_redundant_mechanisms": redundant(a) + redundant(b) + redundant(m),
        "n_unknown": n_unknown,
        "n_conflicted": n_conflicted,
        "n_unsupported_mechanisms": n_unsupported,
        "unknown_rate": round(n_unknown / len(all_items), 4) if all_items else None,
        "conflicted_rate": round(n_conflicted / len(all_items), 4) if all_items else None,
        "unsupported_mechanism_rate": (round(n_unsupported / len(all_items), 4)
                                       if all_items else None),
        "redundant_mechanism_rate": (round((redundant(a) + redundant(b) + redundant(m))
                                           / len(all_items), 4) if all_items else None),
        "n_counter_evidence_search_performed": n_search_performed,
        "counter_evidence_search_performed_rate": (round(n_search_performed / len(all_items), 4)
                                                    if all_items else None),
        "n_states_with_counter_evidence": n_with_counter,
        "counter_evidence_presence_rate": (round(n_with_counter / len(all_items), 4)
                                            if all_items else None),
        "support_evidence_total": sum(support_counts),
        "counter_evidence_total": sum(counter_counts),
        "support_evidence_mean_per_state": (round(statistics.mean(support_counts), 3)
                                            if support_counts else None),
        "counter_evidence_mean_per_state": (round(statistics.mean(counter_counts), 3)
                                             if counter_counts else None),
        "support_evidence_ids": sorted({e for it in all_items for e in support_ids(it)}),
        "counter_evidence_ids": sorted({e for it in all_items
                                        for e in (it.get("counter_evidence_ids") or [])}),
    }


# ------------------------------------------------------------------ prespend audit
def run_prespend_audit(limit: int | None = None, persist: bool = True) -> dict:
    """Render + audit the literal serialized request for every manifest fixture. ZERO Bedrock
    calls. This is the gate that must pass BEFORE the first paid 4.6 call (mandate SS9)."""
    manifest = build_or_load_manifest()
    sp = manifest["generation_fingerprint"]["sampling_params"]
    ctx = H.HarnessContext(enrich_halves=False)
    picks = {p.fixture_id: p for p in SMP.select_stratified(ctx, n=sp["n"],
                                                            max_scan=sp["max_scan"])}
    fids = manifest["fixture_ids"][:limit] if limit else manifest["fixture_ids"]

    reports, agg = [], {}
    for fid in fids:
        src = ctx.build_packet(picks[fid].candidate, include_formation=True, projected=True)
        neu = NZ3.neutralize_for_llm_v2(src)
        rep = AP.audit_prespend(neu, src)
        reports.append(rep)
        for cat, items in rep["categories"].items():
            agg[cat] = agg.get(cat, 0) + len(items)

    out = {
        "study": "golden_v3_sonnet46_prespend_audit",
        "generation_id": V46.GENERATION_ID,
        "audit_version": AP.AUDIT_PRESPEND_VERSION,
        "model_id": V46.DEFAULT_BEDROCK_MODEL_ID,
        "n_fixtures_audited": len(reports),
        "category_leak_totals": agg,
        "n_leaks_total": sum(agg.values()),
        "all_clean": all(r["clean"] for r in reports),
        "all_existing_audit_clean": all(r["existing_audit_clean"] for r in reports),
        "created_unix": int(time.time()),
        "reports": reports,
    }
    if persist:
        os.makedirs(OUT, exist_ok=True)
        json.dump(out, open(PRESPEND_AUDIT_PATH, "w"), indent=2, default=str)
    return out


# ------------------------------------------------------------------ live run
def run(limit: int | None = None, use_cache: bool = True, dry_run: bool = False,
        require_clean_audit: bool = True) -> dict:
    """Idempotent, quota-safe 4.6 golden batch (mandates SS10, SS11, SS14).

    `limit` caps how many NOT-YET-SUCCESS fixtures are attempted in this invocation (limit=1
    is the single-call connectivity smoke). Fixtures already SUCCESS in the 4.6 ledger consume
    zero new calls. The instant a call classifies as AWS_DAILY_TOKEN_QUOTA the batch stops and
    every remaining fixture is recorded NOT_ATTEMPTED -- infrastructure censoring, never
    semantic failure.
    """
    manifest = build_or_load_manifest()
    sp = manifest["generation_fingerprint"]["sampling_params"]

    # Generation guard: the 4.6 manifest must match CURRENT 4.6 code exactly.
    cur = GM.current_generation_fingerprint(n=sp["n"], max_scan=sp["max_scan"], gen=V46)
    compat = GM.check_compatible(manifest, cur)
    if not compat["compatible"]:
        return {"status": "ABORT_GENERATION_MISMATCH", "mismatches": compat["mismatches"]}
    if manifest.get("generation_id") != V46.GENERATION_ID:
        return {"status": "ABORT_GENERATION_ID_MISMATCH",
                "manifest_generation_id": manifest.get("generation_id")}

    ledger = load_ledger()
    fixtures = ledger.setdefault("fixtures", {})
    ledger["fixture_manifest_hash"] = manifest["fixture_manifest_hash"]
    ledger["model_id"] = V46.DEFAULT_BEDROCK_MODEL_ID
    ledger["content_hashes"] = content_hashes()

    ctx = None
    picks = None
    ch = content_hashes()
    stopped_for_quota = False
    attempted = 0
    results = []
    new_states = []

    for fid in manifest["fixture_ids"]:
        entry = fixtures.setdefault(fid, {"status": "NOT_ATTEMPTED", "attempts": []})
        if entry["status"] == "SUCCESS":
            results.append({"fixture_id": fid, "status": "SUCCESS", "source": "ledger_idempotent"})
            continue
        if stopped_for_quota:
            entry["status"] = "NOT_ATTEMPTED"
            entry["censored_reason"] = "AWS_DAILY_TOKEN_QUOTA"
            results.append({"fixture_id": fid, "status": "NOT_ATTEMPTED", "source": "quota_stop"})
            continue
        if limit is not None and attempted >= limit:
            results.append({"fixture_id": fid, "status": "NOT_ATTEMPTED", "source": "limit"})
            continue

        if ctx is None:
            ctx = H.HarnessContext(enrich_halves=False)
            picks = {p.fixture_id: p for p in SMP.select_stratified(
                ctx, n=sp["n"], max_scan=sp["max_scan"])}

        src = ctx.build_packet(picks[fid].candidate, include_formation=True, projected=True)
        neu = NZ3.neutralize_for_llm_v2(src)

        audit = AP.audit_prespend(neu, src)
        if require_clean_audit and not audit["clean"]:
            entry["status"] = "BLOCKED_PRESPEND_AUDIT"
            entry["prespend_audit_counts"] = audit["counts"]
            results.append({"fixture_id": fid, "status": "BLOCKED_PRESPEND_AUDIT",
                            "counts": audit["counts"]})
            break

        if dry_run:
            results.append({"fixture_id": fid, "status": "WOULD_ATTEMPT",
                            "packet_hash": neu["packet_hash"],
                            "source_evidence_packet_hash": neu["source_evidence_packet_hash"],
                            "audit_clean": audit["clean"]})
            attempted += 1
            continue

        attempted += 1
        res = A4.analyze_matchup_v4(neu, use_cache=use_cache, gen=V46, cache_dir=CACHE_DIR,
                                    capture_rejected_raw=True)
        err_class = None if res.status == "OK" else RG.classify_bedrock_error(
            res.manifest.get("error"))

        met = state_metrics(res.state) if res.status == "OK" else {}
        cost = A4.estimate_cost_usd(res.manifest.get("input_tokens"),
                                    res.manifest.get("output_tokens"))
        attempt = {
            "unix": int(time.time()),
            "status": res.status,
            "error_class": err_class,
            "error": res.manifest.get("error"),
            "cache_hit": res.manifest.get("cache_hit"),
            "model_id": res.manifest.get("model_id"),
            "resolved_model_id": res.manifest.get("resolved_model_id"),
            "region": res.manifest.get("region"),
            "latency_s": res.manifest.get("latency_s"),
            "input_tokens": res.manifest.get("input_tokens"),
            "output_tokens": res.manifest.get("output_tokens"),
            "total_tokens": ((res.manifest.get("input_tokens") or 0)
                             + (res.manifest.get("output_tokens") or 0)) or None,
            "cost_usd_estimate": cost if res.status == "OK" else None,
            "reject_field": res.manifest.get("reject_field"),
            "reject_reason": res.manifest.get("reject_reason"),
        }
        entry["attempts"].append(attempt)
        entry.update({
            "source_evidence_packet_hash": neu["source_evidence_packet_hash"],
            "neutralized_packet_hash": neu["neutral_llm_packet_hash"],
            "model_id": V46.DEFAULT_BEDROCK_MODEL_ID,
            "resolved_model_id": attempt["resolved_model_id"],
            "generation_id": V46.GENERATION_ID,
            **ch,
            "prespend_audit_clean": audit["clean"],
            "request_text_sha256": audit["request_text_sha256"],
            "validation_result": ("ACCEPTED" if res.status == "OK"
                                  else ("VALIDATOR_REJECTED"
                                        if res.status == "LLM_STATE_REJECTED" else None)),
        })
        if met:
            entry["state_metrics"] = met

        if res.status == "OK":
            entry["status"] = "SUCCESS"
            results.append({"fixture_id": fid, "status": "SUCCESS", "source": "new_call",
                            "cache_hit": attempt["cache_hit"],
                            "output_tokens": attempt["output_tokens"]})
        elif res.status == "LLM_STATE_REJECTED":
            entry["status"] = "VALIDATOR_REJECTED"
            results.append({"fixture_id": fid, "status": "VALIDATOR_REJECTED",
                            "reject_field": attempt["reject_field"],
                            "reject_reason": attempt["reject_reason"]})
        elif err_class == "AWS_DAILY_TOKEN_QUOTA":
            entry["status"] = "AWS_DAILY_TOKEN_QUOTA"
            stopped_for_quota = True
            results.append({"fixture_id": fid, "status": "AWS_DAILY_TOKEN_QUOTA"})
        else:
            entry["status"] = err_class
            results.append({"fixture_id": fid, "status": err_class,
                            "error": attempt.get("error")})

        new_states.append({"study": "golden_v3_sonnet46", "fixture_id": fid,
                           "status": res.status, "state": res.state,
                           "manifest": res.manifest, "state_metrics": met})

        # DURABILITY: persist after EVERY paid call, not just at the end of the batch. A long
        # live batch that dies mid-flight (quota, timeout, interrupt) must never lose the
        # observations it already paid for -- otherwise a resume re-spends tokens on fixtures
        # that were already answered.
        save_ledger(ledger)
        os.makedirs(OUT, exist_ok=True)
        with open(STATES_PATH, "a") as f:
            f.write(json.dumps(new_states[-1], default=str) + "\n")

    if not dry_run:
        save_ledger(ledger)

    return {"status": "RAN", "dry_run": dry_run, "attempted": attempted,
            "stopped_for_quota": stopped_for_quota, "results": results,
            "n_new_states": len(new_states)}


# ------------------------------------------------------------------ summary
def _pct(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return {}
    s = sorted(vals)

    def p(q):
        if len(s) == 1:
            return s[0]
        i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
        return s[i]
    return {"n": len(s), "min": s[0], "max": s[-1],
            "mean": round(statistics.mean(s), 2),
            "median": round(statistics.median(s), 2),
            "p90": p(0.90)}


def summarize(persist: bool = True) -> dict:
    """Golden acceptance with HONEST denominators (mandate SS15): semantic denominators
    EXCLUDE infrastructure-censored calls."""
    manifest = build_or_load_manifest()
    ledger = load_ledger()
    fixtures = ledger.get("fixtures", {})
    manifest_ids = manifest["fixture_ids"]

    INFRA = {"AWS_DAILY_TOKEN_QUOTA", "READ_TIMEOUT", "THROTTLING_TRANSIENT",
             "OTHER_UNAVAILABLE"}
    accepted, rejected, infra, not_attempted = [], [], [], []
    for fid in manifest_ids:
        st = (fixtures.get(fid) or {}).get("status")
        if st == "SUCCESS":
            accepted.append(fid)
        elif st == "VALIDATOR_REJECTED":
            rejected.append(fid)
        elif st in INFRA:
            infra.append(fid)
        else:
            not_attempted.append(fid)

    completed = len(accepted) + len(rejected)          # SEMANTIC denominator
    in_toks, out_toks, tot_toks, lats, costs = [], [], [], [], []
    metrics_rows = []
    for fid in accepted:
        e = fixtures[fid]
        ok = [a for a in e.get("attempts", []) if a.get("status") == "OK"]
        if not ok:
            continue
        a = ok[-1]
        if not a.get("cache_hit"):
            in_toks.append(a.get("input_tokens"))
            out_toks.append(a.get("output_tokens"))
            tot_toks.append(a.get("total_tokens"))
            lats.append(a.get("latency_s"))
            costs.append(a.get("cost_usd_estimate"))
        m = e.get("state_metrics") or {}
        if m:
            metrics_rows.append({"fixture_id": fid, **m})

    def agg(field):
        return _pct([r.get(field) for r in metrics_rows])

    summary = {
        "study": "golden_v3_sonnet46_summary",
        "generation_id": V46.GENERATION_ID,
        "model_id": V46.DEFAULT_BEDROCK_MODEL_ID,
        "resolved_model_ids": sorted({(fixtures[f] or {}).get("resolved_model_id")
                                      for f in accepted if fixtures.get(f)} - {None}),
        "fixture_manifest_hash": manifest["fixture_manifest_hash"],
        "content_hashes": content_hashes(),
        # --- honest execution accounting (mandate SS15) ---
        "counts": {
            "manifest_size": len(manifest_ids),
            "attempted": completed + len(infra),
            "semantically_completed": completed,
            "accepted": len(accepted),
            "validator_rejected": len(rejected),
            "infrastructure_censored": len(infra),
            "not_attempted": len(not_attempted),
        },
        "acceptance": {
            "accepted_over_completed": (round(len(accepted) / completed, 4)
                                        if completed else None),
            "validator_rejects_over_completed": (round(len(rejected) / completed, 4)
                                                  if completed else None),
            "note": ("Denominator is SEMANTICALLY COMPLETED calls only. Infrastructure-censored "
                     "calls (AWS quota / timeouts) are EXCLUDED from semantic denominators and "
                     "reported separately. accepted/manifest_size is NOT a model-quality rate."),
        },
        "infrastructure_censored_fixtures": infra,
        "validator_rejected_fixtures": rejected,
        "not_attempted_fixtures": not_attempted,
        # --- token / latency / cost from REAL Bedrock usage metadata (mandate SS12) ---
        "tokens": {
            "input_tokens": _pct(in_toks),
            "output_tokens": _pct(out_toks),
            "total_tokens": _pct(tot_toks),
            "note": ("Values come from the Bedrock Converse response `usage` block "
                     "(inputTokens/outputTokens). Cache hits are excluded so no figure is "
                     "double-counted. No quota-division estimation is used anywhere."),
        },
        "latency_s": _pct(lats),
        "cost_usd_estimate": {
            **_pct(costs),
            "note": ("Estimate from public on-demand Sonnet pricing ($0.003/1K in, $0.015/1K "
                     "out) via adapter_v4.estimate_cost_usd -- NOT a billed figure. Bedrock "
                     "Converse does not return per-call price."),
        },
        # --- structural output metrics (mandate SS13) ---
        "state_metrics_distribution": {
            k: agg(k) for k in ("n_mechanisms_total", "n_distinct_mechanisms",
                                "n_redundant_mechanisms", "n_unknown", "n_conflicted",
                                "n_unsupported_mechanisms", "support_evidence_total",
                                "counter_evidence_total", "n_states_with_counter_evidence")
        },
        "rates": {
            k: agg(k) for k in ("unknown_rate", "conflicted_rate",
                                "unsupported_mechanism_rate", "redundant_mechanism_rate",
                                "counter_evidence_search_performed_rate",
                                "counter_evidence_presence_rate")
        },
        "per_fixture_metrics": metrics_rows,
        "created_unix": int(time.time()),
    }
    if persist:
        os.makedirs(OUT, exist_ok=True)
        json.dump(summary, open(SUMMARY_PATH, "w"), indent=2, default=str)
    return summary


def verify_packets_match_45() -> dict:
    """Prove the DETERMINISTIC evidence packets are byte-identical across arms by comparing
    freshly-built 4.6 packet hashes with the hashes recorded in the 4.5 states file. This is
    what licenses the single-variable claim: same evidence, different model."""
    if not os.path.exists(SONNET45_STATES_PATH):
        return {"status": "NO_45_STATES"}
    rec45 = {}
    for line in open(SONNET45_STATES_PATH):
        r = json.loads(line)
        m = r.get("manifest") or {}
        rec45[r["fixture_id"]] = {"packet_hash": m.get("packet_hash"),
                                  "source": m.get("source_evidence_packet_hash")}
    manifest = build_or_load_manifest()
    sp = manifest["generation_fingerprint"]["sampling_params"]
    ctx = H.HarnessContext(enrich_halves=False)
    picks = {p.fixture_id: p for p in SMP.select_stratified(ctx, n=sp["n"],
                                                            max_scan=sp["max_scan"])}
    rows, mismatches = [], []
    for fid in manifest["fixture_ids"]:
        src = ctx.build_packet(picks[fid].candidate, include_formation=True, projected=True)
        neu = NZ3.neutralize_for_llm_v2(src)
        exp = rec45.get(fid, {})
        same_n = neu["neutral_llm_packet_hash"] == exp.get("packet_hash")
        same_s = neu["source_evidence_packet_hash"] == exp.get("source")
        rows.append({"fixture_id": fid, "neutral_hash_matches_45": same_n,
                     "source_hash_matches_45": same_s,
                     "neutral_llm_packet_hash": neu["neutral_llm_packet_hash"],
                     "source_evidence_packet_hash": neu["source_evidence_packet_hash"]})
        if not (same_n and same_s):
            mismatches.append(fid)
    return {"status": "CHECKED", "n": len(rows), "n_mismatches": len(mismatches),
            "mismatched_fixtures": mismatches, "all_identical": not mismatches, "rows": rows}
