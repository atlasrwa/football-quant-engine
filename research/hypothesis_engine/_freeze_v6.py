"""Freeze the V6 preregistration. ZERO SPEND -- no Bedrock, no network.

Everything a paid run consumes is fixed here, before the run, with the reason it takes the
value it does: the call sequence (§6, §27), the cost model (§28), the evaluator (§24), the
stop rules (§7, §8), the scientific gates (§25, §26), and every module/packet/request hash
(§30, §36). Nothing that affects scientific aggregation may be created after the first paid
call, so this script is the last thing that runs before authorization and the artifacts it
writes are the contract.

CALL COUNT IS DERIVED, NOT INHERITED (§27)
-------------------------------------------
V5A.2's 38 is not carried over. `v6_schedule.build_sequence` derives 36 from the design:
10 paired fixtures x 2 arms (20 primaries) + 4 repeat fixtures x 2 arms x 2 extra repeats
(16 self-noise repeats). The sequence is a FLAT list with an explicit `seq`; the driver
consumes it verbatim and cannot expand a count into an order of its own -- the seam that
put V5A.2's stop rule on one fixture.

COST IS MEASURED AGAINST THE EXACT V6 REQUESTS (§28)
-----------------------------------------------------
tokens-per-byte is calibrated from V5A.1's six OBSERVED paid calls (the only real
measurement of how this packet shape tokenizes), then applied to the ACTUAL serialized V6
request bytes -- system prompt + NUL + serialized packet, per call, at the frozen
max_tokens. The hard ceiling assumes max_tokens on every output, so it is a true bound
under the configured request parameters, not an average dressed up as one.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import (capability, firewall, firewall_v4, firewall_v5,
                                            schema_v2, schema_v3, schema_v4,
                                            validator_v5, vocabulary)
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_contract as C
from src.research.hypothesis_oos import v5a2_ontology as O
from src.research.hypothesis_oos import v5a2_translate as TR
from src.research.hypothesis_oos import v6_baseline as BL
from src.research.hypothesis_oos import v6_classes as K
from src.research.hypothesis_oos import v6_conditioning as CD
from src.research.hypothesis_oos import v6_numeric_contract as NC
from src.research.hypothesis_oos import v6_prompt as PR
from src.research.hypothesis_oos import v6_qualified as Q
from src.research.hypothesis_oos import v6_repeatability as RP
from src.research.hypothesis_oos import v6_schedule as SCH
from src.research.hypothesis_oos import v6_scorecard as SCC
from src.research.hypothesis_oos import v6_selfnoise as SN
from src.research.hypothesis_oos import v6_stop as STOP
from src.research.hypothesis_oos import v6_token_count as TC
from src.research.hypothesis_oos import v6_transport as TRN
from src.research.hypothesis_oos import v6_verdict as VD

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v6"
V5A1_OUT = f"{ROOT}/research/hypothesis_oos/out/v5a1"

# ---- calibration, from V5A.1's six observed paid calls (same source as V5A.2) ----------
V5A1_OBSERVED = {"base": 14380, "research": 57011}
OUTPUT_TOKENS_MEAN = 4376
OUTPUT_TOKENS_P90 = 5232
OUTPUT_TOKENS_MAX = 8192           # the request's own max_tokens ceiling -- the hard bound
PRICE_IN_PER_1K = 0.003
PRICE_OUT_PER_1K = 0.015

#: Frozen pricing contract (Audit 9). On-demand / standard service tier for the exact model
#: the inference profile resolves to, in the run region. The hard ceiling uses the standard
#: on-demand rate and takes NO caching/batch/long-context discount, because none is
#: mechanically guaranteed for this run. If AWS pricing changes before execution, the
#: contract is STALE and must be refrozen transparently -- never silently edited mid-run.
PRICING_CONTRACT = {
    "provider": "aws_bedrock",
    "model_family": "anthropic.claude-sonnet-4-6",
    "inference_profile": "us.anthropic.claude-sonnet-4-6",
    "region": "us-east-1",
    "service_tier": "on_demand_standard",
    "input_price_per_1k_usd": PRICE_IN_PER_1K,
    "output_price_per_1k_usd": PRICE_OUT_PER_1K,
    "token_class": "text (no cache read/write discount applied)",
    "discounts_applied": "none -- hard ceiling uses the highest applicable standard rate",
    "source": "AWS Bedrock pricing, Anthropic Claude Sonnet 4.6, on-demand, us-east-1",
    "as_of": "2026-09-14",
    "note": "prices are frozen; a provider price change before execution makes this "
            "contract stale rather than authorizing a silent edit.",
}

MODEL_ID = "us.anthropic.claude-sonnet-4-6"
TEMPERATURE = 0.0
MAX_TOKENS = 8192
CALIBRATION_FIXTURE = "mt_010243515"


def _cost_usd_ceil(input_tokens: int, output_tokens: int) -> float:
    """Maximum dollar cost of a request, ROUNDED UP to the cent, in exact integer arithmetic.

    Works in micro-dollars (integers) so no float can round the bound DOWN, then ceils to
    the next cent. `input_tokens` must be exact or a proven upper bound; `output_tokens` is
    the configured max. A hard ceiling must never round down (Audit 6).
    """
    # price per token in micro-dollars, exact: $0.003/1k = 3 micro-USD/token;
    # $0.015/1k = 15 micro-USD/token.
    in_micro = int(round(PRICE_IN_PER_1K * 1_000_000 / 1000))     # = 3
    out_micro = int(round(PRICE_OUT_PER_1K * 1_000_000 / 1000))   # = 15
    total_micro = input_tokens * in_micro + output_tokens * out_micro
    cents = math.ceil(total_micro / 10_000)      # 10,000 micro-USD = 1 cent; ROUND UP
    return cents / 100.0


def _validate_token_manifest(entries: list, calls: list) -> list:
    """Deterministic pre-inference validation of the token manifest. Returns problems."""
    problems = []
    if len(entries) != len(calls):
        problems.append(f"{len(entries)} manifest entries != {len(calls)} planned calls")
    seqs = [e["seq"] for e in entries]
    if len(set(seqs)) != len(seqs):
        problems.append("duplicate execution index (seq) in token manifest")
    if sorted(seqs) != sorted(c["seq"] for c in calls):
        problems.append("token manifest seqs do not match the planned call seqs")
    for e in entries:
        if not isinstance(e.get("input_tokens"), int) or e["input_tokens"] < 0:
            problems.append(f"seq {e.get('seq')}: input_tokens is not a non-negative int")
        if e.get("input_tokens_is_upper_bound") is not True:
            problems.append(f"seq {e.get('seq')}: input_tokens not flagged upper-bound")
        if e.get("max_billable_attempts") != TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL:
            problems.append(f"seq {e.get('seq')}: max_billable_attempts != 1")
        if not e.get("request_sha256"):
            problems.append(f"seq {e.get('seq')}: missing request_sha256")
    return problems



# V6 modules whose CONTENT is proven by hash.
MODULES = [
    "src/research/hypothesis_oos/v6_classes.py",
    "src/research/hypothesis_oos/v6_numeric_contract.py",
    "src/research/hypothesis_oos/v6_baseline.py",
    "src/research/hypothesis_oos/v6_conditioning.py",
    "src/research/hypothesis_oos/v6_qualified.py",
    "src/research/hypothesis_oos/v6_repeatability.py",
    "src/research/hypothesis_oos/v6_selfnoise.py",
    "src/research/hypothesis_oos/v6_schedule.py",
    "src/research/hypothesis_oos/v6_stop.py",
    "src/research/hypothesis_oos/v6_scorecard.py",
    "src/research/hypothesis_oos/v6_verdict.py",
    "src/research/hypothesis_oos/v6_token_count.py",
    "src/research/hypothesis_oos/v6_prompt.py",
    "src/research/hypothesis_oos/v6_transport.py",
    "src/research/hypothesis_engine/schema_v4.py",
    "src/research/hypothesis_engine/firewall_v5.py",
    "src/research/hypothesis_engine/validator_v5.py",
    "research/hypothesis_engine/_build_v6.py",
    "research/hypothesis_engine/_freeze_v6.py",
    "research/hypothesis_engine/_execute_v6.py",
    "tests/research/hypothesis_oos/test_v6_prespend.py",
]
# Frozen upstream modules that MUST NOT have changed. Hashed to prove V6 did not reach into
# V2/V3/V5A/V5A.1/V5A.2 territory. Includes the entire V5A.2 stack, now frozen.
FROZEN_MODULES = [
    "src/research/hypothesis_engine/schema.py",
    "src/research/hypothesis_engine/schema_v2.py",
    "src/research/hypothesis_engine/schema_v3.py",
    "src/research/hypothesis_engine/validator.py",
    "src/research/hypothesis_engine/validator_v2.py",
    "src/research/hypothesis_engine/validator_v3.py",
    "src/research/hypothesis_engine/validator_v4.py",
    "src/research/hypothesis_engine/firewall.py",
    "src/research/hypothesis_engine/firewall_v2.py",
    "src/research/hypothesis_engine/firewall_v3.py",
    "src/research/hypothesis_engine/firewall_v4.py",
    "src/research/hypothesis_engine/vocabulary.py",
    "src/research/hypothesis_engine/capability.py",
    "src/research/hypothesis_engine/condition_contract.py",
    "src/research/hypothesis_engine/query_plan.py",
    "src/research/hypothesis_engine/availability.py",
    "src/research/hypothesis_engine/lifecycle.py",
    "src/research/hypothesis_oos/v5a1_evidence.py",
    "src/research/hypothesis_oos/v5a1_packet.py",
    "src/research/hypothesis_oos/v5a1_semantics.py",
    "src/research/hypothesis_oos/v5a2_ontology.py",
    "src/research/hypothesis_oos/v5a2_packet.py",
    "src/research/hypothesis_oos/v5a2_admissibility.py",
    "src/research/hypothesis_oos/v5a2_contract.py",
    "src/research/hypothesis_oos/v5a2_translate.py",
    "src/research/hypothesis_oos/v5a2_transport.py",
    "src/research/hypothesis_oos/v5a2_prompt.py",
]
CHAMPION_ARTIFACT = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _sha_text(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def calibration() -> dict:
    """tokens-per-byte, measured per arm on V5A.1's observed counts."""
    from src.research.hypothesis_oos import v5a1_prompt as PR1
    v1 = {arm: json.load(open(f"{V5A1_OUT}/packets_{arm}.json"))
          for arm in ("base", "research")}
    out = {}
    for arm in ("base", "research"):
        payload = PR1.build_user_payload(v1[arm][CALIBRATION_FIXTURE])
        total_bytes = len(payload) + len(PR1.SYSTEM_PROMPT)
        out[arm] = {"v5a1_total_bytes": total_bytes,
                    "v5a1_observed_input_tokens": V5A1_OBSERVED[arm],
                    "tokens_per_byte": V5A1_OBSERVED[arm] / total_bytes}
    return out


