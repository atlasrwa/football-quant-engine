# Formation Data — Pull and Test

**Correction confirmed.** The prior "formation is not backtestable" conclusion was wrong.
`GET /football/matches/{id}/lineups` returns `data.home.formation` / `data.away.formation`
(e.g. `"4-2-3-1"`) for finished matches. The earlier "zero lineup data in the corpus" finding
was correct in fact but wrong in cause: the endpoint had simply never been fetched. It has now
been fetched for 1,000 matches.

**Bottom line.** Formation is largely a **proxy for team quality**. When the confound is removed
by a within-team control, 13 of 14 tested contrasts are null. **One** cell survives multiple-testing
correction and is seed-stable: in **La Liga 2**, a team takes **~0.6 more cards when it lines up
4-2-3-1 than when the same team plays 4-4-2** (within-team diff +0.605, 95% CI [+0.196, +1.042],
p=0.0024, BH-significant, stable at 4/4 seeds). This is a **hypothesis**, not a validated effect,
and it does **not** justify adding formation to the prediction engine now.

Seed fixed in advance: **20260902** (stability seeds {1,7,42}). Zero changes to the prediction
engine, scope, or any ledger.

---

## Step 1 — Coverage check (gate)

`/coverage/leagues?data_type=lineups` is paginated (152 competitions, 2 pages) and reports
`lineups.available` as a **boolean per competition**, not a coverage percentage. All six corpus
competitions report `available = true`:

| Competition | id | lineups | finished events |
|---|---|---|---|
| Championship | comp_8321 | ✓ | 3386 |
| Premier League | comp_3039 | ✓ | 3060 |
| Ligue 1 | comp_0256 | ✓ | 2095 |
| Ligue 2 | comp_9777 | ✓ | 2174 |
| LaLiga | comp_8814 | ✓ | 2310 |
| LaLiga 2 | comp_0976 | ✓ | 2841 |

Because the endpoint gives availability, not a per-match fill rate, the **true usable rate was
measured empirically during the pull** (below). Probe cost: 2 coverage requests + 1 sample lineup.

## Step 2 — The 1,000-match pull

Deterministic balanced selection (seed 20260902) over cached corpus fixtures **that also have
cached stats** (so every pulled match has outcomes). Balanced across leagues (weighted toward the
three primary analysis leagues), balanced per team via round-robin, spread across the season
calendar via a low-discrepancy traversal of each team's date-ordered matches.

| League | pulled | teams | apps min/med/max | both-formations | usable rate |
|---|---|---|---|---|---|
| Championship | 250 | 32 | 8/16/25 | 211 | 84.4% |
| La Liga 2 | 200 | 29 | 8/14/19 | 194 | 97.0% |
| Ligue 2 | 170 | 24 | 8/14/23 | 164 | 96.5% |
| EPL | 140 | 23 | 7/13/15 | 140 | 100.0% |
| La Liga | 140 | 23 | 6/12/17 | 138 | 98.6% |
| Ligue 1 | 100 | 21 | 5/9/15 | 98 | 98.0% |
| **Total** | **1000** | | | **945** | **94.5%** |

- **0 404, 0 empty responses, 1000/1000 HTTP 200.**
- **Usable = both formations present = 945/1000 (94.5%).** The 55 non-usable are cases where the
  API returned a lineup (11-player XI, `confirmed=true`) but `formation` was null for one side —
  concentrated in the **older Championship seasons** (23/24), which is why Championship's usable
  rate (84.4%) is the lowest. Formation fill is near-complete for recent seasons.
- Raw responses cached at `data/thestatsapi/championship/lineups_<mid>.json`; all analysis re-runs
  offline with zero API calls.

**Quota (reported honestly).** The account is **not** at ~10,000 free this month — monthly
remaining was **2,553** before the pull (the Pilot C forward loop shares the same quota). The pull
consumed **exactly 1,000** requests; **monthly remaining is now 1,553**. The probe used 3 more.
A hard local cap (`THESTATS_MAX_REQUESTS=1050`) protected the shared budget.

## Step 3 — Characterisation

| League | matches w/ lineups | both present | distinct formations | top-3 share | HHI | team modal share (median) |
|---|---|---|---|---|---|---|
| Championship | 251 | 84.5% | 17 | 69.3% | 0.307 | 56.0% |
| La Liga 2 | 200 | 97.0% | 15 | 78.4% | 0.235 | 45.5% |
| Ligue 2 | 170 | 96.5% | 16 | 56.8% | 0.145 | 52.3% |
| EPL | 140 | 100.0% | 16 | 79.3% | 0.341 | 64.3% |
| La Liga | 140 | 98.6% | 14 | 71.2% | 0.226 | 57.1% |
| Ligue 1 | 100 | 98.0% | 14 | 70.2% | 0.180 | 50.0% |

- **`4-2-3-1` is the dominant shape in every league.** Ligue 2 is the most varied (HHI 0.145),
  EPL the most concentrated (0.341).
- **Prior-only modal-formation proxy viability — WEAK.** A team's single most-used formation
  accounts for only a **median ~45–65%** of its matches. Teams rotate shape frequently, so a
  modal-formation proxy known days ahead would be right about the next match only about half the
  time — far from the ~90% stability that would make it a reliable pre-kickoff feature. Formation
  from the actual team sheet remains a ~1-hour-before-kickoff quantity.

## Step 4 — Descriptive matchup analysis

