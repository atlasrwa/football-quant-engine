"""Batch 5 — FDR Integration for Research Discovery.

Bridges the research walk-forward results to the frozen FDRController.
Does NOT recreate FDR logic — adapts research-layer outputs to the
existing Benjamini-Hochberg interface.

Key concepts:
- Research Family: group of hypotheses corrected together
- FDR Input: p-values from walk-forward validation
- FDR Result: adjusted significance with family context
"""

from src.research.fdr.adapter import FDRAdapter, FDRHypothesisResult, ResearchFDRResult
from src.research.fdr.family import ResearchFamily, ResearchFamilyBuilder

__all__ = [
    "FDRAdapter",
    "FDRHypothesisResult",
    "ResearchFDRResult",
    "ResearchFamily",
    "ResearchFamilyBuilder",
]
