"""CLI entrypoint for QFE V2.1 exploratory calibration V1."""
from pathlib import Path
import json

from src.research.evaluation.v21_calibration_exploratory import (
    run_exploratory_calibration,
    write_result,
)

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    result = run_exploratory_calibration(repo_root=root)
    write_result(repo_root=root, result=result)
    print(json.dumps({
        "result_hash": result["result_hash"],
        "groups": {
            g["group"]: {
                "reference": g["frozen_v2_reference"]["selected_candidate"],
                "research_selections": g["family_research_selections"],
                "promising_for_fresh_future_holdout": g[
                    "promising_for_fresh_future_holdout"
                ],
            }
            for g in result["group_results"]
        },
    }, indent=2, sort_keys=True))
