"""Batch 4 — Hypothesis Search & Experiment Engine.

Transforms candidates into controlled experiments that produce
statistical evidence about predictive relationships.

Pipeline:
    ResearchCandidate → ResearchHypothesis → ExperimentConfig
    → ResearchDataset → TemporalSplit → ExperimentRunner
    → ExperimentResult → StatisticalEvidence → Classification

This module does NOT:
- Claim profitability
- Implement AI/LLM
- Connect to FootyStats
- Implement persistent storage
- Implement production deployment

It produces RESEARCH EVIDENCE only.
"""
