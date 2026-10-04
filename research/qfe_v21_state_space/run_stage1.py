"""CLI entrypoint for preregistered QFE V2.1 state-space Stage 1."""
from pathlib import Path
import json

from src.research.evaluation.v21_state_space_stage1 import build_stage1, write_stage1


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    result, rows = build_stage1(repo_root=root)
    write_stage1(repo_root=root, result=result, rows=rows)
    print(json.dumps({
        "result_hash": result["result_hash"],
        "development_rows": result["development_rows"],
        "targets": {
            target: result["targets"][target]["selection"]
            for target in ("goals", "corners")
        },
    }, indent=2, sort_keys=True))
