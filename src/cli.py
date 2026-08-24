"""CLI interface for the Football Quant Engine.

Subcommands:
  ingest        — Fetch and cache match data from FootyStats or local fixtures.
  features      — Compute feature vectors from ingested match data.
  backtest      — Run walk-forward backtest on computed features.
  run           — Execute the full pipeline (ingest → features → backtest).
  daily-signals — Fetch upcoming fixtures for today and generate live signals.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.backtest.engine import WalkForwardEngine
from src.backtest.signal import SignalGenerator
from src.features.assembler import FeatureAssembler
from src.ingestion.client import FootyStatsClient
from src.ingestion.pipeline import IngestionPipeline
from src.models.config import StrategyConfig
from src.models.features import MatchFeatures
from src.models.match import Match
from src.serializer import format_summary, save_result


def _setup_logging(verbosity: int) -> None:
    """Configure logging based on verbosity level."""
    level_map = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    level = level_map.get(verbosity, logging.DEBUG)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _build_config(args: argparse.Namespace) -> StrategyConfig:
    """Build StrategyConfig from CLI arguments or config file."""
    if hasattr(args, "config_file") and args.config_file:
        config_path = Path(args.config_file)
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        return StrategyConfig(**config_data)

    kwargs = {}
    if hasattr(args, "train_window") and args.train_window is not None:
        kwargs["train_window"] = args.train_window
    if hasattr(args, "test_window") and args.test_window is not None:
        kwargs["test_window"] = args.test_window
    if hasattr(args, "step_size") and args.step_size is not None:
        kwargs["step_size"] = args.step_size
    if hasattr(args, "base_stake") and args.base_stake is not None:
        kwargs["base_stake"] = args.base_stake
    if hasattr(args, "min_edge") and args.min_edge is not None:
        kwargs["min_edge_threshold"] = args.min_edge
    if hasattr(args, "seed") and args.seed is not None:
        kwargs["random_seed"] = args.seed

    return StrategyConfig(**kwargs)


def _get_api_key() -> Optional[str]:
    """Retrieve FootyStats API key from environment."""
    return os.environ.get("FOOTYSTATS_API_KEY")


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to multiple subcommands."""
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG).",
    )
    parser.add_argument(
        "--league-id", "--league", type=int, default=4759,
        dest="league_id",
        help="FootyStats league ID (default: 4759).",
    )
    parser.add_argument(
        "--season", type=str, default="2023",
        help="Season string (default: '2023'). Supports slash format e.g. '2018/2019'.",
    )


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    """Add strategy configuration arguments."""
    group = parser.add_argument_group("Strategy Configuration")
    group.add_argument(
        "--config-file", type=str, default=None,
        help="Path to JSON config file (overrides other config flags).",
    )
    group.add_argument("--train-window", type=int, default=None)
    group.add_argument("--test-window", type=int, default=None)
    group.add_argument("--step-size", type=int, default=None)
    group.add_argument("--base-stake", type=float, default=None)
    group.add_argument("--min-edge", type=float, default=None)
    group.add_argument("--seed", type=int, default=None)


def _ingest_matches(args: argparse.Namespace) -> List[Match]:
    """Ingest matches using the specified mode (fixture or api).

    Args:
        args: Parsed CLI arguments with league_id, season, and mode.

    Returns:
        List of ingested Match objects.
    """
    mode = getattr(args, "mode", "fixture")

    if mode == "api":
        api_key = _get_api_key() or "example"
        client = FootyStatsClient(api_key=api_key)
        pipeline = IngestionPipeline(client=client)
        matches = asyncio.run(pipeline.ingest_league(args.league_id, args.season))
    else:
        pipeline = IngestionPipeline()
        matches = pipeline.ingest_from_fixtures(args.league_id, args.season)

    return matches


def cmd_ingest(args: argparse.Namespace) -> List[Match]:
    """Execute the ingest subcommand."""
    _setup_logging(args.verbose)
    matches = _ingest_matches(args)
    mode = getattr(args, "mode", "fixture")
    print(
        f"Ingested {len(matches)} matches for "
        f"league={args.league_id} season={args.season} (mode={mode})"
    )
    return matches


