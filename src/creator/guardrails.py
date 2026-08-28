"""Anti-p-hacking guardrails for creator hypothesis testing.

The core problem: a creator submitting 50 variants of the same hypothesis
until one passes by chance. FDR correction handles the statistical side;
this module handles the operational enforcement.

Policy (stated plainly to creators):
- Every submission you make counts in your multiple-testing family.
  Your 50th hypothesis needs to clear a MUCH higher bar than your 1st.
- Submission counts are visible and permanent. You can see yours and
  others can see theirs.
- Rate limiting prevents spray-and-pray submission patterns.
- This is a feature, not a restriction. It's what makes a "validated"
  badge actually mean something.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CreatorSubmissionRecord:
    """Tracks a creator's submission history for FDR enforcement."""
    creator_id: str
    total_submissions: int = 0
    submissions_last_24h: int = 0
    submissions_last_7d: int = 0
    p_values: list[float] = field(default_factory=list)
    last_submission_at: Optional[str] = None
    hypotheses_passed: int = 0
    hypotheses_failed: int = 0


class SubmissionGuardrails:
    """Enforces anti-p-hacking rate limits and tracks submission families.

    Rate limits (per creator):
    - 5 submissions per 24 hours
    - 20 submissions per 7 days
    - No absolute cap, but FDR correction makes high-volume submitters
      progressively less likely to clear validation

    These limits balance freedom to explore with protection against
    brute-force hypothesis mining.
    """

    MAX_PER_24H = 5
    MAX_PER_7D = 20

    def __init__(self) -> None:
        self._records: dict[str, CreatorSubmissionRecord] = {}
        self._submissions: dict[str, list[dict]] = {}  # creator_id → timestamped submissions

    def get_record(self, creator_id: str) -> CreatorSubmissionRecord:
        """Get or create a creator's submission record."""
        if creator_id not in self._records:
            self._records[creator_id] = CreatorSubmissionRecord(creator_id=creator_id)
        return self._records[creator_id]

    def check_can_submit(self, creator_id: str) -> tuple[bool, Optional[str]]:
        """Check if a creator can submit a new hypothesis.

        Returns (allowed, reason_if_blocked).
        """
        record = self.get_record(creator_id)
        now = datetime.now(timezone.utc)
        submissions = self._submissions.get(creator_id, [])

        # Count recent submissions
        last_24h = sum(
            1 for s in submissions
            if datetime.fromisoformat(s["at"]) > now - timedelta(hours=24)
        )
        last_7d = sum(
            1 for s in submissions
            if datetime.fromisoformat(s["at"]) > now - timedelta(days=7)
        )

        if last_24h >= self.MAX_PER_24H:
            return False, (
                f"Rate limit: {last_24h}/{self.MAX_PER_24H} submissions in the last 24 hours. "
                f"This limit exists to prevent brute-force hypothesis mining. "
                f"Each submission counts in your FDR family — submitting many variants "
                f"makes it harder for any of them to clear validation, not easier."
            )

        if last_7d >= self.MAX_PER_7D:
            return False, (
                f"Rate limit: {last_7d}/{self.MAX_PER_7D} submissions in the last 7 days. "
                f"Take time to think through your hypothesis before submitting. "
                f"Quality over quantity — every submission raises your FDR bar."
            )

        return True, None

    def record_submission(
        self,
        creator_id: str,
        hypothesis_id: str,
        p_value: Optional[float] = None,
        passed: bool = False,
    ) -> CreatorSubmissionRecord:
        """Record a new submission and update the creator's record."""
        now = datetime.now(timezone.utc)
        record = self.get_record(creator_id)

        # Store timestamped submission
        if creator_id not in self._submissions:
            self._submissions[creator_id] = []
        self._submissions[creator_id].append({
            "hypothesis_id": hypothesis_id,
            "at": now.isoformat(),
            "p_value": p_value,
            "passed": passed,
        })

        # Update record
        record.total_submissions += 1
        record.last_submission_at = now.isoformat()
        if p_value is not None:
            record.p_values.append(p_value)
        if passed:
            record.hypotheses_passed += 1
        else:
            record.hypotheses_failed += 1

        # Recompute windowed counts
        submissions = self._submissions[creator_id]
        record.submissions_last_24h = sum(
            1 for s in submissions
            if datetime.fromisoformat(s["at"]) > now - timedelta(hours=24)
        )
        record.submissions_last_7d = sum(
            1 for s in submissions
            if datetime.fromisoformat(s["at"]) > now - timedelta(days=7)
        )

        return record

    def get_fdr_family(self, creator_id: str) -> list[float]:
        """Get all p-values in this creator's testing family."""
        record = self.get_record(creator_id)
        return list(record.p_values)

    def get_submission_stats(self, creator_id: str) -> dict:
        """Public-facing submission statistics for a creator."""
        record = self.get_record(creator_id)
        can_submit, block_reason = self.check_can_submit(creator_id)

        return {
            "creator_id": creator_id,
            "total_submissions": record.total_submissions,
            "submissions_last_24h": record.submissions_last_24h,
            "submissions_last_7d": record.submissions_last_7d,
            "hypotheses_passed": record.hypotheses_passed,
            "hypotheses_failed": record.hypotheses_failed,
            "pass_rate": (
                round(record.hypotheses_passed / record.total_submissions, 3)
                if record.total_submissions > 0 else None
            ),
            "can_submit": can_submit,
            "block_reason": block_reason,
            "rate_limits": {
                "per_24h": self.MAX_PER_24H,
                "per_7d": self.MAX_PER_7D,
            },
            "fdr_note": (
                f"Your next submission will be tested in a family of "
                f"{record.total_submissions + 1} hypotheses. The more you submit, "
                f"the higher the statistical bar each new submission must clear. "
                f"This is the Benjamini-Hochberg procedure working as designed."
            ),
            "policy": (
                "Every hypothesis you submit permanently joins your multiple-testing "
                "family. A 'validated' badge means the hypothesis survived correction "
                "across ALL your submissions — not just this one in isolation. "
                "This is what makes validation credible."
            ),
        }
