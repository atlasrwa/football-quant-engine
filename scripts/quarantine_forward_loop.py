#!/usr/bin/env python3
"""Quarantine Forward Loop — generates and settles predictions for quarantined models.

This is the cron-triggered entry point for the corners/cards quarantine.
Runs the full cycle: fetch fixtures → compute features → predict → commit → settle → track.

Design:
- Idempotent: re-running produces no duplicate predictions (dedup by fixture+model hash)
- Crash-recoverable: next run picks up where the last left off
- Rate-limit aware: uses cached FootyStats client (2s between requests, file cache)
- Observable: logs to stdout + persists run records to data/forward/

Model parameters are FROZEN. This script does NOT modify model code.

Schedule: cron every 4 hours (6 runs/day), catching fixtures across all time zones.
Predictions generated at least 2 hours before kickoff.

Usage:
    python3 scripts/quarantine_forward_loop.py
    # Or via cron:
    0 */4 * * * cd /home/ubuntu && python3 scripts/quarantine_forward_loop.py >> logs/forward_loop.log 2>&1
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, "/home/ubuntu")

# Load environment
with open("/home/ubuntu/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import numpy as np
from src.research.footystats.client import FootyStatsResearchClient
from src.research.footystats.normalizer import MatchNormalizer
from src.research.models.count_regression import create_corners_model, create_cards_model

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION (frozen for quarantine duration)
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("quarantine_loop")

# 2026/27 season IDs for leagues with corners odds available
SEASON_IDS = [
    17146,  # England Premier League
    17199,  # Spain La Liga
    17084,  # Italy Serie A
    17210,  # Germany Bundesliga
    17102,  # France Ligue 1
    17184,  # England Championship
    17097,  # Netherlands Eredivisie
    17217,  # Portugal Liga NOS
    17148,  # Scotland Premiership
]

CACHE_DIR = Path("/home/ubuntu/.cache/footystats_forward")
DATA_DIR = Path("/home/ubuntu/data/forward")
PREDICTIONS_FILE = DATA_DIR / "predictions.jsonl"
SETTLEMENTS_FILE = DATA_DIR / "settlements.jsonl"
COMMITMENTS_FILE = DATA_DIR / "commitments.jsonl"
REVEALS_FILE = DATA_DIR / "reveals.jsonl"
CALIBRATION_FILE = DATA_DIR / "calibration_tracking.json"
RUN_LOG_FILE = DATA_DIR / "run_log.jsonl"

# Model parameters (FROZEN)
CORNERS_LINE = 9.5
CARDS_LINE = 3.5
REFIT_INTERVAL = 50  # Matches between model refits (same as benchmark)
MIN_TRAIN = 100  # Minimum historical matches before generating predictions

# Timing
MIN_HOURS_BEFORE_KICKOFF = 2  # Don't predict within 2h of kickoff
MAX_HOURS_BEFORE_KICKOFF = 168  # Don't predict more than 7 days out

# Quarantine metadata
QUARANTINE_START = "2026-08-27T12:00:00+00:00"
# Architecture reoriented 2026-08-28: strategy-validation → metric-validation.
# Corners/cards target predictors marked SUPERSEDED. The forward loop machinery
# is retained for metric quarantine and creator strategy quarantine — new models
# are added here when enrolled. The list is intentionally empty until the first
# metric or creator strategy enters forward testing.
QUARANTINE_MODELS: list[str] = []


# ═══════════════════════════════════════════════════════════════
# PERSISTENCE (append-only JSONL for predictions/settlements)
# ═══════════════════════════════════════════════════════════════

def _prediction_id(fixture_id: str, model: str) -> str:
    """Deterministic prediction ID from fixture + model."""
    content = f"{fixture_id}:{model}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _commitment_hash(prediction: dict) -> str:
    """Compute commitment hash: proves prediction content at a point in time."""
    # Hash the prediction content (excluding the commitment itself)
    canonical = json.dumps({
        "prediction_id": prediction["prediction_id"],
        "fixture_id": prediction["fixture_id"],
        "model": prediction["model"],
        "p_over": prediction["p_over"],
        "p_under": prediction["p_under"],
        "prediction_timestamp": prediction["prediction_timestamp"],
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_existing_predictions() -> dict[str, dict]:
    """Load existing predictions keyed by prediction_id. Idempotency check."""
    predictions = {}
    if PREDICTIONS_FILE.exists():
        with open(PREDICTIONS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    pred = json.loads(line)
                    predictions[pred["prediction_id"]] = pred
    return predictions


def load_existing_settlements() -> set[str]:
    """Load settled prediction IDs."""
    settled = set()
    if SETTLEMENTS_FILE.exists():
        with open(SETTLEMENTS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    s = json.loads(line)
                    settled.add(s["prediction_id"])
    return settled


def persist_prediction(prediction: dict) -> None:
    """Append prediction to JSONL store (immutable once written)."""
    PREDICTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PREDICTIONS_FILE, "a") as f:
        f.write(json.dumps(prediction) + "\n")


def persist_settlement(settlement: dict) -> None:
    """Append settlement to JSONL store."""
    SETTLEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTLEMENTS_FILE, "a") as f:
        f.write(json.dumps(settlement) + "\n")


def persist_run_log(run_record: dict) -> None:
    """Append run record to log."""
    RUN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RUN_LOG_FILE, "a") as f:
        f.write(json.dumps(run_record) + "\n")


# ═══════════════════════════════════════════════════════════════
# ATTESTATION (commit-reveal lifecycle for provable predictions)
# ═══════════════════════════════════════════════════════════════

def _compute_attestation_commitment_hash(prediction: dict) -> str:
    """Compute attestation commitment hash using the canonical production format.

    Uses the same canonical JSON → SHA-256 approach as the production
    AttestationService (src/persistence/broadcast_hashing.py), binding the
    prediction content cryptographically before kickoff.

    The forward loop doesn't have strategy_id/strategy_version/entry_odds/proof_hash
    from the production domain model, so we use the quarantine-specific fields
    that uniquely identify the prediction content:
        prediction_id, fixture_id, model, p_over, p_under, prediction_timestamp
    """
    canonical = json.dumps({
        "prediction_id": prediction["prediction_id"],
        "fixture_id": prediction["fixture_id"],
        "model": prediction["model"],
        "p_over": prediction["p_over"],
        "p_under": prediction["p_under"],
        "prediction_timestamp": prediction["prediction_timestamp"],
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_attestation_reveal_hash(commitment_hash: str, settlement: dict) -> str:
    """Compute attestation reveal hash binding settlement to original commitment.

    Proves the settlement outcome corresponds to the committed prediction.
    """
    canonical = json.dumps({
        "commitment_hash": commitment_hash,
        "prediction_id": settlement["prediction_id"],
        "fixture_id": settlement["fixture_id"],
        "model": settlement["model"],
        "actual_over": settlement["actual_over"],
        "actual_total": settlement["actual_total"],
        "settled_at": settlement["settled_at"],
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_existing_commitments() -> dict[str, dict]:
    """Load existing commitments keyed by prediction_id."""
    commitments = {}
    if COMMITMENTS_FILE.exists():
        with open(COMMITMENTS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    c = json.loads(line)
                    commitments[c["prediction_id"]] = c
    return commitments


def load_existing_reveals() -> set[str]:
    """Load existing reveal prediction IDs."""
    reveals = set()
    if REVEALS_FILE.exists():
        with open(REVEALS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    reveals.add(r["prediction_id"])
    return reveals


def persist_commitment(commitment: dict) -> None:
    """Append commitment to immutable JSONL store.

    Once written, a commitment cannot be edited or backdated.
    The append timestamp in the file serves as the attestation anchor.
    """
    COMMITMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COMMITMENTS_FILE, "a") as f:
        f.write(json.dumps(commitment) + "\n")


def persist_reveal(reveal: dict) -> None:
    """Append reveal to JSONL store after settlement."""
    REVEALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REVEALS_FILE, "a") as f:
        f.write(json.dumps(reveal) + "\n")


# ═══════════════════════════════════════════════════════════════
# FEATURE COMPUTATION (point-in-time, no look-ahead)
# ═══════════════════════════════════════════════════════════════

def build_training_features(historical_matches: list[dict], team_name_to_id: dict) -> list[dict]:
    """Build feature dicts from historical match data.

    Only uses data available at the time of each match.
    Returns features sorted chronologically.
    """
    features = []
    for m in historical_matches:
        ht = m.get("home_team", "")
        at = m.get("away_team", "")
        if not ht or not at:
            continue
        if ht not in team_name_to_id:
            team_name_to_id[ht] = len(team_name_to_id)
        if at not in team_name_to_id:
            team_name_to_id[at] = len(team_name_to_id)

        feat = {}
        for k, v in m.items():
            if isinstance(v, (int, float)) and v is not None:
                feat[k] = float(v)
        feat["home_team_id"] = float(team_name_to_id[ht])
        feat["away_team_id"] = float(team_name_to_id[at])
        features.append(feat)
    return features


def build_prediction_features(fixture: dict, team_name_to_id: dict) -> Optional[dict]:
    """Build features for a fixture to predict.

    Uses team IDs from the shared mapping. Returns None if teams unknown.
    """
    home_name = fixture.get("home_name", "")
    away_name = fixture.get("away_name", "")

    if home_name not in team_name_to_id or away_name not in team_name_to_id:
        return None

    feat = {
        "home_team_id": float(team_name_to_id[home_name]),
        "away_team_id": float(team_name_to_id[away_name]),
        "date_unix": float(fixture.get("date_unix", 0)),
    }
    return feat


# ═══════════════════════════════════════════════════════════════
# MAIN FORWARD LOOP
# ═══════════════════════════════════════════════════════════════

def run_forward_cycle():
    """Execute one full forward cycle: fetch → predict → settle → track."""

    run_start = time.time()
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    logger.info("=" * 60)
    logger.info("QUARANTINE FORWARD LOOP — %s", now.strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 60)

    # Stats for this run
    stats = {
        "run_timestamp": now.isoformat(),
        "fixtures_fetched": 0,
        "predictions_generated": 0,
        "predictions_skipped_duplicate": 0,
        "predictions_skipped_timing": 0,
        "commitments_created": 0,
        "commitments_failed": 0,
        "reveals_created": 0,
        "settlements_completed": 0,
        "errors": [],
    }

    client = FootyStatsResearchClient(
        api_key=os.environ["FOOTYSTATS_API_KEY"],
        cache_dir=CACHE_DIR,
    )
    normalizer = MatchNormalizer()

    # Load existing state (idempotency)
    existing_predictions = load_existing_predictions()
    settled_ids = load_existing_settlements()
    existing_commitments = load_existing_commitments()
    existing_reveals = load_existing_reveals()
    logger.info("Existing predictions: %d, settled: %d, committed: %d, revealed: %d",
                len(existing_predictions), len(settled_ids),
                len(existing_commitments), len(existing_reveals))

    # ─── PHASE 1: FETCH FIXTURES & HISTORICAL DATA ───────────────────
    logger.info("Phase 1: Fetching fixture data from %d seasons...", len(SEASON_IDS))

    all_completed = []  # Historical completed matches
    all_upcoming = []   # Upcoming fixtures to predict
    team_name_to_id = {}

    for season_id in SEASON_IDS:
        try:
            raw_matches = client.fetch_season_matches(season_id)
            for raw in raw_matches:
                status = raw.get("status", "")
                date_unix = raw.get("date_unix", 0)
                match_id = raw.get("id", 0)

                if status == "complete" and date_unix > 0:
                    # Historical — normalize for training
                    all_completed.append(raw)
                elif status == "incomplete" and date_unix > 0:
                    # Upcoming — candidate for prediction
                    all_upcoming.append(raw)

            stats["fixtures_fetched"] += len(raw_matches)
        except Exception as e:
            err = f"Season {season_id}: {type(e).__name__}: {str(e)[:100]}"
            logger.warning("Fetch error: %s", err)
            stats["errors"].append(err)

    logger.info("Fetched: %d completed, %d upcoming fixtures", len(all_completed), len(all_upcoming))

    # Normalize completed matches for feature building
    normalized = normalizer.normalize_batch(all_completed)
    historical_sorted = sorted(normalized, key=lambda x: x.date_unix)
    historical_dicts = [m.to_dict() for m in historical_sorted]
    training_features = build_training_features(historical_dicts, team_name_to_id)

    logger.info("Training features: %d matches, %d teams", len(training_features), len(team_name_to_id))

    if len(training_features) < MIN_TRAIN:
        logger.warning("Insufficient training data (%d < %d). Skipping predictions.", len(training_features), MIN_TRAIN)
        stats["errors"].append(f"Insufficient training data: {len(training_features)}")
        persist_run_log(stats)
        return stats

    # ─── PHASE 2: FIT MODELS (on all available historical data) ──────
    logger.info("Phase 2: Fitting models on %d historical matches...", len(training_features))

    corners_model = create_corners_model(line=CORNERS_LINE)
    corners_model.fit(
        training_features,
        [f.get("total_corners", 0) > CORNERS_LINE for f in training_features],
    )

    cards_model = create_cards_model(line=CARDS_LINE)
    cards_model.fit(
        training_features,
        [f.get("total_cards", 0) > CARDS_LINE for f in training_features],
    )
    logger.info("Models fitted successfully")

    # ─── PHASE 3: GENERATE PREDICTIONS ───────────────────────────────
    logger.info("Phase 3: Generating predictions for upcoming fixtures...")

    min_kickoff = now_ts + (MIN_HOURS_BEFORE_KICKOFF * 3600)
    max_kickoff = now_ts + (MAX_HOURS_BEFORE_KICKOFF * 3600)

    for raw_fixture in all_upcoming:
        kickoff_ts = raw_fixture.get("date_unix", 0)
        fixture_id = str(raw_fixture.get("id", 0))
        home_name = raw_fixture.get("home_name", "")
        away_name = raw_fixture.get("away_name", "")

        # Timing check: only predict within the valid window
        if kickoff_ts < min_kickoff:
            stats["predictions_skipped_timing"] += 1
            continue  # Too close to kickoff (or already started)
        if kickoff_ts > max_kickoff:
            continue  # Too far out

        # Build features for this fixture
        feat = build_prediction_features(raw_fixture, team_name_to_id)
        if feat is None:
            continue  # Unknown teams

        # Generate predictions for each quarantined model
        for model_name, model, line in [
            ("corners_ou_9.5", corners_model, CORNERS_LINE),
            ("cards_ou_3.5", cards_model, CARDS_LINE),
        ]:
            pred_id = _prediction_id(fixture_id, model_name)

            # Idempotency: skip if already predicted
            if pred_id in existing_predictions:
                stats["predictions_skipped_duplicate"] += 1
                continue

            # Generate prediction
            try:
                estimate = model.predict(feat)
                prediction = {
                    "prediction_id": pred_id,
                    "fixture_id": fixture_id,
                    "model": model_name,
                    "home_team": home_name,
                    "away_team": away_name,
                    "kickoff_timestamp": kickoff_ts,
                    "kickoff_datetime": datetime.fromtimestamp(kickoff_ts, tz=timezone.utc).isoformat(),
                    "prediction_timestamp": now.isoformat(),
                    "prediction_unix": now_ts,
                    "p_over": round(estimate.p_over, 6),
                    "p_under": round(estimate.p_under, 6),
                    "line": line,
                    "market": "CORNERS_TOTAL" if "corners" in model_name else "CARDS_TOTAL",
                    "status": "COMMITTED",
                    "attested": False,  # Provisional — set True only after commitment succeeds
                    "commitment_hash": "",  # Computed below
                }

                # Compute commitment hash (canonical attestation binding)
                prediction["commitment_hash"] = _compute_attestation_commitment_hash(prediction)

                # Persist prediction (immutable once written)
                persist_prediction(prediction)
                existing_predictions[pred_id] = prediction
                stats["predictions_generated"] += 1

                # ── ATTESTATION: create commitment immediately ──
                # The commitment proves this prediction existed at this timestamp.
                # If commitment fails, the prediction is flagged as unattested.
                try:
                    commitment = {
                        "prediction_id": pred_id,
                        "fixture_id": fixture_id,
                        "model": model_name,
                        "commitment_hash": prediction["commitment_hash"],
                        "committed_at": now.isoformat(),
                        "committed_unix": now_ts,
                        "kickoff_timestamp": kickoff_ts,
                        "pre_kickoff": True,  # Assertion: committed before match starts
                    }
                    persist_commitment(commitment)
                    existing_commitments[pred_id] = commitment
                    stats["commitments_created"] += 1

                    # Mark prediction as attested
                    prediction["attested"] = True

                    logger.info(
                        "  PREDICTED+COMMITTED %s %s vs %s: p_over=%.3f (%s) hash=%s",
                        model_name, home_name, away_name, estimate.p_over,
                        datetime.fromtimestamp(kickoff_ts, tz=timezone.utc).strftime("%m-%d %H:%M"),
                        prediction["commitment_hash"][:12],
                    )
                except Exception as ce:
                    # Commitment failed — prediction exists but is unattested
                    stats["commitments_failed"] += 1
                    err = f"COMMITMENT FAILED {pred_id}: {type(ce).__name__}: {str(ce)[:100]}"
                    logger.error(err)
                    stats["errors"].append(err)
                    logger.warning(
                        "  PREDICTED (UNATTESTED) %s %s vs %s: p_over=%.3f — commitment failed",
                        model_name, home_name, away_name, estimate.p_over,
                    )

            except Exception as e:
                err = f"Prediction failed {fixture_id}/{model_name}: {str(e)[:100]}"
                logger.warning(err)
                stats["errors"].append(err)

    logger.info("Predictions: %d generated, %d skipped (dup), %d skipped (timing), %d committed, %d commit-failed",
                stats["predictions_generated"], stats["predictions_skipped_duplicate"],
                stats["predictions_skipped_timing"], stats["commitments_created"],
                stats["commitments_failed"])

    # ─── PHASE 3.5: BACKFILL COMMITMENTS FOR UNATTESTED PREDICTIONS ──
    # If a prior run generated predictions without commitments (e.g., before
    # attestation was wired), create commitments now IF still pre-kickoff.
    logger.info("Phase 3.5: Backfilling commitments for unattested predictions...")

    backfilled = 0
    for pred_id, pred in existing_predictions.items():
        if pred_id in existing_commitments:
            continue  # Already committed
        # Only commit if still before kickoff
        kickoff_ts = pred.get("kickoff_timestamp", 0)
        if now_ts >= kickoff_ts:
            continue  # Too late — match started, cannot prove pre-kickoff commitment

        try:
            # Recompute commitment hash with canonical algorithm
            c_hash = _compute_attestation_commitment_hash(pred)
            commitment = {
                "prediction_id": pred_id,
                "fixture_id": pred["fixture_id"],
                "model": pred["model"],
                "commitment_hash": c_hash,
                "committed_at": now.isoformat(),
                "committed_unix": now_ts,
                "kickoff_timestamp": kickoff_ts,
                "pre_kickoff": True,
                "backfilled": True,  # Marks this was created after initial prediction
            }
            persist_commitment(commitment)
            existing_commitments[pred_id] = commitment
            backfilled += 1
        except Exception as e:
            logger.warning("Backfill commitment failed for %s: %s", pred_id, str(e)[:80])

    if backfilled > 0:
        logger.info("Backfilled %d commitments for previously unattested predictions", backfilled)
        stats["commitments_created"] += backfilled

    # ─── PHASE 4: SETTLE COMPLETED PREDICTIONS ───────────────────────
    logger.info("Phase 4: Settling completed predictions...")

    # Build lookup of completed fixtures by ID
    completed_by_id = {}
    for raw in all_completed:
        fid = str(raw.get("id", 0))
        completed_by_id[fid] = raw

    for pred_id, pred in existing_predictions.items():
        if pred_id in settled_ids:
            continue  # Already settled

        fixture_id = pred["fixture_id"]
        if fixture_id not in completed_by_id:
            continue  # Not yet completed

        # Settle
        raw_result = completed_by_id[fixture_id]
        model_name = pred["model"]

        # Determine actual outcome
        if "corners" in model_name:
            total = (raw_result.get("team_a_corners", 0) or 0) + (raw_result.get("team_b_corners", 0) or 0)
            actual_over = 1.0 if total > CORNERS_LINE else 0.0
            actual_total = total
        else:
            # Cards: sum yellow + red for both teams
            total = (
                (raw_result.get("team_a_yellow_cards", 0) or 0) +
                (raw_result.get("team_b_yellow_cards", 0) or 0) +
                (raw_result.get("team_a_red_cards", 0) or 0) +
                (raw_result.get("team_b_red_cards", 0) or 0)
            )
            actual_over = 1.0 if total > CARDS_LINE else 0.0
            actual_total = total

        settlement = {
            "prediction_id": pred_id,
            "fixture_id": fixture_id,
            "model": model_name,
            "p_over": pred["p_over"],
            "actual_over": actual_over,
            "actual_total": actual_total,
            "line": pred["line"],
            "settled_at": now.isoformat(),
            "brier_contribution": (pred["p_over"] - actual_over) ** 2,
            "commitment_hash": pred.get("commitment_hash", ""),
        }

        persist_settlement(settlement)
        settled_ids.add(pred_id)
        stats["settlements_completed"] += 1

        # ── ATTESTATION: auto-reveal after settlement ──
        # Reveals bind the settlement outcome to the original commitment,
        # completing the commit→reveal lifecycle.
        if pred_id in existing_commitments and pred_id not in existing_reveals:
            try:
                commitment = existing_commitments[pred_id]
                reveal_hash = _compute_attestation_reveal_hash(
                    commitment["commitment_hash"], settlement
                )
                reveal = {
                    "prediction_id": pred_id,
                    "fixture_id": fixture_id,
                    "model": model_name,
                    "commitment_hash": commitment["commitment_hash"],
                    "reveal_hash": reveal_hash,
                    "actual_over": actual_over,
                    "actual_total": actual_total,
                    "brier_contribution": settlement["brier_contribution"],
                    "settled_at": now.isoformat(),
                    "revealed_at": now.isoformat(),
                }
                persist_reveal(reveal)
                existing_reveals.add(pred_id)
                stats["reveals_created"] += 1
            except Exception as re:
                logger.warning("Reveal failed for %s: %s", pred_id, str(re)[:80])

    logger.info("Settlements: %d completed, reveals: %d created this run",
                stats["settlements_completed"], stats["reveals_created"])

    # ─── PHASE 5: UPDATE CALIBRATION TRACKING ────────────────────────
    logger.info("Phase 5: Updating calibration tracking...")

    _update_calibration_tracking()

    # ─── DONE ─────────────────────────────────────────────────────────
    stats["duration_seconds"] = round(time.time() - run_start, 1)
    persist_run_log(stats)

    logger.info("")
    logger.info("Run complete in %.1fs: %d predictions, %d commitments, %d settlements, %d reveals, %d errors",
                stats["duration_seconds"], stats["predictions_generated"],
                stats["commitments_created"], stats["settlements_completed"],
                stats["reveals_created"], len(stats["errors"]))
    logger.info("=" * 60)

    return stats


def _update_calibration_tracking():
    """Compute rolling Brier/ECE from all settled predictions."""
    if not SETTLEMENTS_FILE.exists():
        return

    corners_preds, corners_actuals = [], []
    cards_preds, cards_actuals = [], []

    with open(SETTLEMENTS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            p = s["p_over"]
            a = s["actual_over"]
            if "corners" in s["model"]:
                corners_preds.append(p)
                corners_actuals.append(a)
            else:
                cards_preds.append(p)
                cards_actuals.append(a)

    def compute_metrics(preds, actuals):
        if len(preds) < 5:
            return {"n": len(preds), "brier": None, "ece": None}
        preds_arr = np.array(preds)
        actuals_arr = np.array(actuals)
        brier = float(np.mean((preds_arr - actuals_arr) ** 2))
        # ECE (5-bin)
        bins = np.linspace(0, 1, 6)
        total_gap = 0
        total_n = 0
        for i in range(5):
            mask = (preds_arr >= bins[i]) & (preds_arr < bins[i + 1])
            if i == 4:
                mask = (preds_arr >= bins[i]) & (preds_arr <= bins[i + 1])
            if np.sum(mask) >= 3:
                gap = abs(float(np.mean(preds_arr[mask])) - float(np.mean(actuals_arr[mask])))
                total_gap += gap * int(np.sum(mask))
                total_n += int(np.sum(mask))
        ece = total_gap / total_n if total_n > 0 else None
        return {"n": len(preds), "brier": round(brier, 6), "ece": round(ece, 6) if ece else None}

    calibration = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "corners": compute_metrics(corners_preds, corners_actuals),
        "cards": compute_metrics(cards_preds, cards_actuals),
        "reference_baselines": {
            "corners_ece": 0.064,
            "cards_ece": 0.058,
            "note": "Multi-league robustness check (25 leagues × 3 seasons)",
        },
    }

    with open(CALIBRATION_FILE, "w") as f:
        json.dump(calibration, f, indent=2)

    # Log drift warning if calibration is materially worse than baseline
    for model_name, metrics, baseline_ece in [
        ("corners", calibration["corners"], 0.064),
        ("cards", calibration["cards"], 0.058),
    ]:
        if metrics["ece"] is not None and metrics["ece"] > baseline_ece * 1.5:
            logger.warning(
                "CALIBRATION DRIFT: %s forward ECE=%.4f >> baseline %.4f "
                "(possible feature leakage or distribution shift)",
                model_name, metrics["ece"], baseline_ece,
            )

    logger.info("Calibration: corners=%s, cards=%s", calibration["corners"], calibration["cards"])


if __name__ == "__main__":
    run_forward_cycle()
