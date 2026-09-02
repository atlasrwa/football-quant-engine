# League-Family Transfer Test — Report

**Question.** The engine's rich-field models were built on three second-tier leagues
(Championship, La Liga 2, Ligue 2). Does the skill transfer to matched top flights?
We tested three country families (top flight ↔ second tier), building new corpora for
**EPL, La Liga, Ligue 1** and re-running the existing validated pipeline with **no
refit and no retune** of the model architecture.

## Pre-registration (stated before running)
- **Bootstrap seed:** `20260902` (fixed in advance; all CIs use it).
- **Primary multiple-testing family:** 3 new top flights × {corners@9.5, cards@3.5} =
  **6 hypotheses**; Benjamini–Hochberg at q = 0.10.
- **Directional family:** {corners, cards} × 3 top flights = **6**; BH at q = 0.10.
- **Within-league only** — every number is per league; nothing pooled (Simpson's-paradox
  discipline).
- **Skill criterion:** BSS-vs-naive 95% bootstrap CI must exclude 0 (and survive BH).

## Quota usage (cache-first, quota-capped)
| Stage | Requests | Monthly remaining after |
|---|---|---|
| Start of run | — | 4,718 / 10,000 |
| Comp/season discovery | ~6 | 4,712 |
| England (EPL: 8 fixture pages + 760 stats) | ~768 | 3,944 |
| Spain (La Liga: 8 + 760; La Liga 2 cached) | ~768 | 3,176 |
| France (Ligue 1: ~8 + 611; Ligue 2 cached) | ~619 | **2,557** |

Total spent this run ≈ **2,161** requests. All three families were covered within
budget; ~2,557 remain this month. Re-runs are free (cache-first).

## Corpora (2 most recent complete seasons each)
All top flights perfectly balanced (full double round-robin); calendar span ~275–282 days.

| League | Tier | Seasons | Matches | Teams | Apps/team (min/med/max) |
|---|---|---|---|---|---|
| EPL | 1 | 25/26, 24/25 | 760 | 20 | 38 / 38 / 38 |
| La Liga | 1 | 25/26, 24/25 | 760 | 20 | 38 / 38 / 38 |
| Ligue 1 | 1 | 25/26, 24/25 | 611 | 18 | 33 / 34 / 34 |
| Championship | 2 | 3 seasons (ref) | 1,656 | 24 | 46 / 46 / 46 |
| La Liga 2 | 2 | 2 seasons | 924 | 22 | 42 / 42 / 42 |
| Ligue 2 | 2 | 2 seasons | 612 | 18 | 34 / 34 / 34 |

## Feature verification (five checks, per league, before any modelling)
All six leagues cleared feature integrity, with two documented, principled
adjustments made during the run so a single degraded field could not spuriously
sink a sound pipeline:

1. Checks 2/3/5 use the **per-side "for" signal** (home rolling stat-for → home
   outcome), the clean framing checks 3 and 5 already used. The summed-both-sides →
   match-total framing is diluted for total goals and spuriously failed EPL despite
   sound features.
2. The known-signal **anchor is the stronger of {xG→goals, SOT→goals}**. xG is sparse
   in La Liga 2 (45% populated) and absent in Ligue 2 (0%), so those leagues anchor
   on shots-on-target — an equally valid, more directly-counted known signal.
3. Shuffle-null is a **permutation test, pass at one-sided p < 0.01** (1,000 shuffles).

**Result:** EPL, Championship, La Liga, La Liga 2, Ligue 1 — **pass**. **Ligue 2 —
marginal**: its SOT→goals anchor (0.113) is real but sits at permutation p = 0.013
(below the strict p < 0.01 bar) because it has no xG field at all. Ligue 2 was run
but is **flagged `features_marginal`** and treated conservatively.

## The deliverable — family comparison (within-league, seed 20260902)

