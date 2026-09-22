"""Post-execution Item 6 Stage-1 analysis: reconcile execution evidence, freeze it, then run
the ALREADY-FROZEN deterministic Stage-1 harness + gate. Makes NO model call.

Run only after the live run reaches a terminal state for every fixture.

PHASE SPLIT (mechanical; required by the authorized sequence "evidence freeze commit BEFORE
the primary gate"):
    python _analyze_stage1.py freeze    -> reconcile + write evidence manifest + generation
                                           dataset, then STOP (no harness, no gate).
    python _analyze_stage1.py analyze   -> run the frozen harness + frozen gate over the
                                           already-frozen generation dataset read from disk.

Neither phase alters any classification, threshold, packet, prompt or mechanism. The added
fields are PROVENANCE + RECONCILIATION reporting only.
"""
import glob, hashlib, json, os, sys, time

W = "/home/ubuntu/.item6_exec_worktree"
OUT = "/home/ubuntu/research/item6/out/execution/stage1_live_v6"
AUTH = "b79051f45905095facc41f2bcad510bdc1de5728"
sys.path.insert(0, W)
os.chdir(W)

from src.research.item6 import harness as H                        # noqa: E402
from src.research.item6.execution import provenance as PROV        # noqa: E402
from src.research.item6.execution import execution_status as ES    # noqa: E402
from src.research.item6.execution.live_transport import (             # noqa: E402
    LIVE_AUTHENTICITY_KEY, BedrockStage1Transport)

CANON = PROV.canonical_bytes
sha = lambda o: hashlib.sha256(CANON(o)).hexdigest()               # noqa: E731

PHASE = (sys.argv[1] if len(sys.argv) > 1 else "freeze").lower()

manifest = json.load(open(f"{W}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V6.json"))
pkset = json.load(open(f"{W}/research/item6/out/execution/ITEM6_STAGE1_EVIDENCE_PACKET_SET_V1.json"))
reqset = json.load(open(f"{W}/research/item6/out/execution/ITEM6_STAGE1_MATERIALIZED_REQUEST_SET_V1.json"))
packets = {p["fixture_id"]: p for p in pkset["packets"]}
entries = {e["fixture_id"]: e for e in reqset["entries"]}
allowed = {fid: sorted(packets[fid]["packet"]["evidence"].keys()) for fid in packets}

EV_MANIFEST_PATH = f"{OUT}/ITEM6_STAGE1_EXECUTION_EVIDENCE_MANIFEST_V1.json"
DATASET_PATH = f"{OUT}/ITEM6_STAGE1_GENERATION_DATASET_V1.json"


def _payload(raw):
    for blk in raw["output"]["message"]["content"]:
        if "toolUse" in blk:
            return blk["toolUse"]["input"]
    return None


def _verify_envelope(raw):
    """Same predicate the frozen runner applies before persisting a receipt; re-run here so
    N_PROVIDER_ENVELOPE_VERIFIED is measured over persisted receipts, not assumed."""
    if not isinstance(raw, dict):
        return False
    out = raw.get("output", {})
    msg = out.get("message") if isinstance(out, dict) else None
    usage = raw.get("usage")
    return bool(msg) and isinstance(usage, dict) and \
        "inputTokens" in usage and "outputTokens" in usage


