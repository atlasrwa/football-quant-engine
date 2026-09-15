"""Freeze V5A.1: request manifest, section-position audit, cost model, preregistration.

ZERO SPEND. No Bedrock, no network. Run AFTER `_build_v5a1.py` and after the pre-spend
battery passes.
"""
from __future__ import annotations

import hashlib, json, os, sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import schema_v2 as S2, validator_v3 as V3, firewall_v3
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_packet as PK
from src.research.hypothesis_oos import v5a1_prompt as P
from src.research.hypothesis_oos import v5a1_semantics as SEM
from src.research.hypothesis_oos import v5a1_admissibility as ADM

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a1"

#: V3-observed Bedrock calibration (21457 input tokens / 39297 payload bytes), reused so
#: the estimate is grounded in this account's actual usage rather than chars/4.
TOKENS_PER_BYTE = 0.546
OUTPUT_TOKENS_MEAN = 2576
OUTPUT_TOKENS_P90 = 3195
OUTPUT_TOKENS_MAX = 4096
PRICE_IN_PER_1K = 0.003
PRICE_OUT_PER_1K = 0.015

MODEL_ID = "us.anthropic.claude-sonnet-4-6"
TEMPERATURE = 0.0
MAX_TOKENS = 8192
REPEATS_PER_SELECTED_ARM = 3
N_REPEAT_FIXTURES = 3

MODULES = [
    "src/research/hypothesis_oos/v5a1_evidence.py",
    "src/research/hypothesis_oos/v5a1_semantics.py",
    "src/research/hypothesis_oos/v5a1_packet.py",
    "src/research/hypothesis_oos/v5a1_prompt.py",
    "src/research/hypothesis_oos/v5a1_admissibility.py",
    "src/research/hypothesis_oos/v5a1_ontology.py",
    "src/research/hypothesis_engine/validator_v3.py",
    "src/research/hypothesis_engine/firewall_v3.py",
    "src/research/hypothesis_engine/schema_v2.py",
    "src/research/hypothesis_engine/validator_v2.py",
    "src/research/hypothesis_engine/firewall_v2.py",
    "src/research/hypothesis_engine/query_plan.py",
    "src/research/hypothesis_engine/vocabulary.py",
    "src/research/hypothesis_engine/availability.py",
    "src/research/hypothesis_engine/corpus_adapter.py",
    "research/hypothesis_engine/_build_v5a1.py",
    "research/hypothesis_engine/_freeze_v5a1.py",
]
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

#: V5A module hashes as frozen in the ABORTED V5A preregistration. Asserted unchanged so a
#: V5A.1 change can never silently rewrite a frozen historical experiment.
V5A_FROZEN_MODULE_HASHES = {
    "src/research/hypothesis_engine/schema_v2.py":
        "a9f96e19c52aa7fd8d5df42ee9051b57429c581837b7b161eb1172fd68522718",
    "src/research/hypothesis_engine/validator_v2.py":
        "2a2dc4e68daa76974b8656125f469427b2291a129e3674a6fafe9fdf2be4c284",
    "src/research/hypothesis_engine/firewall_v2.py":
        "400e89b9ecf79e322a3efb661fd5c26a2e5cb087ba0cfd4e3ad3768a7ab94d48",
    "src/research/hypothesis_engine/query_plan.py":
        "184991835110d940819dcf35375d025876ed10c2df1fee94d1f10861d3f8826c",
    "src/research/hypothesis_engine/vocabulary.py":
        "ba123f798a404911f62557ed1cb4c985046f9e480375d40ef04e5ffd797a7f0d",
    "src/research/hypothesis_engine/corpus_adapter.py":
        "5c6cb2c770b2734b4ae032b3cbd96ec374b40bece942875a574ba2b3bad28b37",
}


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def section_positions(packet) -> list:
    """Measured byte offsets of every section in the exact serialized payload (task §11)."""
    payload = P.build_user_payload(packet)
    n = len(payload)
    out = []
    for sec in packet["sections"]:
        blob = E.serialize(sec)
        off = payload.find(blob)
        out.append({"section": sec["section"], "section_type": sec["section_type"],
                    "byte_start": off, "byte_end": off + len(blob), "bytes": len(blob),
                    "pct_start": round(off / n * 100, 2),
                    "pct_end": round((off + len(blob)) / n * 100, 2),
                    "pct_of_packet": round(len(blob) / n * 100, 2),
                    "approx_token_start": int(off * TOKENS_PER_BYTE)})
    return out


