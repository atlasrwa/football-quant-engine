#!/usr/bin/env python3
"""Frozen walk-forward evaluation of the latent raw-stat team-state challenger.

The script merges paginated cache files by season, deduplicates match IDs, and
freezes every equal-kickoff batch. It makes no odds, EV, or market claim.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from typing import Any

import numpy as np

from src.research.models.latent_team_state import (
    MODEL_VERSION,
    LatentTeamStateForecaster,
    MatchObservation,
    build_scoreline_forecast,
    joint_poisson_log_loss,
    ranked_probability_score_1x2,
)

SEASON_ID_PATTERN = re.compile(r"season_id:_(\d+)")
SCORE_NAMES = ("joint_log_loss", "rps_1x2", "brier_over_2_5")


def _nonnegative(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) and number >= 0 else None


def _required_int(value: Any) -> int | None:
    number = _nonnegative(value)
    return None if number is None else int(number)


def load_cached_seasons(cache_dir: Path) -> tuple[dict[str, list[MatchObservation]], dict[str, int]]:
    """Merge all pages and deduplicate IDs before constructing observations."""

    raw_by_season: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    pages_seen: dict[str, set[int]] = defaultdict(set)
    declared_max_pages: dict[str, int] = {}
    files = sorted(cache_dir.glob("league-matches_*.json"))
    duplicate_rows = 0
    invalid_rows = 0

    for path in files:
        match = SEASON_ID_PATTERN.search(path.name)
        if match is None:
            continue
        season_id = match.group(1)
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        pager = payload.get("pager", {})
        current_page = _required_int(pager.get("current_page"))
        max_page = _required_int(pager.get("max_page"))
        if current_page is None or max_page is None or current_page < 1 or max_page < 1:
            raise ValueError(f"invalid pagination metadata in {path}")
        prior_max = declared_max_pages.setdefault(season_id, max_page)
        if prior_max != max_page:
            raise ValueError(f"conflicting max_page metadata for season {season_id}")
        pages_seen[season_id].add(current_page)
        for row in payload.get("data", []):
            match_id = row.get("id")
            if match_id is None:
                invalid_rows += 1
                continue
            key = str(match_id)
            if key in raw_by_season[season_id]:
                if raw_by_season[season_id][key] != row:
                    raise ValueError(
                        f"conflicting duplicate match {key} in season {season_id}"
                    )
                duplicate_rows += 1
                continue
            raw_by_season[season_id][key] = row

    incomplete_seasons = [
        season_id
        for season_id, max_page in declared_max_pages.items()
        if pages_seen[season_id] != set(range(1, max_page + 1))
    ]

    seasons: dict[str, list[MatchObservation]] = {}
    for season_id, rows_by_id in raw_by_season.items():
        observations: list[MatchObservation] = []
        for match_id, row in rows_by_id.items():
            kickoff = _required_int(row.get("date_unix"))
            home_id = row.get("homeID")
            away_id = row.get("awayID")
            home_goals = _required_int(row.get("homeGoalCount"))
            away_goals = _required_int(row.get("awayGoalCount"))
            if (
                row.get("status") != "complete"
                or kickoff is None
                or home_id is None
                or away_id is None
                or home_goals is None
                or away_goals is None
            ):
                invalid_rows += 1
                continue
            observations.append(
                MatchObservation(
                    match_id=match_id,
                    kickoff=kickoff,
                    home_team_id=str(home_id),
                    away_team_id=str(away_id),
                    home_goals=home_goals,
                    away_goals=away_goals,
                    home_shots=_nonnegative(row.get("team_a_shots")),
                    away_shots=_nonnegative(row.get("team_b_shots")),
                    home_shots_on_target=_nonnegative(row.get("team_a_shotsOnTarget")),
                    away_shots_on_target=_nonnegative(row.get("team_b_shotsOnTarget")),
                    home_dangerous_attacks=_nonnegative(row.get("team_a_dangerous_attacks")),
                    away_dangerous_attacks=_nonnegative(row.get("team_b_dangerous_attacks")),
                    home_attacks=_nonnegative(row.get("team_a_attacks")),
                    away_attacks=_nonnegative(row.get("team_b_attacks")),
                    home_corners=_nonnegative(row.get("team_a_corners")),
                    away_corners=_nonnegative(row.get("team_b_corners")),
                )
            )
        observations.sort(key=lambda item: (item.kickoff, item.match_id))
        if observations:
            seasons[season_id] = observations

    metadata = {
        "cache_files": len(files),
        "season_ids": len(seasons),
        "loaded_matches": sum(len(matches) for matches in seasons.values()),
        "duplicate_rows_removed": duplicate_rows,
        "invalid_or_incomplete_rows_removed": invalid_rows,
        "seasons_with_incomplete_pagination": len(incomplete_seasons),
    }
    return seasons, metadata


def evaluate_season(season_id: str, matches: list[MatchObservation]) -> list[dict[str, float | str]]:
    raw_model = LatentTeamStateForecaster(mode="raw")
    goals_model = LatentTeamStateForecaster(mode="goals")
    home_goal_sum = 0.0
    away_goal_sum = 0.0
    climatology_count = 0
    records: list[dict[str, float | str]] = []

    for _, grouped in groupby(matches, key=lambda item: item.kickoff):
        batch = list(grouped)
        if climatology_count:
            climate_home = max(home_goal_sum / climatology_count, 0.05)
            climate_away = max(away_goal_sum / climatology_count, 0.05)
        else:
            climate_home = climate_away = 1.0

        raw_forecasts = raw_model.process_batch(batch)
        goals_forecasts = goals_model.process_batch(batch)
        for match, raw, goals in zip(batch, raw_forecasts, goals_forecasts, strict=True):
            if raw is None or goals is None:
                continue
            climate = build_scoreline_forecast(
                match,
                climate_home,
                climate_away,
                score_grid_max=raw.score_grid_max,
                model_version="expanding-climatology",
            )
            actual_over = float(match.home_goals + match.away_goals > 2)
            records.append(
                {
                    "season_id": season_id,
                    "raw_joint_log_loss": joint_poisson_log_loss(
                        match.home_goals,
                        match.away_goals,
                        raw.lambda_home,
                        raw.lambda_away,
                    ),
                    "goals_joint_log_loss": joint_poisson_log_loss(
                        match.home_goals,
                        match.away_goals,
                        goals.lambda_home,
                        goals.lambda_away,
                    ),
                    "climate_joint_log_loss": joint_poisson_log_loss(
                        match.home_goals,
                        match.away_goals,
                        climate.lambda_home,
                        climate.lambda_away,
                    ),
                    "raw_rps_1x2": ranked_probability_score_1x2(
                        raw, match.home_goals, match.away_goals
                    ),
                    "goals_rps_1x2": ranked_probability_score_1x2(
                        goals, match.home_goals, match.away_goals
                    ),
                    "climate_rps_1x2": ranked_probability_score_1x2(
                        climate, match.home_goals, match.away_goals
                    ),
                    "raw_brier_over_2_5": (raw.over_2_5 - actual_over) ** 2,
                    "goals_brier_over_2_5": (goals.over_2_5 - actual_over) ** 2,
                    "climate_brier_over_2_5": (climate.over_2_5 - actual_over) ** 2,
                }
            )

        # Climatology is updated only after every match at this kickoff was scored.
        home_goal_sum += sum(match.home_goals for match in batch)
        away_goal_sum += sum(match.away_goals for match in batch)
        climatology_count += len(batch)

    return records


def _cluster_bootstrap(
    records: list[dict[str, float | str]],
    score: str,
    draws: int,
    seed: int,
) -> tuple[float, float]:
    clusters: dict[str, list[float]] = defaultdict(list)
    for row in records:
        improvement = float(row[f"goals_{score}"]) - float(row[f"raw_{score}"])
        clusters[str(row["season_id"])].append(improvement)
    sums = np.asarray([sum(values) for values in clusters.values()], dtype=float)
    counts = np.asarray([len(values) for values in clusters.values()], dtype=float)
    rng = np.random.default_rng(seed)
    estimates = np.empty(draws, dtype=float)
    for draw in range(draws):
        sampled = rng.integers(0, len(sums), size=len(sums))
        estimates[draw] = float(np.sum(sums[sampled]) / np.sum(counts[sampled]))
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def summarize(
    records: list[dict[str, float | str]],
    metadata: dict[str, int],
    bootstrap_draws: int,
    seed: int,
) -> dict[str, Any]:
    if not records:
        raise RuntimeError("no post-burn predictions were produced")
    metrics: dict[str, Any] = {}
    season_ids = sorted({str(row["season_id"]) for row in records})

    for score in SCORE_NAMES:
        raw_mean = float(np.mean([float(row[f"raw_{score}"]) for row in records]))
        goals_mean = float(np.mean([float(row[f"goals_{score}"]) for row in records]))
        climate_mean = float(np.mean([float(row[f"climate_{score}"]) for row in records]))
        improvement = goals_mean - raw_mean
        ci_low, ci_high = _cluster_bootstrap(records, score, bootstrap_draws, seed)
        positive_clusters = 0
        for season_id in season_ids:
            values = [
                float(row[f"goals_{score}"]) - float(row[f"raw_{score}"])
                for row in records
                if row["season_id"] == season_id
            ]
            positive_clusters += int(float(np.mean(values)) > 0.0)
        metrics[score] = {
            "raw_state": raw_mean,
            "goals_only_state": goals_mean,
            "expanding_climatology": climate_mean,
            "raw_improvement_vs_goals_only": improvement,
            "cluster_bootstrap_95_ci": [ci_low, ci_high],
            "positive_season_clusters": positive_clusters,
            "season_clusters": len(season_ids),
        }

    promotion = {
        "cache_pagination_complete": metadata["seasons_with_incomplete_pagination"] == 0,
        "scoreline_gain_at_least_0_005": metrics["joint_log_loss"][
            "raw_improvement_vs_goals_only"
        ]
        >= 0.005,
        "scoreline_ci_excludes_zero": metrics["joint_log_loss"][
            "cluster_bootstrap_95_ci"
        ][0]
        > 0.0,
        "rps_gain_at_least_0_002": metrics["rps_1x2"][
            "raw_improvement_vs_goals_only"
        ]
        >= 0.002,
        "rps_ci_excludes_zero": metrics["rps_1x2"]["cluster_bootstrap_95_ci"][0]
        > 0.0,
    }
    promotion["passes_internal_challenger_gate"] = all(promotion.values())

    return {
        "model_version": MODEL_VERSION,
        "scope": "scoreline_and_1x2_research_challenger_only",
        "excluded_claims": ["EV", "ROI", "market_beating", "totals_edge"],
        "protocol": {
            "chronological": True,
            "equal_kickoff_batches_frozen": True,
            "cache_pages_merged": True,
            "match_ids_deduplicated": True,
            "burn_in_matches": 100,
            "refit_every_matches": 50,
            "state_half_life_matches": 8,
            "bootstrap_draws": bootstrap_draws,
            "bootstrap_seed": seed,
        },
        "data": {**metadata, "post_burn_predictions": len(records)},
        "metrics": metrics,
        "internal_promotion_screen": promotion,
        "interpretation": (
            "Positive values mean the raw-stat state beat the identically filtered "
            "goals-only state. Internal passage is not prospective validation or "
            "evidence of economic value."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/discovery/corpus"),
        help="directory containing paginated league-matches JSON files",
    )
    parser.add_argument("--bootstrap-draws", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=20_260_903)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSON output path; stdout is always emitted",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seasons, metadata = load_cached_seasons(args.cache_dir)
    records: list[dict[str, float | str]] = []
    for season_id, matches in sorted(seasons.items()):
        records.extend(evaluate_season(season_id, matches))
    result = summarize(records, metadata, args.bootstrap_draws, args.seed)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
