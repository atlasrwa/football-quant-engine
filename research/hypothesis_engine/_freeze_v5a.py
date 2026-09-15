"""Freeze the V5A preregistration: call manifest, cost model, module hashes, prereg JSON.

ZERO SPEND. No Bedrock, no network. Builds the request manifest (Arm A + Arm B + repeats),
calibrated cost estimate, and the machine-readable preregistration. Does NOT call any LLM.
"""
from __future__ import annotations
import hashlib, json, os, sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")
from src.research.hypothesis_oos import v5a_prompt as P
from src.research.hypothesis_oos import v5a_full_fidelity as V5
from src.research.hypothesis_engine import schema_v2 as S2

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a"

# --- token calibration from the frozen V3 run (observed, not chars/4) -------------------
TOKENS_PER_BYTE = 0.546          # V3: 21457 input_tokens / 39297 packet bytes
SYSTEM_PROMPT_TOKENS = None      # computed below from actual system+schema overhead
OUTPUT_TOKENS_MEAN = 2576        # V3 reference mean
OUTPUT_TOKENS_P90 = 3195         # V3 reference max (used as p90 upper)
OUTPUT_TOKENS_MAX = 4096         # schema maxTokens ceiling

# Claude Sonnet 4.6 Bedrock pricing (USD per 1K tokens). Recorded for transparency;
# adjust to the account's actual rate card before authorizing spend.
PRICE_IN_PER_1K = 0.003
PRICE_OUT_PER_1K = 0.015

REPEATABILITY_FIXTURES = 3       # repeat calls per arm to estimate self-noise
MODEL_ID = "us.anthropic.claude-sonnet-4-6"
TEMPERATURE = 0.0
MAX_TOKENS = 8192

# The 10 paired fixtures (mt_013233190 excluded: below min history in Arm B).
PAIRED = ['mt_010243515', 'mt_010243537', 'mt_010243938', 'mt_010244159', 'mt_010244193',
          'mt_010441320', 'mt_010441491', 'mt_010444904', 'mt_012232295', 'mt_012232411']
EXCLUDED = {'mt_013233190': "below history_policy.min_matches_per_team in Arm B; "
                            "excluded from BOTH arms to keep the pairing symmetric"}

MODULES = [
    "src/research/hypothesis_oos/v5a_full_fidelity.py",
    "src/research/hypothesis_oos/v5a_prompt.py",
    "src/research/hypothesis_engine/schema_v2.py",
    "src/research/hypothesis_engine/validator_v2.py",
    "src/research/hypothesis_engine/firewall_v2.py",
    "src/research/hypothesis_engine/query_plan.py",
    "src/research/hypothesis_engine/vocabulary.py",
    "src/research/hypothesis_engine/corpus_adapter.py",
    "research/hypothesis_engine/_build_v5a.py",
    "research/hypothesis_engine/_freeze_v5a.py",
]
CHAMPION_ARTIFACT = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _est_input_tokens(packet_dict, system_tokens):
    body = P.build_user_payload(packet_dict)
    return int(len(body) * TOKENS_PER_BYTE) + system_tokens


