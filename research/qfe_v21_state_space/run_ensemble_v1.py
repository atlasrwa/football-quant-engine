"""CLI entrypoint for QFE V2.1 regularized ensemble Stage 1."""
from pathlib import Path
import json

from src.research.evaluation.v21_regularized_ensemble import (
    build_ensemble_stage1,
    write_ensemble_stage1,
)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    result = build_ensemble_stage1(repo_root=root)
    write_ensemble_stage1(repo_root=root, result=result)
    print(
        json.dumps(
            {
                "result_hash": result["result_hash"],
                "families": {
                    family: {
                        "selected_ridge_lambda": result["families"][family][
                            "selected_ridge_lambda"
                        ],
                        "paired_improvement_vs_anchor": result["families"][
                            family
                        ]["paired_improvement_vs_anchor"],
                        "fold_log_loss_wins": result["families"][family][
                            "fold_log_loss_wins"
                        ],
                        "passes_stage1_gate": result["families"][family][
                            "passes_stage1_gate"
                        ],
                        "decision": result["families"][family]["decision"],
                        "final_refit_weights": result["families"][family][
                            "final_refit_weights_descriptive_only"
                        ],
                    }
                    for family in ("goals", "corners")
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
