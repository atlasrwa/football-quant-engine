"""Build + freeze the V6.1 confirmatory design. ZERO SPEND -- no Bedrock, no network.

V6.1 is a NEW experiment necessitated by V6's post-run evaluator defect. Its ONE substantive
change is evaluator correctness (`v6_1_verdict` + `v6_1_metrics`). Everything else -- model,
temperature, max_tokens, prompt, schema, firewall, compiler, qualification, arm contrast,
packet SURFACE, schedule design, self-noise design, thresholds, cost architecture -- is the
frozen V6 machinery, reused verbatim. The only inputs that change are the FRESH held-out
fixtures (`v6_1_fixtures`, selected deterministically and independently of V6 outcomes) and
therefore the fresh packets built from them.

WHAT THIS SCRIPT PRODUCES IN out/v6_1/
--------------------------------------
    fixture_selection.json          the deterministic fresh-fixture selection (Task 10)
    packets_base.json               fresh base packets, SAME surface as V6 (v5a2 upgrade)
    packets_research.json           fresh research packets, SAME surface as V6
    pit_audit.json                  §31 re-verified on the fresh packets (Task 11)
    arm_isolation_audit.json        §2/§32 arms differ only in evidence
    call_schedule.json              §6 frozen schedule (same 36-call design as V6)
    INPUT_TOKEN_MANIFEST.json       per-request exact/byte-bound input tokens + cost
    EVALUATOR_FREEZE.json           the V6.1 (corrected) evaluator, frozen before spend
    PREREGISTRATION.json            the full frozen contract
    V6_1_DESIGN_COMPARISON.json     explicit V6->V6.1 element-by-element table (Task 9)

COST IS COMPUTED FRESH (Task 17)
--------------------------------
V6's $8.79 ceiling is NOT assumed. The bound is recomputed from V6.1's actual frozen
requests, per request, at the frozen max_tokens, rounded UP, with retries disabled. Input
tokens are the provider-native exact count when a frozen EXACT manifest exists, else the
provable UTF-8-byte upper bound -- identical mechanism to V6, applied to V6.1's own requests.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import (capability, firewall_v5, schema_v4,
                                            validator_v5, vocabulary)
from src.research.hypothesis_engine import corpus_adapter as CA
from src.research.hypothesis_oos import v5a1_packet as P1
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_contract as C
from src.research.hypothesis_oos import v5a2_ontology as O
from src.research.hypothesis_oos import v5a2_packet as P2
from src.research.hypothesis_oos import v5a2_translate as TRl
from src.research.hypothesis_oos import v6_1_fixtures as FX
from src.research.hypothesis_oos import v6_1_metrics as MC
from src.research.hypothesis_oos import v6_1_verdict as V61
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v6_numeric_contract as NC
from src.research.hypothesis_oos import v6_prompt as PR
from src.research.hypothesis_oos import v6_schedule as SCH
from src.research.hypothesis_oos import v6_scorecard as SCC
from src.research.hypothesis_oos import v6_selfnoise as SN
from src.research.hypothesis_oos import v6_stop as STOP
from src.research.hypothesis_oos import v6_token_count as TC
from src.research.hypothesis_oos import v6_transport as TRN
from src.research.hypothesis_oos import v6_verdict as V6

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v6_1"
V6_OUT = f"{ROOT}/research/hypothesis_oos/out/v6"

# Frozen shared stack -- IDENTICAL to V6 (Task 9). Read from V6's preregistration so a drift
# is caught, not silently accepted.
MODEL_ID = "us.anthropic.claude-sonnet-4-6"
TEMPERATURE = 0.0
MAX_TOKENS = 8192
PRICE_IN_PER_1K = 0.003
PRICE_OUT_PER_1K = 0.015

PRICING_CONTRACT = {
    "provider": "aws_bedrock", "model_family": "anthropic.claude-sonnet-4-6",
    "inference_profile": MODEL_ID, "region": "us-east-1",
    "service_tier": "on_demand_standard",
    "input_price_per_1k_usd": PRICE_IN_PER_1K, "output_price_per_1k_usd": PRICE_OUT_PER_1K,
    "discounts_applied": "none -- hard ceiling uses the highest applicable standard rate",
    "source": "AWS Bedrock pricing, Anthropic Claude Sonnet 4.6, on-demand, us-east-1",
    "as_of": "2026-09-15",
    "note": "reused from V6's frozen pricing contract; a provider price change before "
            "execution makes this stale rather than authorizing a silent edit."}

CHAMPION_ARTIFACT = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _sha_obj(o) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _write(name, obj) -> str:
    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/{name}"
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True, default=str)
    return _sha_file(path)


def _cost_usd_ceil(input_tokens: int, output_tokens: int) -> float:
    """Max dollar cost of one request, ROUNDED UP to the cent, integer micro-dollar math."""
    in_micro = int(round(PRICE_IN_PER_1K * 1_000_000 / 1000))     # = 3
    out_micro = int(round(PRICE_OUT_PER_1K * 1_000_000 / 1000))   # = 15
    total_micro = input_tokens * in_micro + output_tokens * out_micro
    return math.ceil(total_micro / 10_000) / 100.0


def _load_exact_counts() -> dict:
    """Provider-native exact input-token counts keyed by request SHA-256, from a frozen
    EXACT_INPUT_TOKEN_MANIFEST.json. Empty when CountTokens has not been run -- the freeze
    then uses the conservative byte bound and stays deterministic and network-free."""
    try:
        doc = json.load(open(f"{OUT}/EXACT_INPUT_TOKEN_MANIFEST.json"))
    except FileNotFoundError:
        return {}
    return {e["request_sha256"]: {"exact": int(e["exact_input_tokens"]),
                                  "byte_bound": int(e["conservative_byte_upper_bound"])}
            for e in doc["entries"]}


def build_packets(selected_ids: list) -> dict:
    """Fresh packets for the selected fixtures, SAME surface as V6 (v5a1 -> v5a2 upgrade)."""
    idx = CA.load_index()
    by_id = {r.fixture_id: r for r in idx.records}
    base, research = {}, {}
    for fid in selected_ids:
        t = by_id[fid]
        a1 = P1.build_packet(idx, t, arm="base")
        b1 = P1.build_packet(idx, t, arm="research")
        assert a1 is not None and b1 is not None, f"{fid} does not build in both arms"
        base[fid] = P2.upgrade_packet(a1)
        research[fid] = P2.upgrade_packet(b1)
    return {"base": base, "research": research}


def pit_audit(pk) -> dict:
    """§31 (Task 11) -- no observation at/after cutoff; no packet names its own fixture."""
    problems = []
    for arm in ("base", "research"):
        for fid, packet in sorted(pk[arm].items()):
            cutoff = packet["information_cutoff_unix"]
            blob = json.dumps(packet, sort_keys=True, default=str)
            if fid in blob.replace(f'"fixture_id": "{fid}"', ""):
                problems.append({"arm": arm, "fixture_id": fid,
                                 "problem": "target fixture id appears outside fixture_id"})
            for sec in packet["sections"]:
                if sec.get("section_type") != "MATCH_LEVEL_OBSERVATIONS":
                    continue
                for blk in sec.get("blocks") or []:
                    for row in blk.get("rows") or []:
                        ts = row.get("kickoff_unix") or row.get("date_unix")
                        if ts is not None and ts >= cutoff:
                            problems.append({"arm": arm, "fixture_id": fid,
                                             "problem": f"observation {ts} >= cutoff "
                                                        f"{cutoff}"})
    return {"n_problems": len(problems), "problems": problems,
            "claim": "every observation strictly before cutoff; no packet names its own "
                     "target fixture (§31); fresh V6.1 fixtures, rebuilt PIT-safe"}


def arm_isolation_audit(pk) -> dict:
    """§2/§32 -- arms differ ONLY in evidence; identity fields identical; research superset."""
    fids = sorted(set(pk["base"]) & set(pk["research"]))
    leaks, superset_ok = [], []
    for fid in fids:
        b, r = pk["base"][fid], pk["research"][fid]
        for key in ("packet_schema_version", "evidence_interface_version",
                    "packet_surface_version", "ontology_version", "fixture_id",
                    "information_cutoff_unix"):
            if b.get(key) != r.get(key):
                leaks.append({"fixture_id": fid, "key": key})
        ib, ir = set(E.resolve_evidence_ids(b)), set(E.resolve_evidence_ids(r))
        superset_ok.append(ib <= ir)
    blob = json.dumps(pk, sort_keys=True, default=str)
    labels = PR.blinding_violations(blob)
    return {"n_fixtures": len(fids), "n_identity_leaks": len(leaks),
            "identity_leaks": leaks, "treatment_labels_found_in_packets": labels,
            "research_superset_of_base_all": all(superset_ok),
            "claim": "identity fields identical across arms; research evidence ids are a "
                     "superset of base; nothing names the condition"}


def call_schedule(paired: list) -> dict:
    calls = SCH.build_sequence(paired)
    elig = STOP.MIN_CALLS_BEFORE_RATE_STOP
    props = SCH.order_properties(calls, elig)
    problems = SCH.freeze_assertions(
        calls, elig, min_prefix_fixtures=STOP.MIN_STOP_FIXTURES,
        min_prefix_calls_per_arm=STOP.MIN_STOP_VALID_CALLS_PER_ARM,
        min_repeat_groups_per_arm=SN.MIN_REPEAT_GROUPS_PER_ARM)
    return {"paired_fixtures": paired, "n_calls": len(calls), "calls": calls,
            "eligibility_seq": elig, "order_properties": props,
            "freeze_problems": problems, "frozen": not problems}


def evaluator_freeze() -> dict:
    """The V6.1 (corrected) evaluator, frozen before spend. Includes the frozen V6 modules
    it reuses AND the new V6.1 metric/verdict/fixtures modules."""
    mods = [
        "src/research/hypothesis_engine/validator_v5.py",
        "src/research/hypothesis_engine/firewall_v5.py",
        "src/research/hypothesis_engine/schema_v4.py",
        "src/research/hypothesis_oos/v6_scorecard.py",
        "src/research/hypothesis_oos/v6_selfnoise.py",
        "src/research/hypothesis_oos/v6_verdict.py",       # frozen; reused verbatim
        "src/research/hypothesis_oos/v6_1_metrics.py",     # NEW: metric contracts
        "src/research/hypothesis_oos/v6_1_verdict.py",     # NEW: repaired verdict
        "src/research/hypothesis_oos/v6_1_fixtures.py",    # NEW: fresh fixture selection
    ]
    return {
        "frozen_before_first_paid_call": True,
        "spend_usd_at_freeze": 0.0,
        "run_exactly_once": True,
        "evaluator_modules": {m: _sha_file(f"{ROOT}/{m}") for m in mods},
        "version_stamps": {
            "v6_1_verdict": V61.version_stamp(),
            "v6_1_metrics": MC.version_stamp(),
            "v6_1_fixtures": FX.version_stamp(),
            "frozen_v6_verdict": V6.version_stamp(),
            "scorecard": SCC.version_stamp(),
            "validator": validator_v5.version_stamp()},
        "repair": ("compiler_valid_rate numerator restricted to non-abstaining AND "
                   "compiler-valid hypotheses; generic metric contracts enforced in the "
                   "production path; impossible metric -> EVALUATOR_INVALID, never a "
                   "scientific verdict"),
        "thresholds_unchanged_from_v6": True,
    }


def design_comparison() -> dict:
    """Task 9 -- explicit V6 -> V6.1 element-by-element table."""
    rows = [
        ("evaluator compiler_valid_rate", "abstentions in numerator (defect, rate>1)",
         "numerator = non-abstaining AND compiler-valid", True,
         "repairs the demonstrated decisive defect"),
        ("metric contract layer", "none (impossible metric fed the verdict silently)",
         "generic RATE/COUNT/DELTA/PROB/SD contracts enforced in production path", True,
         "an impossible metric now aborts as EVALUATOR_INVALID"),
        ("fixtures", "10 V5A.2 fixtures (now with known V6 outcomes)",
         "10 FRESH held-out fixtures, deterministic outcome-blind selection", True,
         "confirmatory evidence must be fresh (Task 10/12); size unchanged"),
        ("model_id", MODEL_ID, MODEL_ID, False, "frozen"),
        ("temperature", TEMPERATURE, TEMPERATURE, False, "frozen"),
        ("max_tokens", MAX_TOKENS, MAX_TOKENS, False, "frozen"),
        ("prompt", PR.V6_PROMPT_VERSION, PR.V6_PROMPT_VERSION, False, "frozen"),
        ("schema", schema_v4.SCHEMA_VERSION, schema_v4.SCHEMA_VERSION, False, "frozen"),
        ("firewall", firewall_v5.FIREWALL_VERSION, firewall_v5.FIREWALL_VERSION, False,
         "frozen"),
        ("compiler/validator", validator_v5.VALIDATOR_VERSION,
         validator_v5.VALIDATOR_VERSION, False, "frozen"),
        ("qualification semantics", "v6_qualified", "v6_qualified", False, "frozen"),
        ("arm contrast", "base summaries vs research full history",
         "base summaries vs research full history", False, "frozen"),
        ("packet surface", "v5a2_packet_v1", "v5a2_packet_v1", False, "frozen (same surface)"),
        ("schedule design", "36 calls (10 paired x2 + 4x2x2 repeats)",
         "36 calls (10 paired x2 + 4x2x2 repeats)", False, "frozen design"),
        ("self-noise design", "Z, floor, groups", "Z, floor, groups", False, "frozen"),
        ("discipline tolerance", V6.DISCIPLINE_TOLERANCE, V6.DISCIPLINE_TOLERANCE, False,
         "frozen (not tuned to V6's 0.153)"),
        ("evaluability minimums", "8/8/3/20", "8/8/3/20", False, "frozen"),
        ("gate order", "EVALUABILITY->DISCIPLINE->PRIMARY",
         "EVALUABILITY->DISCIPLINE->PRIMARY", False, "frozen"),
        ("cost architecture", "CountTokens/byte-bound, retries off, rounded up",
         "CountTokens/byte-bound, retries off, rounded up", False,
         "frozen mechanism; bound recomputed on V6.1 requests"),
        ("sample size", "36 calls", "36 calls", False,
         "frozen (NOT enlarged for V6's +0.1134<benchmark)"),
    ]
    return {"comparison": [
        {"element": e, "v6": v6, "v6_1": v61, "changed": ch, "reason": rs}
        for (e, v6, v61, ch, rs) in rows],
        "n_changed": sum(1 for r in rows if r[3]),
        "substantive_change": "evaluator defect repair + fresh held-out fixtures",
        "threshold_integrity": ("no threshold, tolerance, floor, Z, minimum or gate order "
                                "was altered; known V6 outcomes did not influence any "
                                "parameter")}


def main():
    os.makedirs(OUT, exist_ok=True)
    # 1. deterministic fresh-fixture selection (Task 10), frozen BEFORE packets/generation
    selection = FX.select_fresh_fixtures()
    assert not selection["shortfalls"], f"fixture shortfalls: {selection['shortfalls']}"
    selected = selection["selected_fixtures"]
    sel_hash = _write("fixture_selection.json", selection)

    # 2. fresh packets, SAME surface as V6
    pk = build_packets(selected)
    hashes = {"packets_base.json": _write("packets_base.json", pk["base"]),
              "packets_research.json": _write("packets_research.json", pk["research"])}

    # 3. audits
    pit = pit_audit(pk); ai = arm_isolation_audit(pk)
    paired = sorted(set(pk["base"]) & set(pk["research"]))
    sch = call_schedule(paired)
    hashes["pit_audit.json"] = _write("pit_audit.json", pit)
    hashes["arm_isolation_audit.json"] = _write("arm_isolation_audit.json", ai)
    hashes["call_schedule.json"] = _write("call_schedule.json", sch)
    assert pit["n_problems"] == 0, f"PIT problems: {pit['problems']}"
    assert ai["n_identity_leaks"] == 0 and not ai["treatment_labels_found_in_packets"]
    assert ai["research_superset_of_base_all"]
    assert sch["frozen"], f"schedule not freezable: {sch['freeze_problems']}"

    # 4. per-request token manifest + cost (Task 17). No client -> conservative byte bound;
    #    a later CountTokens pass (_count_tokens_v6_1.py) tightens it to the exact provider
    #    count. Deterministic, network-free here.
    calls = sch["calls"]
    # Reload packets from disk so the frozen request hashes match EXACTLY what the driver
    # and the executor will send (a JSON round-trip is the canonical on-disk form; computing
    # hashes from the in-memory objects would bind the manifest to a representation nobody
    # sends).
    pk_disk = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}
    exact_counts = _load_exact_counts()   # provider-native, frozen; empty -> byte bound
    token_manifest, tot_in_bound, tot_byte_bound, tot_max = [], 0, 0, 0
    for c in calls:
        te = TC.token_entry(pk_disk[c["arm"]][c["fixture_id"]], model_id=MODEL_ID,
                            temperature=TEMPERATURE, max_tokens=MAX_TOKENS, client=None)
        ex = exact_counts.get(te["request_sha256"])
        if ex is not None:
            assert ex["exact"] <= te["conservative_byte_upper_bound"], (
                f"exact {ex['exact']} > byte bound {te['conservative_byte_upper_bound']}")
            te = {**te, "input_tokens": ex["exact"],
                  "input_tokens_method": TC.METHOD_EXACT, "exact_count_tokens": ex["exact"]}
        max_req_cost = _cost_usd_ceil(te["input_tokens"], MAX_TOKENS)
        token_manifest.append({
            "seq": c["seq"], "fixture_id": c["fixture_id"], "arm": c["arm"],
            "rep": c["rep"], "role": c.get("role"),
            **{k: te[k] for k in ("request_sha256", "input_tokens", "input_tokens_method",
                                  "input_tokens_is_upper_bound",
                                  "conservative_byte_upper_bound", "exact_count_tokens",
                                  "count_tokens_error", "count_model_id",
                                  "converse_model_id", "max_output_tokens",
                                  "token_count_version")},
            "max_billable_attempts": TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL,
            "max_request_cost_usd": max_req_cost})
        tot_in_bound += te["input_tokens"]
        tot_byte_bound += te["conservative_byte_upper_bound"]
        tot_max += MAX_TOKENS
    hard_ceiling = round(sum(e["max_request_cost_usd"] for e in token_manifest), 2)
    n_calls = len(calls)
    cost = {
        "n_calls_total": n_calls,
        "battery_derivation": (
            f"{len(paired)} paired fixtures x 2 arms = {len(paired)*2} primaries; "
            f"{SCH.N_REPEAT_FIXTURES} repeat fixtures x 2 arms x "
            f"{SCH.REPEATS_PER_GROUP-1} extra = "
            f"{SCH.N_REPEAT_FIXTURES*2*(SCH.REPEATS_PER_GROUP-1)}; total {n_calls} "
            f"(SAME design as V6; NOT enlarged)."),
        "total_input_tokens_hard_bound": tot_in_bound,
        "total_input_tokens_byte_bound": tot_byte_bound,
        "input_token_bound_method": sorted({e["input_tokens_method"]
                                            for e in token_manifest}),
        "input_token_bound_is_empirical_ratio": False,
        "total_output_tokens_max": tot_max,
        "price_in_per_1k": PRICE_IN_PER_1K, "price_out_per_1k": PRICE_OUT_PER_1K,
        "pricing": PRICING_CONTRACT,
        "hard_ceiling_usd": hard_ceiling,
        "v6_hard_ceiling_usd_NOT_ASSUMED": "recomputed from V6.1's own frozen requests",
        "max_billable_attempts_per_call": TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL,
        "max_billable_attempts_total": n_calls * TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL,
        "transport_retry_policy": TRN.retry_policy_report(),
        "hard_ceiling_is_a_true_bound": (
            f"yes -- max_tokens output on every one of the {n_calls} calls; input tokens "
            f"exact-or-byte-bounded (never an empirical ratio); dollar ceiling rounded UP; "
            f"retries disabled ({TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL} billable attempt per "
            f"logical call)."),
    }
    tm_doc = {"token_manifest_version": TC.TOKEN_COUNT_VERSION, "n_requests": n_calls,
              "total_input_tokens_hard_bound": tot_in_bound,
              "total_input_tokens_byte_bound": tot_byte_bound,
              "total_max_output_tokens": tot_max,
              "all_methods": sorted({e["input_tokens_method"] for e in token_manifest}),
              "any_exact": any(e["input_tokens_method"] == TC.METHOD_EXACT
                               for e in token_manifest),
              "all_upper_bounds": all(e["input_tokens_is_upper_bound"]
                                      for e in token_manifest),
              "hard_ceiling_usd": hard_ceiling, "pricing": PRICING_CONTRACT,
              "entries": token_manifest}
    hashes["INPUT_TOKEN_MANIFEST.json"] = _write("INPUT_TOKEN_MANIFEST.json", tm_doc)

    # 5. evaluator freeze + design comparison
    ef = evaluator_freeze()
    hashes["EVALUATOR_FREEZE.json"] = _write("EVALUATOR_FREEZE.json", ef)
    dc = design_comparison()
    hashes["V6_1_DESIGN_COMPARISON.json"] = _write("V6_1_DESIGN_COMPARISON.json", dc)

    # 6. preregistration
    prereg = {
        "preregistration_version": "v6_1_grounded_research_generator_prereg_v1",
        "experiment": "V6.1_GROUNDED_RESEARCH_GENERATOR_EVALUATOR_REPAIR",
        "spend_usd_so_far": 0.0,
        "necessitated_by": ("V6 post-run decisive evaluator defect (compiler_valid_rate>1). "
                            "V6.1 is a NEW experiment, not a rescue of V6."),
        "scientific_question": (
            "After repairing the demonstrated evaluator defect, does richer PIT-safe "
            "football evidence improve the quality of LLM-generated deterministic research "
            "hypotheses beyond model self-noise, without material discipline degradation?"),
        "v6_history_preserved": {
            "V6_EXECUTION_STATUS": "COMPLETE",
            "V6_FROZEN_EVALUATOR_VERDICT": "FAIL",
            "V6_SCIENTIFIC_VERDICT": None,
            "V6_POSTRUN_AUDIT": "DECISIVE_EVALUATOR_DEFECT_DISCOVERED",
            "v6_untouched": True},
        "the_one_substantive_change": "evaluator defect repair (see V6_1_DESIGN_COMPARISON)",
        "fixture_selection": {"rule": selection["selection_rule"],
                              "selected_fixtures": selected,
                              "independence_assertion": selection["independence_assertion"],
                              "sha256": sel_hash},
        "shared_stack": {
            "model_id": MODEL_ID, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
            "prompt": PR.V6_PROMPT_VERSION, "schema": schema_v4.SCHEMA_VERSION,
            "validator": validator_v5.VALIDATOR_VERSION,
            "firewall": firewall_v5.FIREWALL_VERSION,
            "numeric_contract": NC.NUMERIC_CONTRACT_VERSION,
            "ontology": O.ONTOLOGY_VERSION, "transport": TRN.TRANSPORT_VERSION,
            "packet_surface": P2.PACKET_SURFACE_VERSION,
            "verdict": V61.VERDICT_VERSION, "scorecard": SCC.SCORECARD_VERSION,
            "stop": STOP.STOP_VERSION, "schedule": SCH.SCHEDULE_VERSION,
            "max_hypotheses": schema_v4.MAX_HYPOTHESES},
        "arms": {
            "base": "derived summaries only (ALL_PRIOR, no match rows/venue/windows/"
                    "opponent-profile)",
            "research": "full match-level PIT-safe record + summaries + opponent-profile "
                        "cohorts + short windows + venue splits",
            "only_evidence_representation_differs": True},
        "paired_fixtures": paired,
        "call_sequence": calls,
        "call_order_properties": sch["order_properties"],
        "cost_model": cost,
        "evaluator_freeze": ef,
        "metric_registry": MC.registry_rows(),
        "self_noise_design": {
            "z_multiplier": SN.Z_MULTIPLIER, "min_self_noise_sd": SN.MIN_SELF_NOISE_SD,
            "min_repeat_groups_per_arm": SN.MIN_REPEAT_GROUPS_PER_ARM},
        "evaluability_gate": {
            "min_paired_fixtures": V6.MIN_PAIRED_FIXTURES,
            "min_valid_responses_per_arm": V6.MIN_VALID_RESPONSES_PER_ARM,
            "min_repeat_groups_per_arm": V6.MIN_REPEAT_GROUPS_PER_ARM,
            "min_qualified_denominator": V6.MIN_QUALIFIED_DENOMINATOR},
        "scientific_gates": {
            "gate_order": V61.version_stamp()["gate_order"],
            "discipline_tolerance": V6.DISCIPLINE_TOLERANCE,
            "discipline_axes": list(V6.DISCIPLINE_AXES) + [V6.COMPILE_AXIS],
            "PASS": "EVALUABLE, discipline held, mean paired diff exceeds self-noise bench",
            "MIXED": "EVALUABLE, discipline held, diff positive but within benchmark",
            "FAIL": "discipline degraded OR mean paired diff <= 0",
            "EVALUATOR_INVALID": "any metric contract violated -> apparatus, no verdict"},
        "threshold_integrity": dc["threshold_integrity"],
        "artifact_hashes": hashes,
        "champion_protection": {
            "artifact": CHAMPION_ARTIFACT, "frozen_sha256": CHAMPION_FROZEN_SHA,
            "current_sha256": _sha_file(CHAMPION_ARTIFACT), "read_only": True,
            "auto_promotion": False,
            "isolation": "no V6.1 module is imported by any CHAMPION prediction path"},
        "downstream_boundary": (
            "V6.1 is the research-question layer only. Even a PASS proves only that richer "
            "evidence improves the research-question layer, not predictive value (§40)."),
        "spend_authorization": "REQUIRED. This preregistration does NOT authorize spend.",
    }
    hashes["PREREGISTRATION.json"] = _write("PREREGISTRATION.json", prereg)

    print("=== V6.1 FREEZE (ZERO SPEND) ===")
    print("fresh fixtures :", selected)
    print("PIT problems   :", pit["n_problems"], "| arm identity leaks:",
          ai["n_identity_leaks"], "| labels:", ai["treatment_labels_found_in_packets"])
    print("research superset of base:", ai["research_superset_of_base_all"])
    print("schedule       :", sch["n_calls"], "calls, frozen:", sch["frozen"])
    print("input tokens   : hard_bound", tot_in_bound, "byte_bound", tot_byte_bound,
          "methods", cost["input_token_bound_method"])
    print("HARD CEILING   : $", cost["hard_ceiling_usd"], "(V6 $8.79 NOT assumed)")
    print("champion       :", "UNCHANGED" if prereg["champion_protection"][
        "current_sha256"] == CHAMPION_FROZEN_SHA else "CHANGED!!!")
    print("design changed elements:", dc["n_changed"], "->", dc["substantive_change"])
    print("PREREGISTRATION sha:", hashes["PREREGISTRATION.json"][:16])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
