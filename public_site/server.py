"""Public transparency site — free, no auth, read-only over quarantine data.

Standalone FastAPI app serving:
1. Live quarantine countdown
2. Live prediction feed with attestation visibility
3. Calibration dashboard (forward vs backtest, separate)
4. Full per-league robustness results (75 league-seasons)
5. Failure ledger (append-only)

Reads directly from flat files — no database dependency.
Does NOT touch model code or parameters.

Run:
    cd /home/ubuntu && uvicorn public_site.server:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# ═══════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════

ROOT = Path("/home/ubuntu")
DATA_DIR = ROOT / "data" / "forward"
PREDICTIONS_FILE = DATA_DIR / "predictions.jsonl"
COMMITMENTS_FILE = DATA_DIR / "commitments.jsonl"
SETTLEMENTS_FILE = DATA_DIR / "settlements.jsonl"
REVEALS_FILE = DATA_DIR / "reveals.jsonl"
ROBUSTNESS_FILE = ROOT / "robustness_results.json"
ENROLLMENTS_FILE = ROOT / "quarantine_enrollments.json"
FAILURE_LEDGER_FILE = ROOT / "public_site" / "failure_ledger.json"

# ═══════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Football Quant Engine — Public Transparency",
    version="1.0.0",
    description="Free, public, read-only view of quarantine progress and model calibration.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# DATA LOADERS (read fresh each request — files are small)
# ═══════════════════════════════════════════════════════════════

def _load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file into a list of dicts."""
    if not path.exists():
        return []
    results = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def _load_json(path: Path) -> Any:
    """Load a JSON file."""
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/quarantine")
def get_quarantine_status():
    """Live quarantine countdown and enrollment metadata."""
    enrollments = _load_json(ENROLLMENTS_FILE)
    if not enrollments:
        return {"error": "Enrollment data not found"}

    now = datetime.now(timezone.utc)
    enrollment_ts = datetime.fromisoformat(enrollments["enrollment_timestamp"])

    models = []
    for e in enrollments["enrollments"]:
        if e["status"] == "QUARANTINED":
            expires = datetime.fromisoformat(e["quarantine_expires"])
            days_remaining = max(0, (expires - now).days)
            days_elapsed = (now - enrollment_ts).days
        else:
            days_remaining = None
            days_elapsed = (now - enrollment_ts).days

        models.append({
            "model": e["model"],
            "hypothesis_id": e["hypothesis_id"],
            "status": e["status"],
            "status_explanation": _status_explanation(e["status"], e["model"]),
            "enrollment_timestamp": e["enrollment_timestamp"],
            "quarantine_expires": e["quarantine_expires"],
            "days_remaining": days_remaining,
            "days_elapsed": days_elapsed,
            "paper_trading": e["paper_trading"],
            "odds_available": e["odds_available"],
            "calibration_ece_reference": e["calibration_ece_reference"],
        })

    return {
        "enrollment_timestamp": enrollments["enrollment_timestamp"],
        "quarantine_days": enrollments["quarantine_days"],
        "current_time": now.isoformat(),
        "models": models,
    }


def _status_explanation(status: str, model: str) -> str:
    if status == "QUARANTINED":
        return (
            "This model is in a 90-day quarantine — generating real predictions against "
            "live fixtures, but with no money at risk. The quarantine proves out-of-sample "
            "performance before any real-money deployment."
        )
    elif status == "TRACKED_NO_MARKET":
        return (
            f"The {model} model generates calibrated probabilities, but no betting market "
            f"currently offers over/under {model} lines at major bookmakers. It's tracked for "
            f"calibration purposes only — we can verify whether our probabilities are accurate, "
            f"but cannot paper-trade against real odds."
        )
    return status


