# In-Play Reconstruction — Corpus Validation & State Schema

**Date:** 2026-08-30
**Scope:** Build & validate the reconstruction corpus. **No hypothesis testing, no modelling,
no candidate generation, no FDR, no metric-library entries.** Odds out of scope (none touched).
Reconstruction only — no live polling.
**Verdict:** **Step 2 reconciliation gate FAILED — DO NOT SCALE.** Usable rate 3.9% strict /
35.3% after two justified corrections, well below the 85% bar. Reported as a finding.
**Requests this task:** 204 live (Step 2 batch only). Monthly quota remaining: **5,518 / 10,000**.

---

## Headline

Historical reconstruction *works mechanically* — timeline+shotmap replay rebuilds per-side
match state at any minute — but the **data is not clean enough to scale a multi-league corpus
on right now**, and the required sample size is larger than the remaining budget supports.
Three concrete data-quality problems were characterized (not guessed), and the within-match
independence question was answered. This closes the "just scale it" path and replaces it with a
precise list of what would have to be true first.

## Step 1 — Inventory (zero requests)

3,189 matches already have `/stats` cached (the reconciliation reference, free):

| League | Matches w/ stats | Seasons |
|---|---|---|
| Championship | 1,656 | sn_2930227, sn_3064530, sn_343481 (552 each) |
| LaLiga2 | 924 | sn_8425423, sn_8437950 (462 each) |
| Ligue2 | 609 | sn_3057202 (303), sn_3064056 (306) |

**Zero** timeline or shotmap were cached for the corpus. So each reconstruction costs **2
additional requests** (timeline + shotmap); `/stats` is free. At 5,722 then-remaining, ~2,861
matches were reconstructable in principle — but see the gate.

## Step 2 — Reconciliation layer (the gate) — FAILED

Batch: **102 matches**, balanced across 3 leagues × 2 seasons (17 each). 204 requests.
Team appearances min 1 / median 2 / max 7 (validation batch; tighter balance was reserved for
the — now cancelled — scale-up).

The reconciliation layer, per match: requires `coverage=full`; reconstructs per-side totals;
reconciles every reconstructable variable against official `/stats` per side; checks home/away
**transposition** explicitly; normalizes event taxonomy; flags score-vs-event-log contradictions;
quarantines on any failure.

**Usable rate:**

| Definition | Usable | Rate |
|---|---|---|
| Strict (any transposition/mismatch → quarantine) | 4 / 102 | **3.9%** |
| After 2 justified corrections (below) | 36 / 102 | **35.3%** |

Both are far below the 85% gate. **The gate fails.**

**Failure breakdown by cause:** `coverage=none` 51, bad-variable 47→15 (after fixes),
score-vs-eventlog 2.

**By league — coverage is strongly league-dependent, and is the dominant killer:**

| League | Full coverage | Usable (post-fix) |
|---|---|---|
| Ligue2 | 34/34 | **28/34 (82%)** |
| Championship | 17/34 (50% `coverage=none`) | 8/34 (24%) |
| LaLiga2 | **0/34 (no timeline coverage at all)** | 0/34 (0%) |

### The three data-quality findings (characterized, not guessed)

1. **Corner home/away transposition — systematic.** In **45 of 51** full-coverage matches, the
   timeline's `corner_kick` events are attributed to the **wrong side** relative to the `/stats`
   corner totals. Critically, this is **isolated to corners** — in the same matches, fouls,
   shots, cards, and xG are all correctly oriented. A global side-mapping bug on our end would
   transpose *everything*; it doesn't. So this is a genuine TheStatsAPI attribution defect on
   corner events, not our wiring. **This is exactly the silent-swap failure mode the brief
   flagged** (the same class that produced the Championship −0.105 gate failure) — caught here
   by the explicit orientation check, before any modelling.
2. **Shots must come from the shotmap, not the timeline.** Timeline shot-events reconcile
   `total_shots` only **62%** of the time; the purpose-built `/shotmap` reconciles **92%**. The
   layer was corrected to source shots/SOT/xG from the shotmap. (Legitimate reconciliation
   improvement, not a workaround.)
3. **Residual ±1 count discrepancies** even after both fixes: `fouls` (9 matches), `total_shots`
   (4), `SOT` (3), `xG` (3) disagree with the aggregate by small margins — timeline/aggregate
   granularity differences.

The "35.3% post-fix" figure already **credits** corrections (1) and (2). It is the optimistic
bound, and it is still less than half.

**Decision (reported before any scaling):** **DO NOT SCALE.** LaLiga2 has no coverage,
Championship loses half to missing coverage, corner attribution needs a validated correction
before trust, and even the clean full-coverage rate (71%) is carried almost entirely by Ligue2.

## Step 3 — Sample size & independence (advisory; no requests)

Run despite the gate because the independence question governs any future in-play work.

- **Windowing assumption (stated):** rolling 15-min horizon, evaluated every 5 min, minute
  10→85 = **16 windows/match**.
- **Within-match windows are NOT independent.** The label ("goal in next 15 min") has lag-1
  autocorrelation ≈ **0.53** (adjacent windows overlap by 2/3). Design effect ≈ **8.9×**, so 16
  raw windows/match ≈ **~1.8 effective independent observations**. Treating raw windows as
  independent would overstate significance by ~9×. **This is the "matters a lot" point: raw
  window counts are not the sample size.**
