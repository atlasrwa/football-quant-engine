# QFE V2.1 — Hierarchical State-Space Stage 1 Protocol

Status: **PREREGISTERED / DEVELOPMENT ONLY**

This experiment tests a new odds-blind latent strength estimator against the frozen QFE V2 dynamic hierarchy.

The central structural change is that cross-competition team strength is represented as a **residual relative to the competition environment in which the observation occurred**. It is never formed as a ratio against the universal global count rate. A competition-specific local residual is then layered on top.

The challenger uses Gaussian log-intensity state dynamics, Poisson likelihoods, Laplace posterior updates, same-kickoff batch aggregation, and explicit posterior variance.

Only WARMUP state updates and DEVELOPMENT D1-D4 outcomes may be used. CALIBRATION and PROTECTED outcomes are forbidden in Stage 1. Market prices and LLM calls are forbidden.

Three fixed candidate profiles are preregistered: CONSERVATIVE, BALANCED and RESPONSIVE. The grid may not be expanded after results are observed.

Primary selection metric is fixture-mean side Poisson NLL. A candidate must also win that metric in at least 3/4 chronological folds and avoid material fixed-line binary-LL regression. Stage 1 cannot directly promote a production model.
