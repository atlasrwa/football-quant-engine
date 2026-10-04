"""CLI entrypoint for QFE V2.1 CMP distribution Stage 1."""
from pathlib import Path
import json

from src.research.evaluation.v21_cmp_distribution_stage1 import (
    build_cmp_stage1,
    write_cmp_stage1,
)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    result, rows = build_cmp_stage1(repo_root=root)
    write_cmp_stage1(repo_root=root, result=result, rows=rows)
    print(
        json.dumps(
            {
                "result_hash": result["result_hash"],
                "development_rows": result["development_rows"],
                "targets": {
                    target: {
                        "deltas": result["targets"][target]["deltas"],
                        "fold_primary_wins": result["targets"][target][
                            "fold_primary_wins"
                        ],
                        "passes_stage1_gate": result["targets"][target][
                            "passes_stage1_gate"
                        ],
                        "decision": result["targets"][target]["decision"],
                        "fold_nu": [
                            (x["fold_id"], x["selected_nu"])
                            for x in result["targets"][target]["folds"]
                        ],
                    }
                    for target in ("goals", "corners")
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
