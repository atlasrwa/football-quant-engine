#!/usr/bin/env python3
from pathlib import Path
from src.research.prospective.capture import ProspectiveApiClient
from src.research.prospective.price_movement import run_price_movement_cycle, scanner_lock

REPO=Path("/srv/qfe/football-quant-engine")
COHORT_ROOT=Path("/home/ubuntu/data/qfe_prospective_v1/cohort_f3d5bb667f8849b33baf29fb9666400427a17c4cf02f47e9dc0e0a098af6f8f0")
MOVEMENT_ROOT=COHORT_ROOT/"market_movement"
with scanner_lock(MOVEMENT_ROOT/"scanner.lock"):
    result=run_price_movement_cycle(
        repo_root=REPO,
        cohort_root=COHORT_ROOT,
        movement_root=MOVEMENT_ROOT,
        client=ProspectiveApiClient(),
    )
print(result)
