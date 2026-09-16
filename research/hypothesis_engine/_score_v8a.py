"""Score the V8A development run into V8A_STRUCTURAL_RESULTS.json. EFFECT BLIND.

Brief section 22: the first V8A report must NOT use historical effect sizes. Nothing in this
module measures an outcome, computes an effect, or reads a confirmatory result. It measures
the RESEARCH SPACE: validity, measurability, novelty, football research character, diversity,
complexity and evidence grounding.

Every rate the report quotes is computed HERE and read from the JSON. The report does not
hand-tabulate anything -- that is how the three V7.1 reporting overstatements happened.

Run:  /home/ubuntu/.venv/bin/python research/hypothesis_engine/_score_v8a.py
"""
from __future__ import annotations

import collections
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu/v8a-worktree")

import src  # noqa: F401,E402

from src.research.hypothesis_v71 import controls as C                    # noqa: E402
from src.research.hypothesis_v8a import audit as A                       # noqa: E402
from src.research.hypothesis_v8a import genericlib as G                  # noqa: E402
from src.research.hypothesis_v8a.frozencap import FrozenCapability       # noqa: E402

ROOT = "/home/ubuntu/v8a-worktree"
OUT = f"{ROOT}/research/hypothesis_engine/out/v8a"
RESP = f"{OUT}/responses"
CAP_PATH = f"{ROOT}/research/hypothesis_oos/out/v7_1/V7_1_CAPABILITY_MATRIX.json"


def pct(n, d):
    return None if not d else round(100.0 * n / d, 1)


def blank_counters():
    return {
        "fixtures": 0, "calls": 0, "raw_candidates": 0,
        "schema_valid": 0, "compiler_valid": 0, "pit_valid": 0, "provider_valid": 0,
        "measurable": 0,
        "exact_generic_duplicates": 0, "structural_generic_equivalents": 0,
        "incremental_structure": 0, "invalid": 0,
        "unsupported_metric": 0, "unknown_metric": 0,
        "tautology": 0, "cohort_equals_baseline": 0,
        "excessive_complexity": 0, "fragmentation_risk": 0,
        "duplicate_candidates": 0,
        "n_evidence_refs_cited": 0, "n_evidence_refs_hallucinated": 0,
        "candidates_with_hallucinated_refs": 0,
        "firewall_blocking": 0, "firewall_clean": 0,
        "attack_defense_interactions": 0, "similar_opponent": 0,
        "recent_vs_long": 0, "venue_interaction": 0,
        "formation_context_used": 0, "half_state": 0,
        "opponent_profile_conditioned": 0, "multi_kind_interaction": 0,
        "n_conditions_total": 0, "n_targets_total": 0,
    }


def fold(acc, rec):
    acc["raw_candidates"] += 1
    if rec["schema_valid"]:
        acc["schema_valid"] += 1
    if rec["compiler"]["ir_ok"]:
        acc["compiler_valid"] += 1
    m = rec["measurability"]
    if m["measurable"]:
        acc["measurable"] += 1
    if not m["unsupported_metrics"] and not m["unknown_metrics"]:
        acc["provider_valid"] += 1
    if m["unsupported_metrics"]:
        acc["unsupported_metric"] += 1
    if m["unknown_metrics"]:
        acc["unknown_metric"] += 1
    t = rec["tautology"]
    if t["tautology"]:
        acc["tautology"] += 1
    if t["cohort_equals_baseline"]:
        acc["cohort_equals_baseline"] += 1
    lbl = rec["novelty_verdict"]["label"]
    key = {G.EXACT_DUPLICATE: "exact_generic_duplicates",
           G.STRUCTURAL_EQUIVALENT: "structural_generic_equivalents",
           G.INCREMENTAL_STRUCTURE: "incremental_structure",
           G.INVALID: "invalid"}.get(lbl)
    if key:
        acc[key] += 1
    cx = rec["complexity"]
    if cx["excessive_complexity"]:
        acc["excessive_complexity"] += 1
    if cx["fragmentation_risk"]:
        acc["fragmentation_risk"] += 1
    acc["n_conditions_total"] += cx["n_cohort_conditions"]
    acc["n_targets_total"] += cx["n_target_metrics"]
    er = rec["evidence_refs"]
    acc["n_evidence_refs_cited"] += er["n_cited"]
    acc["n_evidence_refs_hallucinated"] += er["n_hallucinated"]
    if er["n_hallucinated"]:
        acc["candidates_with_hallucinated_refs"] += 1
    if rec["firewall"]["clean"]:
        acc["firewall_clean"] += 1
    else:
        acc["firewall_blocking"] += 1
    ch = rec["character"]
    for k, key in (("attack_defense_interaction", "attack_defense_interactions"),
                   ("similar_opponent", "similar_opponent"),
                   ("recent_vs_long_run", "recent_vs_long"),
                   ("venue_interaction", "venue_interaction"),
                   ("formation_context_used", "formation_context_used"),
                   ("half_state_conditional", "half_state"),
                   ("opponent_profile_conditioned", "opponent_profile_conditioned"),
                   ("multi_kind_interaction", "multi_kind_interaction")):
        if ch.get(k):
            acc[key] += 1