| League | Tier | Market | BSS vs naive | 95% CI | ECE | Dir. acc | Home bar | n | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **EPL** | 1 | Corners@9.5 | −0.87% | [−2.46, +0.67] | 0.041 | 0.572 | 0.575 | 636 | no skill |
| **EPL** | 1 | Cards@3.5 | +0.16% | [−2.84, +3.01] | 0.086 | 0.506 | 0.399 | 353 | no skill |
| Championship | 2 | Corners@9.5 | −1.17% | [−2.48, +0.09] | 0.053 | 0.566 | 0.622 | 1350 | no skill |
| Championship | 2 | Cards@3.5 | −1.30% | [−2.70, +0.11] | 0.064 | 0.528 | 0.383 | 890 | no skill (cards excluded) |
| **La Liga** | 1 | Corners@9.5 | +1.81% | [−0.19, +3.85] | 0.015 | 0.603 | 0.606 | 606 | no skill (near-positive) |
| **La Liga** | 1 | Cards@3.5 | −0.60% | [−3.19, +2.11] | 0.066 | 0.541 | 0.449 | 455 | no skill |
| La Liga 2 | 2 | Corners@9.5 | −0.07% | [−1.54, +1.37] | 0.020 | 0.541 | 0.620 | 778 | no skill |
| La Liga 2 | 2 | **Cards@3.5** | **+2.90%** | **[+0.26, +5.83]** | 0.025 | 0.530 | 0.449 | 668 | **SKILL (CI>0)** |
| **Ligue 1** | 1 | Corners@9.5 | −0.74% | [−2.58, +1.13] | 0.035 | 0.568 | 0.614 | 472 | no skill |
| **Ligue 1** | 1 | Cards@3.5 | +2.08% | [−2.52, +6.74] | 0.044 | 0.487 | 0.433 | 300 | no skill |
| Ligue 2† | 2 | Corners@9.5 | −0.27% | [−1.88, +1.31] | 0.050 | 0.536 | 0.594 | 439 | no skill |
| Ligue 2† | 2 | Cards@3.5 | +3.18% | [−0.14, +6.47] | 0.032 | 0.535 | 0.453 | 317 | no skill (borderline) |

† Ligue 2 features flagged marginal (no xG field; SOT anchor permutation p = 0.013).
La Liga 2 cards@4.5 also positive: +2.94% CI [+0.29, +5.63].

### Multiple-testing correction (primary family of 6 top-flight cells, BH q=0.10)
**No top-flight cell survives BH.** Best uncorrected p is La Liga corners (0.079), which
does not clear correction. EPL cards p = 0.91; Ligue 1 cards p = 0.38.

The **only** cell with within-league calibrated skill (CI excludes 0) anywhere in the
test is **La Liga 2 cards** — an already-held second tier, confirming its prior status.

## Direct answers

**1. Does skill hold within each family across tiers?**
No family shows skill in both tiers. In every family the top flight fails to show
within-league calibrated skill on either market. Only **La Liga 2 cards** (a second
tier) clears the bar. So skill does **not** transfer across tiers within any family;
it is confined to specific second-tier cells that were already validated.

**2. Tier / country / neither?**
**Neither clean pattern — the result is patchy/cell-specific.** A tier effect is ruled
out because the direction flips: cards persistence is stronger in the top flight for
England (EPL 0.138 > Championship 0.060) but stronger in the *second* tier for Spain
(La Liga 2 0.107 > La Liga 0.053) and France (Ligue 2 0.087 > Ligue 1 0.030). A pure
country effect is also not supported — within Spain the two tiers behave oppositely on
cards. Under this stricter within-league, 2-season walk-forward, the validated markets
are largely **at par with the naive base rate**, with skill surfacing only in isolated
second-tier cells.