def do_freeze():
    # ---- reconcile execution evidence from disk ------------------------------------------
    markers = {os.path.basename(p)[:-5]: json.load(open(p))
               for p in sorted(glob.glob(f"{OUT}/attempts/*.json"))}
    receipts = {os.path.basename(p)[:-5]: json.load(open(p))
                for p in sorted(glob.glob(f"{OUT}/receipts/*.json"))}
    ledger = json.load(open(f"{OUT}/spend_ledger.json")) \
        if os.path.exists(f"{OUT}/spend_ledger.json") else {}
    summary = json.load(open(f"{OUT}/RUN_LIVE_SUMMARY.json")) \
        if os.path.exists(f"{OUT}/RUN_LIVE_SUMMARY.json") else {}
    corpus_manifest = json.load(open(f"{OUT}/ITEM6_STAGE1_CORPUS_SNAPSHOT_MANIFEST_V1.json"))
    prever = json.load(open(f"{OUT}/PRE_TREATMENT_VERIFICATION_V1.json"))

    # per-fixture reservations, straight from the durable spend-ledger events.
    reservations = {e["fixture_id"]: e.get("reservation_usd")
                    for e in ledger.get("events", []) if e.get("event") == "RESERVE"}
    realized = {e["fixture_id"]: e.get("realized_cost_usd")
                for e in ledger.get("events", []) if e.get("event") == "RECONCILE"}

    # statuses the runner returns WITHOUT writing an attempt marker (blocked before step 5)
    # exist only in the run summary; counted from there, labelled as summary-derived.
    res_by_status = {}
    for r in summary.get("results", []):
        res_by_status[r.get("status")] = res_by_status.get(r.get("status"), 0) + 1

    n_env_ok = sum(1 for r in receipts.values() if _verify_envelope(r["raw_response"]))
    # provider AUTHENTICITY via the committed transport predicate: a stand-in response can
    # never carry a well-formed stamp bound to its own envelope.
    n_authentic = sum(1 for r in receipts.values()
                      if BedrockStage1Transport.is_authentic_live_response(r["raw_response"]))
    rec = {
        "n_fixtures_planned": reqset["n_fixtures"],
        "n_attempt_markers": len(markers),
        "n_receipts": len(receipts),
        "n_receipts_verified": n_env_ok,
        "n_provider_envelope_verified": n_authentic,
        "n_provider_envelope_structurally_verified": n_env_ok,
        "n_transport_ok": sum(1 for m in markers.values()
                              if m.get("status") == ES.TRANSPORT_OK),
        "n_transmitted": sum(1 for m in markers.values() if m.get("transmitted")),
        "n_paid_attempts": sum(1 for m in markers.values() if m.get("transmitted")),
        # Uncertain attempts are classified from DURABLE DISK EVIDENCE, not from the marker's
        # status field: the frozen runner derives UNCERTAIN_ATTEMPT_NOT_RETRIED at resume time
        # (marker written, no receipt) and returns early WITHOUT rewriting the marker, so a
        # marker orphaned by an interrupted run still reads UNKNOWN_EXECUTION_STATUS on disk.
        # This matches _resume_status() exactly; it does not reclassify any science.
        "n_uncertain_attempts": sum(
            1 for fid, m in markers.items()
            if fid not in receipts and m.get("attempt_marker_written")),
        "n_uncertain_attempts_by_marker_status": sum(
            1 for m in markers.values()
            if m.get("status") == ES.UNCERTAIN_ATTEMPT_NOT_RETRIED),
        "n_transport_failures": sum(1 for m in markers.values() if m.get("status") in
                                    (ES.MODEL_TRANSPORT_FAILURE, ES.MODEL_TIMEOUT)),
        "n_provider_errors": sum(1 for m in markers.values()
                                 if m.get("status") == ES.MODEL_PROVIDER_ERROR),
        "n_receipt_verification_failed": sum(
            1 for m in markers.values() if m.get("status") == ES.RECEIPT_VERIFICATION_FAILED),
        "status_histogram_from_run_summary": res_by_status,
        "n_call_blocked_by_token_count":
            res_by_status.get(ES.CALL_BLOCKED_BY_TOKEN_COUNT, 0),
        "n_call_blocked_by_monetary_cap":
            res_by_status.get(ES.CALL_BLOCKED_BY_SPEND_CAP, 0),
        "n_call_blocked_by_call_cap": res_by_status.get(ES.CALL_BLOCKED_BY_CALL_CAP, 0),
        "n_duplicate_paid_attempts": 0,   # one marker file per fixture_id makes >1 impossible
        "n_retries": 0,                   # MAX_RETRIES_PER_FIXTURE=0; no retry path exists
        "count_tokens_counters": summary.get("count_tokens_counters", {}),
        "actual_provider_input_tokens": sum(int(r["usage"]["inputTokens"])
                                            for r in receipts.values()),
        "actual_provider_output_tokens": sum(int(r["usage"]["outputTokens"])
                                             for r in receipts.values()),
        "spend_ledger": ledger,
    }

    evidence = []
    for fid in sorted(markers):
        m = markers[fid]
        r = receipts.get(fid)
        evidence.append({
            "fixture_id": fid,
            "packet_sha256": entries[fid]["packet_sha256"] if fid in entries else None,
            "frozen_request_sha256":
                entries[fid]["canonical_request_sha256"] if fid in entries else None,
            "attempt_request_sha256": m.get("request_sha256"),
            "attempt_marker_written": bool(m.get("attempt_marker_written")),
            "status": m.get("status"),
            "resume_derived_status": (
                ES.TRANSPORT_OK if fid in receipts
                else ES.UNCERTAIN_ATTEMPT_NOT_RETRIED if m.get("attempt_marker_written")
                else m.get("status")),
            "transmitted": bool(m.get("transmitted")),
            "reservation_usd": reservations.get(fid),
            "realized_cost_usd": realized.get(fid),
            "provider_counted_input_tokens": (r or {}).get("provider_counted_input_tokens"),
            "usage": (r or {}).get("usage"),
            "model_provider": manifest["model_provider"],
            "model_profile_id": manifest["model_profile_id"],
            "model_id": manifest["model_id"],
            "resolved_model_id": (r or {}).get("resolved_model_id"),
            "provider_envelope_verified":
                _verify_envelope(r["raw_response"]) if r else False,
            "authentic_live_provider_response":
                BedrockStage1Transport.is_authentic_live_response(r["raw_response"])
                if r else False,
            "transport_converse_model_id":
                (r["raw_response"].get(LIVE_AUTHENTICITY_KEY) or {}).get("converse_model_id")
                if r else None,
            "aws_request_id":
                (r["raw_response"].get(LIVE_AUTHENTICITY_KEY) or {}).get("aws_request_id")
                if r else None,
            "stop_reason": r["raw_response"].get("stopReason") if r else None,
            "raw_response_sha256": sha(r["raw_response"]) if r else None,
            "receipt_sha256": sha(r) if r else None,
        })
    rec["n_request_hash_mismatches_vs_frozen"] = sum(
        1 for e in evidence if e["attempt_request_sha256"] and
        e["attempt_request_sha256"] != e["frozen_request_sha256"])

    # ---- extract mechanism payloads (no retries, no filtering) ---------------------------
    responses, payload_hashes = [], {}
    for fid in sorted(receipts):
        p = _payload(receipts[fid]["raw_response"])
        if p is None:
            continue
        responses.append(p)
        payload_hashes[fid] = sha(p)

    evidence_manifest = {
        "artifact_version": "item6_stage1_execution_evidence_manifest_v1",
        "authorized_execution_head": AUTH,
        "apparatus_provenance_commit": manifest["apparatus_provenance_commit"],
        "run_manifest_version": manifest["run_manifest_version"],
        "run_manifest_sha256": manifest["run_manifest_sha256"],
        "model_provider": manifest["model_provider"],
        "model_profile_id": manifest["model_profile_id"],
        "model_id": manifest["model_id"],
        "region": manifest["region"],
        "evidence_packet_set_sha256": manifest["evidence_input"]["evidence_packet_set_sha256"],
        "materialized_request_set_sha256":
            manifest["evidence_input"]["materialized_request_set_sha256"],
        "champion_sha256": manifest["champion_sha256"],
        # provenance-only binding of the exact corpus snapshot used for execution
        "corpus_snapshot_manifest_sha256":
            corpus_manifest["corpus_snapshot_manifest_sha256"],
        "corpus_snapshot_manifest_path":
            f"{OUT}/ITEM6_STAGE1_CORPUS_SNAPSHOT_MANIFEST_V1.json",
        "pre_treatment_verification": {
            "N_PACKET_HASH_MISMATCHES": prever["N_PACKET_HASH_MISMATCHES"],
            "N_MATERIALIZED_REQUEST_HASH_MISMATCHES":
                prever["N_MATERIALIZED_REQUEST_HASH_MISMATCHES"],
            "n_requests_over_byte_limit": prever["n_requests_over_byte_limit"],
        },
        "reconciliation": rec,
        "per_fixture": evidence,
        "mechanism_payload_sha256_by_fixture": payload_hashes,
        "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    evidence_manifest["execution_evidence_manifest_sha256"] = sha(evidence_manifest)
    generation_dataset = {"artifact_version": "item6_stage1_generation_dataset_v1",
                          "authorized_execution_head": AUTH, "responses": responses}
    generation_dataset["generation_dataset_sha256"] = sha(
        {k: v for k, v in generation_dataset.items() if k != "generation_dataset_sha256"})

    for path, obj in ((EV_MANIFEST_PATH, evidence_manifest), (DATASET_PATH, generation_dataset)):
        with open(path, "w") as f:
            json.dump(obj, f, indent=1, sort_keys=True)
    print("EXECUTION_EVIDENCE_MANIFEST_SHA256=" +
          evidence_manifest["execution_evidence_manifest_sha256"])
    print("GENERATION_DATASET_SHA256=" + generation_dataset["generation_dataset_sha256"])
    print("RECONCILIATION=" + json.dumps(rec, sort_keys=True))


def do_analyze():
    """Frozen deterministic Stage-1 analysis + gate over the ALREADY-FROZEN dataset."""
    dataset = json.load(open(DATASET_PATH))
    recomputed = sha({k: v for k, v in dataset.items() if k != "generation_dataset_sha256"})
    if recomputed != dataset["generation_dataset_sha256"]:
        raise SystemExit(f"FROZEN DATASET HASH MISMATCH {recomputed} != "
                         f"{dataset['generation_dataset_sha256']}")
    print("ANALYZING_FROZEN_DATASET_SHA256=" + dataset["generation_dataset_sha256"])
    responses = dataset["responses"]
    result = H.run_stage1(responses, allowed_evidence_refs_by_fixture=allowed)
    result["analyzed_generation_dataset_sha256"] = dataset["generation_dataset_sha256"]
    with open(f"{OUT}/ITEM6_STAGE1_RESULT_V1.json", "w") as f:
        json.dump(result, f, indent=1, sort_keys=True, default=str)
    print("STAGE1_RESULT=" + json.dumps(result.get("endpoints"), sort_keys=True, default=str))
    print("STAGE1_GATE=" + json.dumps(result.get("gate"), sort_keys=True, default=str))


if PHASE == "freeze":
    do_freeze()
elif PHASE == "analyze":
    do_analyze()
else:
    raise SystemExit(f"unknown phase {PHASE!r}; use 'freeze' or 'analyze'")
