# MARKET PRIOR + INDEPENDENT FUNDAMENTAL + FIXTURE INFO DELTA — findings

Branch: `research/market-residual-lineup-alpha` · Baseline SHA: `184f09d6d989133c768c2fb53c544f2a09cafbb0`

**Outcome: INFRASTRUCTURE_READY / PROSPECTIVE_DATA_REQUIRED.**

This is a research / data-plane PR. It builds the leakage-safe architecture to
answer whether the engine improves on the market prior and whether confirmed
lineup/player state adds value. The champion is not modified and nothing is
promoted.

---

## Information-value table (historical M0-M4, discovery corpus)

Scored on a single common-support set per family; earlier chronological half
trains M1/M2/M4, later half is evaluated. Lower log loss / Brier is better;
resolution higher is better; calibration slope target ≈ 1.

### Goals — Over 2.5 (n_common = 3842)

| Layer | Δ LogLoss (vs prev) | LogLoss | Brier | Calib. slope | Resolution |
|-------|--------------------:|--------:|------:|-------------:|-----------:|
| M0 Climatology | — | 0.6913 | 0.2491 | 1.00 | 0.0000 |
| M1 Team/league | -0.0013 | 0.6900 | 0.2484 | 0.90 | 0.0014 |
| M2 Champion fundamentals | +0.0004 | 0.6904 | 0.2483 | 0.69 | 0.0041 |
| M3 Market prior | **-0.0142** | **0.6762** | **0.2417** | 1.03 | 0.0075 |
| M4 Market + fundamental residual | +0.0274 | 0.7036 | 0.2536 | 0.49 | 0.0032 |
| + confirmed lineup delta (M5) | — | — | — | — | **HISTORICAL PIT UNSUPPORTED** |
| + referee/context (M6) | — | — | — | — | prospective-only |

### Corners — Over 9.5 (n_common = 3583)

| Layer | Δ LogLoss (vs prev) | LogLoss | Brier | Calib. slope | Resolution |
|-------|--------------------:|--------:|------:|-------------:|-----------:|
| M0 Climatology | — | 0.6973 | 0.2521 | 0.97 | 0.0000 |
| M1 Team/league | +0.0043 | 0.7016 | 0.2539 | 0.70 | 0.0009 |
| M2 Champion fundamentals | +0.0022 | 0.7038 | 0.2543 | 0.60 | 0.0032 |
| M3 Market prior | **-0.0175** | **0.6863** | **0.2466** | 0.96 | 0.0040 |
| M4 Market + fundamental residual | +0.0534 | 0.7397 | 0.2682 | 0.28 | 0.0018 |
| + confirmed lineup delta (M5) | — | — | — | — | **HISTORICAL PIT UNSUPPORTED** |
| + referee/context (M6) | — | — | — | — | prospective-only |

**Reading.** The market prior (M3) is the single best layer on both families.
The champion (M2) does not beat the market. The naive residual (M4, one
disagreement feature) DEGRADES log loss/Brier and collapses calibration slope —
the fundamental-minus-market disagreement carries little exploitable historical
signal at these lines. These numbers were NOT tuned on the evaluation set.

---

## 23-item deliverables report

1. **Live llms.txt capabilities verified.** Base URL `…/api`; Bearer auth;
   `X-RateLimit-*` + `X-Monthly-Quota-*` budgets; endpoints for matches,
   match detail, stats, player-stats, lineups, odds, odds/live, referee,
   player stats, team players, and (newly noted) injuries-suspensions; odds
   bookmakers Bet365/Paddy Power/BetMGM UK/Pinnacle/Betfair Exchange with
   `opening`/`last_seen` (no timestamp); stats missing periods = `null`.
2. **Discrepancies from current implementation.** (a) base URL missing `/api`
   in the legacy client; (b) legacy client authenticates via query param, docs
   require Bearer header; (c) legacy client parses only `Retry-After`, not the
   two rate-limit budgets; (d) legacy endpoint strings predate this
   verification; (e) injuries-suspensions endpoints exist but were unwired.
   All documented in `api_contract.KNOWN_DISCREPANCIES`; legacy client left
   intact for backward compat; prospective plane uses corrected settings and
   only the verified `Endpoint` enum; fails closed.
3. **Baseline SHA.** `184f09d6d989133c768c2fb53c544f2a09cafbb0`.
4. **Branch.** `research/market-residual-lineup-alpha`.
5. **Files added/changed.** New package `src/research/prospective/*` (17 modules),
   `scripts/prospective_historical_eval.py`, tests under
   `tests/research/prospective/*`, `.gitignore` for `data/prospective/` and
   `research/evaluation/`, small artifacts in `research/evaluation/`. No
   champion / existing-source files changed.
6. **Commits.** `08d14a846` (infra + tests + CLI + gitignores);
   `dd45627f2` (M0-M4 historical decomposition + adversarial review);
   plus this report commit.
7. **Tests / results.** 61 new prospective tests pass; existing champion and
   anti-leakage regression suites still pass; champion diff vs main is empty.
8. **Prospective capture architecture.** Append-only `CaptureRecord` →
   `ProviderObservation` (reusing the observation layer) persisted as
   idempotent JSONL(.gz); replayable into an `ObservationStore` for PIT queries.
   Read-only Bearer client fails closed without a key and never exposes it.
