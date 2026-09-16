"""Execute the frozen V8A development design. THIS IS THE BILLABLE PATH.

Preconditions, asserted before the first call and again as it runs:
  * the frozen artifacts re-hash to their recorded values (nothing drifted since freeze);
  * the interpreter can actually make a Converse call (no silent per-fixture failure);
  * the packet's TEAM_A really is the HOME team, so subject roles cannot silently invert;
  * the running spend never exceeds the frozen ceiling.

Every response is written to its OWN file the moment it arrives, with the request hash and
provenance, so a crash at call 90 does not cost the first 89 calls. A resumed run skips any
record whose content hash still matches, and recomputes any that is partial or corrupt --
the same pattern V7.1's execution layer uses.

Run:  /home/ubuntu/.venv/bin/python research/hypothesis_engine/_execute_v8a.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from decimal import Decimal

sys.path.insert(0, "/home/ubuntu/v8a-worktree")

import src  # noqa: F401,E402

from src.research.hypothesis_oos import v6_prompt as V6PR                # noqa: E402
from src.research.hypothesis_engine import schema_v4 as SCHEMA_V4        # noqa: E402
from src.research.hypothesis_v8a import genericlib as G                  # noqa: E402
from src.research.hypothesis_v8a import packet as PK                     # noqa: E402
from src.research.hypothesis_v8a import prompt_v8a as PR                 # noqa: E402
from src.research.hypothesis_v8a import schema_v8a as S                  # noqa: E402
from src.research.hypothesis_v8a import transport as TR                  # noqa: E402
from src.research.hypothesis_v8a.frozencap import FrozenCapability       # noqa: E402

ROOT = "/home/ubuntu/v8a-worktree"
OUT = f"{ROOT}/research/hypothesis_engine/out/v8a"
RESP = f"{OUT}/responses"
CAP_PATH = f"{ROOT}/research/hypothesis_oos/out/v7_1/V7_1_CAPABILITY_MATRIX.json"

MODEL_ID = "us.anthropic.claude-sonnet-4-6"
TEMPERATURE = 0.0
MAX_TOKENS_PASS1 = 8192
MAX_TOKENS_PASS2 = 2048
REGION = "us-east-1"


def _sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def save(name: str, body: dict):
    body = dict(body)
    body["record_sha256"] = _sha({k: v for k, v in body.items()
                                  if k != "record_sha256"})
    tmp = os.path.join(RESP, name + ".tmp")
    json.dump(body, open(tmp, "w"), indent=1, sort_keys=True, default=str)
    os.replace(tmp, os.path.join(RESP, name))
    return body


def load_ok(name: str):
    """A previously written record, but only if it is complete and self-consistent."""
    path = os.path.join(RESP, name)
    if not os.path.exists(path):
        return None
    try:
        rec = json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return None
    core = {k: v for k, v in rec.items() if k != "record_sha256"}
    return rec if rec.get("record_sha256") == _sha(core) else None


def main():
    os.makedirs(RESP, exist_ok=True)
    cap = FrozenCapability.load(CAP_PATH)
    VOCAB = list(cap.measurable_vocabulary())

    freeze = json.load(open(f"{OUT}/V8A_FREEZE.json"))
    plan = json.load(open(f"{OUT}/V8A_CALL_PLAN.json"))
    packets = json.load(open(f"{OUT}/packets_v8a.json"))
    arm_a_packets = json.load(open(f"{OUT}/packets_arm_a.json"))
    ceiling = Decimal(plan["hard_max_cost_usd"])

    # ---- precondition: nothing drifted since the freeze --------------------------------
    drift = []
    for name, want in freeze["artifact_hashes"].items():
        got = _sha(json.load(open(os.path.join(OUT, name))))
        if got != want:
            drift.append(name)
    if drift:
        raise SystemExit(f"ABORT_FROZEN_ARTIFACT_DRIFT: {drift}")

    # ---- precondition: TEAM_A really is HOME -------------------------------------------
    for fid, pkt in packets.items():
        if pkt["target_fixture"]["TEAM_A"]["role"] != "HOME_TEAM":
            raise SystemExit(f"ABORT_SUBJECT_ROLE_INVERSION: {fid}")

    # ---- precondition: this interpreter can actually call Converse ---------------------
    client = TR.build_client(REGION)
    if not hasattr(client, "converse"):
        raise SystemExit("ABORT_INCOMPATIBLE_BOTO3: client has no converse(); "
                         "run under /home/ubuntu/.venv/bin/python")

    p1_schema, p2_schema = S.pass1_schema(), S.pass2_schema()
    v4_schema = SCHEMA_V4.build_schema()
    lib = G.build_library(VOCAB)

    spent = Decimal("0.00")
    made = {"A_pass1": 0, "B_pass1": 0, "B_pass2": 0}
    reused = {"A_pass1": 0, "B_pass1": 0, "B_pass2": 0}
    errors = []

    def price(in_tok, out_tok) -> Decimal:
        return (Decimal(in_tok or 0) * TR.PRICE_IN_PER_1K
                + Decimal(out_tok or 0) * TR.PRICE_OUT_PER_1K) / Decimal(1000)

    def call(system, user, schema, desc, *, max_tokens, name, meta):
        nonlocal spent
        got = load_ok(name)
        if got is not None:
            return got, True
        if spent >= ceiling:
            raise SystemExit(f"ABORT_CEILING_REACHED: spent {spent} of {ceiling}")
        t0 = time.time()
        try:
            out, prov = TR.converse(client, system, user, schema, desc,
                                    model_id=MODEL_ID, temperature=TEMPERATURE,
                                    max_tokens=max_tokens)
            err = None
        except Exception as exc:                                     # noqa: BLE001
            out, prov, err = None, {"resolved_model_id": MODEL_ID}, \
                f"{type(exc).__name__}: {exc}"[:400]
        spent += price(prov.get("input_tokens"), prov.get("output_tokens"))
        rec = save(name, {**meta, "response": out, "provenance": prov, "error": err,
                          "elapsed_s": round(time.time() - t0, 2),
                          "model_id": MODEL_ID, "temperature": TEMPERATURE,
                          "max_tokens": max_tokens})
        if err:
            errors.append({"name": name, "error": err})
            # Fail fast on a systemic fault (bad schema, revoked access, wrong region)
            # rather than burning the whole budget recording the same error 120 times.
            if len(errors) >= 3 and all(
                    e["error"][:40] == errors[-1]["error"][:40] for e in errors[-3:]):
                raise SystemExit(f"ABORT_CONSECUTIVE_FAILURES: {errors[-1]['error']}")
        return rec, False

    # ---- ARM A: the genuine V6.1 protocol, one pass ------------------------------------
    for fid in sorted(arm_a_packets):
        pkt = arm_a_packets[fid]
        rec, was_cached = call(V6PR.SYSTEM_PROMPT, V6PR.build_user_payload(pkt),
                               v4_schema, "Return the hypothesis set.",
                               max_tokens=MAX_TOKENS_PASS1,
                               name=f"A_pass1_{fid}.json",
                               meta={"arm": "A", "pass": 1, "fixture_id": fid,
                                     "prompt_version": V6PR.V6_PROMPT_VERSION})
        made["A_pass1"] += 0 if was_cached else 1
        reused["A_pass1"] += 1 if was_cached else 0
        print(f"A/pass1 {fid} {'cached' if was_cached else 'called'} "
              f"n_hyp={len((rec.get('response') or {}).get('hypotheses') or [])} "
              f"spent={spent:.2f}")

    # ---- ARM B pass 1 -------------------------------------------------------------------
    b_candidates = {}
    for fid in sorted(packets):
        pkt = packets[fid]
        rec, was_cached = call(PR.SYSTEM_PROMPT_PASS1, PK.serialize(pkt),
                               p1_schema, "Return the research analysis.",
                               max_tokens=MAX_TOKENS_PASS1,
                               name=f"B_pass1_{fid}.json",
                               meta={"arm": "B", "pass": 1, "fixture_id": fid,
                                     "prompt_version": PR.PROMPT_VERSION})
        made["B_pass1"] += 0 if was_cached else 1
        reused["B_pass1"] += 1 if was_cached else 0
        cands = ((rec.get("response") or {}).get("candidates") or [])
        b_candidates[fid] = cands
        print(f"B/pass1 {fid} {'cached' if was_cached else 'called'} "
              f"n_cand={len(cands)} spent={spent:.2f}")

    # ---- ARM B pass 2: ONE CALL PER CANDIDATE -------------------------------------------
    for fid in sorted(b_candidates):
        for i, cand in enumerate(b_candidates[fid]):
            cid = str(cand.get("candidate_id") or f"C{i}")
            safe_cid = "".join(ch if ch.isalnum() else "_" for ch in cid)[:40]
            near = G.nearest(
                {"target_metrics": cand.get("target_metric") or [],
                 "side": cand.get("metric_perspective"),
                 "comparison": cand.get("comparison"),
                 "subject": {"TEAM_A": "HOME_TEAM",
                             "TEAM_B": "AWAY_TEAM"}.get(cand.get("subject")),
                 "window": cand.get("window"),
                 "conditions": cand.get("conditions") or []}, lib, 3)
            rec, was_cached = call(PR.SYSTEM_PROMPT_PASS2,
                                   PR.build_pass2_user(cand, near),
                                   p2_schema, "Return the novelty judgment.",
                                   max_tokens=MAX_TOKENS_PASS2,
                                   name=f"B_pass2_{fid}_{safe_cid}.json",
                                   meta={"arm": "B", "pass": 2, "fixture_id": fid,
                                         "candidate_id": cid,
                                         "retrieved_generic_ids": [g["generic_id"]
                                                                   for g in near],
                                         "retrieved_distances": [g["distance"]
                                                                 for g in near]})
            made["B_pass2"] += 0 if was_cached else 1
            reused["B_pass2"] += 1 if was_cached else 0
            act = (rec.get("response") or {}).get("action")
            print(f"B/pass2 {fid} {cid} {'cached' if was_cached else 'called'} "
                  f"action={act} spent={spent:.2f}")

    summary = {
        "execution_version": "v8a_execution_v1",
        "model_id": MODEL_ID,
        "calls_made": made, "calls_reused_from_disk": reused,
        "total_calls_made": sum(made.values()),
        "calls_planned_max": plan["calls_planned_max"],
        "hard_max_cost_usd": str(ceiling),
        "actual_spend_usd": str(spent.quantize(Decimal("0.0001"))),
        "errors": errors,
        "arm_c_executed": False,
        "arm_c_blocker": ("No model named Terra exists in this repository; no OpenAI or "
                          "other non-Bedrock credential is present; no adapter exists. "
                          "Substituting another model is forbidden by brief 19/33."),
    }
    json.dump(summary, open(f"{OUT}/V8A_EXECUTION_SUMMARY.json", "w"), indent=2)
    print("\n" + json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
