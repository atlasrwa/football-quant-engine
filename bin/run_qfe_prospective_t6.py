#!/usr/bin/env python3
from pathlib import Path
from src.research.prospective.capture import ProspectiveApiClient
from src.research.prospective.t6_runner import run_t6_cycle, runner_lock

REPO=Path("/srv/qfe/football-quant-engine")
ROOT=Path("/home/ubuntu/data/qfe_prospective_v1/cohort_f3d5bb667f8849b33baf29fb9666400427a17c4cf02f47e9dc0e0a098af6f8f0")
with runner_lock(ROOT/"t6_runner.lock"):
    result=run_t6_cycle(
        repo_root=REPO,
        output_root=ROOT,
        history_snapshot_root=Path("/home/ubuntu/data/thestatsapi/prospective_history_v1"),
        base_data_dir=Path("/home/ubuntu/data/thestatsapi/championship"),
        client=ProspectiveApiClient(),
    )
print(result)