def cmd_features(args: argparse.Namespace) -> List[MatchFeatures]:
    """Execute the features subcommand."""
    _setup_logging(args.verbose)
    config = _build_config(args)

    matches = _ingest_matches(args)
    print(f"Ingested {len(matches)} matches")

    assembler = FeatureAssembler(config=config)
    features = assembler.assemble(matches)
    print(f"Computed {len(features)} feature vectors")
    return features


def cmd_backtest(args: argparse.Namespace) -> None:
    """Execute the backtest subcommand."""
    _setup_logging(args.verbose)
    config = _build_config(args)

    matches = _ingest_matches(args)

    assembler = FeatureAssembler(config=config)
    features = assembler.assemble(matches)

    engine = WalkForwardEngine(config=config)
    result = engine.run(features)

    # Output summary
    print(format_summary(result))

    # Save result if output path specified
    output_dir = Path(args.output) if hasattr(args, "output") and args.output else None
    saved_path = save_result(result, output_dir=output_dir)
    print(f"Results saved to: {saved_path}")


def cmd_run(args: argparse.Namespace) -> None:
    """Execute the full pipeline (ingest → features → backtest)."""
    _setup_logging(args.verbose)
    config = _build_config(args)
    mode = getattr(args, "mode", "fixture")

    print("━" * 60)
    print("  Football Quant Engine — Full Pipeline")
    print("━" * 60)

    # Step 1: Ingest
    print(f"\n[1/3] Ingesting matches (league={args.league_id}, season={args.season}, mode={mode})...")
    matches = _ingest_matches(args)
    print(f"      ✓ {len(matches)} matches loaded")

    # Step 2: Features
    print("\n[2/3] Computing feature vectors...")
    assembler = FeatureAssembler(config=config)
    features = assembler.assemble(matches)
    print(f"      ✓ {len(features)} feature vectors assembled")

    # Step 3: Backtest
    print("\n[3/3] Running walk-forward backtest...")
    engine = WalkForwardEngine(config=config)
    result = engine.run(features)
    print(f"      ✓ {result.total_bets} bets placed across {len(result.fold_results)} folds")

    # Output
    print(format_summary(result))

    output_dir = Path(args.output) if hasattr(args, "output") and args.output else None
    saved_path = save_result(result, output_dir=output_dir)
    print(f"Results saved to: {saved_path}")


