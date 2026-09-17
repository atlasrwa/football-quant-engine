"""V8B.1 task 11: the 3-call canary. Validates transport, search tool wiring, schema
validation, parser correctness, canonical-ID resolution, caching, and token budget using AT
MOST 3 real Sonnet calls. Per instruction: does NOT tune the prompt based on whether the
generated football hypotheses look good -- only mechanical correctness is checked.

Picks the FIRST three fixtures (by manifest order) from the frozen V8B1_FIXTURE_MANIFEST.json
-- a deterministic, pre-stated selection, not cherry-picked after seeing any result.
"""
from __future__ import annotations

import json
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT)
sys.path.insert(0, f"{ROOT}/scripts")

N_CANARY = 3


def main():
    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import execution as EX
    from src.research.hypothesis_v71 import recency as REC
    from src.research.hypothesis_v8b1 import packet as PK
    from src.research.hypothesis_v8b1 import prompt as PR
    from src.research.hypothesis_v8b1 import runner as RN
    from src.research.hypothesis_v8b1 import search as SE

    manifest = json.load(open(f"{ROOT}/research/hypothesis_engine/V8B1_FIXTURE_MANIFEST.json"))
    model_config = json.load(open(f"{ROOT}/research/hypothesis_engine/V8B1_MODEL_CONFIG.json"))
    canary_fixtures = manifest["fixtures"][:N_CANARY]
    print(f"canary fixtures (first {N_CANARY} of manifest, deterministic, not cherry-picked):")
    for f in canary_fixtures:
        print(f"  {f['fixture_id']} ({f['competition']}, kickoff={f['kickoff_unix']})")

    cap = CAP.CapabilityContract(
        json.load(open(f"{ROOT}/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json")))
    recs = CI.load_records(include_fresh=True)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)
    ctx = EX.build_context(index)
    recency_family = tuple(REC.family()) + (REC.UniformRecency(),)

    cfg = model_config["chosen_configuration"]
    config_stamp = {"max_tokens": cfg["max_tokens"], "temperature": cfg["temperature"],
                   "thinking": cfg["thinking"]}
    model_id = model_config["model_id"]
    region = model_config["region"]
    assert model_id == "us.anthropic.claude-sonnet-4-6", "canary must use the frozen model_id"

    results = []
    for f in canary_fixtures:
        pos = index.pos_of_fixture.get(f["fixture_id"])
        if pos is None:
            print(f"  SKIP {f['fixture_id']}: not found in live index (corpus drift?)")
            results.append({"fixture_id": f["fixture_id"], "status": "SKIP_NOT_IN_INDEX"})
            continue
        packet = PK.build_packet(index, pos, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                                 recency_family)
        print(f"\n--- fixture {f['fixture_id']}: packet built, hash={packet['packet_hash'][:16]} ---")
        result = RN.run_fixture(packet, cap, model_id=model_id, region=region,
                                config_stamp=config_stamp, use_cache=True)
        print(f"  status: {result.status}")
        print(f"  manifest: {json.dumps(result.manifest, indent=2, default=str)[:800]}")
        if result.status == "OK":
            print(f"  n_final_selections: {len(result.final_selections)}")
            for sel in result.final_selections:
                resolved = SE.resolve(sel["hypothesis_id"], cap)
                print(f"    - {sel['hypothesis_id'][:16]}... resolves={resolved is not None}")
        results.append({"fixture_id": f["fixture_id"], "status": result.status,
                        "manifest": result.manifest,
                        "n_final_selections": len(result.final_selections)})

    print("\n=== CANARY SUMMARY ===")
    print(json.dumps(results, indent=2, default=str))

    out_path = f"{ROOT}/research/hypothesis_engine/V8B1_CANARY_RESULTS.json"
    with open(out_path, "w") as f:
        json.dump({"n_canary": N_CANARY, "results": results,
                   "model_id": model_id, "prompt_content_hash": PR.prompt_content_hash()},
                  f, indent=1, default=str)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
