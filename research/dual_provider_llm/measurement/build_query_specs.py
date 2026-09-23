"""Compile the frozen hypotheses into DIRECT_HYPOTHESIS_QUERY_SPECS_V1.json and write the
manifest. Validation only: reads the hypotheses and the packet; no match data, no outcome, no
LLM, no network."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.research.dual_provider_llm.measurement import compiler as C  # noqa: E402

D = ROOT / "research/dual_provider_llm"
OUT = D / "measurement"
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")


def fsha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    champ_before = fsha(CHAMPION)
    doc = C.compile_all(D / "out/direct_pilot/CHATGPT_HYPOTHESES_V1.json",
                        D / "out/direct_pilot/PILOT_FIXTURE_PACKET_V1.json")
    spec_path = OUT / "DIRECT_HYPOTHESIS_QUERY_SPECS_V1.json"
    spec_path.write_text(C.dumps(doc))
    proto = OUT / "DIRECT_HYPOTHESIS_MEASUREMENT_PROTOCOL_V1.md"
    mods = sorted((ROOT / "src/research/dual_provider_llm/measurement").glob("*.py"))
    manifest = {
        "manifest_version": "direct_hypothesis_measurement_manifest_v1",
        "status": "DESIGN_FROZEN_AWAITING_EXPLICIT_AUTHORIZATION_TO_RUN_HISTORICAL_MEASUREMENT",
        "source_hypotheses_sha256": doc["source_hypotheses_sha256"],
        "source_packet_sha256": doc["source_packet_sha256"],
        "query_specs": {"path": str(spec_path.relative_to(ROOT)), "sha256": fsha(spec_path)},
        "protocol": {"path": str(proto.relative_to(ROOT)),
                     "sha256": fsha(proto) if proto.exists() else None},
        "modules": {str(m.relative_to(ROOT)): fsha(m) for m in mods},
        "runner": {"entrypoint": "python -m src.research.dual_provider_llm.measurement.executor "
                                 "--authorized-head <HEAD>",
                   "gate": "HEAD == --authorized-head and clean worktree", "executed": False},
        "bh_family_frozen": ["DP1_BOX_PRESSURE_MATCHUP", "DP2_WIDE_CENTRAL_INTERACTION",
                             "DP3_ALBACETE_DIRECT_PROGRESSION",
                             "DP4_GIRONA_CURRENT_TERRITORIAL_REGIME",
                             "DP6_PRESSURE_RESOLUTION_CLEARANCE_PROFILE"],
        "n_frozen_bh_tests": 5,
        "pre_execution_implementation_amendments": [{
            "id": "PRE_EXECUTION_IMPLEMENTATION_AMENDMENT_A1",
            "base_head": "6342275e7755a384400b569d9b0b68fa477631fc",
            "defect": "executor.run_all built the BH family from members with status OK only, "
                      "so a non-evaluable member shrank the preregistered five-test family",
            "fix": "BH always runs over the frozen five; a non-evaluable member enters with "
                   "bh_input_p=1.0 as bookkeeping only (primary_p_value=null, "
                   "multiplicity_placeholder=true)",
            "scientific_design_changed": False,
            "query_specs_changed": False,
            "real_historical_measurement_run_before_amendment": False}],
        "n_hypotheses": len(doc["specs"]),
        "n_compilable": sum(a["COMPILABLE"] for a in doc["audits"]),
        "bh_family": doc["bh_family"],
        "outcomes_read": False, "historical_effects_computed": False, "model_fit": False,
        "p_model_produced": False, "llm_calls": 0,
        "champion_sha256_before": champ_before, "champion_sha256_after": fsha(CHAMPION),
    }
    (OUT / "DIRECT_HYPOTHESIS_MEASUREMENT_MANIFEST_V1.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"specs_sha256": manifest["query_specs"]["sha256"],
                      "n_compilable": manifest["n_compilable"],
                      "bh_family": manifest["bh_family"]}, indent=1))


if __name__ == "__main__":
    main()
