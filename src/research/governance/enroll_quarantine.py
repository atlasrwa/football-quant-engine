"""Quarantine enrollment for corners and cards models.

Executed once to formally enroll both models in the quarantine pipeline.
Creates immutable records with start timestamps.

Run: python3 -m src.research.governance.enroll_quarantine
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/ubuntu")

from src.engine.analysis.fdr import QuarantineTracker
from src.research.governance.classifier import GovernanceDecision, GovernanceState
from src.research.governance.quarantine_adapter import QuarantineAdapter


# ═══════════════════════════════════════════════════════════════
# ENROLLMENT DEFINITIONS
# ═══════════════════════════════════════════════════════════════

# Immutable enrollment timestamp — this is the quarantine start.
# UTC, set at first execution and never modified.
ENROLLMENT_TIMESTAMP = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

CORNERS_STRATEGY = {
    "hypothesis_id": "corners_ou_9.5_count_regression_v1",
    "model_class": "CountRegressionModel",
    "target": "total_corners",
    "line": 9.5,
    "market": "CORNERS_TOTAL",
    "status": "QUARANTINED",
    "paper_trading": True,
    "odds_available": True,  # FootyStats carries corners O/U odds
    "calibration_ece": 0.064,  # Multi-league reference (not single-sample)
    "calibration_brier_vs_naive": "+6.8%",  # Mean across 25 leagues × 3 seasons
    "robustness": {
        "leagues_tested": 25,
        "seasons_per_league": 3,
        "league_seasons_positive": "68/75 (91%)",
        "meta_analysis_z": 15.33,
        "meta_analysis_p": "<1e-50",
        "fdr_pass": True,
    },
    "refit_interval": 50,
    "shrinkage": "empirical_bayes_team_effects",
}

CARDS_STRATEGY = {
    "hypothesis_id": "cards_ou_3.5_count_regression_v1",
    "model_class": "CountRegressionModel",
    "target": "total_cards",
    "line": 3.5,
    "market": "CARDS_TOTAL",
    "status": "TRACKED_NO_MARKET",  # No odds source — calibration tracking only
    "paper_trading": False,  # No EV, no CLV, no simulated positions
    "odds_available": False,
    "calibration_ece": 0.058,  # Multi-league reference
    "calibration_brier_vs_naive": "+6.1%",
    "robustness": {
        "leagues_tested": 25,
        "seasons_per_league": 3,
        "league_seasons_positive": "72/75 (96%)",
        "meta_analysis_z": 15.12,
        "meta_analysis_p": "<1e-50",
        "fdr_pass": True,
    },
    "refit_interval": 50,
    "shrinkage": "empirical_bayes_team_effects",
}


def _compute_candidate_hash(strategy: dict) -> str:
    """Deterministic hash of strategy configuration for identity."""
    canonical = json.dumps(
        {k: v for k, v in strategy.items() if k != "robustness"},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def enroll():
    """Enroll corners and cards models in quarantine."""

    tracker = QuarantineTracker()
    adapter = QuarantineAdapter(tracker=tracker)

    enrollments = []

    for name, strategy in [("corners", CORNERS_STRATEGY), ("cards", CARDS_STRATEGY)]:
        candidate_hash = _compute_candidate_hash(strategy)

        # Create governance decision (QUARANTINE_ELIGIBLE — FDR already passed)
        decision = GovernanceDecision(
            hypothesis_id=strategy["hypothesis_id"],
            candidate_hash=candidate_hash,
            previous_state=GovernanceState.FDR_VALIDATED,
            new_state=GovernanceState.QUARANTINE_ELIGIBLE,
            reasons=(
                "FDR correction passed (meta-analysis p < 1e-50)",
                f"Robustness: {strategy['robustness']['league_seasons_positive']} league-seasons positive",
                f"Mean vs naive: {strategy['calibration_brier_vs_naive']}",
            ),
            evidence_summary=strategy["robustness"],
        )

        # Submit to quarantine
        submission = adapter.submit_for_quarantine(
            decision=decision,
            entry_date=ENROLLMENT_TIMESTAMP,
        )

        enrollment_record = {
            "model": name,
            "hypothesis_id": strategy["hypothesis_id"],
            "candidate_hash": candidate_hash,
            "strategy_name": submission.strategy_name,
            "status": strategy["status"],
            "enrollment_timestamp": ENROLLMENT_TIMESTAMP.isoformat(),
            "quarantine_expires": "2026-11-25T12:00:00+00:00" if strategy["paper_trading"] else "N/A (calibration-only)",
            "paper_trading": strategy["paper_trading"],
            "odds_available": strategy["odds_available"],
            "calibration_ece_reference": strategy["calibration_ece"],
            "submitted": submission.submitted,
        }
        enrollments.append(enrollment_record)

        status_label = strategy["status"]
        print(f"  [{name.upper()}] Enrolled as {status_label}")
        print(f"    Strategy: {submission.strategy_name}")
        print(f"    Hypothesis: {strategy['hypothesis_id']}")
        print(f"    Hash: {candidate_hash}")
        print(f"    Submitted: {submission.submitted}")
        print()

    return enrollments, tracker


def main():
    print("=" * 70)
    print("QUARANTINE ENROLLMENT")
    print("=" * 70)
    print()
    print(f"Enrollment timestamp: {ENROLLMENT_TIMESTAMP.isoformat()}")
    print(f"Quarantine duration: 90 days")
    print()

    enrollments, tracker = enroll()

    # Persist enrollment records (immutable after creation)
    records_path = Path("/home/ubuntu/quarantine_enrollments.json")
    if records_path.exists():
        print(f"WARNING: {records_path} already exists. NOT overwriting.")
        print("Quarantine start timestamps are immutable once set.")
        return

    with open(records_path, "w") as f:
        json.dump(
            {
                "enrollment_timestamp": ENROLLMENT_TIMESTAMP.isoformat(),
                "quarantine_days": 90,
                "enrollments": enrollments,
                "attestation_status": {
                    "commit_reveal_available": True,
                    "auto_commit_wired": False,
                    "blocker_note": (
                        "AttestationService.create_commitment exists as API endpoint "
                        "but is NOT automatically called by the prediction pipeline. "
                        "Pre-commitment must be triggered manually or wired into the "
                        "prediction generation step before the track record is credible. "
                        "This is flagged as a prerequisite for promotion, not enrollment."
                    ),
                },
                "calibration_reference": {
                    "corners_ece": 0.064,
                    "cards_ece": 0.058,
                    "source": "Multi-league robustness check (25 leagues × 3 seasons)",
                    "note": "These are the realistic figures, NOT the original single-sample EPL numbers (0.018/0.027)",
                },
            },
            f,
            indent=2,
        )

    print(f"Enrollment records saved to: {records_path}")
    print()

    # Report attestation status
    print("-" * 70)
    print("ATTESTATION STATUS (BLOCKER FLAGGED)")
    print("-" * 70)
    print()
    print("The commit-reveal attestation mechanism EXISTS:")
    print("  - POST /api/v1/attestations/commit (creates server-generated hash)")
    print("  - POST /api/v1/attestations/{id}/reveal (after settlement)")
    print("  - Enforces: commit BEFORE settlement, reveal AFTER")
    print()
    print("BUT it is NOT automatically wired to prediction generation.")
    print("AttestationService.create_commitment is only callable via API route")
    print("or direct service invocation — there is no automatic trigger when a")
    print("prediction is generated.")
    print()
    print("IMPLICATION: For the quarantine track record to be credible (proving")
    print("predictions were made before kickoff), the attestation commit step must")
    print("be wired into the prediction pipeline. Without this, the track record")
    print("is claimed rather than proved.")
    print()
    print("RECOMMENDATION: Wire create_commitment into the prediction generation")
    print("step before the first quarantine predictions are recorded. This is a")
    print("prerequisite for promotion, flagged now so it can be addressed during")
    print("the 90-day window rather than discovered at promotion time.")
    print()

    # Verify tracker state
    print("-" * 70)
    print("TRACKER STATE")
    print("-" * 70)
    for name, entry in tracker.entries.items():
        print(f"  {name}: {entry.status.value} (entered {entry.entry_date.date()})")


if __name__ == "__main__":
    main()