def rates(acc):
    d_raw, d_meas = acc["raw_candidates"], acc["raw_candidates"]
    return {
        "schema_valid_rate_pct": pct(acc["schema_valid"], d_raw),
        "compiler_valid_rate_pct": pct(acc["compiler_valid"], d_raw),
        "provider_valid_rate_pct": pct(acc["provider_valid"], d_raw),
        "measurable_rate_pct": pct(acc["measurable"], d_meas),
        "unsupported_metric_rate_pct": pct(acc["unsupported_metric"], d_raw),
        "unknown_metric_rate_pct": pct(acc["unknown_metric"], d_raw),
        "tautology_rate_pct": pct(acc["tautology"], d_raw),
        "exact_generic_duplicate_rate_pct": pct(acc["exact_generic_duplicates"], d_raw),
        "structural_generic_equivalent_rate_pct": pct(
            acc["structural_generic_equivalents"], d_raw),
        "incremental_structure_rate_pct": pct(acc["incremental_structure"], d_raw),
        "invalid_rate_pct": pct(acc["invalid"], d_raw),
        "attack_defense_interaction_rate_pct": pct(acc["attack_defense_interactions"],
                                                   d_raw),
        "similar_opponent_rate_pct": pct(acc["similar_opponent"], d_raw),
        "recent_vs_long_rate_pct": pct(acc["recent_vs_long"], d_raw),
        "venue_interaction_rate_pct": pct(acc["venue_interaction"], d_raw),
        "formation_context_rate_pct": pct(acc["formation_context_used"], d_raw),
        "half_state_rate_pct": pct(acc["half_state"], d_raw),
        "multi_kind_interaction_rate_pct": pct(acc["multi_kind_interaction"], d_raw),
        "excessive_complexity_rate_pct": pct(acc["excessive_complexity"], d_raw),
        "fragmentation_risk_rate_pct": pct(acc["fragmentation_risk"], d_raw),
        "hallucinated_evidence_ref_rate_pct": pct(acc["n_evidence_refs_hallucinated"],
                                                  acc["n_evidence_refs_cited"]),
        "candidates_with_hallucinated_refs_rate_pct": pct(
            acc["candidates_with_hallucinated_refs"], d_raw),
        "firewall_blocking_rate_pct": pct(acc["firewall_blocking"], d_raw),
        "mean_conditions_per_candidate": (round(acc["n_conditions_total"] / d_raw, 2)
                                          if d_raw else None),
        "mean_target_metrics_per_candidate": (round(acc["n_targets_total"] / d_raw, 2)
                                              if d_raw else None),
    }


