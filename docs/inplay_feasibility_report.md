# In-Play Data Feasibility Check — TheStatsAPI

**Date:** 2026-08-30
**Scope:** Prediction-layer feasibility only. **Odds are out of scope** and were not
fetched, analysed, or referenced. This is a data-capability check — no modelling, no
hypothesis generation.
**Data:** live + cached, all raw responses saved under `data/thestatsapi/inplay/`.
**Verdict:** **FEASIBLE — by BOTH routes.** The gate passes: match data populates during
play. Historical reconstruction is also viable and is the cheaper validation route,
subject to data-quality caveats.

---

## Headline

- **Step 1 gate: PASSES (direct observation, not inference).** Stats populate *during* a
  match via a dedicated `/live-stats` endpoint, and values advance in near-real-time.
- **Live polling is viable** at per-minute cadence; the practical ceiling is set by the
  **monthly quota**, not the burst cap.
- **Historical reconstruction is viable** for event-based state at any minute from
  `/timeline` + `/shotmap` — the **strongly-preferred route** because in-play hypotheses
  can be backtested on cached data with no live infrastructure. It is **not turnkey**:
  timeline coverage and home/away attribution vary by match and need a reconciliation layer.
- **Request usage this task: 48 live requests.** Monthly quota remaining afterwards:
  **5,722 / 10,000**. (Note: the brief estimated ~7,544 remaining; the true figure at
  task start was ~5,769. Reported per the standing rule.)

---

## Step 1 — Live population check (the gate)

At run time (2026-08-30 ~01:0x UTC) no match in the day's fixture window was live, but the
API exposes `status=live` as a first-class filter, which returned **20 live matches** in
progress worldwide. So a direct live test *was* possible and was performed.

**Decisive discovery — the API separates post-match from in-play data:**

| Endpoint | During play | Post-match |
|---|---|---|
| `/matches/{id}` | `status=live`, live score, updates | final score, full detail |
| `/matches/{id}/stats` | **HTTP 409** `MATCH_IS_LIVE — use /live-stats` | full totals (14 stat groups, all/1H/2H splits) |
| `/matches/{id}/live-stats` | **HTTP 200 — populated live** | (live only) |
| `/matches/{id}/timeline` | **HTTP 409** during play | full minute-stamped event log |
| `/matches/{id}/shotmap` | HTTP 200, fills as shots occur | full minute-stamped shot list |

The in-play pathway is **`/live-stats`**. Its schema:
```
{ meta:  { match_status, elapsed_minutes, home_goals, away_goals, ht_score, period },
  stats: { ball_possession, total_shots, shots_on_target, expected_goals, corner_kicks,
           fouls, yellow_cards, big_chances, offsides, goalkeeper_saves }  # each {all:{home,away}} }
```

**Direct proof that values populate and advance live** — two polls 75 s apart on three
long-running live matches:

| Match | T0 | T1 | Change |
|---|---|---|---|
| Junior Barranquilla v Ind. Santa Fe | elapsed 83′ | elapsed 84′ | minute advanced |
| Toronto FC v NYCFC | 73′, fouls_h 7, xG_h 0.67 | 75′, fouls_h 8, xG_h 0.70 | foul + xG updated live |
| NY Red Bulls v Philadelphia | 73′, 0–3, shots_h 9 | 75′, **1–3**, shots_h 10 | **goal appeared live** + shot |

A goal, a foul, shot counts, xG and possession all changed within 75 seconds of live play.
Confirmed on a scheduled (pre-match) match as the null baseline: `/stats` → 404, `/shotmap`
empty, `/timeline` empty (`coverage: none`), score all null. **Stats do not exist pre-match
and are populated during play. Gate passes.**

**Latency — honest limitation.** `elapsed_minutes` tracks wall-clock, and the Red Bulls goal
was present by the next poll (≤75 s), so update latency is at most a poll interval. I could
**not** measure precise second-level latency: doing so requires a synchronised independent
live feed, which was out of scope (odds/live-score third parties) and not reliably available
in this environment. So: **latency is sub-poll-interval but not precisely quantified.** A
"next 15 minutes" model is fine against per-minute updates; a "next 60 seconds" model would
need the latency pinned down first.

## Step 2 — Resolution and cadence

- **Finest live resolution:** per-minute (`elapsed_minutes`), updated continuously — values
  moved within a 75 s window, not only at half-time. Each `/live-stats` call returns the
  *current cumulative totals* (a snapshot), not a per-minute time series; the series is built
  by polling over time.
- **Per-event timestamps:** the `/timeline` (minute-stamped events) and `/shotmap`
  (minute-stamped shots with xG) give event-level timing. `/timeline` is **409 during play**,
  so live event timing must come from diffing `/live-stats` snapshots plus the live
  `/shotmap`. Post-match, `/timeline` provides the full minute-level event log.
- **Rate limit (confirmed empirically):** **12 requests per rolling 60 s window** (reset
  step measured at exactly 60 s). Monthly quota **10,000**.
- **`/live-stats` is a single call** carrying all 10 stat groups + score + minute, so **1
  request/match/poll** suffices for core in-play state (add `/shotmap` for shot coordinates =
  2 req/match).

**Concurrency ceiling (burst cap):**

| Requests/match/poll | Cadence | Max concurrent matches |
|---|---|---|
| 1 (`/live-stats` only) | 60 s | **12** |
| 1 | 30 s | 6 |
| 2 (+ shotmap) | 60 s | 6 |
| 2 | 30 s | 3 |

