"""Research Context — bounded information for AI proposals.

Never dumps entire databases into prompts.
Context is configurable and bounded.
Never includes secrets.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from src.research.persistence.repository import ResearchRepository


@dataclass(frozen=True)
class ResearchContext:
    """Bounded research context for AI consumption.

    Contains only structured research history — never raw credentials,
    filesystem paths, or database connection strings.
    """

    market_type: str = ""
    available_features: tuple[str, ...] = ()
    available_markets: tuple[str, ...] = ()
    previous_candidates: tuple[dict[str, Any], ...] = ()
    previous_results: tuple[dict[str, Any], ...] = ()
    promising_hypotheses: tuple[dict[str, Any], ...] = ()
    rejected_hypotheses: tuple[dict[str, Any], ...] = ()
    dataset_summary: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    # Multi-season context (Batch 9)
    season_coverage: tuple[dict[str, Any], ...] = ()
    research_families: tuple[dict[str, Any], ...] = ()
    temporal_cutoff: Optional[float] = None  # Unix timestamp — context valid up to this point

    @property
    def content_hash(self) -> str:
        """Deterministic hash of context content."""
        canonical = json.dumps({
            "market_type": self.market_type,
            "features": sorted(self.available_features),
            "markets": sorted(self.available_markets),
            "n_previous": len(self.previous_candidates),
            "n_results": len(self.previous_results),
            "n_seasons": len(self.season_coverage),
            "temporal_cutoff": self.temporal_cutoff,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def to_prompt_section(self) -> str:
        """Format context as a prompt section for the AI."""
        parts = []
        parts.append(f"Market: {self.market_type}")

        if self.available_markets:
            parts.append(f"Available markets: {', '.join(self.available_markets)}")

        if self.available_features:
            features_display = self.available_features[:50]
            parts.append(f"Available features ({len(self.available_features)} total): {', '.join(features_display)}")
            if len(self.available_features) > 50:
                parts.append(f"  ... and {len(self.available_features) - 50} more")

        if self.dataset_summary:
            parts.append("\nDataset coverage:")
            for key, val in self.dataset_summary.items():
                if key not in ("field_coverage",):  # Skip verbose sub-dicts
                    parts.append(f"  {key}: {val}")

        if self.season_coverage:
            parts.append(f"\nSeasons ({len(self.season_coverage)}):")
            for s in self.season_coverage[:10]:
                parts.append(
                    f"  - {s.get('season', '?')}: {s.get('matches', '?')} matches, "
                    f"{s.get('date_range', '?')}"
                )

        if self.previous_results:
            parts.append(f"\nPrevious experiments ({len(self.previous_results)}):")
            for r in self.previous_results[:10]:
                parts.append(
                    f"  - {r.get('hypothesis_hash', '?')[:8]}: "
                    f"market={r.get('market_type', '?')}, "
                    f"classification={r.get('classification', '?')}, "
                    f"p_value={r.get('p_value', '?')}"
                )

        if self.rejected_hypotheses:
            parts.append(f"\nRejected hypotheses ({len(self.rejected_hypotheses)}) — DO NOT REPEAT:")
            for r in self.rejected_hypotheses[:10]:
                parts.append(
                    f"  - features={r.get('feature_ids', '?')}, "
                    f"direction={r.get('direction', '?')}, "
                    f"reason={r.get('rejection_reason', '?')}"
                )

        if self.promising_hypotheses:
            parts.append(f"\nPromising directions ({len(self.promising_hypotheses)}):")
            for p in self.promising_hypotheses[:5]:
                parts.append(
                    f"  - features={p.get('feature_ids', '?')}, "
                    f"direction={p.get('direction', '?')}, "
                    f"classification={p.get('classification', '?')}"
                )

        if self.research_families:
            parts.append(f"\nResearch families ({len(self.research_families)}):")
            for f in self.research_families[:5]:
                parts.append(
                    f"  - {f.get('family_id', '?')[:8]}: "
                    f"{f.get('hypothesis_count', 0)} hypotheses tested"
                )

        if self.constraints:
            parts.append("\nConstraints:")
            for key, val in self.constraints.items():
                parts.append(f"  {key}: {val}")

        return "\n".join(parts)


class ResearchContextBuilder:
    """Builds bounded research context from repository data.

    Never includes secrets. Always bounded.
    Supports multi-season research with temporal cutoff.
    """

    def __init__(
        self,
        repository: Optional[ResearchRepository] = None,
        max_candidates: int = 20,
        max_results: int = 10,
        max_hypotheses: int = 10,
    ) -> None:
        self._repo = repository
        self._max_candidates = max_candidates
        self._max_results = max_results
        self._max_hypotheses = max_hypotheses

    def build(
        self,
        market_type: str = "",
        available_features: Optional[list[str]] = None,
        available_markets: Optional[list[str]] = None,
        dataset_summary: Optional[dict[str, Any]] = None,
        season_coverage: Optional[list[dict[str, Any]]] = None,
        temporal_cutoff: Optional[float] = None,
    ) -> ResearchContext:
        """Build a bounded research context.

        Args:
            market_type: Target market for proposals.
            available_features: Features available for research.
            available_markets: Markets available for research.
            dataset_summary: Coverage summary from data source.
            season_coverage: Per-season coverage information.
            temporal_cutoff: Unix timestamp — only include context up to this point.

        Returns:
            ResearchContext (never contains secrets).
        """
        previous_candidates: list[dict[str, Any]] = []
        previous_results: list[dict[str, Any]] = []
        promising: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        families: list[dict[str, Any]] = []

        if self._repo:
            # Get recent candidates (bounded)
            candidates = self._repo.list_candidates(
                market_type=market_type, limit=self._max_candidates
            )
            previous_candidates = [
                {"hash": c.get("_hash", c.get("content_hash", "")), "market": c.get("market_type", "")}
                for c in candidates
            ]

            # Get experiment results (bounded)
            experiments = self._repo.list_experiments(limit=self._max_results) if hasattr(self._repo, "list_experiments") else []
            for exp in experiments[:self._max_results]:
                result_entry: dict[str, Any] = {
                    "hypothesis_hash": exp.get("hypothesis_hash", exp.get("_id", "")),
                    "market_type": exp.get("market_type", ""),
                    "classification": exp.get("classification", ""),
                    "p_value": exp.get("p_value"),
                }
                # Respect temporal cutoff
                if temporal_cutoff and exp.get("completed_at", 0) > temporal_cutoff:
                    continue
                previous_results.append(result_entry)

            # Get governance decisions for promising/rejected classification
            if hasattr(self._repo, "list_governance_decisions"):
                decisions = self._repo.list_governance_decisions(limit=self._max_hypotheses * 2)
                for d in decisions:
                    if temporal_cutoff and d.get("decided_at", 0) > temporal_cutoff:
                        continue
                    entry = {
                        "hypothesis_hash": d.get("hypothesis_id", ""),
                        "feature_ids": d.get("feature_ids", []),
                        "direction": d.get("direction", ""),
                        "classification": d.get("classification", ""),
                        "rejection_reason": d.get("rejection_reason", ""),
                    }
                    if d.get("classification") in ("REJECTED", "FDR_FAIL"):
                        rejected.append(entry)
                    elif d.get("classification") in ("WALK_FORWARD_VALIDATED", "FDR_VALIDATED", "QUARANTINE_ELIGIBLE"):
                        promising.append(entry)

        return ResearchContext(
            market_type=market_type,
            available_features=tuple(available_features or []),
            available_markets=tuple(available_markets or []),
            previous_candidates=tuple(previous_candidates[:self._max_candidates]),
            previous_results=tuple(previous_results[:self._max_results]),
            promising_hypotheses=tuple(promising[:self._max_hypotheses]),
            rejected_hypotheses=tuple(rejected[:self._max_hypotheses]),
            dataset_summary=dataset_summary or {},
            season_coverage=tuple(season_coverage or []),
            research_families=tuple(families),
            temporal_cutoff=temporal_cutoff,
        )
