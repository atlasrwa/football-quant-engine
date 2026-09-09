"""Run the full FootyStats->TheStatsAPI coverage scan and write artifacts.

Builds the identity crosswalk from the provider-league registry, runs a bounded
live reconnaissance over VERIFIED competitions, classifies each, and writes:

    research/evaluation/prospective_crosswalk.json
    research/evaluation/prospective_coverage_matrix.json
    research/evaluation/prospective_coverage_matrix.md

Reconnaissance is capped (default 1000 requests). No secrets, no large dumps,
no live capture data written. Read-only against the API.

Usage:
    .venv/bin/python scripts/prospective_coverage_scan.py [--budget 1000] [--horizon-hours 504]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.research.prospective.capture import ProspectiveApiClient
from src.research.prospective.coverage_matrix import build_coverage_matrix, matrix_summary
from src.research.prospective.crosswalk import build_crosswalk, crosswalk_summary
from src.research.prospective.recon import Reconnaissance

OUT = Path("research/evaluation")


def _md(rows) -> str:
    lines = [
        "# Prospective competition coverage matrix", "",
        "| Competition | Country | TSA comp | Identity | Class | Prio | Books | Markets seen | Fixtures | Nearest KO |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: (r.capture_priority, r.entry.canonical_name)):
        cov = r.coverage
        books = ",".join(cov.bookmakers_present) if cov and cov.bookmakers_present else ""
        markets = ",".join(cov.markets_present) if cov and cov.markets_present else ""
        fixtures = cov.scheduled_fixtures_in_scan if cov else None
        nearest = (cov.nearest_kickoff_iso or "")[:16] if cov else ""
        lines.append(
            f"| {r.entry.canonical_name} | {r.entry.country or ''} | "
            f"{r.entry.thestatsapi_competition_id or ''} | {r.entry.identity_status.value} | "
            f"{r.capture_classification.value} | {r.capture_priority} | {books} | {markets} | "
            f"{fixtures if fixtures is not None else ''} | {nearest} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=1000)
    ap.add_argument("--horizon-hours", type=int, default=21 * 24)
    args = ap.parse_args()

    entries = build_crosswalk()
    print("crosswalk:", crosswalk_summary(entries))

    client = ProspectiveApiClient()
    if not client.is_configured:
        print("No API key; writing identity-only crosswalk (no live coverage).")
        coverage = []
        recon_dict = {"total_requests": 0, "note": "no_api_key"}
    else:
        recon = Reconnaissance(client, budget=args.budget, horizon_hours=args.horizon_hours)
        result = recon.run(entries)
        coverage = result.coverage
        recon_dict = result.to_dict()
        print(f"recon: {result.total_requests} requests, "
              f"monthly_remaining={result.monthly_quota_remaining}, "
              f"stopped_early={result.stopped_early}")

    rows = build_coverage_matrix(entries, coverage)
    print("classification:", matrix_summary(rows))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prospective_crosswalk.json").write_text(
        json.dumps({"summary": crosswalk_summary(entries),
                    "entries": [e.to_dict() for e in entries]}, indent=2))
    (OUT / "prospective_coverage_matrix.json").write_text(
        json.dumps({"summary": matrix_summary(rows), "recon": recon_dict,
                    "rows": [r.to_dict() for r in rows]}, indent=2))
    (OUT / "prospective_coverage_matrix.md").write_text(_md(rows))
    print("wrote artifacts to", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
