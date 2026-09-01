"""DerivedOutcomeCombiner — match-level outcomes from per-side distributions.

Responsibility:
    Combine the two directions' predictive distributions to produce match-level
    Derived_Outcomes (total corners/cards/goals via discrete convolution,
    both-teams-to-score, and clean sheet per side) under an explicitly stated
    independence assumption emitted alongside each outcome. Never models any
    Derived_Outcome directly.

Scaffold only — the combiner is implemented in task 6.1.
"""