**The pairing view is uninformative at this sample size, and is reported as such rather than with
misleading averages.** With 14–17 distinct formations per league and ~100–250 matches each, the
(home × away) pairing grid is extremely sparse: the **only** pairing reaching the minimum sample
(n≥30) is the `4-2-3-1 vs 4-2-3-1` self-pairing (Championship n=60, La Liga 2 n=31, EPL n=44).
Every cross-formation pairing falls below the gate. Full per-pairing / per-side tables (corners,
fouls, cards, SOT, blocked shots, clearances, crosses — total and per side, with n) are in
`data/results/formation_analysis.json`; nearly all are flagged `insufficient`.

**The marginal per-formation view is more robustly estimated** and is where any signal lives. The
one coherent pattern: in La Liga 2, teams average **2.74 cards under 4-2-3-1 vs 2.05 under 4-4-2**
(marginal own-team), matching the within-team result below.

## Step 5 — Team-quality control (the decisive check)

Formations correlate with team quality, so raw differences can just mean "good teams play shape X."
The clean control is **within-team**: when the *same* team switches shape, do its own outcomes
change? Contrasts are paired per team and bootstrapped over teams (each team weighted equally),
which removes cross-team quality differences by construction.

Only the top-common formations produce enough within-team switches. Teams switching often enough to
study: Championship 25, La Liga 2 26, Ligue 2 19, La Liga 20, Ligue 1 17, EPL 13.

## Step 6 — Statistical discipline

- **Per league, never pooled** (Simpson's-paradox trap avoided).
- **Fresh BH FDR family = 14** — every within-team (formation-contrast × outcome × league) cell
  that met the min-sample gate (≥8 teams, ≥30 matches per arm). The descriptive pairing/marginal
  tables carry no p-values and are not part of the inferential family.
- **Bootstrap seed fixed in advance (20260902)**; separate stability seeds {1,7,42}.
- CIs throughout; small-n cells reported as insufficient, not as findings.

### Result

| League | contrast | outcome | within-team diff | 95% CI | p | BH |
|---|---|---|---|---|---|---|
| **La Liga 2** | **4-2-3-1 vs 4-4-2** | **cards** | **+0.605** | **[+0.196, +1.042]** | **0.0024** | **reject** |
| La Liga 2 | 4-2-3-1 vs 4-4-2 | fouls | +0.788 | [−0.073, +1.666] | 0.077 | — |
| La Liga 2 | 4-2-3-1 vs 4-4-2 | corners | −0.393 | [−1.177, +0.449] | 0.337 | — |
| La Liga | 4-2-3-1 vs 4-4-2 | (all 7 outcomes) | — | span 0 | ≥0.09 | — |
| … | (13 cells total, all others) | | | span 0 | | — |

**One cell survives BH: La Liga 2, 4-2-3-1 vs 4-4-2, cards (+0.6 cards under 4-2-3-1).**
- **Seed-stable:** CI excludes 0 at **3/3** stability seeds plus the primary seed.
- **Leave-one-out robust:** dropping any single team leaves the mean in +0.48…+0.70; 11 of 17 teams
  show the positive difference. No single team drives it.
- Everything else — corners, SOT, fouls, blocks, clearances, crosses across both leagues with
  enough switches — is null.

**Caveats that keep this a hypothesis, not a result:** within-team removes team quality but **not
opponent quality or referee**; some team arms are thin (as few as 2 matches per arm); and it is a
**single surviving cell out of a family of 14**. A seed-stable single cell is a lead, not a
confirmed effect.

## Step 7 — Verdict (direct answers)

1. **Do formation matchups show meaningful differences in corners, fouls/cards, SOT?**
   The **matchup (pairing) view is uninformative** at 1,000 matches — too sparse to estimate.
   The more robust **marginal and within-team** views show **no** meaningful, quality-independent
   difference in corners, SOT, fouls, blocks, clearances, or crosses. The **one** exception is
   **cards** in **La Liga 2**, where 4-2-3-1 is associated with ~0.6 more cards than 4-4-2.

2. **Do the differences survive controlling for team quality?**
   **Almost entirely no.** 13 of 14 within-team contrasts are null — meaning most apparent
   formation effects are a **proxy for quality**, not an independent driver. The lone survivor
   (La Liga 2 cards) does survive the control and is seed-stable, but stands alone.

3. **Is a prior-only modal formation stable enough to use days before kickoff?**
   **No — weak.** Median modal-formation share is only ~45–65%; teams rotate too much for a
   modal proxy to reliably predict the next match's shape. Formation is effectively a
   ~1-hour-pre-kickoff quantity, usable for imminent fixtures only.

4. **Does this justify testing formation as a model feature vs the prior-only baseline
   (corners −1.83%, cards −1.82%)?**
   **Not as a general feature.** The corners/SOT/fouls nulls give no basis, and the weak modal-proxy
   stability means a prior-only formation feature would be mostly noise. The *only* thread worth
   pulling is a **narrow, pre-registered forward test of cards in La Liga 2** (4-2-3-1 vs 4-4-2),
   treated as the confirmation that this exploratory pass cannot provide. Confirmation would require
   held-out / forward fixtures not used here, with the opponent-quality and referee confounds
   controlled. **No formation feature was added to the engine in this pass**, per the brief.

---

*Artifacts: `scripts/formation_probe.py`, `scripts/formation_pull.py`,
`scripts/formation_analysis.py`; `data/results/formation_coverage_raw.json`,
`formation_sample_lineup_raw.json`, `formation_selection.json`, `formation_pull_report.json`,
`formation_analysis.json`; raw lineups `data/thestatsapi/championship/lineups_*.json`.
Seed 20260902; within-team FDR family 14; 1000 API requests (+3 probe), monthly remaining 1553.*