def main():
    arm_a = json.load(open(f"{OUT}/arm_a_packets.json"))
    arm_b = json.load(open(f"{OUT}/arm_b_packets.json"))

    system_tokens = int(len(P.SYSTEM_PROMPT) * TOKENS_PER_BYTE) + 2000  # +vocab/schema overhead
    manifest = {"model_id": MODEL_ID, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
                "prompt_version": P.V5A_PROMPT_VERSION,
                "schema_version": S2.SCHEMA_VERSION,
                "schema_content_hash": S2.schema_content_hash(),
                "calls": []}
    tot_in = tot_out_mean = tot_out_p90 = tot_out_max = 0

    for fid in PAIRED:
        for arm, packets in (("A", arm_a), ("B", arm_b)):
            pk = packets[fid]
            payload = P.build_user_payload(pk)
            in_tok = _est_input_tokens(pk, system_tokens)
            req_hash = hashlib.sha256(
                (P.SYSTEM_PROMPT + "\x00" + payload).encode()).hexdigest()
            reps = REPEATABILITY_FIXTURES if fid in PAIRED[:REPEATABILITY_FIXTURES] else 0
            n_calls = 1 + reps
            manifest["calls"].append({
                "fixture_id": fid, "arm": arm, "n_calls": n_calls,
                "repeatability_calls": reps,
                "est_input_tokens": in_tok,
                "packet_hash": pk.get("packet_hash"),
                "serialized_request_sha256": req_hash,
                "payload_bytes": len(payload)})
            tot_in += in_tok * n_calls
            tot_out_mean += OUTPUT_TOKENS_MEAN * n_calls
            tot_out_p90 += OUTPUT_TOKENS_P90 * n_calls
            tot_out_max += OUTPUT_TOKENS_MAX * n_calls

    n_calls_total = sum(c["n_calls"] for c in manifest["calls"])
    cost = {
        "token_calibration": {"tokens_per_byte": TOKENS_PER_BYTE,
                              "source": "V3 observed 21457 in / 39297 bytes",
                              "system_prompt_tokens_est": system_tokens},
        "n_calls_total": n_calls_total,
        "n_base_calls": len(PAIRED) * 2,
        "n_repeatability_fixture_arms": REPEATABILITY_FIXTURES * 2,
        "repeat_calls_per_selected_fixture_arm": REPEATABILITY_FIXTURES,
        "n_repeatability_extra_calls": REPEATABILITY_FIXTURES * 2 * REPEATABILITY_FIXTURES,
        "total_input_tokens_est": tot_in,
        "total_output_tokens_mean": tot_out_mean,
        "total_output_tokens_p90": tot_out_p90,
        "total_output_tokens_max": tot_out_max,
        "price_in_per_1k": PRICE_IN_PER_1K, "price_out_per_1k": PRICE_OUT_PER_1K,
        "expected_cost_usd": round(tot_in / 1000 * PRICE_IN_PER_1K
                                   + tot_out_mean / 1000 * PRICE_OUT_PER_1K, 4),
        "p90_cost_usd": round(tot_in / 1000 * PRICE_IN_PER_1K
                              + tot_out_p90 / 1000 * PRICE_OUT_PER_1K, 4),
        "hard_ceiling_usd": round(tot_in / 1000 * PRICE_IN_PER_1K
                                  + tot_out_max / 1000 * PRICE_OUT_PER_1K, 4),
    }

    module_hashes = {m: _sha_file(f"{ROOT}/{m}") for m in MODULES}

    prereg = {
        "preregistration_version": "v5a_full_fidelity_prereg_v1",
        "spend_usd_so_far": 0.0,
        "experiment": "V5A: full-fidelity evidence vs frozen V3 compressed evidence",
        "governing_architecture": "LLM = research-question layer only; no LLM->p_model path",
        "paired_fixtures": PAIRED, "excluded_fixtures": EXCLUDED,
        "history_policy": V5.DEFAULT_POLICY.to_dict(),
        "canonical_match_metrics": list(V5.CANONICAL_MATCH_METRICS),
        "semantic_exclusions": V5.SEMANTIC_EXCLUSIONS,
        "profile_similarity_axes": list(V5.PROFILE_SIMILARITY_AXES),
        "arms": {
            "A": "frozen V3 compressed evidence body (venue=ALL, window=ALL_PRIOR scalars)",
            "B": "full match-level PIT-safe research view (columnar lossless) + "
                 "DERIVED_SUMMARY + opponent-profile bands + availability map"},
        "shared_stack": {
            "model_id": MODEL_ID, "temperature": TEMPERATURE,
            "schema": "schema_v2", "schema_content_hash": S2.schema_content_hash(),
            "validator": "validator_v2", "firewall": "firewall_v2",
            "compiler": "query_plan.compile_hypothesis", "vocabulary": "hypothesis_vocabulary_v1",
            "aliases": "HOME_TEAM/AWAY_TEAM/COMPETITION/OPP_nnn (identity-neutral)",
            "max_hypotheses": S2.MAX_HYPOTHESES,
            "only_evidence_representation_differs": True},
        "request_manifest": manifest,
        "cost_model": cost,
        "evaluation_rubric": _rubric(),
        "meaningful_interaction_rule": _interaction_rule(),
        "availability_aware_scoring": True,
        "stop_rules": _stop_rules(),
        "verdict_gates": _verdict_gates(),
        "module_hashes": module_hashes,
        "champion_protection": {"artifact": CHAMPION_ARTIFACT,
                                "frozen_sha256": CHAMPION_FROZEN_SHA,
                                "current_sha256": _sha_file(CHAMPION_ARTIFACT),
                                "read_only": True, "auto_promotion": False},
        "downstream_boundary": "V5A stops at hypothesis-generation evaluation; no predictive "
                               "coefficients, no candidate features, no OOS search, no "
                               "shrinkage tuning, no thresholds, no prospective betting. A "
                               "PASS triggers a SEPARATE preregistered V5B.",
    }
    with open(f"{OUT}/PREREGISTRATION.json", "w") as fh:
        json.dump(prereg, fh, indent=1, sort_keys=True, default=str)

    print("n_calls_total:", n_calls_total)
    print("expected cost $%.4f | p90 $%.4f | ceiling $%.4f" % (
        cost["expected_cost_usd"], cost["p90_cost_usd"], cost["hard_ceiling_usd"]))
    print("total input tokens est:", tot_in)
    print("champion unchanged:", prereg["champion_protection"]["current_sha256"]
          == CHAMPION_FROZEN_SHA)
    print("prereg sha:", _sha_json(prereg)[:16])
    return 0


def _sha_json(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _rubric():
    return {"note": "Success is NOT more/complex hypotheses. Scored on:",
            "criteria": ["groundedness (evidence_refs resolve to real rows/summaries)",
                         "compilability (VALID rate under query_plan)",
                         "non_degenerate_conditions", "evidence_referenced_rate",
                         "appropriate_venue_use (given availability)",
                         "appropriate_opponent_profile_use",
                         "appropriate_recent_vs_long_use",
                         "restraint_on_weak_formation_coverage",
                         "meaningful_interactions", "baseline_diversity",
                         "metric_family_diversity", "redundancy_rate",
                         "unsupported_data_rate", "fabricated_evidence_rate",
                         "repeatability_vs_self_noise"]}


def _interaction_rule():
    return ["both conditions independently supported", "not aliases/duplicates",
            "not contradictory", "neither baseline-absorbed",
            "dimensions available", "sample feasibility exists",
            "football reason visible in evidence"]


def _stop_rules():
    return ["PIT leakage", "target-fixture leakage", "future data", "hash mismatch",
            "unexplained metric omission", "provenance failure", "semantic conflict",
            "serialization truncation", "schema-invalid rate > 0.30 preregistered",
            "transport failure > 3 consecutive", "cost ceiling exceeded"]


def _verdict_gates():
    return {"PASS": "Arm B shows materially higher grounded, availability-appropriate use "
                    "of venue/opponent-profile/recent-vs-long than Arm A, at equal or better "
                    "compilability and firewall-clean rate, with repeatability above "
                    "self-noise floor.",
            "MIXED": "Arm B improves some dimensions but not others, or improvement is "
                     "within self-noise.",
            "FAIL": "Arm B shows no material grounded-use improvement over Arm A, or "
                    "degrades compilability/firewall cleanliness."}


if __name__ == "__main__":
    raise SystemExit(main())
