"""V8C PROCESS 1 driver -- pre-T selection and freeze. Runs in its OWN process and EXITS.

Never imports a scorer. Never reads a target outcome. Writes a durable hashed freeze file
which `_run_v8c_score.py` (process 2) consumes.

usage: python3 _run_v8c_select.py <freeze_out.json> <mode>
       mode = golden | golden15
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/home/ubuntu")


def main():
    out_path, mode = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "golden")
    from src.research.hypothesis_v8c import golden as G
    from src.research.hypothesis_v8c import receipt as RCPT
    from src.research.hypothesis_v8c import select_freeze as SF
    from src.research.hypothesis_v8c import vintage as VIN

    SF.assert_no_scorer_loaded()          # entry assertion, before anything is built

    metrics = ("goals", "yellow_cards")
    n_targets = 15 if mode == "golden15" else 1
    env = G.build_environment(n_targets=n_targets, metrics=metrics)
    payload = SF.select_cohort(
        env.index, env.target_positions or [env.target_pos],
        capability=env.capability, k=3,
        fixture_ids=env.target_fixture_ids or [env.target_fixture_id],
        classification="SYNTHETIC_ONLY",
        grammar_kwargs={"metrics": list(metrics)}, enforce_seal=True)
    h = SF.write_freeze(payload, out_path)

    # P0-B: anchor the freeze in a SEPARATE receipt. Process 2 refuses without it.
    receipt_path = out_path.replace(".json", "_receipt.json")
    rec = RCPT.build_receipt(
        freeze_path=out_path,
        corpus_hash=VIN.corpus_vintage_full(env.index),
        capability_hash=VIN.capability_hash(env.capability),
        fixture_ids_ordered=payload["fixture_ids_ordered"],
        classification=payload["classification"])
    RCPT.write_receipt(rec, receipt_path)

    SF.assert_no_scorer_loaded()          # exit assertion, after everything is written
    print(f"FREEZE_HASH={h}")
    print(f"RECEIPT_HASH={rec['receipt_hash']}")
    print(f"PRODUCER_COMMIT={rec['producer_git_commit']}")
    print(f"TARGET_OUTCOMES_VIEWED={payload['totals']['target_outcomes_viewed']}")
    print(f"SCORER_LOADED={payload['scorer_loaded_in_this_process']}")
    print(f"N_FIXTURES={payload['n_fixtures']}")


if __name__ == "__main__":
    main()
