"""CLI entrypoint for QFE V2.1 competition-local Gamma-Poisson Stage 1 V3."""
from pathlib import Path
import json

from src.research.evaluation.v21_comp_local_stage1 import (
    build_stage1_v3,
    write_stage1_v3,
)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    result, rows = build_stage1_v3(repo_root=root)
    write_stage1_v3(repo_root=root, result=result, rows=rows)
    print(
        json.dumps(
            {
                "result_hash": result["result_hash"],
                "development_rows": result["development_rows"],
                "targets": {
                    name: {
                        "delta_side_poisson_nll": result["targets"][name][
                            "delta_side_poisson_nll"
                        ],
                        "delta_binary_log_loss": result["targets"][name][
                            "delta_binary_log_loss"
                        ],
                        "delta_brier": result["targets"][name]["delta_brier"],
                        "fold_primary_wins": result["targets"][name][
                            "fold_primary_wins"
                        ],
                        "passes_stage1_gate": result["targets"][name][
                            "passes_stage1_gate"
                        ],
                        "decision": result["targets"][name]["decision"],
                    }
                    for name in ("goals", "corners")
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
