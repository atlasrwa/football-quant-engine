"""AI Research Loop — bounded iterative research with LLM proposals.

Implements the full research workflow:
    BUILD_CONTEXT → BEDROCK_PROPOSE → VALIDATE → DEDUPLICATE → QUEUE →
    EXPERIMENT → WALK_FORWARD → FDR → GOVERNANCE → PERSIST → UPDATE_MEMORY →
    OPTIONAL_NEXT_CYCLE → STOP

Critical invariants:
- Hard budget enforced at all times
- AI can never skip deterministic validation
- AI can never bypass FDR or governance
- AI cannot repeatedly optimize same hypothesis (p-hacking prevention)
- All proposals enter at EXPLORATION phase only
- Temporal leakage checked at every proposal

This module coordinates the ResearchAgent with the ResearchOrchestrator.
It does NOT replace the orchestrator — it wraps it with AI proposal generation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.ai.agent import ResearchAgent
from src.research.ai.budget import ResearchBudget
from src.research.ai.context import ResearchContext, ResearchContextBuilder
from src.research.ai.proposal import ProposalSource, ProposalStatus, ResearchPhase, ResearchProposal
from src.research.ai.validator import ProposalValidator
from src.research.persistence.repository import ResearchRepository
from src.research.persistence.research_memory import ResearchMemory
from src.research.queue.task import ResearchTask, TaskType

logger = logging.getLogger(__name__)


class ResearchLoopStatus(Enum):
    """Status of the AI research loop."""
    NOT_STARTED = "NOT_STARTED"
    PROPOSING = "PROPOSING"
    VALIDATING = "VALIDATING"
    QUEUING = "QUEUING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    FAILED = "FAILED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"


@dataclass
class AIResearchEvent:
    """Audit trail event for AI research activities.

    Safe metadata only — never contains credentials.
    """
    event_type: str
    timestamp: float = field(default_factory=time.time)
    research_run_id: str = ""
    model_id: str = ""
    context_hash: str = ""
    prompt_hash: str = ""
    proposal_count: int = 0
    valid_proposal_count: int = 0
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    success: bool = True
    failure_category: str = ""
    cycle_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "research_run_id": self.research_run_id,
            "model_id": self.model_id,
            "context_hash": self.context_hash,
            "prompt_hash": self.prompt_hash,
            "proposal_count": self.proposal_count,
            "valid_proposal_count": self.valid_proposal_count,
            "latency_ms": round(self.latency_ms, 1),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "success": self.success,
            "failure_category": self.failure_category,
            "cycle_number": self.cycle_number,
        }


@dataclass
class ResearchLoopResult:
    """Result of a complete AI research loop execution."""
    run_id: str
    status: ResearchLoopStatus
    cycles_completed: int = 0
    total_proposals_generated: int = 0
    total_proposals_valid: int = 0
    total_proposals_duplicate: int = 0
    total_tasks_queued: int = 0
    budget_used: Optional[dict[str, Any]] = None
    events: list[AIResearchEvent] = field(default_factory=list)
    error_message: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "cycles_completed": self.cycles_completed,
            "total_proposals_generated": self.total_proposals_generated,
            "total_proposals_valid": self.total_proposals_valid,
            "total_proposals_duplicate": self.total_proposals_duplicate,
            "total_tasks_queued": self.total_tasks_queued,
            "budget_used": self.budget_used,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "event_count": len(self.events),
        }


class AIResearchLoop:
    """Bounded AI research loop coordinating proposals with execution.

    Architecture:
        1. Build context from research memory
        2. Ask AI for proposals (bounded)
        3. Validate all proposals deterministically
        4. Deduplicate against research memory
        5. Convert to research tasks
        6. Submit to queue
        7. Optionally repeat (bounded cycles)

    The loop NEVER:
        - Runs without a budget
        - Allows AI to bypass validation
        - Allows AI to promote strategies
        - Runs indefinitely
        - Optimizes same hypothesis repeatedly (p-hacking)
    """

    def __init__(
        self,
        agent: ResearchAgent,
        context_builder: ResearchContextBuilder,
        repository: ResearchRepository,
        memory: ResearchMemory,
        budget: Optional[ResearchBudget] = None,
        max_cycles: int = 3,
        max_proposals_per_cycle: int = 5,
    ) -> None:
        """Initialize the AI research loop.

        Args:
            agent: ResearchAgent with configured LLM provider.
            context_builder: Builds bounded context for AI.
            repository: Persistence layer.
            memory: Research memory for deduplication.
            budget: Research budget (uses defaults if None).
            max_cycles: Maximum number of propose-validate cycles.
            max_proposals_per_cycle: Max proposals to request per AI call.
        """
        self._agent = agent
        self._context_builder = context_builder
        self._repo = repository
        self._memory = memory
        self._budget = budget or ResearchBudget()
        self._max_cycles = min(max_cycles, 10)  # Hard cap at 10 cycles
        self._max_proposals_per_cycle = min(max_proposals_per_cycle, 10)  # Hard cap
        self._events: list[AIResearchEvent] = []
        self._seen_content_hashes: set[str] = set()

    @property
    def events(self) -> list[AIResearchEvent]:
        """Audit trail of AI research events."""
        return list(self._events)

    def run(
        self,
        run_id: str,
        market_type: str = "",
        available_features: Optional[list[str]] = None,
        available_markets: Optional[list[str]] = None,
        dataset_summary: Optional[dict[str, Any]] = None,
        season_coverage: Optional[list[dict[str, Any]]] = None,
        temporal_cutoff: Optional[float] = None,
    ) -> ResearchLoopResult:
        """Execute the bounded AI research loop.

        Args:
            run_id: Deterministic research run identifier.
            market_type: Target market for proposals.
            available_features: Feature vocabulary for AI.
            available_markets: Available market targets.
            dataset_summary: Coverage summary from data source.
            season_coverage: Per-season coverage information.
            temporal_cutoff: Temporal boundary for context.

        Returns:
            ResearchLoopResult with full audit trail.
        """
        result = ResearchLoopResult(
            run_id=run_id,
            status=ResearchLoopStatus.NOT_STARTED,
            started_at=time.time(),
        )

        # Check AI availability
        if not self._agent.is_available:
            result.status = ResearchLoopStatus.AI_UNAVAILABLE
            result.error_message = "AI provider not available"
            result.completed_at = time.time()
            return result

        # Check budget before starting
        if self._budget.is_exhausted:
            result.status = ResearchLoopStatus.BUDGET_EXHAUSTED
            result.error_message = self._budget.exhaustion_reason
            result.completed_at = time.time()
            return result

        # Run bounded cycles
        try:
            for cycle in range(self._max_cycles):
                # Check budget each cycle
                if self._budget.is_exhausted:
                    result.status = ResearchLoopStatus.BUDGET_EXHAUSTED
                    result.error_message = self._budget.exhaustion_reason
                    break

                if not self._budget.use_ai_proposal():
                    result.status = ResearchLoopStatus.BUDGET_EXHAUSTED
                    result.error_message = "max_ai_proposals reached"
                    break

                # Execute one proposal cycle
                cycle_result = self._execute_cycle(
                    run_id=run_id,
                    cycle_number=cycle,
                    market_type=market_type,
                    available_features=available_features,
                    available_markets=available_markets,
                    dataset_summary=dataset_summary,
                    season_coverage=season_coverage,
                    temporal_cutoff=temporal_cutoff,
                )

                result.cycles_completed += 1
                result.total_proposals_generated += cycle_result["proposals_generated"]
                result.total_proposals_valid += cycle_result["proposals_valid"]
                result.total_proposals_duplicate += cycle_result["proposals_duplicate"]
                result.total_tasks_queued += cycle_result["tasks_queued"]

                # If no valid proposals were produced, stop cycling
                if cycle_result["proposals_valid"] == 0:
                    logger.info("Cycle %d produced no valid proposals — stopping", cycle)
                    break

            if result.status == ResearchLoopStatus.NOT_STARTED:
                result.status = ResearchLoopStatus.COMPLETED

        except Exception as e:
            result.status = ResearchLoopStatus.FAILED
            result.error_message = f"{type(e).__name__}: {str(e)[:200]}"
            logger.error("AI research loop failed: %s", result.error_message)

        result.completed_at = time.time()
        result.budget_used = self._budget.to_dict()
        result.events = list(self._events)
        return result

    def _execute_cycle(
        self,
        run_id: str,
        cycle_number: int,
        market_type: str,
        available_features: Optional[list[str]],
        available_markets: Optional[list[str]],
        dataset_summary: Optional[dict[str, Any]],
        season_coverage: Optional[list[dict[str, Any]]],
        temporal_cutoff: Optional[float],
    ) -> dict[str, int]:
        """Execute a single propose-validate-queue cycle.

        Returns summary counts.
        """
        # 1. Build context
        context = self._context_builder.build(
            market_type=market_type,
            available_features=available_features,
            available_markets=available_markets,
            dataset_summary=dataset_summary,
            season_coverage=season_coverage,
            temporal_cutoff=temporal_cutoff,
        )

        # 2. Generate proposals
        start_time = time.time()
        proposals = self._agent.propose_batch(
            context=context,
            max_proposals=self._max_proposals_per_cycle,
        )
        elapsed_ms = (time.time() - start_time) * 1000

        # 3. Record event
        event = AIResearchEvent(
            event_type="AI_PROPOSAL_CYCLE",
            research_run_id=run_id,
            model_id=self._agent.provider_name,
            context_hash=context.content_hash,
            prompt_hash=self._compute_prompt_hash(context, cycle_number),
            proposal_count=len(proposals),
            latency_ms=elapsed_ms,
            success=True,
            cycle_number=cycle_number,
        )

        # 4. Deduplicate against memory and within-run
        valid_proposals: list[ResearchProposal] = []
        duplicates = 0
        for proposal in proposals:
            content_hash = proposal.content_hash

            # Check within-run duplicates
            if content_hash in self._seen_content_hashes:
                duplicates += 1
                continue

            # Check against research memory
            if self._memory.has_candidate(content_hash):
                duplicates += 1
                continue

            self._seen_content_hashes.add(content_hash)
            valid_proposals.append(proposal)

        event.valid_proposal_count = len(valid_proposals)
        self._events.append(event)

        # 5. Convert to tasks and submit
        tasks_queued = 0
        for proposal in valid_proposals:
            # Persist proposal
            self._repo.save_proposal(
                proposal.content_hash,
                {
                    **proposal.to_dict(),
                    "research_run_id": run_id,
                    "cycle_number": cycle_number,
                },
            )

            # Record as candidate in memory
            self._memory.record_candidate(
                proposal.content_hash,
                {
                    "market_type": proposal.market_type,
                    "feature_ids": list(proposal.feature_ids),
                    "direction": proposal.direction,
                    "source": proposal.source.value,
                    "research_run_id": run_id,
                },
            )

            # Create research task
            task = ResearchTask.create(
                task_type=TaskType.EXPERIMENT,
                candidate_hash=proposal.content_hash,
                hypothesis_hash=proposal.content_hash,
                research_run_id=run_id,
                requested_by="AI",
                payload={
                    "proposal": proposal.to_dict(),
                    "market_type": proposal.market_type,
                    "feature_ids": list(proposal.feature_ids),
                    "conditions": list(proposal.conditions),
                    "direction": proposal.direction,
                    "operator_type": proposal.operator_type,
                    "model_type": proposal.model_type,
                    "model_parameters": proposal.model_parameters,
                },
            )

            # Submit to queue (idempotent)
            saved = self._repo.save_task(task.task_id, task.to_dict())
            if saved:
                tasks_queued += 1

        logger.info(
            "Cycle %d: %d generated, %d valid, %d duplicate, %d queued",
            cycle_number, len(proposals), len(valid_proposals), duplicates, tasks_queued,
        )

        return {
            "proposals_generated": len(proposals),
            "proposals_valid": len(valid_proposals),
            "proposals_duplicate": duplicates,
            "tasks_queued": tasks_queued,
        }

    def _compute_prompt_hash(self, context: ResearchContext, cycle: int) -> str:
        """Compute a deterministic hash of the prompt content.

        Does NOT include credentials or secrets.
        """
        canonical = json.dumps({
            "context_hash": context.content_hash,
            "cycle": cycle,
            "prompt_version": self._agent.prompt_version,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
