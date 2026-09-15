"""Acquire the V7.1 FRESH confirmatory sample: TheStatsAPI 2026/27, six V7 competitions.

Outcome-blind DATA ACQUISITION ONLY. It fetches finished fixtures and their per-match
/stats into the existing cache, under dedicated `f27_*` tags so neither the frozen
`multisrc_corpus.LEAGUES` registry nor V7's corpus identity can change.

No effects are computed here. No Bedrock. No CHAMPION. Cache-first and idempotent:
a re-run costs zero API budget.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.discovery.corpus import _load_env_for_thestats

_load_env_for_thestats()

import multisrc_fetch as F          # noqa: E402
import thestatsapi_client as api    # noqa: E402

# TheStatsAPI 2026/27 season ids, discovered from /competitions/<comp>/seasons.
FRESH_SEASONS = [
    ("f27_champ",   "comp_8321", "sn_3014533", "Championship 26/27"),
    ("f27_epl",     "comp_3039", "sn_8406098", "Premier League 26/27"),
    ("f27_laliga",  "comp_8814", "sn_8407970", "LaLiga 26/27"),
    ("f27_laliga2", "comp_0976", "sn_1368511", "LaLiga 2 26/27"),
    ("f27_ligue1",  "comp_0256", "sn_3011424", "Ligue 1 26/27"),
    ("f27_ligue2",  "comp_9777", "sn_7255696", "Ligue 2 26/27"),
]

OUT = "/home/ubuntu/research/hypothesis_oos/out/v7_1/V7_1_FRESH_ACQUISITION.json"


def main():
    report = {"seasons": [], "provider": "thestatsapi",
              "note": "acquisition only; no effect, no outcome, no model"}
    for tag, comp, season, display in FRESH_SEASONS:
        print(f"=== {display} ({tag}) ===", flush=True)
        F.fetch_fixtures(comp, season, tag)
        got, cached = F.fetch_stats(comp, season, tag)
        path = f"{F.CACHE}/_all_fixtures_{tag}_{season}.json"
        n = json.load(open(path))["n"] if os.path.exists(path) else 0
        report["seasons"].append({"tag": tag, "comp": comp, "season_id": season,
                                  "display": display, "n_finished_fixtures": n,
                                  "stats_live": got, "stats_cached": cached})
        print(f"  -> {n} finished fixtures, stats live={got} cached={cached}", flush=True)
    report["budget_after"] = api.budget_snapshot()
    json.dump(report, open(OUT, "w"), indent=1, sort_keys=True)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