def main():
    cap = FrozenCapability.load(CAP_PATH)
    VOCAB = list(cap.measurable_vocabulary())
    lib = G.build_library(VOCAB)
    LIBKEYS = {h["structural_key_sha256"] for h in lib}

    packets = json.load(open(f"{OUT}/packets_v8a.json"))
    arm_a_packets = json.load(open(f"{OUT}/packets_arm_a.json"))

    arms = {"A": blank_counters(), "B": blank_counters(), "D": blank_counters()}
    per_candidate = {"A": [], "B": []}
    keys_seen = {"A": collections.Counter(), "B": collections.Counter()}
    families = {"A": collections.Counter(), "B": collections.Counter()}
    metrics_used = {"A": collections.Counter(), "B": collections.Counter()}
    pass2 = {"KEEP": 0, "REFINE": 0, "ABSTAIN": 0, "MISSING": 0}
    pass2_predictive_claims = []
    reconnaissance = {"fixtures_with_all_four_blocks": 0, "n_observations_total": 0,
                      "n_interaction_lines_total": 0, "n_tensions": 0,
                      "n_asymmetries": 0, "n_regime_changes": 0}
    errors = []
    zero_candidate_fixtures = {"A": [], "B": []}

    # ---- Arm A -------------------------------------------------------------------------
    for fp in sorted(glob.glob(f"{RESP}/A_pass1_*.json")):
        rec = json.load(open(fp))
        fid = rec["fixture_id"]
        arms["A"]["fixtures"] += 1
        arms["A"]["calls"] += 1
        if rec.get("error"):
            errors.append({"arm": "A", "fixture": fid, "error": rec["error"]})
            continue
        pkt = arm_a_packets.get(fid) or {}
        valid = A.armA_evidence_ref_index(pkt)
        hyps = (rec.get("response") or {}).get("hypotheses") or []
        if not hyps:
            zero_candidate_fixtures["A"].append(fid)
        for i, h in enumerate(hyps):
            r = A.audit_armA_hypothesis(h, i, cap=cap, packet=pkt, library_keys=LIBKEYS,
                                        vocabulary=VOCAB, valid_refs=valid)
            r["fixture_id"] = fid
            fold(arms["A"], r)
            per_candidate["A"].append(r)
            keys_seen["A"][r["novelty_verdict"].get("structural_key_sha256")] += 1
            families["A"][h.get("research_family")] += 1
            for m in (h.get("target_metrics") or []):
                metrics_used["A"][str(m).lower()] += 1

    # ---- Arm B pass 1 -------------------------------------------------------------------
    b_by_cid = {}
    for fp in sorted(glob.glob(f"{RESP}/B_pass1_*.json")):
        rec = json.load(open(fp))
        fid = rec["fixture_id"]
        arms["B"]["fixtures"] += 1
        arms["B"]["calls"] += 1
        if rec.get("error"):
            errors.append({"arm": "B", "fixture": fid, "error": rec["error"]})
            continue
        pkt = packets.get(fid) or {}
        valid = A.evidence_ref_index(pkt)
        values = A.packet_values(pkt)
        resp = rec.get("response") or {}

        recon = resp.get("reconnaissance") or {}
        if all(recon.get(k) for k in ("team_a_attack", "team_a_defense",
                                      "team_b_attack", "team_b_defense")):
            reconnaissance["fixtures_with_all_four_blocks"] += 1
        reconnaissance["n_observations_total"] += sum(
            len(recon.get(k) or []) for k in recon)
        imap = resp.get("interaction_map") or {}
        reconnaissance["n_interaction_lines_total"] += (
            len(imap.get("a_attack_vs_b_defense") or [])
            + len(imap.get("b_attack_vs_a_defense") or []))
        reconnaissance["n_tensions"] += len(imap.get("tensions") or [])
        reconnaissance["n_asymmetries"] += len(imap.get("asymmetries") or [])
        reconnaissance["n_regime_changes"] += len(imap.get("regime_changes") or [])

        cands = resp.get("candidates") or []
        if not cands:
            zero_candidate_fixtures["B"].append(fid)
        for i, c in enumerate(cands):
            r = A.audit_candidate(c, i, cap=cap, packet=pkt, library_keys=LIBKEYS,
                                  vocabulary=VOCAB, valid_refs=valid, values=values)
            r["fixture_id"] = fid
            fold(arms["B"], r)
            per_candidate["B"].append(r)
            b_by_cid[(fid, str(c.get("candidate_id")))] = (c, r)
            keys_seen["B"][r["novelty_verdict"].get("structural_key_sha256")] += 1
            families["B"][c.get("research_family")] += 1
            for m in (c.get("target_metric") or []):
                metrics_used["B"][str(m).lower()] += 1

    # ---- Arm B pass 2 -------------------------------------------------------------------
    for fp in sorted(glob.glob(f"{RESP}/B_pass2_*.json")):
        rec = json.load(open(fp))
        arms["B"]["calls"] += 1
        if rec.get("error"):
            errors.append({"arm": "B", "pass": 2, "error": rec["error"]})
            pass2["MISSING"] += 1
            continue
        resp = rec.get("response") or {}
        act = resp.get("action")
        pass2[act if act in pass2 else "MISSING"] += 1
        pc = A.predictive_claims(resp)
        if pc:
            pass2_predictive_claims.append({"candidate_id": rec.get("candidate_id"),
                                            "phrases": pc})

    # ---- Arm D: the deterministic generic baseline, no LLM ------------------------------
    pool = C.enumerate_pool(VOCAB, 2000)
    for i, spec in enumerate(pool):
        view = {"candidate_id": f"D{i}",
                "subject": {"HOME_TEAM": "TEAM_A",
                            "AWAY_TEAM": "TEAM_B"}.get(spec["subject"]),
                "opponent": None,
                "target_metric": spec["target_metrics"],
                "metric_perspective": spec["side"], "comparison": spec["comparison"],
                "window": spec["window"], "conditions": spec["conditions"],
                "provider_requirements": spec.get("required_capabilities") or []}
        r = A.audit_candidate(view, i, cap=cap, packet={}, library_keys=LIBKEYS,
                              vocabulary=VOCAB, valid_refs=set(), values=())
        fold(arms["D"], r)
    arms["D"]["fixtures"] = 0
    arms["D"]["calls"] = 0

    for arm in ("A", "B"):
        dupes = sum(v - 1 for v in keys_seen[arm].values() if v > 1)
        arms[arm]["duplicate_candidates"] = dupes

    results = {
        "v8a_results_version": "v8a_results_v1",
        "effect_blind": True,
        "historical_effects_computed": False,
        "confirmatory_oos_opened": False,
        "per_arm_counts": arms,
        "per_arm_rates": {a: rates(arms[a]) for a in arms},
        "pass2_actions": pass2,
        "pass2_predictive_claims": pass2_predictive_claims,
        "reconnaissance": reconnaissance,
        "zero_candidate_fixtures": zero_candidate_fixtures,
        "research_family_distribution": {a: dict(families[a].most_common())
                                         for a in families},
        "target_metric_distribution": {a: dict(metrics_used[a].most_common())
                                       for a in metrics_used},
        "family_concentration_top1_pct": {
            a: pct(families[a].most_common(1)[0][1], sum(families[a].values()))
            if families[a] else None for a in families},
        "errors": errors,
        "arm_c_executed": False,
        "arm_d_note": ("Arm D is the deterministic generic library scored through the SAME "
                       "audit path. It has no fixtures and makes no calls; evidence "
                       "grounding and firewall metrics are not meaningful for it."),
    }
    json.dump(results, open(f"{OUT}/V8A_STRUCTURAL_RESULTS.json", "w"),
              indent=2, sort_keys=True, default=str)
    json.dump(per_candidate, open(f"{OUT}/V8A_PER_CANDIDATE_AUDIT.json", "w"),
              indent=1, sort_keys=True, default=str)
    print(json.dumps({"arms": {a: {"raw": arms[a]["raw_candidates"],
                                   "measurable": arms[a]["measurable"],
                                   "incremental": arms[a]["incremental_structure"]}
                               for a in arms},
                      "pass2": pass2, "errors": len(errors)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
