# Data-driven prospective capture universe — final report

Branch: `research/prospective-live-capture` (PR #7) · Baseline main: `ab883da64`
· Head: `5cd77e87e`

Replaces the temporary five-major-league universe with a verified, data-driven
competition universe over every FootyStats-supported league. Champion untouched;
PR not merged.

## 35-item report

1. **FootyStats-supported competitions:** 49 (authoritative source: the
   `leagues` array in `data/discovery/provider_league_registry.json`; the
   corpus holds only a 25-league subset — all present in the registry).
2. **With existing explicit TheStatsAPI mapping:** 46 (`mapping_status == MATCHED`, each with exactly one comp id).
3. **Newly mapped this phase:** 0 new identity mappings created — the registry's reviewed crosswalk already provides Level-A evidence; this phase consumes it (no competing identity truth) and adds live coverage.
4. **VERIFIED:** 46 (single MATCHED comp id confirmed via the canonical-registry link).
5. **PROBABLE:** 0.
6. **AMBIGUOUS:** 2 (Mexico Liga MX — apertura/clausura split, two comp ids; Colombia Categoria Primera A — SPLIT_OR_PARTIAL). Never auto-joined.
7. **UNRESOLVED:** 0 (the ambiguous two are surfaced as AMBIGUOUS).
8. **API_UNSUPPORTED:** 1 (Poland 1. Liga — registry BLOCKED, no comp id).
9. **CAPTURE_READY:** 9 (fixtures near enough to have live odds at scan time).
10. **CAPTURE_PARTIAL:** 37 (VERIFIED, registry odds_available true, but odds not yet posted on the probed fixture — 36/37 odds-404, 1 no fixture in scan).
11. **MARKET_COVERAGE_INSUFFICIENT:** 0.
12. **Crosswalk artifact:** `research/evaluation/prospective_crosswalk.json`.
13. **Coverage matrix artifact:** `research/evaluation/prospective_coverage_matrix.json` (+ `.md`).
14. **Each CAPTURE_READY league (priority · Pinnacle):** Bundesliga (P1·yes), Premier League (P1·yes), Ligue 1 (P1·yes), Serie A (P1·yes), Iceland Úrvalsdeild (P1·yes), Scotland Premiership (P2·no), Netherlands Eredivisie (P2·no), Austria Bundesliga (P2·no), Brazil Serie A (P2·no).
15. **Market eligibility by league:** per-market {READY/PARTIAL/UNSUPPORTED/UNKNOWN} for total_goals, match_corners, total_cards, match_shots_on_target — stored per row in the coverage matrix. READY leagues show total_goals READY (some + shots-on-target); other champion markets PARTIAL (registry odds true, not priced on the single probe).
16. **Bookmaker coverage by league:** recorded per row. The five P1 READY leagues carry Pinnacle + Bet365 + Betfair + Paddy Power; P2 READY leagues carry Bet365 (+ Paddy Power for Austria/Brazil). Broader per-fixture book coverage is measured continuously at capture.
17. **Current-season mapping:** resolved live per VERIFIED comp via the seasons endpoint `is_current` flag (handles cross-year / calendar / summer / winter / split seasons without assuming Aug–May).
18. **Live reconnaissance request count:** 137 (coverage scan), well under the 1,000 hard cap.
19. **Monthly quota after all live activity:** 97,183 / 100,000 remaining (≈2,817 used across recon + the capture run + probes).
20. **Revised requests/fixture:** ~17.3 (full lifecycle: 8 odds snapshots + 4 lineup polls + 2 injuries + 1 referee + amortised discovery/monitoring + 10% retries) — NOT the naive odds-only figure.
21. **Projected monthly consumption:** ≈43,175 requests at 2,500 active fixtures/month.
22. **Reserve / headroom:** hard 20% reserve ⇒ usable 80,000/month; capacity ≈4,632 fixtures/month; headroom ≈36,825 requests at the 2,500-fixture projection. `QuotaGuard` refuses new work below the 20,000 reserve floor and pauses on per-minute exhaustion.
23. **Dynamic activation policy:** `ACTIVE = identity==VERIFIED AND classification in {CAPTURE_READY, approved CAPTURE_PARTIAL}`; keyed on the stable `thestatsapi_competition_id`; carries per-league eligible markets; deterministic + unit-tested. Default operational choice: activate READY+PARTIAL (46) — the scheduler captures per-fixture only when odds actually exist, so PARTIAL leagues cost nothing until their fixtures approach kickoff.
24. **Discovered fixtures by league (live capture-due --hours 96):** 248 total across 46 comps (e.g. MLS 26, England Championship 14, EFL L1/L2 12 each, Saudi Pro League 9, Japan J1 8, Ligue 2 8, Serie B 8; full breakdown in the run output).
25. **Due fixtures by league:** 16 total (MLS 14, Czech First League 1, Finland Veikkausliiga 1) — the fixtures that had entered the EARLY (~16–32h) window.
26. **Health state:** HEALTHY (fixtures discovered and some due + captured). The collector also reports HEALTHY_WAITING_FOR_VINTAGE (discovered, none due) and NO_UPCOMING_FIXTURES (empty universe) explicitly.
27. **Coverage-bias funnel:** 49 FootyStats → 46 VERIFIED → 9 CAPTURE_READY (this scan) → 16 fixtures captured (this run) → 0 with confirmed lineup / same-book movement yet (nothing has reached the LATE window). Reported via `coverage_funnel` + nested analysis-support strata so a large captured count is never mistaken for usable paired-transition N.
28. **Tests:** 127 prospective tests pass (46 new this phase across crosswalk/coverage/activation/quota/funnel/adversarial); anti-leakage + champion regression (54) pass.
29. **Adversarial-review fixes:** 30 checks (`prospective_universe_adversarial.md`); confirmed the earlier odds bookmaker-attribution fix and per-league eligible-market filtering; all identity/coverage/quota/safety vectors guarded with regression tests.
30. **Champion diff:** `git diff main -- src/research/models/ src/research/calibration.py` empty.
31. **Unrelated working-tree safety:** `data/forward/*.jsonl` and `data/discovery/provider_league_registry.json` remain modified-and-unstaged throughout; `.env`/live capture data never staged.
32. **PR head SHA:** `5cd77e87e`.
33. **PR mergeability:** clean/mergeable against main (verify on GitHub after push).
34. **Remaining operational limitations:** classification is a point-in-time snapshot (37 PARTIAL leagues will promote to READY as their fixtures near kickoff and odds post); lineup/injury/referee coverage not yet observed (nothing in the LATE window this run); Mexico/Colombia stay AMBIGUOUS pending split-season disambiguation; real fixture load is weekend-heavy vs the flat monthly projection.
35. **Recommended scheduler cadence:** `*/15 * * * * python -m src.research.prospective.cli capture-due --hours 96` (restart-safe; captures only due work; reserve-aware). Re-run `scripts/prospective_coverage_scan.py` weekly to refresh READY/PARTIAL classification as seasons/fixtures move.

## Success criterion

Every supported FootyStats competition has been examined; identity uncertainty
is explicit (46 VERIFIED, 2 AMBIGUOUS, 1 API_UNSUPPORTED); and every league
worth spending prospective quota on enters capture automatically under
deterministic rules. Quota is no longer the reason to restrict research — the
full 46-league universe fits comfortably within the 20%-reserved budget. The
number of active leagues is an OUTPUT of data quality, not a tuned target.
