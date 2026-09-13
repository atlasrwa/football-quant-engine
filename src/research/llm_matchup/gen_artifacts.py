"""Generate machine-readable Phase-A artifacts into research/llm_matchup/out/.

Writes only under research/llm_matchup/out/ (no other filesystem mutation). Deterministic.
Run: .venv/bin/python -m src.research.llm_matchup.gen_artifacts
"""
from __future__ import annotations
import os, json, csv, hashlib

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup import schema as SCH
from src.research.llm_matchup import prompt as PR
from src.research.llm_matchup import versions as V
from src.research.llm_matchup import golden as G

OUT = "/home/ubuntu/research/llm_matchup/out"


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "cache"), exist_ok=True)

    ontology = ONT.to_dict()
    schema = SCH.build_schema()
    json.dump(ontology, open(f"{OUT}/ontology.json", "w"), indent=2)
    json.dump(schema, open(f"{OUT}/schema.json", "w"), indent=2)

    prompt_manifest = {
        "prompt_version": V.PROMPT_VERSION,
        "ontology_version": V.ONTOLOGY_VERSION,
        "schema_version": V.SCHEMA_VERSION,
        "cohort_policy_version": V.COHORT_POLICY_VERSION,
        "packet_schema_version": V.PACKET_SCHEMA_VERSION,
        "default_model_id": V.DEFAULT_BEDROCK_MODEL_ID,
        "default_region": V.DEFAULT_BEDROCK_REGION,
        "inference_config": V.INFERENCE_CONFIG,
        "system_prompt_sha256": hashlib.sha256(PR.SYSTEM_PROMPT.encode()).hexdigest(),
        "system_prompt_chars": len(PR.SYSTEM_PROMPT),
        "ontology_sha256": _sha(ontology),
        "schema_sha256": _sha(schema),
        "system_prompt": PR.SYSTEM_PROMPT,
    }
    json.dump(prompt_manifest, open(f"{OUT}/prompt_manifest.json", "w"), indent=2)

    # golden_cases.jsonl (packet + expectations)
    with open(f"{OUT}/golden_cases.jsonl", "w") as f:
        for name, (packet, exp) in G.cases().items():
            f.write(json.dumps({"name": name, "packet": packet, "expectations": exp}, default=str) + "\n")

    # ontology mechanism table
    with open(f"{OUT}/ontology_mechanisms.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["mechanism", "family", "level_kind", "markets", "allowed_evidence", "description"])
        for mid, m in sorted(ONT.MECHANISMS.items()):
            w.writerow([mid, m["family"], m["level_kind"], "|".join(m["markets"]),
                        "|".join(m["allow"]), m["desc"]])

    # empty-but-headed manifests for later phases (architecture phase leaves them empty)
    with open(f"{OUT}/llm_call_manifest.csv", "w", newline="") as f:
        csv.writer(f).writerow(["fixture_id", "packet_hash", "model_id", "resolved_model_id",
                                "prompt_version", "ontology_version", "schema_version", "status",
                                "cache_hit", "latency_s", "input_tokens", "output_tokens",
                                "reject_field", "created_unix"])
    with open(f"{OUT}/llm_state_features.csv", "w", newline="") as f:
        csv.writer(f).writerow(["fixture_id", "mechanism", "side", "level_or_assessment",
                                "confidence", "n_evidence_cited", "n_counter", "preferred_evidence_level",
                                "packet_hash", "prompt_version", "model_id"])
    with open(f"{OUT}/oos_results.csv", "w", newline="") as f:
        csv.writer(f).writerow(["market", "line", "model", "n", "logloss", "d_logloss_vs_baseline",
                                "brier", "auc", "ece", "p_std", "class", "phase"])

    # feature dictionary / provenance for the deterministic evidence layer
    with open(f"{OUT}/EVIDENCE_METRIC_DICTIONARY.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "all_period_source", "half_split_available", "raw_group_stat",
                    "provider", "definition"])
        from src.research.llm_matchup import cohorts as CH
        for m, src in sorted(CH.ALL_METRICS.items()):
            half = m in CH.HALF_METRICS
            grp = "/".join(CH.HALF_METRICS[m]) if half else ""
            w.writerow([m, (f"{src[0]}:{src[1]}" if src[0] else "base"), half, grp,
                        "thestatsapi", f"team {m} (for/against), PIT rolling, shrunk"])

    summary = {
        "phase": "B_pilot_stack",
        "versions": V.version_stamp(),
        "default_model_id": V.DEFAULT_BEDROCK_MODEL_ID,
        "n_mechanisms": len(ONT.MECHANISMS),
        "n_golden_cases": len(G.cases()),
        "prompt_manifest_sha256": _sha(prompt_manifest),
        "note": "Phase B frozen stack (ontology/schema/prompt v2 + formation_policy_v1). "
                "Live Bedrock call/state/oos manifests are produced by the B0/B1/B2 harnesses "
                "under out/ (phase_b_calls.csv, b*_states / llm_states_b*.jsonl).",
    }
    json.dump(summary, open(f"{OUT}/PHASE_A_SUMMARY.json", "w"), indent=2)
    print("wrote artifacts to", OUT)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