def main():
    base = json.load(open(f"{OUT}/packets_base.json"))
    research = json.load(open(f"{OUT}/packets_research.json"))
    fixtures = sorted(base)
    repeat_fixtures = fixtures[:N_REPEAT_FIXTURES]

    manifest = {"model_id": MODEL_ID, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
                "prompt_version": P.V5A1_PROMPT_VERSION,
                "schema_version": S2.SCHEMA_VERSION,
                "schema_content_hash": S2.schema_content_hash(),
                "system_prompt_sha256":
                    hashlib.sha256(P.SYSTEM_PROMPT.encode()).hexdigest(),
                "system_prompt_identical_across_arms": True,
                "calls": []}
    positions, tot_in = {}, 0
    for fid in fixtures:
        for arm, packets in (("base", base), ("research", research)):
            pk = packets[fid]
            payload = P.build_user_payload(pk)
            req = P.serialized_request(pk)
            in_tok = int(len(req) * TOKENS_PER_BYTE)
            reps = REPEATS_PER_SELECTED_ARM if fid in repeat_fixtures else 0
            manifest["calls"].append({
                "fixture_id": fid, "arm_internal": arm, "n_calls": 1 + reps,
                "repeatability_calls": reps,
                "payload_bytes": len(payload),
                "request_bytes": len(req),
                "est_input_tokens": in_tok,
                "packet_hash": pk["packet_hash"],
                "serialized_request_sha256": hashlib.sha256(req.encode()).hexdigest(),
                "valid_evidence_ids": len(E.resolve_evidence_ids(pk))})
            tot_in += in_tok * (1 + reps)
            positions.setdefault(fid, {})[arm] = section_positions(pk)

    n_calls = sum(c["n_calls"] for c in manifest["calls"])
    out_mean = OUTPUT_TOKENS_MEAN * n_calls
    out_p90 = OUTPUT_TOKENS_P90 * n_calls
    out_max = OUTPUT_TOKENS_MAX * n_calls
    cost = {
        "calibration": {"tokens_per_byte": TOKENS_PER_BYTE,
                        "source": "V3 observed 21457 input tokens / 39297 payload bytes",
                        "note": "computed from the ACTUAL frozen serialized requests, not "
                                "reused from the aborted V5A estimate"},
        "n_calls_total": n_calls, "n_base_calls": len(fixtures) * 2,
        "n_repeatability_extra_calls": n_calls - len(fixtures) * 2,
        "total_input_bytes": sum(c["request_bytes"] * c["n_calls"]
                                 for c in manifest["calls"]),
        "total_input_tokens_est": tot_in,
        "total_output_tokens_mean": out_mean,
        "total_output_tokens_p90": out_p90,
        "total_output_tokens_max": out_max,
        "price_in_per_1k": PRICE_IN_PER_1K, "price_out_per_1k": PRICE_OUT_PER_1K,
        "expected_cost_usd": round(tot_in / 1000 * PRICE_IN_PER_1K
                                   + out_mean / 1000 * PRICE_OUT_PER_1K, 4),
        "p90_cost_usd": round(tot_in / 1000 * PRICE_IN_PER_1K
                              + out_p90 / 1000 * PRICE_OUT_PER_1K, 4),
        "hard_ceiling_usd": round(tot_in / 1000 * PRICE_IN_PER_1K
                                  + out_max / 1000 * PRICE_OUT_PER_1K, 4),
    }

    module_hashes = {m: _sha_file(f"{ROOT}/{m}") for m in MODULES}
    frozen_ok = {m: module_hashes[m] == h for m, h in V5A_FROZEN_MODULE_HASHES.items()}

    prereg = {
        "preregistration_version": "v5a1_full_fidelity_interface_prereg_v1",
        "experiment": "V5A.1_FULL_FIDELITY_EVIDENCE_INTERFACE",
        "spend_usd_so_far": 0.0,
        "V5A_PREVIOUS_VERSION": "ABORTED_PRE_SPEND",
        "v5a_abort_reasons": [
            "Arm B evidence references incompatible with shared validator/firewall",
            "A/B comparison not isolated to evidence representation",
            "shared prompt invited unavailable dimensions",
            "raw rows buried behind summary volume",
            "opponent-profile semantics ambiguous",
            "match alias collisions",
            "unresolved xG/npxG semantic conflict",
        ],
        "v5a_artifacts_preserved_unchanged": "research/hypothesis_oos/out/v5a/",
        "governing_architecture":
            "LLM = research-question layer only. No LLM -> p_model path, no coefficients, "
            "no probabilities. The deterministic engine computes every effect; OOS "
            "validation decides generalisation; the quant model alone owns probabilities.",
        "arms": {
            "base": "shared long-run evidence only: ALL_PRIOR/venue=ANY summaries over the "
                    "FULL PIT-safe history, formation coverage, availability map, metric "
                    "semantics, fixture context",
            "research": "EXACTLY the base evidence (identical evidence_ids and values) PLUS "
                        "match-level rows, W5/W10 summaries, venue-split summaries and "
                        "opponent-profile response summaries",
        },
        "treatment_definition": "research = base + additional exposed evidence. Proven per "
                                "fixture in ab_isolation_audit.json, not asserted.",
        "shared_stack": {
            "model_id": MODEL_ID, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
            "system_prompt": "IDENTICAL, capability-driven, promises no section",
            "schema": "schema_v2 (frozen, unmodified)",
            "schema_content_hash": S2.schema_content_hash(),
            "validator": "validator_v3 (arm-neutral evidence resolution)",
            "firewall": "firewall_v3 (arm-neutral evidence provenance)",
            "compiler": "query_plan.compile_hypothesis (frozen, unmodified)",
            "evidence_interface": E.EVIDENCE_INTERFACE_VERSION,
            "evidence_id_format": "identical in both arms",
            "admissibility": ADM.ADMISSIBILITY_VERSION,
            "aliases": "HOME_TEAM/AWAY_TEAM/COMPETITION/OPP_nnn/COMP_nnn",
            "max_hypotheses": S2.MAX_HYPOTHESES,
            "baseline_universe": PK.BASELINE_UNIVERSE,
            "summary_estimator": PK.SUMMARY_ESTIMATOR,
            "only_exposed_evidence_differs": True,
        },
        "history_policy": {
            "baseline_universe": PK.BASELINE_UNIVERSE,
            "summaries": "ALL_PRIOR summaries in BOTH arms aggregate every PIT-safe prior "
                         "match, uncapped and identical across arms",
            "raw_rows": f"the most recent {PK.MAX_RAW_ROWS_PER_TEAM} matches are serialized "
                        f"as rows in the research arm, for prompt size only; this bounds "
                        f"ROW VISIBILITY, never the baseline population",
            "min_prior_matches_per_team": PK.MIN_PRIOR_MATCHES_PER_TEAM,
        },
        "paired_fixtures": fixtures,
        "provider_semantics": {
            "version": SEM.PROVIDER_SEMANTICS_VERSION,
            "provider": SEM.PROVIDER,
            "canonical_metrics": list(SEM.CANONICAL_METRICS),
            "excluded_metrics": SEM.EXCLUDED_METRICS,
            "xg_npxg_resolution": "npxg EXCLUDED (provider-source inconsistency, 15.8% of "
                                  "raw pairs violate npxG <= xG and no penalty field exists "
                                  "to recompute it); xg EXPOSED with coverage declared",
        },
        "opponent_profile": {
            "method": PK.PROFILE_METHOD,
            "directions": list(E.PROFILE_DIRECTIONS),
            "direction_meaning": E.DIRECTION_MEANING,
            "defensive_axes": list(PK.DEFENSIVE_SIMILARITY_AXES),
            "offensive_axes": list(PK.OFFENSIVE_SIMILARITY_AXES),
            "response_metrics": list(PK.PROFILE_RESPONSE_METRICS),
            "min_cohort_n": PK.MIN_COHORT_N,
            "status": "DESCRIPTIVE_HISTORICAL_EVIDENCE_ONLY",
        },
        "request_manifest": manifest,
        "cost_model": cost,
        "evaluation_rubric": _rubric(),
        "primary_outcome":
            "Does the research arm increase the production of grounded, non-degenerate, "
            "deterministically measurable, contextually justified research hypotheses "
            "beyond repeatability noise, without materially degrading discipline?",
        "availability_aware_denominators":
            "A dimension is scored only where it is EXPOSED. The base arm is never "
            "penalised for not using evidence it was truthfully told it does not have, and "
            "the research arm is never rewarded for merely mentioning a dimension: use must "
            "be grounded in a resolvable evidence_id.",
        "repeatability": {"fixtures": repeat_fixtures,
                          "repeats_per_arm": REPEATS_PER_SELECTED_ARM,
                          "purpose": "self-noise floor; the A-vs-B difference is "
                                     "interpreted relative to it"},
        "stop_rules": _stop_rules(),
        "verdict_gates": _verdict_gates(),
        "downstream_boundary":
            "V5A.1 stops at hypothesis-generation evaluation. No predictive coefficients, "
            "no candidate features, no OOS search, no shrinkage tuning, no thresholds, no "
            "prospective betting. A PASS triggers a SEPARATE preregistered stage.",
        "module_hashes": module_hashes,
        "frozen_v5a_modules_unchanged": frozen_ok,
        "champion_protection": {"artifact": CHAMPION,
                                "frozen_sha256": CHAMPION_FROZEN_SHA,
                                "current_sha256": _sha_file(CHAMPION),
                                "read_only": True, "auto_promotion": False},
    }
    with open(f"{OUT}/PREREGISTRATION.json", "w") as fh:
        json.dump(prereg, fh, indent=1, sort_keys=False, default=str)
    with open(f"{OUT}/section_position_audit.json", "w") as fh:
        json.dump(positions, fh, indent=1, sort_keys=False, default=str)

    print("calls:", n_calls)
    print("expected $%.4f | p90 $%.4f | ceiling $%.4f" % (
        cost["expected_cost_usd"], cost["p90_cost_usd"], cost["hard_ceiling_usd"]))
    print("total input tokens est:", tot_in)
    print("frozen V5A/V3 modules unchanged:", all(frozen_ok.values()), frozen_ok)
    print("champion unchanged:",
          prereg["champion_protection"]["current_sha256"] == CHAMPION_FROZEN_SHA)
    return 0


