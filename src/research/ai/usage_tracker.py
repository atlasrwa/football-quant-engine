"""AI Usage Tracker — cost control and usage monitoring.

Tracks:
- Request count per run
- Token usage (input/output)
- Latency
- Failures
- Proposal counts

Never tracks:
- Credentials
- Raw prompts containing operational secrets
- AWS access keys

Persistence: safe metadata only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AIUsageRecord:
    """Single AI call usage record — safe metadata only."""

    timestamp: float = field(default_factory=time.time)
    model_id: str = ""
    research_run_id: str = ""
    cycle_number: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    proposals_generated: int = 0
    proposals_valid: int = 0
    success: bool = True
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "model_id": self.model_id,
            "research_run_id": self.research_run_id,
            "cycle_number": self.cycle_number,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": round(self.latency_ms, 1),
            "proposals_generated": self.proposals_generated,
            "proposals_valid": self.proposals_valid,
            "success": self.success,
            "error_code": self.error_code,
        }


@dataclass
class AIUsageTracker:
    """Tracks AI usage for cost control and auditing.

    Enforces:
    - Max calls per run
    - Max total tokens
    - Max total runtime

    Reports:
    - Cumulative usage statistics
    - Per-run usage breakdown
    - Cost estimates (optional, not billing-accurate)
    """

    max_calls_per_run: int = 20
    max_total_input_tokens: int = 100_000
    max_total_output_tokens: int = 50_000
    max_total_runtime_seconds: float = 300.0  # 5 min AI time budget

    # Counters
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: float = 0.0
    total_failures: int = 0
    total_proposals: int = 0
    total_valid_proposals: int = 0

    # Records
    records: list[AIUsageRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    @property
    def is_budget_exceeded(self) -> bool:
        """Check if any usage limit has been exceeded."""
        if self.total_calls >= self.max_calls_per_run:
            return True
        if self.total_input_tokens >= self.max_total_input_tokens:
            return True
        if self.total_output_tokens >= self.max_total_output_tokens:
            return True
        elapsed = time.time() - self.started_at
        if elapsed >= self.max_total_runtime_seconds:
            return True
        return False

    @property
    def budget_exhaustion_reason(self) -> str:
        """Why the budget was exhausted."""
        if self.total_calls >= self.max_calls_per_run:
            return f"max_calls ({self.max_calls_per_run}) reached"
        if self.total_input_tokens >= self.max_total_input_tokens:
            return f"max_input_tokens ({self.max_total_input_tokens}) reached"
        if self.total_output_tokens >= self.max_total_output_tokens:
            return f"max_output_tokens ({self.max_total_output_tokens}) reached"
        elapsed = time.time() - self.started_at
        if elapsed >= self.max_total_runtime_seconds:
            return f"max_runtime ({self.max_total_runtime_seconds}s) reached"
        return ""

    @property
    def calls_remaining(self) -> int:
        return max(0, self.max_calls_per_run - self.total_calls)

    def record_call(
        self,
        model_id: str,
        research_run_id: str = "",
        cycle_number: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
        proposals_generated: int = 0,
        proposals_valid: int = 0,
        success: bool = True,
        error_code: str = "",
    ) -> None:
        """Record an AI call. Updates cumulative counters."""
        record = AIUsageRecord(
            model_id=model_id,
            research_run_id=research_run_id,
            cycle_number=cycle_number,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            proposals_generated=proposals_generated,
            proposals_valid=proposals_valid,
            success=success,
            error_code=error_code,
        )
        self.records.append(record)

        self.total_calls += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_latency_ms += latency_ms
        self.total_proposals += proposals_generated
        self.total_valid_proposals += proposals_valid
        if not success:
            self.total_failures += 1

    def to_dict(self) -> dict[str, Any]:
        """Safe summary — no credentials."""
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_latency_ms": round(self.total_latency_ms, 1),
            "total_failures": self.total_failures,
            "total_proposals": self.total_proposals,
            "total_valid_proposals": self.total_valid_proposals,
            "calls_remaining": self.calls_remaining,
            "is_budget_exceeded": self.is_budget_exceeded,
            "avg_latency_ms": round(
                self.total_latency_ms / max(1, self.total_calls), 1
            ),
        }

    def reset(self) -> None:
        """Reset all counters for a new research run."""
        self.total_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_latency_ms = 0.0
        self.total_failures = 0
        self.total_proposals = 0
        self.total_valid_proposals = 0
        self.records = []
        self.started_at = time.time()