@app.get("/api/predictions")
def get_predictions():
    """Live prediction feed with attestation status."""
    predictions = _load_jsonl(PREDICTIONS_FILE)
    commitments = {c["prediction_id"]: c for c in _load_jsonl(COMMITMENTS_FILE)}
    settlements_list = _load_jsonl(SETTLEMENTS_FILE)
    settlements = {s["prediction_id"]: s for s in settlements_list}

    feed = []
    for p in sorted(predictions, key=lambda x: x.get("kickoff_timestamp", 0), reverse=True):
        pred_id = p["prediction_id"]
        commitment = commitments.get(pred_id)
        settlement = settlements.get(pred_id)

        entry = {
            "prediction_id": pred_id,
            "fixture_id": p["fixture_id"],
            "model": p["model"],
            "home_team": p["home_team"],
            "away_team": p["away_team"],
            "kickoff_datetime": p.get("kickoff_datetime"),
            "kickoff_timestamp": p.get("kickoff_timestamp"),
            "prediction_timestamp": p["prediction_timestamp"],
            "p_over": p["p_over"],
            "p_under": p["p_under"],
            "line": p["line"],
            "market": p["market"],
            # Attestation
            "attested": commitment is not None,
            "commitment_hash": commitment["commitment_hash"] if commitment else None,
            "committed_at": commitment["committed_at"] if commitment else None,
            "committed_before_kickoff": commitment["pre_kickoff"] if commitment else False,
            "backfilled": commitment.get("backfilled", False) if commitment else False,
            # Settlement
            "settled": settlement is not None,
            "actual_over": settlement["actual_over"] if settlement else None,
            "actual_total": settlement["actual_total"] if settlement else None,
            "correct": (
                (p["p_over"] > 0.5 and settlement["actual_over"] == 1.0) or
                (p["p_over"] <= 0.5 and settlement["actual_over"] == 0.0)
            ) if settlement else None,
            "brier_contribution": settlement["brier_contribution"] if settlement else None,
        }
        feed.append(entry)

    return {
        "total_predictions": len(predictions),
        "total_attested": sum(1 for p in predictions if p["prediction_id"] in commitments),
        "total_unattested": sum(1 for p in predictions if p["prediction_id"] not in commitments),
        "total_settled": len(settlements),
        "predictions": feed,
    }


@app.get("/api/calibration")
def get_calibration():
    """Calibration dashboard — forward (live) vs backtest (historical), kept separate."""
    settlements = _load_jsonl(SETTLEMENTS_FILE)
    robustness = _load_json(ROBUSTNESS_FILE) or []

    # Forward calibration (live quarantine window)
    forward = _compute_calibration_metrics(settlements)

    # Backtest calibration (from robustness results — historical)
    backtest = _compute_backtest_summary(robustness)

    return {
        "forward": forward,
        "backtest": backtest,
        "reference_baselines": {
            "corners_ece": 0.064,
            "cards_ece": 0.058,
            "source": "Multi-league robustness check (25 leagues x 3 seasons)",
            "note": "These are the realistic multi-league figures, NOT the optimistic single-sample EPL numbers (0.018/0.027) that proved unrepresentative.",
        },
        "explanation": {
            "what_is_calibration": (
                "Calibration measures whether a model's stated probabilities match reality. "
                "If we say '70% chance of over 9.5 corners' across 100 matches, calibration "
                "asks: did ~70 of those matches actually go over? A well-calibrated model's "
                "probabilities are trustworthy at face value. An uncalibrated model might say "
                "'70%' but only be right 50% of the time — its numbers are directionally "
                "useful but can't be taken literally."
            ),
            "why_it_matters": (
                "Most prediction services report 'accuracy' (% of picks that won). But accuracy "
                "doesn't tell you whether the stated confidence was meaningful. A service that "
                "says 'strong pick' on everything is accurate ~50% of the time on binary markets "
                "and tells you nothing. Calibration is the harder, more honest standard: it asks "
                "whether the model's confidence levels actually correspond to real-world frequencies."
            ),
            "ece_explained": (
                "ECE (Expected Calibration Error) is the average gap between predicted probability "
                "and actual outcome frequency, across probability buckets. Lower is better. "
                "ECE = 0 means perfect calibration. ECE = 0.05 means the model's probabilities "
                "are off by about 5 percentage points on average."
            ),
            "brier_explained": (
                "Brier Score is the mean squared error of probability predictions — it rewards "
                "both calibration and sharpness (confident correct predictions). Range 0-1, lower "
                "is better. A naive 50/50 predictor scores 0.25."
            ),
            "forward_vs_backtest": (
                "The forward (live) calibration is computed on predictions made BEFORE kickoff "
                "during the current 90-day quarantine window. The backtest calibration is from "
                "historical data where the model was fitted and tested in a walk-forward manner. "
                "If forward calibration is materially worse than backtest, it suggests a data "
                "leakage or distribution shift problem. They are shown separately because "
                "conflating them would hide exactly the divergence we most need to detect."
            ),
        },
    }