def _rubric():
    return {"note": "Success is NOT more hypotheses, more conditions, more tokens or more "
                    "varied wording. Scored on:",
            "criteria": ["grounded_acceptance_rate", "compilability",
                         "valid_evidence_reference_rate", "fabricated_evidence_rate",
                         "unsupported_dimension_use_rate", "meaningful_conditionality",
                         "meaningful_interaction_rate",
                         "context_utilization_conditional_on_availability",
                         "baseline_diversity", "metric_family_diversity",
                         "redundancy_rate", "formation_restraint",
                         "evidence_specificity", "self_noise",
                         "within_fixture_research_minus_base_difference"]}


def _stop_rules():
    return ["PIT leakage", "target-fixture leakage", "future data", "hash mismatch",
            "unexplained metric omission", "provenance failure", "semantic conflict",
            "serialization truncation", "duplicate evidence id", "arm label visible",
            "availability declaration untruthful", "valid_evidence_ids == 0 for any packet",
            "schema-invalid rate > 0.30", "transport failure > 3 consecutive",
            "cost ceiling exceeded"]


def _verdict_gates():
    return {"PASS": "The research arm shows materially higher grounded, "
                    "availability-appropriate evidence use than the base arm, at equal or "
                    "better compilability and firewall-clean rate, with the difference "
                    "above the measured self-noise floor.",
            "MIXED": "Improvement on some dimensions but not others, or within self-noise.",
            "FAIL": "No material grounded-use improvement, or degraded compilability or "
                    "firewall cleanliness."}


if __name__ == "__main__":
    raise SystemExit(main())
