"""Research agent interface — deterministic and LLM-guided.

The agent is a SECOND-ORDER RESEARCHER. It does NOT:
- Determine whether something works (statistics do)
- Calculate significance (validator does)
- Approve strategies (FDR does)
- Bypass walk-forward validation

The agent DOES:
- Analyze experiment results
- Generate follow-up hypotheses
- Suggest parameter variations
- Identify patterns in failures
- Propose new feature combinations
- Prioritize the research queue
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from src.research.candidate_generator import GenerationMethod, ResearchHypothesis
from src.research.experiment import ExperimentResult
from src.research.market import MarketType
from src.research.memory import ResearchMemory


@dataclass(frozen=True)
class ResearchProposal:
    """A structured research proposal from the agent.

    Every proposal enters the same Research Queue.
    The quantitative system evaluates it — not the agent.
    """
    hypothesis: ResearchHypothesis
    rationale: str
    priority: int = 5  # 1=highest, 10=lowest
    follow_up_from: Optional[str] = None  # Parent hypothesis ID
    suggested_variations: list[dict[str, Any]] = field(default_factory=list)


class ResearchAgent(ABC):
    """Abstract research agent interface."""

    @abstractmethod
    def analyze_results(
        self,
        memory: ResearchMemory,
        recent_results: list[ExperimentResult],
    ) -> list[ResearchProposal]:
        """Analyze recent results and propose follow-up experiments.

        Args:
            memory: Full research memory for context.
            recent_results: Results from latest batch.

        Returns:
            List of structured research proposals.
        """
        ...

    @abstractmethod
    def suggest_next_experiments(
        self,
        memory: ResearchMemory,
        available_features: list[str],
        available_markets: list[MarketType],
    ) -> list[ResearchProposal]:
        """Suggest new experiments based on current knowledge.

        Args:
            memory: Research memory.
            available_features: Feature IDs available.
            available_markets: Markets available for research.

        Returns:
            Prioritized list of proposals.
        """
        ...


class DeterministicResearchAgent(ResearchAgent):
    """Rule-based research agent that works without an LLM.

    Strategies:
    1. If a feature shows promise at one threshold, try nearby thresholds
    2. If a feature works for one market, try other markets
    3. Combine promising single-feature hypotheses into pairs
    4. Try different lookback windows for promising features
    5. Avoid re-testing duplicates
    """

    def analyze_results(
        self,
        memory: ResearchMemory,
        recent_results: list[ExperimentResult],
    ) -> list[ResearchProposal]:
        """Generate follow-ups from recent results."""
        proposals: list[ResearchProposal] = []

        promising = [r for r in recent_results if r.roi_pct > 0 and r.n_bets >= 20]

        for result in promising:
            entry = memory.get_entry(result.hypothesis_id)
            if entry is None:
                continue

            hyp = entry.hypothesis

            # Strategy 1: Try adjacent thresholds
            for fid, op, threshold in hyp.conditions:
                for delta_pct in [-0.1, 0.1, -0.2, 0.2]:
                    new_threshold = threshold * (1 + delta_pct)
                    new_conditions = tuple(
                        (f, o, new_threshold if f == fid else t)
                        for f, o, t in hyp.conditions
                    )
                    new_hyp = ResearchHypothesis(
                        hypothesis_id=f"{hyp.hypothesis_id}_adj_{delta_pct:.1f}",
                        market=hyp.market,
                        feature_ids=hyp.feature_ids,
                        conditions=new_conditions,
                        direction=hyp.direction,
                        generation_method=GenerationMethod.DETERMINISTIC,
                        rationale=f"Threshold adjustment {delta_pct:+.0%} from {result.hypothesis_id} (ROI={result.roi_pct:.1f}%)",
                    )

                    if not memory.is_duplicate(new_hyp):
                        proposals.append(ResearchProposal(
                            hypothesis=new_hyp,
                            rationale=f"Follow-up: adjust threshold from promising result (ROI={result.roi_pct:.1f}%)",
                            priority=3,
                            follow_up_from=result.hypothesis_id,
                        ))

            # Strategy 2: Try opposite direction
            opp_dir = "UNDER" if hyp.direction == "OVER" else "OVER"
            opp_hyp = ResearchHypothesis(
                hypothesis_id=f"{hyp.hypothesis_id}_opp",
                market=hyp.market,
                feature_ids=hyp.feature_ids,
                conditions=hyp.conditions,
                direction=opp_dir,
                generation_method=GenerationMethod.DETERMINISTIC,
                rationale=f"Test opposite direction from {result.hypothesis_id}",
            )
            if not memory.is_duplicate(opp_hyp):
                proposals.append(ResearchProposal(
                    hypothesis=opp_hyp,
                    rationale="Test opposite direction",
                    priority=7,
                    follow_up_from=result.hypothesis_id,
                ))

        return proposals

    def suggest_next_experiments(
        self,
        memory: ResearchMemory,
        available_features: list[str],
        available_markets: list[MarketType],
    ) -> list[ResearchProposal]:
        """Suggest experiments combining promising features."""
        proposals: list[ResearchProposal] = []

        # Find features that appeared in promising results
        promising_entries = memory.get_promising()
        promising_features: dict[str, int] = {}  # feature_id → count

        for entry in promising_entries:
            for fid in entry.hypothesis.feature_ids:
                promising_features[fid] = promising_features.get(fid, 0) + 1

        # Suggest combining top promising features
        sorted_features = sorted(
            promising_features.items(), key=lambda x: x[1], reverse=True
        )[:5]

        for i, (f1, _) in enumerate(sorted_features):
            for f2, _ in sorted_features[i + 1:]:
                for market in available_markets:
                    hyp = ResearchHypothesis(
                        hypothesis_id=f"combo_{f1[:8]}_{f2[:8]}_{market.value}",
                        market=market,
                        feature_ids=(f1, f2),
                        conditions=((f1, ">", 0.0), (f2, ">", 0.0)),
                        direction="OVER",
                        generation_method=GenerationMethod.DETERMINISTIC,
                        rationale=f"Combine promising features {f1[:8]} + {f2[:8]}",
                    )
                    if not memory.is_duplicate(hyp):
                        proposals.append(ResearchProposal(
                            hypothesis=hyp,
                            rationale="Feature combination from promising singles",
                            priority=4,
                        ))

        return proposals


class LLMResearchAgent(ResearchAgent):
    """LLM-guided research agent (interface only — requires LLM provider).

    The LLM receives:
    - Research memory context (past results)
    - Available features and markets
    - Structured output schema

    The LLM returns structured ResearchProposals that enter the
    same quantitative evaluation queue.
    """

    def __init__(self, llm_callable=None) -> None:
        """Initialize with optional LLM callable.

        Args:
            llm_callable: async function(prompt: str) -> str
                         If None, falls back to DeterministicResearchAgent.
        """
        self._llm = llm_callable
        self._fallback = DeterministicResearchAgent()

    def analyze_results(
        self,
        memory: ResearchMemory,
        recent_results: list[ExperimentResult],
    ) -> list[ResearchProposal]:
        """Analyze with LLM or fallback to deterministic."""
        if self._llm is None:
            return self._fallback.analyze_results(memory, recent_results)

        # LLM integration point — to be implemented when LLM provider available
        # For now, use deterministic fallback
        return self._fallback.analyze_results(memory, recent_results)

    def suggest_next_experiments(
        self,
        memory: ResearchMemory,
        available_features: list[str],
        available_markets: list[MarketType],
    ) -> list[ResearchProposal]:
        """Suggest with LLM or fallback to deterministic."""
        if self._llm is None:
            return self._fallback.suggest_next_experiments(
                memory, available_features, available_markets
            )
        return self._fallback.suggest_next_experiments(
            memory, available_features, available_markets
        )
