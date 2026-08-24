"""JSON serialization for BacktestResult and related structures."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.models.results import BacktestResult

logger = logging.getLogger(__name__)

# Default output directory
_DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent.parent / "data" / "results"


def result_to_dict(result: BacktestResult) -> Dict[str, Any]:
    """Convert a BacktestResult to a JSON-serializable dict.

    Args:
        result: The BacktestResult to serialize.

    Returns:
        Dict suitable for json.dumps().
    """
    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": "0.1.0",
        },
        "strategy_config": asdict(result.strategy_config),
        "aggregate_metrics": {
            "net_roi_pct": result.net_roi_pct,
            "win_rate_pct": result.win_rate_pct,
            "max_drawdown_pct": result.max_drawdown_pct,
            "p_value": result.p_value,
            "total_bets": result.total_bets,
            "total_staked": result.total_staked,
            "total_profit": result.total_profit,
        },
        "fold_results": [
            {
                "fold_index": fr.fold_index,
                "train_start": fr.train_start,
                "train_end": fr.train_end,
                "test_start": fr.test_start,
                "test_end": fr.test_end,
                "net_roi_pct": fr.net_roi_pct,
                "win_rate_pct": fr.win_rate_pct,
                "num_bets": fr.num_bets,
            }
            for fr in result.fold_results
        ],
        "bet_log": [
            {
                "match_id": br.match_id,
                "date_unix": br.date_unix,
                "prediction": br.prediction,
                "actual_outcome": br.actual_outcome,
                "odds": br.odds,
                "stake": br.stake,
                "profit_loss": br.profit_loss,
            }
            for br in result.bet_log
        ],
    }


def save_result(
    result: BacktestResult,
    output_dir: Path | None = None,
    filename: str | None = None,
) -> Path:
    """Serialize and save a BacktestResult to a JSON file.

    Args:
        result: The BacktestResult to save.
        output_dir: Directory for output. Defaults to data/results/.
        filename: Optional filename. Defaults to backtest_YYYYMMDD_HHMMSS.json.

    Returns:
        Path to the saved JSON file.
    """
    output_dir = output_dir or _DEFAULT_RESULTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_{timestamp}.json"

    output_path = output_dir / filename
    data = result_to_dict(result)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info("Saved backtest result to %s", output_path)
    return output_path


def format_summary(result: BacktestResult) -> str:
    """Format a human-readable summary for terminal output.

    Args:
        result: The BacktestResult to summarize.

    Returns:
        Formatted multi-line string.
    """
    lines = [
        "",
        "=" * 60,
        "  FOOTBALL QUANT ENGINE — BACKTEST RESULTS",
        "=" * 60,
        "",
        f"  Total Bets:       {result.total_bets}",
        f"  Total Staked:     {result.total_staked:.2f} units",
        f"  Total Profit:     {result.total_profit:+.2f} units",
        "",
        "  ─── Performance Metrics ───",
        f"  Net ROI:          {result.net_roi_pct:+.2f}%",
        f"  Win Rate:         {result.win_rate_pct:.1f}%",
        f"  Max Drawdown:     {result.max_drawdown_pct:.2f}%",
        f"  p-value:          {result.p_value:.4f}",
        "",
        "  ─── Strategy Config ───",
        f"  Train Window:     {result.strategy_config.train_window}",
        f"  Test Window:      {result.strategy_config.test_window}",
        f"  Step Size:        {result.strategy_config.step_size}",
        f"  Base Stake:       {result.strategy_config.base_stake}",
        f"  Min Edge:         {result.strategy_config.min_edge_threshold}",
        "",
        f"  ─── Fold Breakdown ({len(result.fold_results)} folds) ───",
    ]

    for fr in result.fold_results:
        lines.append(
            f"    Fold {fr.fold_index}: "
            f"ROI={fr.net_roi_pct:+.1f}%, "
            f"WR={fr.win_rate_pct:.0f}%, "
            f"Bets={fr.num_bets}"
        )

    lines.extend(["", "=" * 60, ""])
    return "\n".join(lines)
