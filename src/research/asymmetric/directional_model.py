"""DirectionalCountModel — elastic-net Poisson/NB count model.

Responsibility:
    One direction, one Per_Side_Target. Extends the reused count-regression MLE
    machinery: reuses the dispersion-driven Poisson/NB selection and reports the
    empirical dispersion ratio, replaces the L2-only penalty with an elastic-net
    penalty, removes the team-identity effect layer, and applies n/(n+k)
    shrinkage to per-team profile-feature estimates toward the global mean.
    Produces full predictive distributions and keeps coefficients readable for
    reporting.

Scaffold only — the model is implemented in task 4.
"""
