"""Metric Discovery Pipeline — orchestrates the full discovery process.

Stages:
1. Generate candidates (report family size)
2. Screen on discovery set
3. FDR correction across FULL search space
4. Adversarial review
5. Held-out validation
6. Library entry

Reports attrition honestly at every stage.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np

from src.discovery.adversarial import AdversarialReviewer
from src.discovery.corpus import load_discovery_set, load_heldout_set
from src.discovery.generator import CandidateMetric, MetricGenerator, compute_metric_value
from src.discovery.library import MetricLibrary, MetricStatus
from src.discovery.screener import MetricScreener, ScreeningResult, compute_outcome, TARGET_GROUPS
from src.engine.analysis.fdr import FDRController

logger = logging.getLogger(__name__)


class DiscoveryPipeline:
    """Orchestrates the full metric discovery process.

    The held-out set is NEVER touched until Step 5. Any access during
    search would compromise the entire exercise.
    """

    def __init__(self, fdr_alpha: float = 0.05) -> None:
        self._fdr = FDRController(alpha=fdr_alpha)
        self._library = MetricLibrary()

    def run_discovery(self, max_candidates: int | None = None) -> dict[str, Any]:
        """Execute the full discovery pipeline.

        Args:
            max_candidates: Optional cap on candidates to test (for dev/testing).

        Returns:
            Attrition report dict.
        """
        start = time.time()
        now = datetime.now(timezone.utc)

        logger.info("=" * 60)
        logger.info("METRIC DISCOVERY PIPELINE — %s", now.strftime("%Y-%m-%d %H:%M UTC"))
        logger.info("=" * 60)

        # ─── Step 1: Generate candidates ───
        logger.info("Step 1: Generating candidate metrics...")
        generator = MetricGenerator()
        candidates = generator.generate_all()

        if max_candidates and len(candidates) > max_candidates:
            candidates = candidates[:max_candidates]

        family_size = len(candidates)
        logger.info("Generated %d candidates (FDR family size = %d)", len(candidates), family_size)

        # Register all in library (for auditable search log)
        for c in candidates:
            self._library.add_candidate(
                metric_id=c.metric_id,
                name=c.name,
                formula_type=c.formula_type,
                fields=list(c.fields),
                params=c.params,
                description=c.description,
            )

        # ─── Step 2: Screen on discovery set ───
        logger.info("Step 2: Loading discovery set...")
        discovery_matches = load_discovery_set()
        logger.info("Discovery set: %d matches", len(discovery_matches))

        logger.info("Step 2: Screening %d candidates...", len(candidates))
        screener = MetricScreener(discovery_matches)

        screening_results: list[tuple[CandidateMetric, ScreeningResult]] = []
        passed_screen = []

        for i, candidate in enumerate(candidates):
            if (i + 1) % 100 == 0:
                logger.info("  Screened %d/%d...", i + 1, len(candidates))

            result = screener.screen(candidate)
            screening_results.append((candidate, result))

            # Log to search record (every candidate, pass or fail)
            self._library.log_search(candidate.metric_id, {
                "passed_screen": result.passed_screen,
                "targets_positive": result.targets_positive,
                "breadth_score": result.breadth_score,
                "overall_p_value": result.overall_p_value,
                "best_vs_naive_pct": result.best_vs_naive_pct,
            })

            if result.passed_screen:
                passed_screen.append((candidate, result))
                self._library.promote_to_screened(candidate.metric_id, {
                    "targets_tested": result.targets_tested,
                    "targets_positive": result.targets_positive,
                    "breadth_score": result.breadth_score,
                    "best_vs_naive_pct": result.best_vs_naive_pct,
                    "min_p_value": result.min_p_value,
                    "overall_p_value": result.overall_p_value,
                })

        logger.info("Screening: %d/%d passed (%.1f%%)",
                    len(passed_screen), len(candidates),
                    100 * len(passed_screen) / max(len(candidates), 1))

        # ─── Step 3: FDR correction across FULL search space ───
        logger.info("Step 3: FDR correction (family size = %d)...", family_size)

        # Collect all p-values (every candidate ever tested)
        all_p_values = [r.overall_p_value for _, r in screening_results]
        fdr_results = self._fdr.correct(all_p_values)

        fdr_survivors = []
        for i, (candidate, screen_result) in enumerate(screening_results):
            fdr_result = fdr_results[i]
            if fdr_result.rejected and screen_result.passed_screen:
                fdr_survivors.append((candidate, screen_result, fdr_result))
                self._library.promote_to_fdr_survivor(candidate.metric_id, {
                    "original_p": fdr_result.original_p,
                    "adjusted_threshold": fdr_result.adjusted_threshold,
                    "rank": fdr_result.rank,
                    "total_hypotheses": fdr_result.total_hypotheses,
                    "family_size": family_size,
                })

        logger.info("FDR correction: %d/%d survive (family=%d, alpha=%.2f)",
                    len(fdr_survivors), len(passed_screen), family_size, self._fdr.alpha)

        # ─── Step 4: Adversarial review ───
        logger.info("Step 4: Adversarial review of %d FDR survivors...", len(fdr_survivors))

        existing_metrics = [m.name for m in self._library.get_by_status(MetricStatus.VALIDATED)]
        reviewer = AdversarialReviewer(existing_metrics=existing_metrics)

        reviewed_pass = []
        for candidate, screen_result, fdr_result in fdr_survivors:
            review = reviewer.review(candidate, screen_result)

            if review.recommendation == "PROCEED":
                reviewed_pass.append((candidate, screen_result, review))
                self._library.promote_to_reviewed(
                    candidate.metric_id,
                    review.to_dict(),
                    review.mechanism,
                )
            elif review.recommendation == "FLAG_FOR_HUMAN":
                # Still pass through but flagged
                reviewed_pass.append((candidate, screen_result, review))
                self._library.promote_to_reviewed(
                    candidate.metric_id,
                    review.to_dict(),
                    review.mechanism,
                )
            else:
                self._library.reject(candidate.metric_id, f"Adversarial: {review.recommendation}")

        logger.info("Adversarial review: %d/%d pass or flagged",
                    len(reviewed_pass), len(fdr_survivors))

        # ─── Step 5: Held-out validation ───
        logger.info("Step 5: Held-out validation of %d reviewed metrics...", len(reviewed_pass))
        # WARNING: This is the ONLY time held-out data is accessed
        heldout_matches = load_heldout_set()
        logger.info("Held-out set: %d matches (FIRST ACCESS)", len(heldout_matches))

        heldout_screener = MetricScreener(heldout_matches)
        discovered = []

        for candidate, discovery_result, review in reviewed_pass:
            heldout_result = heldout_screener.screen(candidate)

            if heldout_result.passed_screen and heldout_result.targets_positive >= 1:
                discovered.append((candidate, heldout_result, review))
                self._library.promote_to_discovered(candidate.metric_id, {
                    "targets_tested": heldout_result.targets_tested,
                    "targets_positive": heldout_result.targets_positive,
                    "breadth_score": heldout_result.breadth_score,
                    "best_vs_naive_pct": heldout_result.best_vs_naive_pct,
                    "overall_p_value": heldout_result.overall_p_value,
                    "discovery_vs_heldout_consistency": (
                        "CONSISTENT" if heldout_result.targets_positive >= discovery_result.targets_positive * 0.5
                        else "DEGRADED"
                    ),
                })
            else:
                self._library.reject(candidate.metric_id, "Failed held-out validation")

        logger.info("Held-out validation: %d/%d confirmed",
                    len(discovered), len(reviewed_pass))

        # ─── Attrition report ───
        duration = time.time() - start
        attrition = {
            "pipeline_run_at": now.isoformat(),
            "duration_seconds": round(duration, 1),
            "stages": {
                "1_candidates_generated": family_size,
                "2_passed_screening": len(passed_screen),
                "3_survived_fdr": len(fdr_survivors),
                "4_passed_adversarial": len(reviewed_pass),
                "5_confirmed_heldout": len(discovered),
            },
            "attrition_rates": {
                "screening": f"{len(passed_screen)}/{family_size} ({100*len(passed_screen)/max(family_size,1):.1f}%)",
                "fdr": f"{len(fdr_survivors)}/{len(passed_screen)} ({100*len(fdr_survivors)/max(len(passed_screen),1):.1f}%)",
                "adversarial": f"{len(reviewed_pass)}/{len(fdr_survivors)} ({100*len(reviewed_pass)/max(len(fdr_survivors),1):.1f}%)",
                "heldout": f"{len(discovered)}/{len(reviewed_pass)} ({100*len(discovered)/max(len(reviewed_pass),1):.1f}%)",
            },
            "fdr_parameters": {
                "alpha": self._fdr.alpha,
                "family_size": family_size,
                "note": "BH correction across ALL candidates tested, not just survivors",
            },
            "corpus": {
                "discovery_matches": len(discovery_matches),
                "heldout_matches": len(heldout_matches),
                "split": "Temporal: older seasons for discovery, newer for held-out",
            },
            "discovered_metrics": [
                {
                    "metric_id": c.metric_id,
                    "name": c.name,
                    "formula": c.formula_type,
                    "fields": list(c.fields),
                    "breadth_score": hr.breadth_score,
                    "targets_positive": hr.targets_positive,
                    "best_vs_naive_pct": hr.best_vs_naive_pct,
                    "mechanism": rev.mechanism,
                    "recommendation": rev.recommendation,
                }
                for c, hr, rev in discovered
            ],
            "note": (
                "Most candidates failing is success, not underperformance. "
                "Testing thousands of random combinations guarantees many will "
                "clear p<0.05 by chance alone. The FDR correction + held-out "
                "validation is what separates discovery from automated p-hacking."
            ),
        }

        self._library.save_attrition_report(attrition)
        self._library.save()

        logger.info("")
        logger.info("═" * 60)
        logger.info("DISCOVERY COMPLETE")
        logger.info("═" * 60)
        logger.info("Candidates generated: %d", family_size)
        logger.info("Passed screening:     %d", len(passed_screen))
        logger.info("Survived FDR:         %d", len(fdr_survivors))
        logger.info("Passed adversarial:   %d", len(reviewed_pass))
        logger.info("Confirmed held-out:   %d", len(discovered))
        logger.info("Duration: %.1fs", duration)
        logger.info("═" * 60)

        return attrition
