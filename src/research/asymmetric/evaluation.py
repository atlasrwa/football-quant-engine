"""SymmetricBaseline and AsymmetryEvaluator — decisive asymmetry test.

Responsibility:
    SymmetricBaseline uses the same modelling family but only the team's own
    marginal rate, with no interaction layer. AsymmetryEvaluator drives
    walk-forward CV folds to compare the Interaction_Model against the
    Symmetric_Baseline out-of-sample per market and per league, applies the beat
    criterion (BSS improvement with 95% CI lower bound > 0), enforces
    within-league significance at alpha 0.05, labels pooled-only significance as
    an artifact and below-minimum samples as insufficient-sample, and corrects
    within-league significance against a fresh FDR family via Benjamini-Hochberg
    at q=0.05.

Scaffold only — the evaluator is implemented in task 9.
"""
