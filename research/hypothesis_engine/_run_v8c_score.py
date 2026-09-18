"""V8C PROCESS 2 driver -- post-freeze scoring. Starts only after process 1 has exited.

Verifies the freeze hash BEFORE opening any target outcome, then scores exactly the frozen
selections. Cannot select and cannot alter a selection.

usage: python3 _run_v8c_score.py <freeze_in.json> <results_out.json> <mode>
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/ubuntu")


def main():
    freeze_path, out_path = sys.argv[1], sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "golden"
    from src.research.hypothesis_v8c import golden as G
    from src.research.hypothesis_v8c import score_frozen as SFZ

    metrics = ("goals", "yellow_cards")
    n_targets = 15 if mode == "golden15" else 1
    env = G.build_environment(n_targets=n_targets, metrics=metrics)
    receipt_path = freeze_path.replace(".json", "_receipt.json")
    res = SFZ.score_frozen(freeze_path, env.index, capability=env.capability,
                           grammar_kwargs={"metrics": list(metrics)},
                           receipt_path=receipt_path)
    with open(out_path, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"FREEZE_HASH_VERIFIED={res['freeze_hash_verified']}")
    print(f"RECEIPT_VERIFIED={res['receipt_verified']}")
    print(f"BINDING_VERIFIED_FIXTURES={res['binding_verified_fixtures']}")
    print(f"SR_STATUS={res['endpoint_S_vs_R']['inference']['inference_status']}")
    print(f"SR_PAIRED_N={res['endpoint_S_vs_R']['paired_n_all']}")
    print(f"SH_PAIRED_N={res['endpoint_S_vs_H']['paired_n_all']}")


if __name__ == "__main__":
    main()
