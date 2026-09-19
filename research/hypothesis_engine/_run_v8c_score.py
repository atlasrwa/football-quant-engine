"""V8C PROCESS 2 driver -- post-freeze scoring. Starts only after process 1 has exited.

Verifies the freeze hash BEFORE opening any target outcome, then scores exactly the frozen
selections. Cannot select and cannot alter a selection.

The external ANCHOR is MANDATORY and must be pinned explicitly. Passing a receipt alone is
not enough: the receipt and the freeze are both editable by whoever holds the working tree, so
a consistent rewrite of the pair verifies. The anchor is read back out of Git at a commit the
caller names, which is the only reference the editor does not control.

usage: python3 _run_v8c_score.py <freeze_in.json> <results_out.json> <mode> \
           <ANCHOR_COMMIT> <anchor_repo_relpath> [repo_root]
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/ubuntu")


def main():
    if len(sys.argv) < 6:
        raise SystemExit(
            "ANCHOR_COMMIT and anchor_repo_relpath are REQUIRED.\n"
            "usage: _run_v8c_score.py <freeze_in.json> <results_out.json> <mode> "
            "<ANCHOR_COMMIT> <anchor_repo_relpath> [repo_root]")
    freeze_path, out_path = sys.argv[1], sys.argv[2]
    mode = sys.argv[3]
    anchor_commit, anchor_relpath = sys.argv[4], sys.argv[5]
    repo_root = sys.argv[6] if len(sys.argv) > 6 else None
    from src.research.hypothesis_v8c import golden as G
    from src.research.hypothesis_v8c import score_frozen as SFZ

    metrics = ("goals", "yellow_cards")
    n_targets = 15 if mode == "golden15" else 1
    env = G.build_environment(n_targets=n_targets, metrics=metrics)
    receipt_path = freeze_path.replace(".json", "_receipt.json")
    res = SFZ.score_frozen(freeze_path, env.index, capability=env.capability,
                           grammar_kwargs={"metrics": list(metrics)},
                           receipt_path=receipt_path,
                           anchor_commit=anchor_commit,
                           anchor_repo_relpath=anchor_relpath,
                           repo_root=repo_root)
    with open(out_path, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"FREEZE_HASH_VERIFIED={res['freeze_hash_verified']}")
    print(f"RECEIPT_VERIFIED={res['receipt_verified']}")
    print(f"ANCHOR_VERIFIED={res['anchor_verified']}")
    print(f"ANCHOR_COMMIT={res['anchor_commit']}")
    print(f"PRODUCER_CODE_COMMIT={res['producer_code_commit']}")
    print(f"EXECUTING_CODE_VERIFIED={res['executing_code_verified']}")
    print(f"BLOCKS_VALIDATED_BEFORE_TARGET_READ="
          f"{res['blocks_validated_before_any_target_read']}")
    print(f"BINDING_VERIFIED_FIXTURES={res['binding_verified_fixtures']}")
    print(f"SR_STATUS={res['endpoint_S_vs_R']['inference']['inference_status']}")
    print(f"SR_PAIRED_N={res['endpoint_S_vs_R']['paired_n_all']}")
    print(f"SH_PAIRED_N={res['endpoint_S_vs_H']['paired_n_all']}")


if __name__ == "__main__":
    main()
