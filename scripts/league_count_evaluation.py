#!/usr/bin/env python3
"""Run the governed three-arm count evaluation on cached broad corpus data.

This is a zero-API entry point. It reads the static corpus and, by default when
present, the cache-only expanded-league registry. It never edits corpus files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.discovery.corpus import (
    CORPUS_MANIFEST_FILE,
    CORPUS_SEASONS,
    load_discovery_set,
    load_heldout_set,
)
from src.research.evaluation.league_count import (
    LeagueCountEvaluationConfig,
    LeagueCountEvaluator,
    build_broad_count_rows,
    default_count_markets,
)
from src.research.footystats.corpus_expansion import (
    DEFAULT_EXPANSION_REGISTRY,
    load_expanded_completed_matches,
    load_expanded_league_names,
)

DEFAULT_OUTPUT = Path("data/results/league_count_hierarchical_report.json")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-draws", type=int, default=2000)
    parser.add_argument("--refit-batches", type=int, default=20)
    parser.add_argument("--min-global-train", type=int, default=200)
    parser.add_argument("--min-league-train", type=int, default=40)
    parser.add_argument("--min-cell", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument(
        "--bootstrap-block", choices=("date", "league_week"), default="league_week"
    )
    parser.add_argument(
        "--discovery-only",
        action="store_true",
        help="Use only older static seasons (expanded registered seasons remain included).",
    )
    parser.add_argument(
        "--expanded-registry",
        type=Path,
        default=DEFAULT_EXPANSION_REGISTRY,
        help="cache-only expanded-league registry to include when present",
    )
    parser.add_argument(
        "--no-expanded-registry",
        action="store_true",
        help="exclude the expanded-league registry even when it is present",
    )
    return parser.parse_args(argv)


def _deduplicate_matches(matches: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    deduplicated: list[dict[str, object]] = []
    seen: set[str] = set()
    for match in matches:
        fixture_id = match.get("id", match.get("match_id"))
        if fixture_id is None:
            identity = "payload:" + hashlib.sha256(
                json.dumps(match, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
        else:
            identity = f"id:{fixture_id}"
        if identity in seen:
            continue
        seen.add(identity)
        deduplicated.append(dict(match))
    return deduplicated


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    discovery = load_discovery_set()
    heldout = [] if args.discovery_only else load_heldout_set()

    expanded_matches: list[dict[str, object]] = []
    expanded_names: tuple[str, ...] = ()
    expansion_registry_used = (
        not args.no_expanded_registry and args.expanded_registry.exists()
    )
    if expansion_registry_used:
        expanded_matches = load_expanded_completed_matches(args.expanded_registry)
        expanded_names = load_expanded_league_names(args.expanded_registry)

    matches = _deduplicate_matches(discovery + heldout + expanded_matches)
    declared_leagues = tuple(dict.fromkeys((*CORPUS_SEASONS, *expanded_names)))
    markets = default_count_markets()
    rows = build_broad_count_rows(matches, markets)
    config = LeagueCountEvaluationConfig(
        min_global_train=args.min_global_train,
        min_league_train=args.min_league_train,
        refit_every_kickoff_batches=args.refit_batches,
        min_cell_predictions=args.min_cell,
        bootstrap_draws=args.bootstrap_draws,
        bootstrap_block=args.bootstrap_block,
        seed=args.seed,
    )
    report = LeagueCountEvaluator(config).evaluate(
        rows,
        markets,
        preregistered_leagues=declared_leagues,
    ).to_dict()

    manifest_bytes = CORPUS_MANIFEST_FILE.read_bytes()
    expansion_bytes = (
        args.expanded_registry.read_bytes() if expansion_registry_used else None
    )
    report["corpus"] = {
        "name": (
            "FootyStats broad static plus expanded corpus"
            if expansion_registry_used
            else "FootyStats broad static corpus"
        ),
        "manifest": str(CORPUS_MANIFEST_FILE),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "expansion_registry": (
            str(args.expanded_registry) if expansion_registry_used else None
        ),
        "expansion_registry_sha256": (
            hashlib.sha256(expansion_bytes).hexdigest()
            if expansion_bytes is not None
            else None
        ),
        "registered_leagues": len(declared_leagues),
        "expanded_leagues": list(expanded_names),
        "scope": (
            "older static plus expanded registered seasons"
            if args.discovery_only
            else "older and newer static plus expanded registered seasons"
        ),
        "n_loaded_completed_fixtures": len(matches),
        "zero_api": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.output} ({len(report['cells'])} complete preregistered cells; "
        f"valid BH family={report['governance']['valid_family_size']})"
    )


if __name__ == "__main__":
    main()