def _load_exact_counts() -> dict:
    """The provider-native exact input-token counts, keyed by canonical request SHA-256.

    Read from the FROZEN `EXACT_INPUT_TOKEN_MANIFEST.json` produced by the CountTokens
    driver (`_count_tokens_v6.py`). The freeze stays DETERMINISTIC and makes NO network
    call: it reads a frozen file whose contents are byte-reproducible. When the file is
    absent (e.g. before CountTokens was ever run), the freeze falls back to the provable
    UTF-8-byte upper bound, exactly as before -- so the freeze never depends on live
    CountTokens availability. When present, the exact count is bound to the request hash and
    used as the input-token term, tightening the ceiling to the provider's own accounting.

    An exact count is a hard bound too: `input_tokens_is_upper_bound` stays True because the
    provider's own count is exactly what the provider will bill, and it is asserted <= the
    conservative byte bound so a tokenizer-assumption break is caught at freeze.
    """
    path = f"{OUT}/EXACT_INPUT_TOKEN_MANIFEST.json"
    try:
        doc = json.load(open(path))
    except FileNotFoundError:
        return {}
    out = {}
    for e in doc["entries"]:
        out[e["request_sha256"]] = {
            "exact_input_tokens": int(e["exact_input_tokens"]),
            "count_model_id": e["count_tokens_model_id"],
            "byte_bound": int(e["conservative_byte_upper_bound"]),
        }
    return out


