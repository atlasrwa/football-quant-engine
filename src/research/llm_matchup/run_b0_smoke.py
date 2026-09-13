"""B0 — Live Bedrock Sonnet smoke test (ENGINEERING VALIDATION ONLY).

Runs ~5-10 fixtures through the real Bedrock Converse path and a set of fail-closed
engineering checks. Does NOT tune predictive ideas (brief §14).

Verifies:
  * a real Converse request works and returns a structured tool response;
  * model / inference-profile identity is recorded per call;
  * the validator accepts a legitimate response and rejects an invalid one (fail closed);
  * packet hash / caching works (second call is a cache hit);
  * AWS/network exceptions map to LLM_STATE_UNAVAILABLE;
  * no credentials are logged; no prose / probabilities / predictions leak.

Run:  .venv/bin/python -m src.research.llm_matchup.run_b0_smoke [N]

Writes: out/phase_b_calls.csv (appended, phase=B0), out/b0_smoke_summary.json,
        out/b0_states.jsonl.
"""
from __future__ import annotations
import os, sys, json, time, copy

from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup import bedrock_adapter as BA
from src.research.llm_matchup.validator import validate, ValidationError
from src.research.llm_matchup import versions as V

OUT = H.OUT


def _redact_check(obj) -> bool:
    """Return True if the serialized object appears free of credential-like tokens."""
    s = json.dumps(obj, default=str).lower()
    for bad in ("aws_secret", "secret_access", "session_token", "aws_access_key"):
        if bad in s:
            return False
    return True


def run(n: int = 6):
    os.makedirs(OUT, exist_ok=True)
    ctx = H.HarnessContext(enrich_halves=False)
    cands = ctx.candidates(min_prior=8, min_form_cov=1)
    cands = cands[:n]
    print(f"B0: {len(cands)} candidate fixtures (of pool)")

    call_rows = []
    states = []
    live_ok = live_reject = unavailable = 0
    engineering = {
        "converse_ok": False, "identity_recorded": False, "cache_hit_works": False,
        "invalid_fails_closed": False, "aws_exception_maps_unavailable": False,
        "no_credentials_logged": True, "no_probability_leak": True,
    }
    first_packet = None
    first_status = None

    for cand in cands:
        packet = ctx.build_packet(cand, include_formation=True, projected=True)
        if first_packet is None:
            first_packet = packet
        res = BA.analyze_matchup(packet, use_cache=True)
        row = H.call_record("B0", cand, packet, res)
        call_rows.append(row)
        if not _redact_check(res.manifest):
            engineering["no_credentials_logged"] = False
        if res.status == "OK":
            live_ok += 1
            engineering["converse_ok"] = True
            if res.manifest.get("resolved_model_id") or res.manifest.get("model_id"):
                engineering["identity_recorded"] = True
            # belt & braces: ensure no probability content survived
            if "probability" in json.dumps(res.state, default=str).lower():
                engineering["no_probability_leak"] = False
            states.append({"fixture_id": cand.target.fixture_id, "status": res.status,
                           "state": res.state, "manifest": res.manifest})
            if first_status is None:
                first_status = "OK"
        elif res.status == "LLM_STATE_REJECTED":
            live_reject += 1
        else:
            unavailable += 1
        print(f"  {cand.target.fixture_id} {cand.target.home[:14]:14} vs "
              f"{cand.target.away[:14]:14} -> {res.status} "
              f"(lat={res.manifest.get('latency_s')}, in={res.manifest.get('input_tokens')}, "
              f"out={res.manifest.get('output_tokens')}, model={res.manifest.get('resolved_model_id') or res.manifest.get('model_id')})")

    # --- cache-hit check: re-run first packet, must be cache_hit=True if it was cached ---
    if first_packet is not None:
        res2 = BA.analyze_matchup(first_packet, use_cache=True)
        engineering["cache_hit_works"] = bool(res2.manifest.get("cache_hit"))

    # --- invalid-response fails closed: feed a corrupt tool input through the validator ---
    if first_packet is not None:
        bad = {"fixture_id": "NOT_THE_FIXTURE", "information_cutoff_unix": 0,
               "context_flags": {}, "team_a_states": [], "team_b_states": [], "matchup_states": []}
        try:
            validate(bad, first_packet, V.version_stamp())
            engineering["invalid_fails_closed"] = False
        except ValidationError:
            engineering["invalid_fails_closed"] = True

    # --- AWS exception mapping: force an impossible model id, expect UNAVAILABLE ---
    if first_packet is not None:
        res3 = BA.analyze_matchup(first_packet, model_id="does.not.exist.model:0",
                                  use_cache=False)
        engineering["aws_exception_maps_unavailable"] = (res3.status == "LLM_STATE_UNAVAILABLE")

    H.append_calls_csv(os.path.join(OUT, "phase_b_calls.csv"), call_rows)
    with open(os.path.join(OUT, "b0_states.jsonl"), "w") as f:
        for s in states:
            f.write(json.dumps(s, default=str) + "\n")

    summary = {
        "phase": "B0", "n_fixtures": len(cands), "live_ok": live_ok,
        "live_rejected": live_reject, "unavailable": unavailable,
        "schema_valid_pct": round(100 * live_ok / max(1, live_ok + live_reject), 1),
        "engineering_checks": engineering,
        "model_id": V.DEFAULT_BEDROCK_MODEL_ID, "region": V.DEFAULT_BEDROCK_REGION,
        "versions": V.version_stamp(),
        "created_unix": int(time.time()),
    }
    json.dump(summary, open(os.path.join(OUT, "b0_smoke_summary.json"), "w"), indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    run(n)
