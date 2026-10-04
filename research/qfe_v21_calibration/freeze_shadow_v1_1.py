"""Freeze the QFE V2.1 corner-side calibration shadow."""
from pathlib import Path
import json

from src.research.prospective.v21_calibration_shadow import (
    build_shadow_freeze,
    write_shadow_freeze,
)

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    freeze = build_shadow_freeze(root)
    write_shadow_freeze(
        json_path=root / "research/qfe_v21_calibration/SHADOW_FREEZE_V1_1.json",
        markdown_path=root / "research/qfe_v21_calibration/SHADOW_FREEZE_V1_1.md",
        freeze=freeze,
    )
    print(json.dumps({
        "shadow_freeze_hash": freeze["shadow_freeze_hash"],
        "challenger": freeze["challenger"]["method"],
        "fit_unique_fixtures": freeze["challenger"]["fit_unique_fixtures"],
        "fit_event_cells": freeze["challenger"]["fit_event_cells"],
        "production_p_model_modified": freeze["boundaries"][
            "production_p_model_modified"
        ],
    }, indent=2, sort_keys=True))
