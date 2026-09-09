# Prospective live-capture activation — deliverables report

Branch: `research/prospective-live-capture` · Baseline SHA: `ab883da64` (PR #6 merge)

Phase goal: activate/validate the PR #6 capture system and build the leakage-safe
mechanism to observe how football information enters the market through time
(price discovery), for the research question: *can info at T-24h/T-6h/T-60m/T-15m
predict subsequent market movement?* This is data acquisition + infrastructure,
NOT a champion experiment. Champion untouched; PR opened, not merged.

## 40-item deliverables

1. **Baseline SHA.** `ab883da64` (verified `git rev-parse HEAD`; log shows PR #6 merge).
2. **Branch.** `research/prospective-live-capture` (from clean current main; preserved edits intact).
3. **Live llms.txt verification date.** Re-fetched this session; header/auth/rate-limit contract byte-for-byte consistent with the PR #6 snapshot.
4. **API contract changes since PR #6.** None. Base URL `…/api`, Bearer auth, `X-RateLimit-*` + `X-Monthly-Quota-*` budgets, 429 `RATE_LIMITED`/`USAGE_LIMIT_EXCEEDED` with `Retry-After` — all unchanged.
5. **Live credentials available?** No. `THESTATSAPI_API_KEY` unset ⇒ **LIVE_VALIDATION_BLOCKED_NO_API_KEY**.
6. **Live endpoints actually exercised.** None (no key). The client fails closed (verified: `capture-odds` exits rc=2, no request).
7. **Sanitized live response-shape findings.** N/A live. Contract-level shapes validated by schema validators + injected-transport tests.
8. **Identity validation results.** Stable-id discipline enforced in code (stable `mt_/tm_/pl_/comp_/sn_` ids; no name joins). Live cross-endpoint fixture-id equality not verifiable without a key.
9. **Bookmaker coverage.** From corpus: goals O/U 2.5 ~100%, corners O/U 9.5 92-100% across the 5 major leagues. Live per-book (Pinnacle/Bet365) coverage not verifiable without a key; collector now tags bookmaker per odds observation so coverage will be measurable once live.
10. **Market coverage.** goals totals, corners totals, BTTS, 1X2, Asian handicap are all documented; over/under extraction implemented for goals/corners/cards/shots.
11. **Lineup payload findings.** Contract: confirmed XI ~1h pre-kickoff, 404 until announced, NO capture timestamp ⇒ trustworthy time is our first observed_at. Normalizer enforces this (PR #6).
12. **First-lineup timing findings.** Not observable without live capture; the quality report computes median first-lineup seconds-to-kickoff once data exists.
13. **Injuries/suspensions semantics.** Endpoints exist with explicit `status`/`reason`/`active`/dates; provider CURRENT-STATE (no per-record observation timestamp). Stored as observed with OUR retrieval time; absence never inferred as injury.
14. **Referee/context findings.** `/matches/{id}/referee` returns identity + career summary (career is current-state ⇒ leak risk if used historically; captured for identity/provenance only this phase).
15. **Rate-limit/quota findings.** Two budgets parsed; conservative pause on low/unknown/exhausted; honours `Retry-After`.
16. **Estimated request budget.** ~14 requests/fixture, ~560/day, ~16,800/month for the proposed schedule (see `prospective_capture_budget.json`). Sustainable ≥~17k/month; not on a 10k trial (documented reduced schedule).
17. **Capture scheduling policy.** Adaptive density: sparse near EARLY, frequent near/through the lineup window; per-vintage due windows; lineup polling from the LATE window until first observed.
18. **Vintage tolerances.** Fixed, pre-registered (`DEFAULT_TOLERANCES`): EARLY 3h/8h, MID 90m/3h, LATE 20m/45m, FINAL 10m/20m (on/near). Not tuned on results.
19. **Restart/recovery design.** Scheduler is a pure function of the persisted store + now; a fresh instance reconstructs captured vintages/lineup state from disk; no in-memory correctness dependency; never rewrites observations.
20. **Genuine-close semantics.** Latest OUR prospective snapshot with observed_at < kickoff, same book/market/selection/line; explicit `NO_GENUINE_CLOSE` reasons; never `last_seen`.
21. **Price-discovery row schema.** `PriceDiscoveryRow` (fixture/league/kickoff, market/selection/line/bookmaker, vintage/observed_at/seconds_to_kickoff, p_market/logit, fundamental+disagreement, lineup/injury/referee availability + deltas, later-market + move target, final pre-kickoff, optional outcome).
22. **CLV/movement semantics.** Logit-space, same-book/same-line only; `signed_clv = sign(disagreement) * (later_logit - current_logit)`; line movement tracked separately; not called profit.
23. **Data-quality report.** JSON+MD: fixtures discovered/mapped, per-vintage coverage %, bookmaker %, lineup %, median first-lineup STK, genuine-close %, referee/injury %, health, readiness counts.
24. **Tests run/results.** 32 new phase tests + 61 PR #6 tests = 93 prospective tests pass; anti-leakage + champion regression (54) pass.
25. **Adversarial-review findings/fixes.** 28 checks (`prospective_live_capture_adversarial.md`). Reproduced+fixed: odds concept now carries bookmaker (was un-attributable).
26. **Champion diff verification.** `git diff main -- src/research/models/ src/research/calibration.py` empty.
27. **Unrelated working-tree edits survived.** The 4 preserved files remain modified-and-unstaged throughout.
28. **Exact operational command(s).** `python -m src.research.prospective.cli capture-due --hours 30 [--max-requests N]` (preferred; restart-safe); also `capture-upcoming`, `capture-odds --match ...`, `capture-lineups --match ...`, `quality-report`.
29. **Fixtures prospectively captured.** 0 (no key / no run).
30. **With multi-vintage odds.** 0.
31. **With confirmed lineup.** 0.
32. **With genuine pre-kickoff close.** 0.
33. **LIVE_CAPTURE readiness.** **LIVE_CAPTURE_BLOCKED** — code + tests are ready but no API key is available to run live.
34. **PRICE_DISCOVERY readiness.** **PRICE_DISCOVERY_NOT_ENOUGH_DATA** — 0 observations.
35. **Known limitations.** No live key here; injuries/referee are provider current-state (no provider timestamp); lineup payloads carry no capture time (mitigated by our observed_at); real fixture load is lumpy (weekend-heavy) vs the flat budget assumption.
36. **Recommended next action.** Provision the API key in the expected env and run `capture-due` on an external scheduler (cron/systemd-timer) every ~15-20 min across the initial universe; monitor `quality-report`; begin descriptive movement/CLV diagnostics once multi-vintage observations accumulate (report sample sizes; promote nothing).

### Pre-registered readiness minimums (fixed BEFORE any data)

- ≥ 300 fixtures captured, AND
- ≥ 200 fixtures with a valid same-bookmaker LATE → FINAL transition, AND
- ≥ 150 fixtures with a confirmed lineup observed before FINAL.

These are minimums for a first serious analysis, not guarantees of statistical
power; small expected effects will require more.

## Operational scheduler recommendation

No permanently running daemon. Use an external scheduler to invoke the
restart-safe command periodically:

```
*/15 * * * *  python -m src.research.prospective.cli capture-due --hours 36
```

`capture-due` discovers upcoming fixtures, computes only the work due from
persisted state, respects the request budget, persists append-only, and is safe
to rerun after a crash.

## Success criterion

Success is a trustworthy mechanism to observe how information enters the market
through time — not a profitable model. That mechanism now exists in code and is
fully tested; it is blocked only on live credentials. If no alpha eventually
appears, that is an acceptable research result.
