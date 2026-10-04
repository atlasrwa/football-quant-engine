"""CLI entrypoint for preregistered QFE V2.1 local state-space Stage 1 V2."""
from pathlib import Path
import json

from src.research.evaluation.v21_local_state_space_stage1 import build_stage1, write_stage1

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    result, rows = build_stage1(repo_root=root)
    write_stage1(repo_root=root, result=result, rows=rows)
    print(json.dumps({
        "result_hash": result["result_hash"],
        "development_rows": result["development_rows"],
        "decisions": {
            target: {
                "chosen_profile": result["targets"][target]["selection"]["chosen_profile"],
                "stage1_decision": result["targets"][target]["selection"]["stage1_decision"],
                "candidates": [
                    {
                        "profile": x["profile"],
                        "delta_side_poisson_nll": x["delta_side_poisson_nll"],
                        "delta_binary_log_loss": x["delta_binary_log_loss"],
                        "delta_brier": x["delta_brier"],
                        "fold_primary_wins": x["fold_primary_wins"],
                        "gate": x["qualifies_stage1_gate"],
                    }
                    for x in result["targets"][target]["selection"]["candidates"]
                ],
            }
            for target in ("goals", "corners")
        },
    }, indent=2, sort_keys=True))
