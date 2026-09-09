"""Run the M0-M4 historical information decomposition and write a small artifact.

Usage:
    .venv/bin/python scripts/prospective_historical_eval.py [--family GOALS|CORNERS|both] [--max N]

Writes research/evaluation/prospective_m0_m4_<family>.json (small summary only).
Large per-fixture dumps are never written. M5 is reported UNSUPPORTED.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.discovery.corpus import load_discovery_set
from src.research.prospective.historical_eval import run_historical_eval

OUT_DIR = Path("research/evaluation")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="both", choices=["goals", "corners", "both"])
    ap.add_argument("--max", type=int, default=0, help="cap number of matches (0=all)")
    args = ap.parse_args()

    matches = load_discovery_set()
    if args.max > 0:
        # keep chronological representativeness: take a contiguous, per-league
        # slice by simply capping the flat list (already league-grouped).
        matches = matches[: args.max]

    families = ["goals", "corners"] if args.family == "both" else [args.family]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for fam in families:
        result = run_historical_eval(matches, family=fam)
        out = OUT_DIR / f"prospective_m0_m4_{fam.lower()}.json"
        out.write_text(json.dumps(result.to_dict(), indent=2))
        print(f"[{fam}] n_common={result.n_common} -> {out}")
        for s in result.scores:
            print(
                f"  {s.layer}: logloss={s.log_loss:.4f} brier={s.brier:.4f} "
                f"slope={s.calibration_slope} res={s.resolution.resolution:.4f} "
                f"dLL={s.delta_log_loss_vs_prev}"
            )
        print(f"  {result.m5_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