**The binding constraint is the monthly quota, not the burst cap.** A full match at 1
poll/min ≈ 100 requests. So 10,000/month ≈ **~100 full match-observations/month** (~57 with
the current 5,722 remaining). Polling 12 concurrent matches would exhaust the monthly quota in
roughly one to two match-days. **Live collection is technically sound but quota-limited for
scale on the current trial plan** — which is exactly why the historical route matters.

## Step 3 — Historical reconstruction

**Yes — match state at an arbitrary minute is reconstructable** by replaying the
minute-stamped `/timeline` (+ `/shotmap` for xG) on cached completed matches.

Worked example, `mt_733031701` reconstructed **at minute 63**:
`home: 0 goals, 9 shots, 2 SOT, 1 corner, 6 fouls, 1 red, xG 0.59` /
`away: 2 goals, 6 shots, 2 SOT, 4 corners, 10 fouls, 1 yellow, xG 0.98`.

**Validation — full-match reconstruction vs the authoritative `/stats` totals, 4 matches:**

| Match | `coverage` | Result |
|---|---|---|
| Botafogo-SP v Cuiabá (`mt_893485226`) | full | **Perfect** — every variable matches, score matches timeline |
| Huracán v Est. Río Cuarto (`mt_378775051`) | full | corners **transposed** (2/8 vs 8/2), shots/fouls ±1, goals via `penalty_scored` not `goal` |
| Kansas City v NC Courage (`mt_209276905`) | **none** | timeline **empty** (0 events) despite 3–2 score + full `/stats` |
| Atlas v Querétaro (`mt_733031701`) | full | corners transposed; `score` field 0–0 **contradicts** 4 timeline goals |

**Reconstructable at any minute** (event-based): goals, corners, cards (yellow/red), fouls,
shots, shots-on-target, offsides, penalties, and **xG accumulation** (via shotmap).
**Half-resolution only** (from `/stats` all/1H/2H splits, not arbitrary-minute): possession,
passes, tackles, free-kicks. **Not** minute-reconstructable: anything continuous without a
timeline event.

**Data-quality caveats (must be handled before trusting at scale):**
1. **Coverage varies** — the `/timeline` response carries a `coverage` field (`full` |
   `none`); some matches/leagues have `none`. Filter on `coverage == full`.
2. **Home/away transposition** on corners (and occasionally ±1 totals) in some matches.
3. **Event-taxonomy variance** — `goal` vs `penalty_scored` vs `penalty_awarded`; the mapping
   must handle all shot/goal subtypes.
4. **Score-summary inconsistency** — the `score` field occasionally disagrees with the event
   log within the same match record.
5. Reconstruction should be **reconciled against `/stats` totals** per match and matches that
   fail reconciliation quarantined.

Cost is low: **3 cached calls per match** (`/timeline`, `/shotmap`, `/stats`), reusable and
no live infrastructure.

## Step 4 — Recommendation

**An in-play prediction engine is feasible on TheStatsAPI, by both routes:**

- **Historical reconstruction — DO THIS FIRST (strongly preferred).** In-play hypotheses
  ("goal in next 15 min", "card imminent", "corner likely") can be backtested *now* on cached
  completed matches by replaying timeline+shotmap to reconstruct state at any minute — before
  building any live pipeline. Prerequisite: a small **reconciliation/validation layer**
  (require `coverage=full`, reconcile reconstructed totals against `/stats`, normalise the
  event taxonomy, detect/repair home-away transposition, quarantine inconsistent matches).
  Event-based state variables reconstruct cleanly; possession/passes/tackles are half-
  resolution only.

- **Live polling — viable, quota-limited.** `/live-stats` gives per-minute in-play state in a
  single call. Up to 12 concurrent matches at 1-min cadence under the burst cap, but the
  10,000/month quota caps sustained collection at ~100 full matches/month. Fine for a live
  pilot on a handful of matches; a paid plan would be needed for breadth. Pin down exact
  update latency (needs a synchronised reference feed) before attempting sub-minute horizons.

- **Not "neither."** Both routes work.

**Practical constraints, stated honestly:** 12 req/60 s burst; 10,000 req/month (5,722 left);
live event-timing needs snapshot-diffing because `/timeline` is 409 during play; timeline
coverage/attribution is imperfect and needs reconciliation; continuous stats are half-
resolution only; live-update latency is ≤1 poll interval but not precisely measured.

## Ground-rules compliance

- Odds out of scope — none fetched/analysed/referenced. ✓
- Feasibility check only — no modelling/hypothesis/discovery. ✓
- Actual usage reported: **48 live requests**, monthly remaining **5,722**. ✓
- Raw responses cached to `data/thestatsapi/inplay/` (52 files) for reuse. ✓
- Held-out set untouched. ✓
- Step 1 gated Steps 2–3 (gate passed). ✓
- No shared/global config changed (a task-local cache dir was used; the shared client module
  was imported unmodified, its cache paths overridden per-process only). ✓

## Artifacts

| Item | Path |
|---|---|
| Discovery (today/live) | `scripts/inplay_step1_discover.py` |
| Endpoint probe (shapes) | `scripts/inplay_probe_endpoints.py` |
| Gate: live-status + pre-match baseline | `scripts/inplay_step1_gate.py` |
| Gate: live `/live-stats` observation | `scripts/inplay_step1_livestats.py` |
| Gate: value-advancement proof | `scripts/inplay_step1_advance.py` → `data/thestatsapi/inplay/_advance_check.json` |
| Step 3: reconstruction + validation | `scripts/inplay_step3_reconstruct.py` → `_step3_reconstruction.json` |
| Step 3: multi-match robustness | `scripts/inplay_step3_multi.py` → `_step3_multi.json` |
| Raw cached responses | `data/thestatsapi/inplay/*.json` |
