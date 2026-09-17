"""V8B.1 cap-validation canary: exactly ONE live T2 infrastructure fixture, run under the
true-search-cap runner (v3). Validates the over-budget tool-result -> forced-submit
conversation path end to end: deterministic termination, canonical output, cache/accounting
integrity, and that a SEARCH_BUDGET_EXHAUSTED tool result (if the model bursts past six
searches in a turn) keeps the Bedrock conversation structurally valid.

Uses the FIRST T2 fixture of the frozen manifest (mt_012232342) -- same deterministic, frozen,
already-excluded-from-primary-sample fixture used in prior canaries. This is infrastructure
validation, NOT scientific evaluation, and does NOT inspect football quality.
"""
from __future__ import annotations

import json
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT)


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
    fixture = manifest["fixtures"][0]  # first T2 fixture, deterministic
    fid = fixture["fixture_id"]
    print(f"cap-canary fixture (T2 infra, deterministic): {fid}")

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
    assert model_id == "us.anthropic.claude-sonnet-4-6"

    pos = index.pos_of_fixture.get(fid)
    packet = PK.build_packet(index, pos, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                             recency_family)
    print(f"packet hash={packet['packet_hash'][:16]} reads_target_outcome="
          f"{packet.get('reads_target_outcome')}")

    result = RN.run_fixture(packet, cap, model_id=model_id, region=region,
                            config_stamp=config_stamp, use_cache=True)
    print(f"status: {result.status}")
    print(f"manifest: {json.dumps(result.manifest, indent=1, default=str)}")
    resolved_all = None
    if result.status in ("OK", "OK_ABSTAIN"):
        resolved_all = all(SE.resolve(s["hypothesis_id"], cap) is not None
                           for s in result.final_selections)
        print(f"n_final_selections={len(result.final_selections)} "
              f"all_resolve={resolved_all}")

    out = {
        "cap_canary": True,
        "runner_version": RN.version_stamp()["runner_version"],
        "fixture_id": fid,
        "status": result.status,
        "manifest": result.manifest,
        "n_final_selections": len(result.final_selections),
        "all_selections_resolve": resolved_all,
        "model_id": model_id,
        "prompt_content_hash": PR.prompt_content_hash(),
    }
    path = f"{ROOT}/research/hypothesis_engine/V8B1_CAP_CANARY_RESULTS.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
