# QFE Reboot Hygiene Record

Date: 2026-10-01 (America/Bogota)

This record defines the first code-hygiene pass after adoption of
QUANT_FOOTBALL_SOURCE_OF_TRUTH.md V2.

## Safety boundary

The cleanup applies to the future main tree only.

The following live/prospective runtimes are protected and were not edited,
reconfigured, restarted, stopped or repointed:

- V3.7 Future50: /home/ubuntu/handoff_out/v37_future50
  - frozen runtime commit: 207290cbaa026b6af0cfa60a1b14cdc90568c695
  - archival branch: runtime/v37-future50-frozen
- V3.8 Paired50: /home/ubuntu/handoff_out/v38_paired50
  - frozen runtime commit: 9a19feb6c991ae3b7bd4e23127e47fb9c8e6cca6
  - archival branch: runtime/v38-paired50-frozen
- V3 legacy settlement-only runner:
  /home/ubuntu/handoff_out/v3_live_pilot
  - commit: f60ef8a5310e85daf3bf9f0f5d1bf101c40bbd31

The existing cron schedule is outside this cleanup and remains unchanged.

As of Foundation V1, these isolated runtimes are **not active QFE products**.
The legacy CHAMPION product is deprecated; QFE V2 on `main` is the sole forward
product path. The runtimes above remain isolated only to preserve/settle their
pre-existing prospective experiments.

## Retained reboot primitives

The future main tree keeps only code with a direct path to Source of Truth V2:

1. TheStatsAPI cached evidence adapter, normalization, ids and provenance.
2. One verified live TheStatsAPI request path in prospective capture.
3. Provider-neutral canonical identity primitives.
4. Point-in-time provider observations and append-only observation storage.
5. Immutable fixture and over/under odds contracts.
6. No-vig conversion, including multiplicative and Shin sensitivity methods.
7. Core probability abstractions and probability-quality evaluation.
8. Calibration mapping primitives: Platt and isotonic. They do not own model fitting.
9. Candidate statistical primitives:
   - Dixon-Coles;
   - Poisson / negative-binomial count regression;
   - hierarchical count model;
   - latent dynamic team state.
10. Prospective infrastructure with direct future value:
   - verified API contract and capture;
   - quota and availability capture;
   - odds capture;
   - one vintage/cutoff contract;
   - append-only storage;
   - quality and scheduler health;
   - lineup/player/referee state normalization;
   - genuine close and CLV-style evaluation.
11. Focused regression tests and explicit reboot architecture guards.

Retention is not model promotion. Existing model primitives are unvalidated
candidates until they pass the new chronological OOS and calibration protocol.

## Removed from future main

The following were removed because they do not belong to the deterministic
market-disagreement reboot or are superseded experiment-specific apparatus:

- all LLM/Bedrock research code;
- LLM agents, prompts, proposal and hypothesis-discovery infrastructure;
- legacy experiment-engine/hypothesis framework;
- asymmetric-directional research apparatus;
- FootyStats-specific research implementation;
- provider-blending/reconciliation policies;
- fuzzy identity suggestion code;
- legacy TheStatsAPI HTTP client with superseded endpoint/auth semantics;
- legacy TheStatsAPI odds/closing adapters scoped to goals + 1X2 + BTTS;
- old all-markets registry including BTTS, 1X2 and offsides targets;
- old hard-coded disagreement detector and 2/5 pp thresholds;
- old dual-provider coverage/crosswalk/universe apparatus;
- duplicate forward-vintage implementation;
- duplicate legacy closing/CLV package;
- old calibrated-model wrapper that internally split model/calibration data;
- old forward/paper-trading orchestration;
- Pilot C scripts and reports;
- retired Telegram/broadcast machinery;
- in-play reconstruction experiments;
- same-game/correlation experiments;
- old market-first/EV/edge scanners;
- old multi-source discovery batteries;
- old provider-comparison experiment runners;
- old price-discovery and shadow/residual/market-prior experiments;
- old queue/governance/quarantine framework;
- product/API/auth/public-site code unrelated to the reboot;
- old SQL migrations and deployment files;
- generated or frozen research data committed to the old tree;
- historical phase reports and one-off analysis reports;
- obsolete tests whose only purpose was to protect removed subsystems.

These artifacts remain recoverable from Git history. Deleting them from main
does not rewrite or invalidate the historical experimental record.

## Hard reboot boundaries now enforced

- The independent ResearchMatch schema contains no bookmaker odds.
- The registered target-market capture contract is full-time goals, corners and
  cards/bookings only.
- Raw shots, shots-on-target and compatible half-level data may remain evidence;
  they are not target markets merely because the provider exposes them.
- The target selection contract is over/under only.
- Market movement may be used only in a separately labeled market-adjusted
  research arm, never in the independent odds-blind p_model.
- Calibration mappings must be fit externally on chronological OOF predictions.
- Provider data are not silently blended.
- Unsupported or post-cutoff information must fail closed.

## What the reboot still needs

Code hygiene deliberately does not pretend the successor engine already exists.
The next architecture still needs fresh, versioned implementations for:

1. Provider capability and target-settlement contracts, including bookings semantics.
2. A point-in-time historical dataset/feature builder that reconstructs each
   fixture strictly from earlier eligible evidence.
3. Dynamic target-specific attack/defence strengths with hierarchical shrinkage.
4. Explicit home, away and total target construction for goals, corners and bookings.
5. A conservative shrinkage baseline.
6. Structured count-model candidates selected by chronological OOS evidence.
7. A nonlinear tabular model with leakage-safe preprocessing and regularization.
8. Deterministic similar-opponent features/model.
9. Chronological fold orchestration and immutable component OOF prediction artifacts.
10. A constrained log-loss-optimized ensemble learned only from earlier OOF predictions.
11. Calibration fitting on OOF predictions, including beta calibration evaluation.
12. Calibration intercept, slope, reliability and probability-region support diagnostics.
13. Distribution diagnostics and coherent home/away/total dependence checks.
14. Deterministic out-of-distribution and support diagnostics.
15. Timestamp/horizon-matched no-vig market benchmark construction.
16. A new disagreement eligibility policy using calibration support, model
    consensus, OOD/support and sample depth—not gap size alone.
17. Separate global and disagreement-subset OOS scorecards.
18. A separately labeled market+QFE incremental-information experiment.
19. A new prospective shadow integration only after the offline/protected stack
    is frozen and accepted.

No protected V3/V3.7/V3.8 pilot result may be used to tune those components.
