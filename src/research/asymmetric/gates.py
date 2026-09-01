"""FeatureVerificationGate and SanityGate — mandatory pre-modelling gates.

Responsibility:
    FeatureVerificationGate runs five checks before any modelling (team-identity
    trace, known-signal, orientation, look-ahead, shuffle-null), reports every
    check, and stops before modelling on any failure. SanityGate records (without
    re-diagnosing) known structural non-persistence results per league and per
    target (corners near-zero team-level persistence; cards disciplinary
    persistence absent in the Championship across three seasons).

Scaffold only — the gates are implemented in task 8.
"""
