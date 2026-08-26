"""Research Agent — AI-assisted proposal generation.

The agent uses an LLM to propose research hypotheses based on
structured context. It is OPTIONAL — the system works without it.

The agent CANNOT:
- Execute code
- Run SQL
- Modify results
- Bypass governance
- Promote strategies
- Access credentials
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.research.ai.context import ResearchContext
from src.research.ai.prompts import DEFAULT_PROMPT_VERSION, get_system_prompt
from src.research.ai.proposal import ProposalSource, ProposalStatus, ResearchPhase, ResearchProposal
from src.research.ai.provider import LLMProvider, LLMResponse
from src.research.ai.validator import ProposalValidator, ValidationResult

logger = logging.getLogger(__name__)

# Keep backward-compatible reference
_SYSTEM_PROMPT_V1 = get_system_prompt("v1")
_PROMPT_VERSION = "v1"


class ResearchAgent:
    """AI research assistant that proposes structured hypotheses.

    Uses LLMProvider abstraction — never imports a specific SDK.
    Validates all output before returning.
    Supports single-proposal (v1) and multi-proposal (v2) generation.
    """

    def __init__(
        self,
        provider: LLMProvider,
        validator: Optional[ProposalValidator] = None,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
    ) -> None:
        self._provider = provider
        self._validator = validator or ProposalValidator()
        self._prompt_version = prompt_version
        self._proposal_count = 0

    @property
    def is_available(self) -> bool:
        """Whether the AI is available."""
        return self._provider.is_available()

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    @property
    def proposal_count(self) -> int:
        return self._proposal_count

    def propose(self, context: ResearchContext) -> Optional[ResearchProposal]:
        """Generate a single research proposal from context.

        Returns None if:
        - AI is unavailable
        - LLM returns invalid output
        - Proposal fails validation

        Args:
            context: Bounded research context (no secrets).

        Returns:
            Validated ResearchProposal or None.
        """
        if not self._provider.is_available():
            logger.info("AI provider unavailable, skipping proposal")
            return None

        # Build prompt
        prompt = self._build_prompt(context)

        # Call LLM
        try:
            system_prompt = get_system_prompt(self._prompt_version)
            response = self._provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=1500,
            )
        except Exception as e:
            logger.warning("LLM call failed: %s", str(e)[:200])
            return None

        # Parse structured output
        proposal = self._parse_response(response, context)
        if proposal is None:
            return None

        # Validate
        result = self._validator.validate(proposal)
        if not result.valid:
            logger.warning("AI proposal rejected: %s", "; ".join(result.errors))
            return None

        self._proposal_count += 1
        return proposal

    def propose_batch(
        self,
        context: ResearchContext,
        max_proposals: int = 5,
        temperature: float = 0.3,
        max_tokens: int = 3000,
    ) -> list[ResearchProposal]:
        """Generate multiple research proposals from context.

        Uses v2 prompt which requests JSON array output.
        All proposals are validated — invalid ones are silently dropped.

        Args:
            context: Bounded research context (no secrets).
            max_proposals: Maximum proposals to request.
            temperature: Sampling temperature for generation.
            max_tokens: Max tokens for response.

        Returns:
            List of validated ResearchProposals (may be empty).
        """
        if not self._provider.is_available():
            logger.info("AI provider unavailable, skipping batch proposal")
            return []

        # Build prompt with explicit count request
        prompt = self._build_batch_prompt(context, max_proposals)

        # Call LLM
        try:
            system_prompt = get_system_prompt(self._prompt_version)
            response = self._provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning("LLM batch call failed: %s", str(e)[:200])
            return []

        # Parse multiple proposals
        proposals = self._parse_batch_response(response, context)
        if not proposals:
            return []

        # Validate each proposal
        valid_proposals: list[ResearchProposal] = []
        for proposal in proposals:
            result = self._validator.validate(proposal)
            if result.valid:
                valid_proposals.append(proposal)
                self._proposal_count += 1
            else:
                logger.info("AI batch proposal rejected: %s", "; ".join(result.errors[:3]))

        # Deduplicate by content_hash
        seen_hashes: set[str] = set()
        deduplicated: list[ResearchProposal] = []
        for p in valid_proposals:
            if p.content_hash not in seen_hashes:
                seen_hashes.add(p.content_hash)
                deduplicated.append(p)

        logger.info(
            "AI batch: %d raw, %d valid, %d unique proposals",
            len(proposals), len(valid_proposals), len(deduplicated),
        )
        return deduplicated[:max_proposals]

    def _build_prompt(self, context: ResearchContext) -> str:
        """Build the prompt from context. Never includes secrets."""
        parts = ["Research context:"]
        parts.append(context.to_prompt_section())
        parts.append("")
        parts.append("Propose a new research hypothesis as JSON:")
        return "\n".join(parts)

    def _build_batch_prompt(self, context: ResearchContext, max_proposals: int) -> str:
        """Build a prompt requesting multiple proposals."""
        parts = ["Research context:"]
        parts.append(context.to_prompt_section())
        parts.append("")
        parts.append(
            f"Propose up to {max_proposals} diverse research hypotheses as a JSON array. "
            f"Each hypothesis should explore a DIFFERENT mechanism or feature combination. "
            f"Avoid near-duplicates (same features with slightly different thresholds)."
        )
        return "\n".join(parts)

    def _parse_response(
        self, response: LLMResponse, context: ResearchContext
    ) -> Optional[ResearchProposal]:
        """Parse LLM response into a structured proposal."""
        content = response.content.strip()

        # Try to extract JSON from response
        try:
            # Handle markdown code blocks
            if "```" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    content = content[start:end]
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse AI response as JSON: %s", str(e)[:100])
            return None

        # If it's a list, take first element
        if isinstance(data, list):
            if not data:
                return None
            data = data[0]

        if not isinstance(data, dict):
            return None

        return self._dict_to_proposal(data, context)

    def _parse_batch_response(
        self, response: LLMResponse, context: ResearchContext
    ) -> list[ResearchProposal]:
        """Parse LLM response expecting a JSON array of proposals."""
        content = response.content.strip()

        # Extract JSON from response (handle markdown fences)
        try:
            if "```" in content:
                # Find the JSON content between fences
                start = content.find("[")
                if start < 0:
                    start = content.find("{")
                end = content.rfind("]") + 1
                if end <= 0:
                    end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    content = content[start:end]
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse AI batch response as JSON: %s", str(e)[:100])
            # Try to salvage individual objects
            return self._salvage_json_objects(content, context)

        # Handle single object or array
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            return []

        proposals: list[ResearchProposal] = []
        for item in data:
            if isinstance(item, dict):
                proposal = self._dict_to_proposal(item, context)
                if proposal is not None:
                    proposals.append(proposal)

        return proposals

    def _salvage_json_objects(
        self, content: str, context: ResearchContext
    ) -> list[ResearchProposal]:
        """Attempt to extract individual JSON objects from malformed response."""
        proposals: list[ResearchProposal] = []
        depth = 0
        start = -1

        for i, ch in enumerate(content):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        data = json.loads(content[start:i + 1])
                        if isinstance(data, dict):
                            proposal = self._dict_to_proposal(data, context)
                            if proposal is not None:
                                proposals.append(proposal)
                    except (json.JSONDecodeError, ValueError):
                        pass
                    start = -1

        return proposals

    def _dict_to_proposal(
        self, data: dict[str, Any], context: ResearchContext
    ) -> Optional[ResearchProposal]:
        """Convert a parsed dict into a ResearchProposal.

        Never executes content — only maps structured fields.
        """
        # Build proposal from parsed data
        conditions = data.get("conditions", [])
        if conditions and isinstance(conditions, list):
            conditions = tuple(conditions)
        else:
            conditions = ()

        feature_ids = data.get("feature_ids", [])
        if isinstance(feature_ids, list):
            feature_ids = tuple(feature_ids)
        else:
            feature_ids = ()

        # Extract extended metadata (v2)
        constraints: dict[str, Any] = {}
        if data.get("novelty_reason"):
            constraints["novelty_reason"] = str(data["novelty_reason"])[:500]
        if data.get("expected_mechanism"):
            constraints["expected_mechanism"] = str(data["expected_mechanism"])[:500]

        try:
            confidence = float(data.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
        except (TypeError, ValueError):
            confidence = 0.0

        return ResearchProposal(
            source=ProposalSource.AI,
            status=ProposalStatus.DRAFT,
            phase=ResearchPhase.EXPLORATION,
            market_type=str(data.get("market_type", "")),
            feature_ids=feature_ids,
            conditions=conditions,
            direction=str(data.get("direction", "")),
            operator_type=str(data.get("operator_type", "")),
            model_type=str(data.get("model_type", "")),
            model_parameters=data.get("model_parameters", {}) if isinstance(data.get("model_parameters"), dict) else {},
            rationale=str(data.get("rationale", ""))[:1000],
            confidence=confidence,
            constraints=constraints,
            prompt_version=self._prompt_version,
            context_hash=context.content_hash,
        )