def cmd_daily_signals(args: argparse.Namespace) -> None:
    """Fetch upcoming fixtures for today and generate live signals.

    Fetches recent historical matches for context, assembles features,
    generates signals for upcoming/today's matches, and appends them
    to data/results/live_signals.jsonl.
    """
    _setup_logging(args.verbose)
    config = _build_config(args)

    api_key = _get_api_key() or "example"
    client = FootyStatsClient(api_key=api_key)
    pipeline = IngestionPipeline(client=client)

    print(f"Fetching matches for league={args.league_id}, season={args.season}...")

    # Fetch all available matches for the league/season (includes upcoming)
    matches = asyncio.run(pipeline.ingest_league(args.league_id, args.season))

    if not matches:
        print("No matches found.")
        return

    # Separate historical (played) from upcoming (no goals yet, or future date)
    now_unix = int(time.time())
    historical = [m for m in matches if m.date_unix < now_unix and m.total_goals >= 0]
    upcoming = [m for m in matches if m.date_unix >= now_unix]

    # If no upcoming detected by timestamp, treat last N as "today's" for demo
    if not upcoming and historical:
        print("No upcoming matches found by timestamp. No signals to generate.")
        return

    print(f"  Historical: {len(historical)} matches")
    print(f"  Upcoming:   {len(upcoming)} matches")

    if len(historical) < 10:
        print("Insufficient historical data for feature computation. Need at least 10 matches.")
        return

    # Assemble features using historical matches for context
    assembler = FeatureAssembler(config=config)
    all_features = assembler.assemble(historical + upcoming)

    # Extract features for upcoming matches only (by match_id)
    upcoming_ids = {m.id for m in upcoming}
    upcoming_features = [f for f in all_features if f.match_id in upcoming_ids]

    if not upcoming_features:
        print("Could not compute features for upcoming matches.")
        return

    # Generate signals
    signal_gen = SignalGenerator(config=config)
    signals = []

    for feat in upcoming_features:
        result = signal_gen.generate(feat)
        if result is not None:
            prediction, edge = result
            signal_record = {
                "match_id": feat.match_id,
                "date_unix": feat.date_unix,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "league_id": args.league_id,
                "season": args.season,
                "prediction": prediction,
                "edge": round(edge, 4),
                "home_xg_eff": round(feat.home_xg_eff_delta_rolling, 4),
                "away_xg_eff": round(feat.away_xg_eff_delta_rolling, 4),
                "home_form": round(feat.home_rolling_form, 4),
                "away_form": round(feat.away_rolling_form, 4),
                "referee_volatility": round(feat.referee_volatility_index, 4),
                "over_odds": feat.over_odds,
                "under_odds": feat.under_odds,
                "status": "pending",
            }
            signals.append(signal_record)

    if not signals:
        print("No signals met the edge threshold.")
        return

    # Write to JSONL
    output_dir = Path(args.output) if hasattr(args, "output") and args.output else None
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent.parent / "data" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "live_signals.jsonl"
    with open(output_path, "a", encoding="utf-8") as f:
        for signal in signals:
            f.write(json.dumps(signal) + "\n")

    print(f"\n  Generated {len(signals)} signals:")
    for s in signals:
        print(f"    Match {s['match_id']}: {s['prediction']} (edge={s['edge']:.3f})")
    print(f"\n  Appended to: {output_path}")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="football-quant-engine",
        description="Over/Under football sports analytics engine with walk-forward backtesting.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest match data from fixtures or API")
    _add_common_args(p_ingest)
    p_ingest.add_argument(
        "--mode", type=str, choices=["fixture", "api"], default="fixture",
        help="Ingestion mode: 'fixture' for local files, 'api' for live FootyStats (default: fixture).",
    )

    # features
    p_features = subparsers.add_parser("features", help="Compute feature vectors")
    _add_common_args(p_features)
    _add_config_args(p_features)
    p_features.add_argument(
        "--mode", type=str, choices=["fixture", "api"], default="fixture",
        help="Ingestion mode (default: fixture).",
    )

    # backtest
    p_backtest = subparsers.add_parser("backtest", help="Run walk-forward backtest")
    _add_common_args(p_backtest)
    _add_config_args(p_backtest)
    p_backtest.add_argument(
        "--mode", type=str, choices=["fixture", "api"], default="fixture",
        help="Ingestion mode (default: fixture).",
    )
    p_backtest.add_argument(
        "--output", type=str, default=None,
        help="Output directory for results JSON.",
    )

    # run (full pipeline)
    p_run = subparsers.add_parser("run", help="Execute full pipeline (ingest → features → backtest)")
    _add_common_args(p_run)
    _add_config_args(p_run)
    p_run.add_argument(
        "--mode", type=str, choices=["fixture", "api"], default="fixture",
        help="Ingestion mode (default: fixture).",
    )
    p_run.add_argument(
        "--output", type=str, default=None,
        help="Output directory for results JSON.",
    )

    # daily-signals
    p_daily = subparsers.add_parser(
        "daily-signals",
        help="Fetch upcoming fixtures and generate live signals",
    )
    _add_common_args(p_daily)
    _add_config_args(p_daily)
    p_daily.add_argument(
        "--output", type=str, default=None,
        help="Output directory for live_signals.jsonl (default: data/results/).",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments. Defaults to sys.argv[1:].

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "ingest":
            cmd_ingest(args)
        elif args.command == "features":
            cmd_features(args)
        elif args.command == "backtest":
            cmd_backtest(args)
        elif args.command == "run":
            cmd_run(args)
        elif args.command == "daily-signals":
            cmd_daily_signals(args)
        else:
            parser.print_help()
            return 1
    except Exception as e:
        logging.error("Pipeline failed: %s", e)
        print(f"\nError: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