def main():
    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}
    paired = sorted(set(packets["base"]) & set(packets["research"]))
    cal = calibration()
    exact_counts = _load_exact_counts()   # provider-native, frozen; empty -> byte-bound path

    # ---- the frozen call sequence (§6, §27) ----
    calls = SCH.build_sequence(paired)
    elig = STOP.MIN_CALLS_BEFORE_RATE_STOP
    order_props = SCH.order_properties(calls, elig)
    freeze_problems = SCH.freeze_assertions(
        calls, elig, min_prefix_fixtures=STOP.MIN_STOP_FIXTURES,
        min_prefix_calls_per_arm=STOP.MIN_STOP_VALID_CALLS_PER_ARM,
        min_repeat_groups_per_arm=SN.MIN_REPEAT_GROUPS_PER_ARM)
    assert not freeze_problems, f"schedule not freezable: {freeze_problems}"

    # ---- per-call request hashes + cost (§28) ----
    # HARD-BOUND input tokens: a provable UTF-8-byte upper bound (never the empirical
    # bytes-to-token ratio, which is kept below only as a diagnostic for expected/p90). The
    # freeze is DETERMINISTIC and makes NO network call: it must rebuild byte-identically
    # across environments and PYTHONHASHSEED, so it cannot depend on live CountTokens
    # availability or on a provider error string. The exact provider-native CountTokens value
    # is used at RUN TIME by the driver to reconcile/tighten (informational) -- it can only
    # ever be <= the byte bound, so using the byte bound in the frozen ceiling is safe and
    # is the conservative choice. See v6_token_count for the proof.
    manifest_calls, tot_in_est, tot_in_bound = [], 0, 0
    tot_byte_bound = 0
    token_manifest = []
    tot_mean = tot_p90 = tot_max = 0
    for c in calls:
        arm, fid = c["arm"], c["fixture_id"]
        pk = packets[arm][fid]
        payload = PR.build_user_payload(pk)
        total_bytes = len(payload) + len(PR.SYSTEM_PROMPT)
        in_tok_est = int(round(total_bytes * cal[arm]["tokens_per_byte"]))   # DIAGNOSTIC

        te = TC.token_entry(pk, model_id=MODEL_ID, temperature=TEMPERATURE,
                            max_tokens=MAX_TOKENS, client=None)   # deterministic byte bound

        # Provider-native EXACT input tokens, if a frozen CountTokens manifest exists for
        # this exact request hash (pre-spend EXACT-token amendment, Audit 5/6). The exact
        # provider count IS what the provider bills, so it is a hard bound; it is asserted
        # <= the conservative byte bound so a tokenizer-assumption break is caught here. When
        # no exact count exists the byte bound stands, and the freeze remains deterministic
        # and network-free in BOTH cases (the exact counts are read from a frozen file).
        ex = exact_counts.get(te["request_sha256"])
        if ex is not None:
            assert ex["exact_input_tokens"] <= te["conservative_byte_upper_bound"], (
                f"exact count {ex['exact_input_tokens']} exceeds byte bound "
                f"{te['conservative_byte_upper_bound']} for {te['request_sha256'][:12]}")
            assert ex["count_model_id"] == te["count_model_id"], (
                f"exact-count model id {ex['count_model_id']} != {te['count_model_id']}")
            te = {**te,
                  "input_tokens": ex["exact_input_tokens"],
                  "input_tokens_method": TC.METHOD_EXACT,
                  "exact_count_tokens": ex["exact_input_tokens"]}
        in_tok_bound = te["input_tokens"]              # exact provider count OR byte bound
        max_req_cost = _cost_usd_ceil(in_tok_bound, MAX_TOKENS)

        manifest_calls.append({
            **c,
            "packet_hash": pk["packet_hash"],
            "derived_from_v5a1_packet_hash": pk.get("derived_from_v5a1_packet_hash"),
            "payload_bytes": len(payload),
            "est_input_tokens": in_tok_est,
            "hard_bound_input_tokens": in_tok_bound,
            "input_tokens_method": te["input_tokens_method"],
            "canonical_request_sha256": te["request_sha256"],
            "serialized_request_sha256": _sha_text(PR.serialized_request(pk))})
        token_manifest.append({
            "seq": c["seq"], "fixture_id": fid, "arm": arm, "rep": c["rep"],
            "role": c.get("role"),
            **{k: te[k] for k in (
                "request_sha256", "input_tokens", "input_tokens_method",
                "input_tokens_is_upper_bound", "conservative_byte_upper_bound",
                "exact_count_tokens", "count_tokens_error", "count_model_id",
                "converse_model_id", "max_output_tokens", "token_count_version")},
            "max_billable_attempts": TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL,
            "max_request_cost_usd": max_req_cost,
            "price_in_per_1k": PRICE_IN_PER_1K, "price_out_per_1k": PRICE_OUT_PER_1K})
        tot_in_est += in_tok_est
        tot_in_bound += in_tok_bound
        tot_byte_bound += te["conservative_byte_upper_bound"]
        tot_mean += OUTPUT_TOKENS_MEAN
        tot_p90 += OUTPUT_TOKENS_P90
        tot_max += OUTPUT_TOKENS_MAX

    # validate + freeze the token manifest (deterministic, pre-inference)
    tm_problems = _validate_token_manifest(token_manifest, calls)
    assert not tm_problems, f"token manifest invalid: {tm_problems}"
    token_manifest_doc = {
        "token_manifest_version": TC.TOKEN_COUNT_VERSION,
        "n_requests": len(token_manifest),
        "total_input_tokens_hard_bound": tot_in_bound,
        "total_input_tokens_byte_bound": tot_byte_bound,
        "total_max_output_tokens": tot_max,
        "all_methods": sorted({e["input_tokens_method"] for e in token_manifest}),
        "any_exact": any(e["input_tokens_method"] == TC.METHOD_EXACT
                         for e in token_manifest),
        "all_exact": all(e["input_tokens_method"] == TC.METHOD_EXACT
                         for e in token_manifest),
        "input_token_source": (
            "aws_bedrock_count_tokens (provider-native, exact) where a frozen "
            "EXACT_INPUT_TOKEN_MANIFEST entry exists for the request hash; otherwise the "
            "conservative UTF-8-byte upper bound"),
        "all_upper_bounds": all(e["input_tokens_is_upper_bound"] for e in token_manifest),
        "price_in_per_1k": PRICE_IN_PER_1K, "price_out_per_1k": PRICE_OUT_PER_1K,
        "pricing": PRICING_CONTRACT,
        "entries": token_manifest,
    }
    tm_path = f"{OUT}/INPUT_TOKEN_MANIFEST.json"
    with open(tm_path, "w") as fh:
        json.dump(token_manifest_doc, fh, indent=1, sort_keys=True, default=str)

    n_calls = len(calls)
    max_attempts = TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL
    max_billable_attempts = n_calls * max_attempts
    # HARD CEILING = sum of PER-REQUEST maximum costs, each rounded UP to the cent. Summing
    # the per-request rounded maxima (rather than rounding the grand total) guarantees the
    # ceiling is >= the sum the pre-call guard will enforce, so a fully-frozen run can never
    # be falsely blocked by the guard, while every request is still priced at its hard-bound
    # input tokens + max output tokens. Expected/p90 use the estimate and are DIAGNOSTICS
    # only -- they never enter the bound.
    hard_ceiling = round(sum(e["max_request_cost_usd"] for e in token_manifest), 2)
    cost = {
        "calibration": cal,
        "calibration_source": "V5A.1 observed input-token counts on the six paid calls",
        "n_calls_total": n_calls,
        "n_paired_calls": len(paired) * 2,
        "n_repeatability_extra_calls": n_calls - len(paired) * 2,
        "battery_derivation": (
            f"{len(paired)} paired fixtures x 2 arms = {len(paired)*2} primaries; "
            f"{SCH.N_REPEAT_FIXTURES} repeat fixtures x 2 arms x "
            f"{SCH.REPEATS_PER_GROUP - 1} extra repeats = "
            f"{SCH.N_REPEAT_FIXTURES * 2 * (SCH.REPEATS_PER_GROUP - 1)}; total {n_calls}. "
            f"V5A.2's 38 is NOT inherited (§27)."),
        "total_input_tokens_est_DIAGNOSTIC": tot_in_est,
        "total_input_tokens_hard_bound": tot_in_bound,
        "input_token_bound_method": sorted({e["input_tokens_method"]
                                            for e in token_manifest}),
        "input_token_bound_is_empirical_ratio": False,
        "total_output_tokens_mean": tot_mean,
        "total_output_tokens_p90": tot_p90,
        "total_output_tokens_max": tot_max,
        "price_in_per_1k": PRICE_IN_PER_1K, "price_out_per_1k": PRICE_OUT_PER_1K,
        "pricing": PRICING_CONTRACT,
        "token_manifest_file": "INPUT_TOKEN_MANIFEST.json",
        "token_manifest_sha256": _sha_file(tm_path),
        # expected / p90 remain ESTIMATE diagnostics on the empirical ratio -- explicitly
        # NOT part of the hard bound.
        "expected_cost_usd": round(tot_in_est / 1000 * PRICE_IN_PER_1K
                                   + tot_mean / 1000 * PRICE_OUT_PER_1K, 4),
        "p90_cost_usd": round(tot_in_est / 1000 * PRICE_IN_PER_1K
                              + tot_p90 / 1000 * PRICE_OUT_PER_1K, 4),
        "hard_ceiling_usd": hard_ceiling,
        # AMENDMENT 1: a "call" in the BILLING sense is a billable ATTEMPT, not a logical
        # call. The ceiling bounds billable attempts ONLY because the frozen transport policy
        # disables retries, so one logical call bills at most once. AMENDMENT 2: the INPUT
        # token term is no longer an empirical bytes-to-token ratio -- it is exact
        # (CountTokens) or a proven UTF-8-byte upper bound, and the ceiling is rounded UP.
        # Together they make the ceiling a true worst-case billable bound.
        "max_billable_attempts_per_call": max_attempts,
        "max_billable_attempts_total": max_billable_attempts,
        "transport_retry_policy": TRN.retry_policy_report(),
        "hard_ceiling_is_a_true_bound": (
            "yes -- max_tokens output on every one of the "
            f"{n_calls} calls; input tokens are exact-or-conservatively-bounded (method(s) "
            f"{sorted({e['input_tokens_method'] for e in token_manifest})}), never an "
            f"empirical ratio; the dollar ceiling is rounded UP; and the frozen transport "
            f"policy disables retries ({max_attempts} billable attempt per logical call, "
            f"asserted on the client in preflight), so {n_calls} logical calls is at most "
            f"{max_billable_attempts} billable attempts and the ceiling is a true worst-case "
            f"billable bound"),
    }

    # ---- evaluator freeze (§24) ----
    evaluator_freeze = {
        "frozen_before_first_paid_call": True,
        "spend_usd_at_freeze": 0.0,
        "run_exactly_once": True,
        "evaluator_modules": {
            m: _sha_file(f"{ROOT}/{m}") for m in [
                "src/research/hypothesis_engine/validator_v5.py",
                "src/research/hypothesis_engine/firewall_v5.py",
                "src/research/hypothesis_engine/schema_v4.py",
                "src/research/hypothesis_oos/v6_classes.py",
                "src/research/hypothesis_oos/v6_numeric_contract.py",
                "src/research/hypothesis_oos/v6_baseline.py",
                "src/research/hypothesis_oos/v6_conditioning.py",
                "src/research/hypothesis_oos/v6_qualified.py",
                "src/research/hypothesis_oos/v6_scorecard.py",
                "src/research/hypothesis_oos/v6_repeatability.py",
                "src/research/hypothesis_oos/v6_selfnoise.py",
                "src/research/hypothesis_oos/v6_stop.py",
                "src/research/hypothesis_oos/v6_verdict.py",
            ]},
        "version_stamps": {
            "validator": validator_v5.version_stamp(),
            "verdict": VD.version_stamp(),
            "scorecard": SCC.version_stamp(),
            "stop": STOP.version_stamp(),
            "schedule": SCH.version_stamp(),
            "repeatability": RP.version_stamp(),
            "numeric_contract": NC.version_stamp(),
            "prompt": PR.version_stamp(),
            "transport": TRN.version_stamp(),
        },
    }
    with open(f"{OUT}/EVALUATOR_FREEZE.json", "w") as fh:
        json.dump(evaluator_freeze, fh, indent=1, sort_keys=True, default=str)

    # ---- the preregistration itself (§25, §26, §36) ----
    prereg = {
        "preregistration_version": "v6_grounded_research_generator_prereg_v1",
        "experiment": "V6_GROUNDED_RESEARCH_GENERATOR",
        "spend_usd_so_far": 0.0,
        "scientific_question": (
            "Given richer PIT-safe football history, can the LLM generate better grounded, "
            "non-degenerate, deterministically measurable football research hypotheses "
            "than from compressed/base evidence, beyond model self-noise and without loss "
            "of discipline?"),
        "governing_principle": (
            "Build V6 so valid research survives, invalid research is rejected precisely, "
            "apparatus errors are distinguishable from model behaviour, multiple fixtures "
            "are observed before conclusions, self-noise is measured, and richer evidence "
            "is judged on quality not verbosity. A clean FAIL is valuable (§39)."),
        "not_a_repair_of_v5a2": (
            "V5A, V5A.1 and V5A.2 remain immutable historical experiments. V6 reuses their "
            "validated interface and packets unchanged and changes only how a RESPONSE is "
            "adjudicated (hypothesis-level, §3) and how the run is scheduled and judged."),
        "architecture_boundary": (
            "football history -> LLM proposes what to measure -> deterministic compiler -> "
            "deterministic measurement -> statistical validation -> candidate feature -> "
            "OOS -> model/calibration -> p_model -> market -> prospective. V6 STOPS before "
            "predictive feature promotion (§1, §40). The LLM never authors p_model, "
            "probabilities, odds, EV, stakes, advantage scores or effect sizes."),
        "arms": {
            "base": "derived summaries only (ALL_PRIOR, no match rows, no venue split, no "
                    "short windows, no opponent-profile cohorts)",
            "research": "full match-level PIT-safe record + summaries + opponent-profile "
                        "cohorts + short windows + venue splits",
            "only_evidence_representation_differs": True,
            "packets": "the FROZEN V5A.2 packets, byte-identical (packet_identity_audit)"},
        "shared_stack": {
            "model_id": MODEL_ID, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
            "prompt": PR.V6_PROMPT_VERSION,
            "schema": schema_v4.SCHEMA_VERSION,
            "validator": validator_v5.VALIDATOR_VERSION,
            "firewall": firewall_v5.FIREWALL_VERSION,
            "numeric_contract": NC.NUMERIC_CONTRACT_VERSION,
            "admissibility": ADM.ADMISSIBILITY_VERSION,
            "contract": C.CONTRACT_VERSION,
            "translation": TR.TRANSLATION_VERSION,
            "ontology": O.ONTOLOGY_VERSION,
            "transport": TRN.TRANSPORT_VERSION,
            "verdict": VD.VERDICT_VERSION,
            "scorecard": SCC.SCORECARD_VERSION,
            "stop": STOP.STOP_VERSION,
            "schedule": SCH.SCHEDULE_VERSION,
            "vocabulary": vocabulary.VOCABULARY_VERSION,
            "capability_inventory": capability.CAPABILITY_INVENTORY_VERSION,
            "max_hypotheses": schema_v4.MAX_HYPOTHESES},
        "hypothesis_level_adjudication": validator_v5.version_stamp()[
            "response_fatal_conditions"],
        "failure_taxonomy": {
            "response_classes": list(K.RESPONSE_CLASSES),
            "response_fatal_classes": list(K.RESPONSE_FATAL_CLASSES),
            "hypothesis_classes": list(K.HYPOTHESIS_CLASSES),
            "gate_order": [list(g) for g in K.GATE_ORDER]},
        "firewall_semantics": firewall_v5.version_stamp(),
        "numeric_authority_contract": NC.contract_snapshot(),
        "paired_fixtures": paired,
        "call_sequence": manifest_calls,
        "call_order_properties": order_props,
        "schedule_freeze_problems": freeze_problems,
        "cost_model": cost,
        "evaluator_freeze": evaluator_freeze,
        "self_noise_design": {
            "benchmark_formula": ("benchmark = Z * sqrt( sum_f sd^2 (1/n_base_f + "
                                  "1/n_research_f) / F^2 )"),
            "z_multiplier": SN.Z_MULTIPLIER,
            "min_self_noise_sd": SN.MIN_SELF_NOISE_SD,
            "min_repeat_groups_per_arm": SN.MIN_REPEAT_GROUPS_PER_ARM,
            "power_sketch_at_sd_0_20": SN.power_sketch(
                0.20, len(paired), SCH.N_REPEAT_FIXTURES, SCH.REPEATS_PER_GROUP),
            "power_sketch_at_sd_0_36": SN.power_sketch(
                0.363, len(paired), SCH.N_REPEAT_FIXTURES, SCH.REPEATS_PER_GROUP),
            "note": "V5A.2 re-scored self-noise SD was 0.363 on the qualified rate; the "
                    "power sketch states, before spend, the minimum detectable difference "
                    "at that SD and at a tighter 0.20."},
        "evaluability_gate": {
            "min_paired_fixtures": VD.MIN_PAIRED_FIXTURES,
            "min_valid_responses_per_arm": VD.MIN_VALID_RESPONSES_PER_ARM,
            "min_repeat_groups_per_arm": VD.MIN_REPEAT_GROUPS_PER_ARM,
            "min_qualified_denominator": VD.MIN_QUALIFIED_DENOMINATOR,
            "rule": "no PASS/MIXED/FAIL is issued unless EVALUABLE; execution and "
                    "scientific status are never collapsed (§26)"},
        "scientific_gates": {
            "gate_order": VD.version_stamp()["gate_order"],
            "discipline_tolerance": VD.DISCIPLINE_TOLERANCE,
            "discipline_axes": list(VD.DISCIPLINE_AXES) + [VD.COMPILE_AXIS],
            "primary_endpoint": VD.version_stamp()["primary_endpoint"],
            "PASS": "EVALUABLE, discipline held, mean paired B-A qualified-rate diff "
                    "exceeds the self-noise benchmark",
            "MIXED": "EVALUABLE, discipline held, diff positive but within benchmark",
            "FAIL": "discipline degraded beyond tolerance OR mean paired diff <= 0"},
        "stop_rules": STOP.version_stamp(),
        "artifact_hashes": {
            "packets_base.json": _sha_file(f"{OUT}/packets_base.json"),
            "packets_research.json": _sha_file(f"{OUT}/packets_research.json"),
            "adversarial_battery.json": _sha_file(f"{OUT}/adversarial_battery.json"),
            "synthetic_mutation_battery.json":
                _sha_file(f"{OUT}/synthetic_mutation_battery.json"),
            "packet_identity_audit.json": _sha_file(f"{OUT}/packet_identity_audit.json"),
            "pit_audit.json": _sha_file(f"{OUT}/pit_audit.json"),
            "arm_isolation_audit.json": _sha_file(f"{OUT}/arm_isolation_audit.json"),
            "call_schedule.json": _sha_file(f"{OUT}/call_schedule.json"),
            "INPUT_TOKEN_MANIFEST.json": _sha_file(f"{OUT}/INPUT_TOKEN_MANIFEST.json"),
            "EVALUATOR_FREEZE.json": _sha_file(f"{OUT}/EVALUATOR_FREEZE.json")},
        "module_hashes": {m: _sha_file(f"{ROOT}/{m}") for m in MODULES},
        "frozen_upstream_module_hashes": {m: _sha_file(f"{ROOT}/{m}")
                                          for m in FROZEN_MODULES},
        "champion_protection": {
            "artifact": CHAMPION_ARTIFACT,
            "frozen_sha256": CHAMPION_FROZEN_SHA,
            "current_sha256": _sha_file(CHAMPION_ARTIFACT),
            "read_only": True, "auto_promotion": False,
            "isolation": "no V6 module is imported by any CHAMPION prediction path; "
                         "CHAMPION produces p_model independently (§32)"},
        "downstream_boundary": (
            "V6 is the research-question layer only. It produces no predictive "
            "coefficients, candidate features, OOS search, thresholds or prospective "
            "predictions. Even a PASS proves only that richer evidence improves the "
            "research-question layer, not predictive value (§40)."),
        "spend_authorization": "REQUIRED. This preregistration does NOT authorize spend.",
        "required_states": [
            "V6_HYPOTHESIS_LEVEL_ADJUDICATION_VALIDATED",
            "V6_FIREWALL_SEMANTICS_VALIDATED",
            "V6_BALANCED_EXECUTION_DESIGN_VALIDATED",
            "V6_SELF_NOISE_DESIGN_VALIDATED",
            "V6_EVALUATOR_FROZEN",
            "V6_FULLY_PREREGISTERED",
            "V6_SPEND_AUTHORIZATION_REQUIRED"],
    }
    with open(f"{OUT}/PREREGISTRATION.json", "w") as fh:
        json.dump(prereg, fh, indent=1, sort_keys=True, default=str)

    print(f"n_calls_total: {n_calls}  (paired {len(paired)*2} + repeats "
          f"{n_calls - len(paired)*2})")
    print(f"expected ${cost['expected_cost_usd']:.4f} | p90 ${cost['p90_cost_usd']:.4f} | "
          f"ceiling ${cost['hard_ceiling_usd']:.4f}")
    print(f"input tokens: est(diag)={tot_in_est}  hard_bound={tot_in_bound} "
          f"({sorted({e['input_tokens_method'] for e in token_manifest})})")
    for arm in ("base", "research"):
        print(f"  {arm:9s} tokens/byte = {cal[arm]['tokens_per_byte']:.6f} "
              f"(observed {cal[arm]['v5a1_observed_input_tokens']})")
    ps = prereg["self_noise_design"]["power_sketch_at_sd_0_36"]
    print(f"self-noise min detectable diff @ sd0.363: "
          f"{ps['minimum_detectable_paired_difference']}")
    print(f"schedule freezable: {not freeze_problems}")
    print(f"champion unchanged: "
          f"{prereg['champion_protection']['current_sha256'] == CHAMPION_FROZEN_SHA}")
    print(f"PREREGISTRATION sha: {_sha_file(f'{OUT}/PREREGISTRATION.json')[:16]}")
    print(f"EVALUATOR_FREEZE sha: {_sha_file(f'{OUT}/EVALUATOR_FREEZE.json')[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