MIN_CALIBRATION_SAMPLE = 200  # Minimum settled predictions before reporting ECE/Brier


def _compute_calibration_metrics(settlements: list[dict]) -> dict:
    """Compute forward calibration from live settlements.

    Applies a minimum-sample gate: below MIN_CALIBRATION_SAMPLE (~200) settled
    predictions per model, no ECE or Brier figure is shown. An ECE on 20 samples
    is noise, and publishing it — high or low — would be a premature claim.
    """
    corners = [s for s in settlements if "corners" in s.get("model", "")]
    cards = [s for s in settlements if "cards" in s.get("model", "")]

    def _metrics(data: list[dict]) -> dict:
        n = len(data)

        # ── MINIMUM-SAMPLE GATE ──
        # Below the threshold, don't publish calibration figures at all.
        # The number would swing wildly and create false impressions.
        if n < MIN_CALIBRATION_SAMPLE:
            return {
                "n": n,
                "brier": None,
                "ece": None,
                "brier_ci": None,
                "ece_ci": None,
                "reliability_curve": [],
                "sufficient_sample": False,
                "min_sample_required": MIN_CALIBRATION_SAMPLE,
                "note": (
                    f"Insufficient settled predictions to report calibration — "
                    f"{n} settled, need ~{MIN_CALIBRATION_SAMPLE} for a meaningful estimate."
                ),
            }

        preds = [d["p_over"] for d in data]
        actuals = [d["actual_over"] for d in data]

        # Brier score
        brier_contributions = [(p - a) ** 2 for p, a in zip(preds, actuals)]
        brier = sum(brier_contributions) / n

        # Brier 95% CI via bootstrap-style normal approximation
        # SE of mean = std / sqrt(n)
        brier_var = sum((b - brier) ** 2 for b in brier_contributions) / (n - 1)
        brier_se = math.sqrt(brier_var / n)
        brier_ci = (round(brier - 1.96 * brier_se, 6), round(brier + 1.96 * brier_se, 6))

        # Reliability curve (5 bins)
        bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
        curve = []
        total_gap = 0
        total_counted = 0
        for lo, hi in bins:
            bucket_p = [p for p in preds if lo <= p < hi]
            bucket_a = [a for p, a in zip(preds, actuals) if lo <= p < hi]
            if len(bucket_p) >= 3:
                mean_pred = sum(bucket_p) / len(bucket_p)
                mean_actual = sum(bucket_a) / len(bucket_a)
                gap = abs(mean_pred - mean_actual)
                total_gap += gap * len(bucket_p)
                total_counted += len(bucket_p)
                curve.append({
                    "bin_range": f"{lo:.1f}-{hi:.1f}",
                    "mean_predicted": round(mean_pred, 4),
                    "mean_actual": round(mean_actual, 4),
                    "count": len(bucket_p),
                    "gap": round(gap, 4),
                })
            else:
                curve.append({
                    "bin_range": f"{lo:.1f}-{hi:.1f}",
                    "mean_predicted": None,
                    "mean_actual": None,
                    "count": len(bucket_p),
                    "gap": None,
                })

        ece = total_gap / total_counted if total_counted > 0 else None

        # ECE confidence interval (bootstrap approximation from per-bin gaps)
        # Use the weighted variance of per-bin gaps as an approximation
        ece_ci = None
        if ece is not None and total_counted > 0:
            # Approximate SE of ECE via delta method on bin gaps
            bin_gaps = []
            bin_counts = []
            for b in curve:
                if b["gap"] is not None and b["count"] >= 3:
                    bin_gaps.append(b["gap"])
                    bin_counts.append(b["count"])
            if len(bin_gaps) >= 2:
                weighted_var = sum(
                    c * (g - ece) ** 2 for g, c in zip(bin_gaps, bin_counts)
                ) / total_counted
                ece_se = math.sqrt(weighted_var / total_counted)
                ece_ci = (round(max(0, ece - 1.96 * ece_se), 6), round(ece + 1.96 * ece_se, 6))

        return {
            "n": n,
            "brier": round(brier, 6),
            "ece": round(ece, 6) if ece is not None else None,
            "brier_ci": brier_ci,
            "ece_ci": ece_ci,
            "reliability_curve": curve,
            "sufficient_sample": True,
            "min_sample_required": MIN_CALIBRATION_SAMPLE,
            "note": f"Based on {n} settled predictions.",
        }

    return {
        "corners": _metrics(corners),
        "cards": _metrics(cards),
        "window": "2026-08-27 to present (live quarantine, out-of-sample)",
        "min_sample_required": MIN_CALIBRATION_SAMPLE,
    }


