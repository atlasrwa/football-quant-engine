"""Batch 7+9 — AI Researcher Infrastructure + Bedrock + Multi-Season.

Provides optional AI-assisted research proposal generation.
The AI proposes. The deterministic system validates and evaluates.

Architecture:
    ResearchContext → ResearchAgent → ResearchProposal → Validator → Queue
    BedrockLLMProvider → AWS Bedrock Runtime → Claude Sonnet

The AI is OPTIONAL. The system functions correctly with AI disabled.
The AI CANNOT: execute code, run SQL, modify results, bypass governance.
"""

from src.research.ai.agent import ResearchAgent
from src.research.ai.provider import LLMProvider, MockLLMProvider, DisabledProvider
from src.research.ai.proposal import ResearchProposal, ProposalSource, ProposalStatus
from src.research.ai.validator import ProposalValidator
from src.research.ai.context import ResearchContext, ResearchContextBuilder
from src.research.ai.budget import ResearchBudget
from src.research.ai.bedrock_config import BedrockConfig
from src.research.ai.bedrock import BedrockLLMProvider, BedrockError
from src.research.ai.prompts import get_system_prompt, SYSTEM_PROMPT_V2
from src.research.ai.research_loop import AIResearchLoop, ResearchLoopResult, ResearchLoopStatus
from src.research.ai.multiseason import MultiSeasonDataset, SeasonCoverage, build_multi_season_dataset
from src.research.ai.usage_tracker import AIUsageTracker
from src.research.ai.season_stability import (
    MultiSeasonStabilityReport,
    SeasonStabilityReport,
    build_season_stability_report,
)

__all__ = [
    # Core AI
    "ResearchAgent",
    "LLMProvider",
    "MockLLMProvider",
    "DisabledProvider",
    "ResearchProposal",
    "ProposalSource",
    "ProposalStatus",
    "ProposalValidator",
    "ResearchContext",
    "ResearchContextBuilder",
    "ResearchBudget",
    # Bedrock
    "BedrockConfig",
    "BedrockLLMProvider",
    "BedrockError",
    # Prompts
    "get_system_prompt",
    "SYSTEM_PROMPT_V2",
    # Research Loop
    "AIResearchLoop",
    "ResearchLoopResult",
    "ResearchLoopStatus",
    # Multi-Season
    "MultiSeasonDataset",
    "SeasonCoverage",
    "build_multi_season_dataset",
    # Usage Tracking
    "AIUsageTracker",
    # Season Stability
    "MultiSeasonStabilityReport",
    "SeasonStabilityReport",
    "build_season_stability_report",
]