9. **Odds timestamp semantics.** `API_OPENING` (usable as opening only),
   `API_LAST_SEEN` (NOT a close — no timestamp), `PROSPECTIVE_SNAPSHOT` (our
   own timestamped capture), `PROSPECTIVE_LAST_BEFORE_KICKOFF` (genuine close =
   latest own snapshot with `observed_at < kickoff`). De-vig kept independent
   of collection; preregistered benchmark hierarchy Pinnacle>Bet365>…; no
   best-price cherry-picking.
10. **Lineup timestamp semantics.** The live lineups endpoint carries NO
    capture timestamp; confirmed XI appears ~1h before kickoff. Only OUR
    prospective retrieval time is a trustworthy `observed_at`; a normalized
    lineup without it is flagged `not pit_usable`. Missing lineup → `None`
    (fails neutrally), never an empty XI.
11. **Player-state methodology.** Rolling per-90 rates from per-match
    observations only, strictly `kickoff < cutoff`; season aggregates are never
    used as historical features; zero-minute denominator → `None` (not 0);
    missing counts stay missing; identity keyed by stable `player_id` across
    transfers.
12. **Market-prior implementation.** `MarketPrior` with fair probability,
    benchmark bookmaker, raw odds, vig method, `observed_at`, age vs cutoff,
    source, and availability `NO_MARKET` / `STALE_MARKET` / `VALID_MARKET`.
13. **Fundamental-disagreement implementation.** `FundamentalForecast` wraps the
    champion (unmodified); `Disagreement` = `fundamental_logit − market_logit`,
    aligned on (fixture, market, line, selection); `available=False` when the
    market is unusable so the residual can shrink to market.
14. **Residual-model implementation.** Ridge-logistic with the market logit as a
    fixed offset: `logit(p_final) = logit(p_market) + λ·delta`. `fit_intercept`
    defaults off, so all-missing/zero features reproduce the market exactly;
    L2 shrinks coefficients toward zero (toward the market); standardization
    frozen at fit; no XGBoost / neural nets.
15. **Information-decomposition results.** See table above. M3 (market) best;
    M2 (champion) does not beat market; M4 residual degrades. M5 unsupported
    historically; M6 prospective-only.
16. **Calibration results.** Market layer near-calibrated (slope ≈ 1.0 / 0.96);
    champion under-confident (slope 0.60–0.69); the naive residual worsens
    calibration (slope 0.28–0.49), consistent with over-extrapolation of a
    weak signal.
17. **Resolution results.** Reported via std/IQR of p, fraction confident, and a
    Murphy uncertainty/resolution/reliability decomposition. Resolution is tiny
    for all layers at these lines; the market has the highest among them. No
    layer is rewarded for shrinking to 0.5.
18. **Historical limitations.** No timestamped historical lineups (M5
    unsupported). Corpus odds are pre-match/opening-grade only — used as such,
    never as a genuine close. No prospective snapshot series exists yet, so
    market-movement and CLV are not computable historically.
19. **Prospective-only components.** Market movement between vintages, CLV
    directional evaluation, confirmed-lineup delta (M5), and referee/context
    (M6). Their code and tests exist; they require prospective capture to run.
20. **Adversarial-review findings.** 20 checks documented and regression-tested
    (`prospective_adversarial_review.md`). One reproduced issue: residual
    over-shift when a global intercept was fit by default — fixed by
    `fit_intercept=False` default. No leakage, key-exposure, or champion-
    modification issues found.
21. **Operational capture commands.**
    `python -m src.research.prospective.cli capture-upcoming --hours 30`,
    `… capture-odds --match mt_…`, `… capture-lineups --match mt_…`. Append-only,
    records exact retrieval time, handles unavailable data, respects rate
    limits, logs no secrets, fails closed without a key; scheduler-friendly.
22. **Exact data we still cannot obtain.** (a) Genuine closing lines
    historically (no timestamped odds); (b) timestamped historical confirmed
    lineups (endpoint has no capture time); (c) the actual availability reason
    for a non-start (recorded as `UNKNOWN` unless the explicit
    injuries-suspensions endpoint states it, which is itself current-state, not
    PIT); (d) any live API responses in this environment (no API key present).
23. **Recommendation for next research phase.** Run the prospective collector on
    a scheduler across supported upcoming fixtures to accumulate timestamped
    odds and confirmed-lineup snapshots. Once a few hundred fixtures of
    multi-vintage snapshots exist, (a) evaluate M5 (confirmed-lineup delta) with
    provable PIT availability, (b) compute CLV/market-movement, and (c) re-fit
    the residual with richer, prior-only lineup/context features and select λ/L2
    on a held-out portion of the TRAINING split. Do not promote the champion or
    trust `last_seen` as a close.

---

## Scope guardrails honoured

Champion unchanged · no new data provider · no injury inferred from absence ·
`last_seen` never treated as close · odds require timestamp provenance for a
close · no future season aggregates · confirmed XI not used for historical
EARLY forecasts · no black-box model · thresholds fixed, not tuned on test ·
no ROI claims · **PR opened, not merged.**