def _compute_backtest_summary(robustness: list[dict]) -> dict:
    """Summarize backtest calibration from robustness results."""
    corners_eces = [r["corners_ece"] for r in robustness if r.get("corners_ece") is not None]
    cards_eces = [r["cards_ece"] for r in robustness if r.get("cards_ece") is not None]

    return {
        "corners": {
            "mean_ece": round(sum(corners_eces) / len(corners_eces), 4) if corners_eces else None,
            "median_ece": round(sorted(corners_eces)[len(corners_eces) // 2], 4) if corners_eces else None,
            "n_league_seasons": len(corners_eces),
        },
        "cards": {
            "mean_ece": round(sum(cards_eces) / len(cards_eces), 4) if cards_eces else None,
            "median_ece": round(sorted(cards_eces)[len(cards_eces) // 2], 4) if cards_eces else None,
            "n_league_seasons": len(cards_eces),
        },
        "window": "Historical walk-forward backtest (25 leagues x 3 seasons)",
        "note": "Backtest figures reflect in-sample performance with walk-forward splits. Forward (live) results above are the true out-of-sample test.",
    }


@app.get("/api/robustness")
def get_robustness_results():
    """Full per-league robustness results — all 75 league-seasons, warts and all."""
    robustness = _load_json(ROBUSTNESS_FILE) or []

    corners_positive = sum(1 for r in robustness if r["corners_vs_naive_pct"] > 0)
    cards_positive = sum(1 for r in robustness if r["cards_vs_naive_pct"] > 0)

    return {
        "total_league_seasons": len(robustness),
        "aggregate": {
            "corners": {
                "positive_count": corners_positive,
                "total_count": len(robustness),
                "summary": f"{corners_positive}/{len(robustness)} league-seasons beat the naive baseline",
            },
            "cards": {
                "positive_count": cards_positive,
                "total_count": len(robustness),
                "summary": f"{cards_positive}/{len(robustness)} league-seasons beat the naive baseline",
            },
            "note": "These counts are stronger evidence than a mean, because a mean can be dominated by one outlier. Here you can see exactly which leagues failed.",
        },
        "results": robustness,
    }


@app.get("/api/failures")
def get_failure_ledger():
    """Permanent, append-only public record of what we tried and what didn't work."""
    ledger = _load_json(FAILURE_LEDGER_FILE)
    if not ledger:
        return {"entries": [], "note": "Failure ledger not yet initialized."}
    return ledger


# ═══════════════════════════════════════════════════════════════
# FRONTEND (single-page HTML served inline)
# ═══════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    """Serve the single-page public transparency dashboard."""
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>Frontend not built yet</h1>"