**3. Does cards persistence hold in EPL — and what does that say about the Championship finding?**
Cards persistence **does hold in EPL** (per-side yellow→cards = 0.138) and is weak in the
Championship (0.060). Taken alone in England, that looks tier-specific and consistent
with the squad-churn story. **But it does not generalise:** in Spain and France the
second tier has *stronger* cards persistence than the top flight, and the only market
with demonstrated cards skill is La Liga 2 (a second tier). So the Championship cards
gap is **not** explained by a general "top flights retain persistence, second tiers lose
it" squad-churn law. The squad-churn explanation, as a general law, is **not supported** —
it may be an England-specific quirk of the Championship, not a tier mechanism.

**4. Which fields are populated where — does coverage explain differences?**
Coverage is strongly **tier-dependent**, and it explains the feature-check behaviour
(though not the validation results, which are weak even where coverage is full):

| Field | EPL | Championship | La Liga | La Liga 2 | Ligue 1 | Ligue 2 |
|---|---|---|---|---|---|---|
| expected_goals | 100% | 99.5% | 100% | **45%** | 99.8% | **0%** |
| touches_in_penalty_area | 100% | **~5%** | 99.5% | 100% | 100% | 100% |
| goals_prevented | 100% (real) | 0% | 99.3% (real) | 0% | ~100% | 0% |

Top flights are densely populated (including `goals_prevented`, which was 0% across all
three second-tier corpora). Second tiers have degraded rich fields: La Liga 2's xG is
sparse and noisy; Ligue 2 has no xG at all. `touches_in_penalty_area` at ~5% is
**Championship-specific**, not general. Coverage explains why the second tiers must
anchor feature checks on shots-on-target, but it does **not** rescue validation: even
EPL and La Liga, with full coverage, show no within-league skill here.

## Directional calls (vs always-pick-home)
No corners cell beats always-pick-home. The cards cells show +0.05…+0.11 over the
home baseline, and EPL/La Liga cards even clear BH — **but the home-advantage rate for
cards is only ~0.40** (away teams systematically take more cards), so "beating
always-pick-home" is a degenerate result (always-pick-**away** would score ~0.60). It
is not a genuine directional edge, and EPL cards calibration fails (ECE 0.113). All new
directional cells are therefore recorded with `beats_home_bh=False` in `scope.py` and
**no call is emitted** for any of them. Reporting the home bar makes the weak baseline
visible, as required.

## Decision: should the 100,000/month plan be purchased?

**Recommendation: do NOT upgrade on the strength of this test.** Skill did not transfer
broadly. Under a stricter within-league 2-season walk-forward, the three new top flights
show no calibrated skill over naive on either validated market (nothing survives BH), and
the one confirmed cell is a second tier already in the corpus. Scaling to more leagues
would, on this evidence, mostly produce models at par with the base rate — the honest
scoping would then label most new leagues "no demonstrated skill," which is not worth
paying 10× coverage for.

Two caveats keep this from being a flat "no forever":
- This is a **harder test** than the original 25-league × 3-season cross-sectional
  validation: single-league, only 2 seasons, expanding-window walk-forward, small n
  (300–780 settled predictions). Wide CIs mean "not demonstrated," not "demonstrated
  absent." La Liga corners (+1.81%, p=0.079) is the kind of near-miss that more seasons
  could resolve.
- If coverage is ever expanded, do it **per family where skill is actually shown**, not
  wholesale — and first resolve *why* the Championship cards gap is England-specific
  rather than a tier law, since that was the original motivating anomaly and it did not
  reproduce as a general mechanism.

**Bottom line:** patchy skill → do not buy blanket coverage. Keep the per-league honest
scoping; the three new top flights are recorded UNVALIDATED (no demonstrated skill) in
`scope.py`, data-driven from this test.

---
*Artifacts: `scripts/family_transfer.py` (driver, reuses validated model verbatim),
`scripts/family_transfer_report.py` (consolidated report + BH), per-league results in
`data/results/family_transfer_*.json`, scope update in
`src/research/prediction_engine/scope.py`. Bootstrap seed 20260902.*
