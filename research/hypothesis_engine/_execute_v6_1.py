"""V6.1 execution driver (`v6_1_execute_v1`). RUNS NOTHING UNLESS EXPLICITLY AUTHORIZED.

ZERO SPEND ON IMPORT. Importing, hashing, or dry-running this file costs nothing: `main()`
refuses a real run without `--i-have-authorization`, and `--dry-run` never constructs a
client or calls Converse.

WHY THIS MODULE EXISTS (pre-spend execution-driver amendment)
-------------------------------------------------------------
The frozen V6.1 package had a scientific design, fixtures, packets, evaluator, metric
contracts, schedule and an exact CountTokens manifest -- but NO V6.1-bound execution driver.
The only executor, `_execute_v6.py`, is hard-bound to `out/v6`, the immutable COMPLETE V6
experiment, and cannot be reused without endangering V6 history. A pre-spend attempt
correctly halted with V6_1_EXECUTION_BLOCKED_COST_GUARD because the prospective cost guard
could not be proven from an actual V6.1 driver. This module is that missing apparatus.

WHAT THIS DRIVER IS, AND IS NOT
-------------------------------
It is a THIN EXECUTOR. It introduces NO scientific policy. It does not decide fixtures,
arms, replicate counts, prompts, packets, treatment, call order, max_tokens, thresholds,
evaluator logic, stop thresholds or self-noise parameters. Every one of those is LOADED from
an already-frozen V6.1 artifact; if a required value is not frozen, the driver STOPS and
reports the missing contract rather than inventing it.

The scientific verdict (`v6_1_verdict.final_verdict`) is intentionally NOT computed at run
time in a way that could vary. This driver records raw responses and scores, and lets the
frozen evaluator be run once, afterwards, on the immutable scores. EXECUTION_STATUS and
SCIENTIFIC_VERDICT are kept strictly separate.

HARD GUARANTEES (each proven by a test in test_execute_v6_1.py)
---------------------------------------------------------------
  * PATH ISOLATION. A startup assertion proves experiment_id starts with "V6.1", the output
    directory is under out/v6_1/, and it is NOT out/v6/. Any V6 path aborts before inference.
  * FROZEN-ARTIFACT REVERIFY. Every preregistered artifact hash + every module in the
    evaluator freeze + CHAMPION are re-hashed before the first paid call; drift aborts at $0.
  * ONE CANONICAL REQUEST. Requests are built ONLY by `v6_token_count.canonical_converse_request`
    (the same builder the token count and freeze used). Immediately before each call the
    request is rebuilt, hashed, and compared to the frozen INPUT_TOKEN_MANIFEST entry; a
    mismatch aborts before inference.
  * PROSPECTIVE COST GUARD (CONSERVATIVE EXPOSURE). Before each Converse call:
    confirmed_actual_spend + unresolved_reserved_exposure + frozen max_request_cost_usd of
    the NEXT request must be <= HARD_MAX_COST, else stop with V6_1_STOP_COST_CEILING
    (APPARATUS). This runs BEFORE client.converse(). "unresolved_reserved_exposure" is the
    sum of the frozen per-request maxima of every request that was SENT but whose billing
    outcome is unknowable (see below); a request that could have been billed is NEVER
    treated as zero financial exposure.
  * NO RETRIES. The client is built by `v6_transport.build_client()` (retries disabled) and
    `assert_no_retries` is proven on the live client before the first request. One logical
    call bills at most once.
  * RAW BEFORE ADJUDICATION. The raw Bedrock response is written and hashed BEFORE it is
    parsed or scored. A raw-persistence failure stops the run rather than adjudicating an
    unpreserved response -- and, because the response was already RECEIVED (hence billed),
    its confirmed usage cost is accounted before stopping.

BILLING-STATUS SEMANTICS (v2 -- unknown-after-send is never zero exposure)
--------------------------------------------------------------------------
Every scheduled request is in exactly one billing state, and only NOT_SENT may carry zero
cost exposure:

    NOT_SENT              the paid method was never entered (guard tripped, request-hash
                          mismatch pre-send, missing manifest). Zero exposure.
    CONFIRMED             client.converse() returned usage; exposure = actual provider cost
                          (reconciled down from the frozen maximum, and asserted <= it).
    UNKNOWN_AFTER_SEND    client.converse() was entered and then raised: Bedrock may have
                          accepted and billed the request, but no usage metadata returned.
                          Exposure = the request's FROZEN maximum cost, retained as
                          unresolved and NEVER released. A post-send transport failure is
                          not proof the request was free.

The next-call guard consumes confirmed_actual_spend + unresolved_reserved_exposure, so an
unknown-after-send attempt reduces the remaining budget by its full frozen maximum. Because
there are 36 frozen requests, each with one billable attempt, and the sum of their frozen
maxima is exactly the $8.52 hard ceiling, the ceiling holds even if EVERY attempt becomes
UNKNOWN_AFTER_SEND.
  * FROZEN STOP RULES. `v6_stop.classify_stop` is used verbatim; the driver defines no
    alternative thresholds.
  * TERMINAL STATE. Once a terminal state is reached (COMPLETE/STOPPED/ABORTED) no further
    call is permitted.

Once the first paid V6.1 Converse call is made, NO PATCH-AND-CONTINUE is permitted: a defect
discovered live stops the run; a repair requires a successor experiment/version.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import validator_v5 as V
from src.research.hypothesis_oos import v6_classes as K
from src.research.hypothesis_oos import v6_scorecard as SC
from src.research.hypothesis_oos import v6_stop as STOP
from src.research.hypothesis_oos import v6_token_count as TC
from src.research.hypothesis_oos import v6_transport as TRN

EXECUTE_VERSION = "v6_1_execute_v2"

ROOT = "/home/ubuntu"
# The ONE experiment this driver may target. Both are asserted at startup.
EXPERIMENT_ID_PREFIX = "V6.1"
OUT = f"{ROOT}/research/hypothesis_oos/out/v6_1"
EXEC_DIR = f"{OUT}/execution"
# The forbidden sibling: the immutable, COMPLETE V6 experiment. NEVER a target.
V6_FORBIDDEN_DIR = f"{ROOT}/research/hypothesis_oos/out/v6"

# ---- lifecycle states (deterministic) --------------------------------------------------
S_NOT_STARTED = "V6_1_EXECUTION_NOT_STARTED"
S_AUTHORIZED = "V6_1_EXECUTION_AUTHORIZED"
S_STARTED = "V6_1_EXECUTION_STARTED"
S_COMPLETE = "V6_1_EXECUTION_COMPLETE"
S_STOPPED = "V6_1_EXECUTION_STOPPED"
S_ABORTED = "V6_1_EXECUTION_ABORTED"
_TERMINAL_STATES = (S_COMPLETE, S_STOPPED, S_ABORTED)

# ---- per-request billing status (v2 conservative exposure) -----------------------------
# Only NOT_SENT may carry zero cost exposure. UNKNOWN_AFTER_SEND retains the full frozen
# maximum as unresolved exposure, because a post-send failure is not proof the call was free.
BILLING_NOT_SENT = "NOT_SENT"
BILLING_CONFIRMED = "CONFIRMED"
BILLING_UNKNOWN_AFTER_SEND = "UNKNOWN_AFTER_SEND"


class PathSafetyError(RuntimeError):
    """The driver was pointed at a non-V6.1 (e.g. V6) path. Abort before any inference."""


class MissingContractError(RuntimeError):
    """A required execution value is not present in the frozen artifacts. The driver refuses
    to invent it; it stops and reports the missing contract."""


class RequestHashMismatch(TRN.TransportPreflightFailure):
    """The canonical request does not match its frozen token-manifest hash. No inference."""


class RawPersistenceError(RuntimeError):
    """The raw response could not be persisted; adjudication must not proceed. Because the
    response was already RECEIVED (hence billed), the observed usage is carried on the
    exception so the driver can account the CONFIRMED cost before stopping (never zero)."""

    def __init__(self, detail: str, *, in_tok: int = 0, out_tok: int = 0):
        super().__init__(detail)
        self.in_tok = int(in_tok)
        self.out_tok = int(out_tok)


class TerminalStateError(RuntimeError):
    """A call was attempted after a terminal execution state. Forbidden."""


# ========================================================================================
# PATH SAFETY (mandatory, runs before anything can spend)
# ========================================================================================
def _norm(p: str) -> str:
    return os.path.normpath(os.path.abspath(p))


def assert_v6_1_paths(experiment_id: str, out_dir: str) -> dict:
    """Prove the experiment is V6.1 and the output directory is under out/v6_1 and is NOT
    out/v6. Raises PathSafetyError otherwise. Returns the resolved-path report."""
    problems = []
    if not (experiment_id or "").startswith(EXPERIMENT_ID_PREFIX):
        problems.append(f"experiment_id {experiment_id!r} does not start with "
                        f"{EXPERIMENT_ID_PREFIX!r}")
    resolved = _norm(out_dir)
    v6_1_root = _norm(OUT)
    v6_root = _norm(V6_FORBIDDEN_DIR)
    # must be inside out/v6_1
    if not (resolved == v6_1_root or resolved.startswith(v6_1_root + os.sep)):
        problems.append(f"resolved output {resolved} is not under {v6_1_root}")
    # must NOT be inside out/v6 (belt-and-braces: the string check AND a path-prefix check;
    # out/v6_1 is not a subpath of out/v6 because of the underscore boundary, but we assert
    # both directions so a future rename cannot silently alias them)
    if resolved == v6_root or resolved.startswith(v6_root + os.sep):
        problems.append(f"resolved output {resolved} is INSIDE the forbidden V6 dir "
                        f"{v6_root}")
    if problems:
        raise PathSafetyError("; ".join(problems))
    return {"experiment_id": experiment_id, "resolved_output_dir": resolved,
            "v6_1_root": v6_1_root, "forbidden_v6_root": v6_root,
            "is_under_v6_1": True, "is_under_v6": False}


def assert_write_target_is_v6_1(path: str) -> None:
    """Guard every write: the target must resolve inside out/v6_1 and never inside out/v6."""
    resolved = _norm(path)
    v6_1_root = _norm(OUT)
    v6_root = _norm(V6_FORBIDDEN_DIR)
    if resolved == v6_root or resolved.startswith(v6_root + os.sep):
        raise PathSafetyError(f"refusing to write into the forbidden V6 dir: {resolved}")
    if not (resolved == v6_1_root or resolved.startswith(v6_1_root + os.sep)):
        raise PathSafetyError(f"refusing to write outside out/v6_1: {resolved}")


# ========================================================================================
# FROZEN-ARTIFACT LOADING + REVERIFY (zero spend)
# ========================================================================================
def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _load(name):
    return json.load(open(f"{OUT}/{name}"))


def load_frozen(out_dir: str = OUT) -> dict:
    """Load the authoritative frozen V6.1 inputs. Raises MissingContractError if a required
    artifact or field is absent -- the driver never invents an execution value."""
    def _req(name):
        p = f"{out_dir}/{name}"
        if not os.path.exists(p):
            raise MissingContractError(f"required frozen artifact missing: {name}")
        return json.load(open(p))

    prereg = _req("PREREGISTRATION.json")
    schedule = _req("call_schedule.json")           # authoritative 36-call schedule
    token_manifest = _req("INPUT_TOKEN_MANIFEST.json")
    evaluator_freeze = _req("EVALUATOR_FREEZE.json")
    packets = {arm: _req(f"packets_{arm}.json") for arm in ("base", "research")}

    shared = prereg.get("shared_stack")
    if not shared:
        raise MissingContractError("PREREGISTRATION.json has no shared_stack")
    for key in ("model_id", "temperature", "max_tokens"):
        if key not in shared:
            raise MissingContractError(f"shared_stack missing {key}")
    cost = prereg.get("cost_model")
    if not cost or "hard_ceiling_usd" not in cost:
        raise MissingContractError("PREREGISTRATION.json has no cost_model.hard_ceiling_usd")
    if not schedule.get("frozen"):
        raise MissingContractError("call_schedule.json is not frozen")
    return {"prereg": prereg, "schedule": schedule, "token_manifest": token_manifest,
            "evaluator_freeze": evaluator_freeze, "packets": packets,
            "shared": shared, "cost": cost}


def reverify(frozen: dict, out_dir: str = OUT) -> list:
    """Nothing frozen may have moved. Returns problems; empty means proceed. Zero spend.

    Re-hashes: every preregistered artifact hash; every evaluator-freeze module; CHAMPION.
    Re-derives: every canonical request hash and checks it against the frozen token manifest,
    and checks the schedule<->manifest join is exact for all 36 calls.
    """
    problems = []
    prereg = frozen["prereg"]
    shared = frozen["shared"]
    packets = frozen["packets"]

    # 1. preregistered artifact hashes
    for name, sha in sorted((prereg.get("artifact_hashes") or {}).items()):
        p = f"{out_dir}/{name}"
        if not os.path.exists(p):
            problems.append(f"preregistered artifact missing: {name}")
            continue
        got = _sha_file(p)
        if got != sha:
            problems.append(f"artifact {name} changed since freeze ({got[:12]} != "
                            f"{sha[:12]})")

    # 2. evaluator-freeze modules (the scientific apparatus). Any drift aborts at $0.
    for rel, sha in sorted((frozen["evaluator_freeze"].get("evaluator_modules")
                            or {}).items()):
        p = f"{ROOT}/{rel}"
        if not os.path.exists(p):
            problems.append(f"evaluator module missing: {rel}")
            continue
        got = _sha_file(p)
        if got != sha:
            problems.append(f"evaluator module {rel} changed since freeze ({got[:12]} != "
                            f"{sha[:12]})")

    # 3. CHAMPION untouched
    champ = prereg.get("champion_protection") or {}
    if champ.get("artifact") and champ.get("frozen_sha256"):
        if _sha_file(champ["artifact"]) != champ["frozen_sha256"]:
            problems.append("CHAMPION artifact changed")

    # 4. schedule <-> token manifest <-> packets: exact join + canonical request hash
    by_seq = {e["seq"]: e for e in frozen["token_manifest"]["entries"]}
    sched_calls = sorted(frozen["schedule"]["calls"], key=lambda c: c["seq"])
    if len(sched_calls) != frozen["cost"]["n_calls_total"]:
        problems.append(f"schedule has {len(sched_calls)} calls; cost_model says "
                        f"{frozen['cost']['n_calls_total']}")
    seen_seq = set()
    for call in sched_calls:
        seq = call["seq"]
        if seq in seen_seq:
            problems.append(f"duplicate execution index {seq} in schedule")
        seen_seq.add(seq)
        me = by_seq.get(seq)
        if me is None:
            problems.append(f"seq {seq} missing from token manifest")
            continue
        # identity must match between schedule and manifest
        for field in ("fixture_id", "arm", "rep"):
            if call.get(field) != me.get(field):
                problems.append(f"seq {seq} {field} mismatch schedule/manifest "
                                f"({call.get(field)} != {me.get(field)})")
        pk = packets.get(call["arm"], {}).get(call["fixture_id"])
        if pk is None:
            problems.append(f"seq {seq}: no {call['arm']} packet for {call['fixture_id']}")
            continue
        req = TC.canonical_converse_request(
            pk, model_id=shared["model_id"], temperature=shared["temperature"],
            max_tokens=shared["max_tokens"])
        if TC.request_sha256(req) != me["request_sha256"]:
            problems.append(f"canonical request hash drift {call['arm']}/"
                            f"{call['fixture_id']} seq {seq}")
        if me.get("converse_model_id") not in (shared["model_id"], None):
            problems.append(f"seq {seq} manifest model id != shared_stack model id")
        if int(me.get("max_output_tokens", -1)) != int(shared["max_tokens"]):
            problems.append(f"seq {seq} manifest max_output_tokens != shared_stack "
                            f"max_tokens")
        if int(me.get("max_billable_attempts", -1)) != 1:
            problems.append(f"seq {seq} manifest max_billable_attempts != 1")
    return problems


# ========================================================================================
# ONE CANONICAL REQUEST + ONE BILLABLE CALL
# ========================================================================================
def build_request(frozen: dict, packet: dict):
    shared = frozen["shared"]
    return TC.canonical_converse_request(
        packet, model_id=shared["model_id"], temperature=shared["temperature"],
        max_tokens=shared["max_tokens"])


def verify_request_binding(frozen: dict, packet: dict, seq: int, manifest_entry: dict):
    """Rebuild -> canonicalize -> hash -> compare to frozen manifest. Also verify model and
    max_tokens. Raises RequestHashMismatch on any drift. Returns the request (unsent)."""
    request = build_request(frozen, packet)
    rhash = TC.request_sha256(request)
    if rhash != manifest_entry["request_sha256"]:
        raise RequestHashMismatch(
            f"seq {seq}: canonical request hash {rhash[:12]} != frozen manifest "
            f"{manifest_entry['request_sha256'][:12]}; executable content changed since "
            f"freeze. No Bedrock call is made; spend is unchanged.")
    if request["modelId"] != frozen["shared"]["model_id"]:
        raise RequestHashMismatch(f"seq {seq}: request modelId != shared_stack model_id")
    if int(request["inferenceConfig"]["maxTokens"]) != int(frozen["shared"]["max_tokens"]):
        raise RequestHashMismatch(f"seq {seq}: request maxTokens != shared_stack max_tokens")
    return request


def _write_raw(seq: int, obj: dict) -> str:
    """Persist a raw response artifact IMMUTABLY and return its SHA-256. V6.1-path-guarded.
    Refuses to overwrite an existing raw file (raw responses are never overwritten)."""
    raw_dir = f"{EXEC_DIR}/raw"
    assert_write_target_is_v6_1(raw_dir)
    os.makedirs(raw_dir, exist_ok=True)
    path = f"{raw_dir}/{seq:03d}.json"
    if os.path.exists(path):
        raise RawPersistenceError(f"raw artifact already exists for seq {seq}; refusing to "
                                  f"overwrite paid data")
    blob = json.dumps(obj, indent=1, sort_keys=True, default=str)
    with open(path, "w") as fh:
        fh.write(blob)
    # read back and hash the on-disk bytes (proves persistence succeeded)
    got = _sha_file(path)
    return got


def call_once(client, frozen: dict, packet: dict, seq: int, manifest_entry: dict):
    """One Converse call from the ONE canonical request. The request hash is verified against
    the frozen manifest BEFORE invoking. Returns (payload|None, in_tok, out_tok, raw_sha)."""
    request = verify_request_binding(frozen, packet, seq, manifest_entry)
    resp = client.converse(**request)              # THE paid call (one billable attempt)
    usage = resp.get("usage") or {}
    in_tok = int(usage.get("inputTokens") or 0)
    out_tok = int(usage.get("outputTokens") or 0)
    payload = None
    for block in ((resp.get("output") or {}).get("message") or {}).get("content") or []:
        if "toolUse" in block:
            payload = block["toolUse"].get("input")
            break
    # RAW BEFORE ADJUDICATION: persist + hash the raw response before anything parses it.
    # The response has already been RECEIVED (hence billed), so if persistence fails we
    # carry the observed usage on the error: the caller accounts the CONFIRMED cost (never
    # zero) before stopping.
    try:
        raw_sha = _write_raw(seq, {"seq": seq,
                                   "request_sha256": manifest_entry["request_sha256"],
                                   "response": resp, "payload": payload})
    except RawPersistenceError as exc:
        raise RawPersistenceError(str(exc), in_tok=in_tok, out_tok=out_tok)
    return payload, in_tok, out_tok, raw_sha


# ========================================================================================
# DRY RUN (zero inference) -- exercise everything up to (not including) client.converse()
# ========================================================================================
def dry_run(out_dir: str = OUT) -> dict:
    """Prove, for all 36 scheduled calls and WITHOUT any Converse/InvokeModel call:
    path isolation, frozen reverify, request build+hash match, token-manifest binding,
    prospective cost guard wiring, stop-rule wiring, and output-path isolation.

    Writes a single synthetic report OUTSIDE the model-observation paths
    (execution/DRY_RUN_REPORT.json), never a raw/scores/ledger observation artifact.
    """
    frozen = load_frozen(out_dir)
    prereg = frozen["prereg"]
    path_report = assert_v6_1_paths(prereg.get("experiment", EXPERIMENT_ID_PREFIX), out_dir)
    problems = reverify(frozen, out_dir)

    shared, cost = frozen["shared"], frozen["cost"]
    ceiling = float(cost["hard_ceiling_usd"])
    price_in = float(cost["price_in_per_1k"])
    price_out = float(cost["price_out_per_1k"])
    acct = TRN.TransportAccounting(price_in, price_out, ceiling)

    by_seq = {e["seq"]: e for e in frozen["token_manifest"]["entries"]}
    calls = sorted(frozen["schedule"]["calls"], key=lambda c: c["seq"])
    checked = []
    running_max = 0.0
    for c in calls:
        seq = c["seq"]
        me = by_seq.get(seq)
        row = {"seq": seq, "arm": c["arm"], "fixture_id": c["fixture_id"], "rep": c["rep"]}
        if me is None:
            row["problem"] = "missing token manifest entry"
            problems.append(f"seq {seq}: missing token manifest entry")
            checked.append(row)
            continue
        pk = frozen["packets"][c["arm"]][c["fixture_id"]]
        try:
            req = verify_request_binding(frozen, pk, seq, me)
            row["request_sha256"] = TC.request_sha256(req)
            row["request_hash_ok"] = True
        except (RequestHashMismatch,) as exc:
            row["request_hash_ok"] = False
            row["problem"] = str(exc)
            problems.append(str(exc))
        # prospective cost guard, simulated at the worst case (record the max each call):
        projected = float(me["max_request_cost_usd"])
        row["max_request_cost_usd"] = projected
        row["guard_would_block_if_alone_over_ceiling"] = (projected > ceiling)
        running_max += projected
        checked.append(row)

    # the guard is prospective: prove the FULL worst-case sequence stays within ceiling
    within_ceiling = running_max <= ceiling
    report = {
        "dry_run_version": EXECUTE_VERSION,
        "synthetic": True,
        "zero_inference": True,
        "path_report": path_report,
        "n_scheduled_calls": len(calls),
        "all_36_present": len(calls) == int(cost["n_calls_total"]),
        "reverify_problems": problems,
        "reverify_ok": not problems,
        "worst_case_total_cost_usd": round(running_max, 6),
        "hard_ceiling_usd": ceiling,
        "worst_case_within_ceiling": within_ceiling,
        "cost_guard_is_prospective": True,
        "cost_guard_formula": ("confirmed_actual_spend + unresolved_reserved_exposure + "
                               "frozen max_request_cost_usd(next) <= hard_ceiling_usd, "
                               "checked BEFORE client.converse(); an unknown-after-send "
                               "request reserves its full frozen maximum and is never "
                               "treated as zero exposure"),
        "conservative_exposure_model": {
            "NOT_SENT": "zero exposure",
            "CONFIRMED": "actual provider usage (<= frozen max)",
            "UNKNOWN_AFTER_SEND": "frozen max_request_cost_usd retained, never released"},
        "checked_calls": checked,
    }
    # write the synthetic report to a NON-observation, NON-execution path, V6.1-guarded.
    # Deliberately NOT under execution/: a dry run must not create the execution directory
    # nor anything a lifecycle check could mistake for a real run. The name is explicit.
    outpath = f"{out_dir}/DRY_RUN_REPORT.json"
    assert_write_target_is_v6_1(outpath)
    with open(outpath, "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True, default=str)
    return report


# ========================================================================================
# LIVE EXECUTION (authorized only)
# ========================================================================================
def execute(client, out_dir: str = OUT, *, ceiling_override: float | None = None) -> dict:
    """Execute the frozen V6.1 schedule against a Converse-capable client. Returns a summary.

    The client is provided by the caller (main() builds the no-retry Bedrock client; tests
    pass deterministic fakes). Path safety, reverify, preflight and the retry assertion have
    already been enforced by main() before this is called; execute() re-checks the terminal
    state and the prospective cost guard on every iteration.
    """
    frozen = load_frozen(out_dir)
    prereg = frozen["prereg"]
    assert_v6_1_paths(prereg.get("experiment", EXPERIMENT_ID_PREFIX), out_dir)

    shared, cost = frozen["shared"], frozen["cost"]
    ceiling = float(ceiling_override if ceiling_override is not None
                    else cost["hard_ceiling_usd"])
    acct = TRN.TransportAccounting(float(cost["price_in_per_1k"]),
                                   float(cost["price_out_per_1k"]), ceiling)
    packets = frozen["packets"]
    by_seq = {e["seq"]: e for e in frozen["token_manifest"]["entries"]}
    calls = sorted(frozen["schedule"]["calls"], key=lambda c: c["seq"])

    assert_write_target_is_v6_1(EXEC_DIR)
    os.makedirs(f"{EXEC_DIR}/raw", exist_ok=True)

    state = S_STARTED
    scores, stop = [], None
    cost_violations = []
    class_counts = {c: 0 for c in K.HYPOTHESIS_CLASSES}
    n_resp_fatal = n_infra = 0
    fixtures_seen, valid_per_arm = set(), {"base": 0, "research": 0}
    executed_seq = set()
    # CONSERVATIVE EXPOSURE (v2): the sum of frozen per-request maxima for SENT requests
    # whose billing outcome is unknowable. Never released. The guard adds this to confirmed
    # spend so an unknown-after-send request can never be treated as zero exposure.
    unresolved_reserved_exposure = 0.0
    billing_ledger = []          # per-seq: {seq, arm, fixture_id, rep, billing_status, ...}
    log_path = f"{EXEC_DIR}/execution_log.jsonl"
    assert_write_target_is_v6_1(log_path)
    log = open(log_path, "a")

    for c in calls:
        if state in _TERMINAL_STATES:
            raise TerminalStateError(f"call attempted in terminal state {state}")
        seq = c["seq"]
        if seq in executed_seq:                              # no duplicate execution index
            stop = [{"rule": "V6_1_STOP_DUPLICATE_INDEX", "class": "APPARATUS",
                     "detail": f"execution index {seq} already executed"}]
            state = S_STOPPED
            break
        pk = packets[c["arm"]][c["fixture_id"]]
        me = by_seq.get(seq)
        if me is None:                                       # missing manifest entry -> NOT_SENT
            billing_ledger.append({"seq": seq, "arm": c["arm"],
                                   "fixture_id": c["fixture_id"], "rep": c["rep"],
                                   "billing_status": BILLING_NOT_SENT,
                                   "reserved_exposure_usd": 0.0,
                                   "reason": "no token-manifest entry; request never sent"})
            stop = [{"rule": "V6_1_STOP_TOKEN_MANIFEST_MISSING", "class": "APPARATUS",
                     "detail": f"no token-manifest entry for seq {seq}; cannot bound cost"}]
            state = S_STOPPED
            break

        # PROSPECTIVE COST GUARD -- conservative exposure, before any paid method.
        projected = float(me["max_request_cost_usd"])
        accounted_exposure = acct.spend_usd + unresolved_reserved_exposure
        if (accounted_exposure + projected) > ceiling:
            billing_ledger.append({"seq": seq, "arm": c["arm"],
                                   "fixture_id": c["fixture_id"], "rep": c["rep"],
                                   "billing_status": BILLING_NOT_SENT,
                                   "reserved_exposure_usd": 0.0,
                                   "reason": "cost guard tripped; request never sent"})
            stop = [{"rule": "V6_1_STOP_COST_CEILING", "class": "APPARATUS",
                     "detail": f"next call max cost ${projected:.4f} + confirmed "
                               f"${acct.spend_usd:.4f} + unresolved "
                               f"${unresolved_reserved_exposure:.4f} would exceed "
                               f"${ceiling:.4f}"}]
            state = S_STOPPED
            break

        try:
            payload, in_tok, out_tok, raw_sha = call_once(client, frozen, pk, seq, me)
            acct.record_call(seq, in_tok, out_tok)
            executed_seq.add(seq)
            confirmed = (in_tok / 1000 * float(cost["price_in_per_1k"])
                         + out_tok / 1000 * float(cost["price_out_per_1k"]))
            billing_ledger.append({"seq": seq, "arm": c["arm"],
                                   "fixture_id": c["fixture_id"], "rep": c["rep"],
                                   "billing_status": BILLING_CONFIRMED,
                                   "confirmed_cost_usd": round(confirmed, 6),
                                   "frozen_max_cost_usd": projected,
                                   "reserved_exposure_usd": 0.0,
                                   "raw_sha256": raw_sha})
            # reconcile observed input usage against the frozen hard bound.
            if in_tok > int(me["input_tokens"]):
                cost_violations.append({"seq": seq, "observed_input_tokens": in_tok,
                                        "frozen_bound": int(me["input_tokens"])})
                stop = [{"rule": "V6_1_STOP_COST_BOUND_VIOLATION", "class": "APPARATUS",
                         "detail": f"seq {seq}: observed input {in_tok} exceeds frozen "
                                   f"bound {me['input_tokens']}; hard-bound guarantee no "
                                   f"longer trustworthy. Aborting further spend."}]
                state = S_STOPPED
                break
        except RawPersistenceError as exc:
            # the response WAS received (hence billed) but could not be persisted: account
            # the CONFIRMED usage (never zero), record evidence, then stop.
            acct.record_call(seq, exc.in_tok, exc.out_tok)
            executed_seq.add(seq)
            confirmed = (exc.in_tok / 1000 * float(cost["price_in_per_1k"])
                         + exc.out_tok / 1000 * float(cost["price_out_per_1k"]))
            billing_ledger.append({"seq": seq, "arm": c["arm"],
                                   "fixture_id": c["fixture_id"], "rep": c["rep"],
                                   "billing_status": BILLING_CONFIRMED,
                                   "confirmed_cost_usd": round(confirmed, 6),
                                   "frozen_max_cost_usd": projected,
                                   "reserved_exposure_usd": 0.0,
                                   "reason": f"raw persistence failed after billed "
                                             f"response: {exc}"})
            stop = [{"rule": "V6_1_STOP_RAW_PERSISTENCE", "class": "APPARATUS",
                     "detail": f"seq {seq}: {exc}"}]
            state = S_STOPPED
            break
        except RequestHashMismatch as exc:
            # raised INSIDE call_once BEFORE client.converse() -> NOT_SENT, zero exposure.
            billing_ledger.append({"seq": seq, "arm": c["arm"],
                                   "fixture_id": c["fixture_id"], "rep": c["rep"],
                                   "billing_status": BILLING_NOT_SENT,
                                   "reserved_exposure_usd": 0.0,
                                   "reason": f"request-hash mismatch before send: {exc}"})
            stop = [{"rule": "V6_1_STOP_REQUEST_HASH_MISMATCH", "class": "APPARATUS",
                     "detail": f"seq {seq}: {exc}"}]
            state = S_STOPPED
            break
        except Exception as exc:      # UNKNOWN_AFTER_SEND -- entered converse(), NO RETRY
            # Bedrock may have accepted and billed the request; no usage returned. Retain
            # the FULL frozen maximum as unresolved exposure. NEVER treat as zero.
            unresolved_reserved_exposure += projected
            acct.record_transport_failure(seq, f"{type(exc).__name__}: {exc}")
            billing_ledger.append({"seq": seq, "arm": c["arm"],
                                   "fixture_id": c["fixture_id"], "rep": c["rep"],
                                   "billing_status": BILLING_UNKNOWN_AFTER_SEND,
                                   "reserved_exposure_usd": projected,
                                   "frozen_max_cost_usd": projected,
                                   "no_retry": True,
                                   "request_sha256": me["request_sha256"],
                                   "send_ts": int(time.time()),
                                   "exception": f"{type(exc).__name__}: "
                                                f"{str(exc)[:300]}"})
            log.write(json.dumps({"seq": seq, "outcome": "UNKNOWN_AFTER_SEND",
                                  "billing_status": BILLING_UNKNOWN_AFTER_SEND,
                                  "reserved_exposure_usd": projected, "no_retry": True,
                                  "request_sha256": me["request_sha256"],
                                  "error": f"{type(exc).__name__}: {exc}"}) + "\n")
            log.flush()
            res = STOP.classify_stop(
                n_calls_charged=acct.n_charged, fixtures_observed=sorted(fixtures_seen),
                valid_calls_per_arm=valid_per_arm, class_counts=class_counts,
                n_hypotheses_adjudicated=sum(class_counts.values()),
                n_responses_fatal=n_resp_fatal, n_infrastructure_failures=n_infra,
                n_consecutive_transport_failures=acct.n_consecutive_transport_failures,
                spend_usd=acct.spend_usd, ceiling_usd=ceiling)
            if res["stop"]:
                stop = res["fired"]
                state = S_STOPPED
                break
            continue

        # RAW IS PERSISTED. Only now adjudicate + score.
        adj = V.adjudicate(payload, packet=pk, expected_packet_hash=pk["packet_hash"],
                           expected_fixture_id=pk["fixture_id"])
        sc = SC.score_response(adj, pk)
        sc["arm"] = c["arm"]
        scores.append({"seq": seq, "arm": c["arm"], "fixture_id": c["fixture_id"],
                       "rep": c["rep"], "raw_sha256": raw_sha, "scorecard": sc})
        fixtures_seen.add(c["fixture_id"])
        if adj.fatal:
            n_resp_fatal += 1
        else:
            valid_per_arm[c["arm"]] = valid_per_arm.get(c["arm"], 0) + 1
            for a in adj.hypotheses:
                class_counts[a.outcome_class] = class_counts.get(a.outcome_class, 0) + 1
                if a.outcome_class == K.INFRASTRUCTURE_FAILURE:
                    n_infra += 1

        log.write(json.dumps({"seq": seq, "arm": c["arm"], "fixture_id": c["fixture_id"],
                              "rep": c["rep"], "input_tokens": in_tok,
                              "output_tokens": out_tok,
                              "cumulative_usd": round(acct.spend_usd, 6),
                              "response_class": adj.response_class,
                              "raw_sha256": raw_sha,
                              "n_qualified": sc.get("n_qualified"),
                              "ts": int(time.time())}) + "\n")
        log.flush()

        res = STOP.classify_stop(
            n_calls_charged=acct.n_charged, fixtures_observed=sorted(fixtures_seen),
            valid_calls_per_arm=valid_per_arm, class_counts=class_counts,
            n_hypotheses_adjudicated=sum(class_counts.values()),
            n_responses_fatal=n_resp_fatal, n_infrastructure_failures=n_infra,
            n_consecutive_transport_failures=acct.n_consecutive_transport_failures,
            spend_usd=acct.spend_usd, ceiling_usd=ceiling)
        if res["stop"]:
            stop = res["fired"]
            state = S_STOPPED
            break

    log.close()
    if state == S_STARTED:
        state = S_COMPLETE
    confirmed_cost = round(acct.spend_usd, 6)
    unknown_exposure = round(unresolved_reserved_exposure, 6)
    conservative_exposure = round(confirmed_cost + unknown_exposure, 6)
    summary = {"execute_version": EXECUTE_VERSION,
               "n_calls_planned": len(calls),
               "transport": acct.to_dict(),
               "class_counts": class_counts,
               "n_responses_fatal": n_resp_fatal,
               "n_infrastructure_failures": n_infra,
               "fixtures_observed": sorted(fixtures_seen),
               "valid_calls_per_arm": valid_per_arm,
               "cost_bound_violations": cost_violations,
               "hard_ceiling_usd": ceiling,
               # CONSERVATIVE COST ACCOUNTING (v2): confirmed vs unknown-after-send exposure
               "confirmed_provider_cost_usd": confirmed_cost,
               "unknown_after_send_max_exposure_usd": unknown_exposure,
               "conservative_accounted_exposure_usd": conservative_exposure,
               "n_unknown_after_send": sum(
                   1 for e in billing_ledger
                   if e["billing_status"] == BILLING_UNKNOWN_AFTER_SEND),
               "billing_ledger": billing_ledger,
               "conservative_exposure_within_ceiling": conservative_exposure <= ceiling,
               "stop": stop,
               "execution_state": state,
               "execution_status": "STOPPED" if stop else "COMPLETE"}
    for name, obj in (("execution_summary.json", summary), ("scores.json", scores)):
        p = f"{EXEC_DIR}/{name}"
        assert_write_target_is_v6_1(p)
        with open(p, "w") as fh:
            json.dump(obj, fh, indent=1, sort_keys=True, default=str)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-have-authorization", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ceiling", type=float, default=None)
    args = ap.parse_args()

    frozen = load_frozen()
    prereg = frozen["prereg"]
    cost = frozen["cost"]

    # PATH SAFETY -- always, before anything else can happen.
    try:
        path_report = assert_v6_1_paths(prereg.get("experiment", EXPERIMENT_ID_PREFIX), OUT)
    except PathSafetyError as exc:
        print("ABORT at $0.00 -- path safety failed:", exc)
        return 4

    if args.dry_run:
        rep = dry_run()
        print("=== V6.1 DRY RUN (ZERO INFERENCE) ===")
        print(f"  experiment           : {path_report['experiment_id']}")
        print(f"  output dir           : {path_report['resolved_output_dir']}")
        print(f"  scheduled calls      : {rep['n_scheduled_calls']} "
              f"(all 36: {rep['all_36_present']})")
        print(f"  reverify ok          : {rep['reverify_ok']}")
        for p in rep["reverify_problems"]:
            print("    PROBLEM:", p)
        print(f"  worst-case cost      : ${rep['worst_case_total_cost_usd']} "
              f"<= ${rep['hard_ceiling_usd']}: {rep['worst_case_within_ceiling']}")
        print(f"  cost guard prospective: {rep['cost_guard_is_prospective']}")
        return 0 if (rep["reverify_ok"] and rep["worst_case_within_ceiling"]) else 5

    if not args.i_have_authorization:
        print("REFUSING TO RUN: no authorization flag. Zero spend.")
        print(f"  experiment            : {prereg.get('experiment')}")
        print(f"  preregistered calls   : {cost['n_calls_total']}")
        print(f"  max billable attempts : {cost['max_billable_attempts_total']} "
              f"({cost['max_billable_attempts_per_call']}/call, retries disabled)")
        print(f"  hard ceiling          : ${cost['hard_ceiling_usd']}")
        print("  NOTE: this driver was frozen as an apparatus amendment; execution requires "
              "FRESH human authorization bound to this driver's hash.")
        return 0

    # reverify frozen artifacts at $0 before constructing a client.
    problems = reverify(frozen)
    if problems:
        print("ABORT at $0.00 -- frozen artifacts moved since preregistration:")
        for p in problems:
            print("   ", p)
        return 2

    client = TRN.build_client()
    try:
        env = TRN.preflight(client)     # raises on no-converse OR retries-enabled
    except TRN.TransportPreflightFailure as exc:
        print("ABORT at $0.00 -- transport preflight failed:", exc)
        return 3
    print(f"preflight OK | retries disabled: "
          f"{env['retry_policy']['retries_disabled_on_client']}")

    ceiling = args.ceiling or cost["hard_ceiling_usd"]
    summary = execute(client, ceiling_override=ceiling)
    print(json.dumps(summary, indent=1, default=str))
    return 0


def version_stamp() -> dict:
    return {"execute_version": EXECUTE_VERSION,
            "experiment_id_prefix": EXPERIMENT_ID_PREFIX,
            "output_dir": OUT,
            "forbidden_dir": V6_FORBIDDEN_DIR,
            "lifecycle_states": [S_NOT_STARTED, S_AUTHORIZED, S_STARTED, S_COMPLETE,
                                 S_STOPPED, S_ABORTED],
            "canonical_request_builder": "v6_token_count.canonical_converse_request",
            "evaluator": "v6_1_verdict (run separately, once, on immutable scores)",
            "stop_rules": "v6_stop.classify_stop (frozen)",
            "retries_disabled": True,
            "prospective_cost_guard": True,
            "conservative_exposure_model": {
                "not_sent": "zero exposure",
                "confirmed": "actual provider usage (reconciled, <= frozen max)",
                "unknown_after_send": "frozen max_request_cost_usd reserved, never released"},
            "unknown_after_send_is_never_zero_exposure": True,
            "billing_states": [BILLING_NOT_SENT, BILLING_CONFIRMED,
                               BILLING_UNKNOWN_AFTER_SEND],
            "raw_before_adjudication": True,
            "defines_scientific_policy": False}


if __name__ == "__main__":
    raise SystemExit(main())