- **Matches needed vs the FDR family (22,855):** h=0.1 → ~1,728 usable; h=0.15 → ~768; h=0.2 →
  ~432. At the observed 35% usable rate and 2 req/match, even the h=0.15 case implies ~2,200
  matches fetched (~4,400 requests) — nearly the entire remaining quota — for a corpus half of
  which is discarded. Independently confirms scaling is unjustified now.

## Step 4 — Scale — NOT PERFORMED

Blocked by the Step-2 gate and confirmed by Step-3. No scaling fetch was made. Only the
102-match validation batch was pulled.

## Step 5 — Reconstructed state schema

What is reconstructable at an arbitrary minute *for a match that passes reconciliation*:

| Variable | Source | Resolution | Reliability |
|---|---|---|---|
| goals (incl. penalties, own goals) | timeline `goal`/`penalty_scored`/`own_goal` | event/minute | high (score-reconciled) |
| yellow cards | timeline `yellow_card` (+`yellow_red_card`→yellow+red) | event/minute | high |
| red cards | timeline `red_card`/`yellow_red_card` | event/minute | high |
| fouls | timeline `foul` | event/minute | good, occasional ±1 |
| **corners** | timeline `corner_kick` | event/minute | **home/away SWAPPED — requires orientation correction; do not trust raw** |
| total shots | **shotmap** (count) | event/minute | good (92% reconcile) |
| shots on target | **shotmap** `is_on_target` | event/minute | good |
| xG (accumulated) | **shotmap** `expected_goals` | event/minute | good (±0.3 tol) |
| possession, passes, tackles, free-kicks | `/stats` splits | **half only** (all/1H/2H) | not minute-reconstructable |

**Event taxonomy encountered** (documented, not guessed): `foul`, `corner_kick`,
`shot_off_target`, `shot_on_target`, `shot_blocked`, `substitution`, `yellow_card`, `red_card`,
`yellow_red_card`, `offside`, `goal`, `penalty_scored`, `penalty_awarded`, `penalty_saved`,
`added_time`, `period_start`, `period_end`, `var`.

**Reconciliation rules applied:** require `coverage=full`; per-side exact match vs `/stats`
(xG within ±0.30); shots/SOT/xG sourced from shotmap; goals cross-checked against the fixture
score. **Quarantine criteria:** `coverage != full`; any per-variable mismatch; any home/away
transposition; score-vs-event-log contradiction.

**Key limitation:** "pressure"-type continuous signals (possession, pass tempo, territorial
dominance) are **half-resolution only** — they cannot be reconstructed at an arbitrary minute
from cached endpoints. In-play "pressure" would have to be proxied by event-based intensity
(shots/attacks/corners accumulation), not possession.

## Recommendation

1. **Do not scale a multi-league corpus on this source as-is.** Coverage is absent (LaLiga2)
   or half-missing (Championship), and corner attribution is systematically wrong.
2. **A Ligue2-only pilot is the only near-viable path** (82% usable post-fix) — but that
   sacrifices the multi-league generalization requirement, so it is a separate, explicit
   decision, not a default.
3. **Before any scale-up:** (a) validate a corner-orientation correction on a held-out batch
   and confirm it is universal, not per-match; (b) treat `coverage=full` as a hard prefilter
   and re-estimate true yield per league; (c) design in-play labels around the ~8.9× design
   effect — cluster by match, do not count overlapping windows as independent.
4. Continuous "pressure" features are not minute-reconstructable here; scope in-play state to
   event-based variables.

## Ground-rules compliance

- Odds out of scope — none fetched/referenced. ✓
- Step-2 usable rate gated Step 4 — did not scale on an unvalidated layer. ✓
- Usable rate + failure breakdown reported honestly (a low rate reported as a finding). ✓
- No live polling — reconstruction only. ✓
- Balanced sampling applied to the validation batch (scale-up cancelled). ✓
- Held-out set untouched. ✓
- Request usage reported per step: Step 1 = 0, Step 2 = 204, Step 3 = 0, Step 4 = 0;
  monthly remaining **5,518**. ✓
- Fetcher + reconciliation code committed (see below). ✓
- No shared/global config changed — the shared `thestatsapi_client.py` was imported unmodified;
  its cache paths were overridden per-process to `data/thestatsapi/inplay/`. ✓

## Artifacts

| Item | Path |
|---|---|
| Inventory (zero-req) | `scripts/inplay_recon_step1_inventory.py` → `data/thestatsapi/inplay/_recon_inventory.json` |
| Fetcher + reconciliation (v1) | `scripts/inplay_recon.py` → `_recon_batch.json`, `_recon_step2_result.json` |
| Reconciliation v2 (corrected) | `scripts/inplay_recon_v2.py` → `_recon_step2_result_v2.json` |
| Sample-size/independence | `scripts/inplay_recon_step3_power.py` → `_recon_step3_power.json` |
| Raw timeline/shotmap responses | `data/thestatsapi/inplay/recon_timeline_*.json`, `recon_shotmap_*.json` |
