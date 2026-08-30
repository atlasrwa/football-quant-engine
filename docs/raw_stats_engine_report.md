# Raw Stats Engine — Systematic Discovery Over Observable Quantities

**Date:** 2026-08-30
**Scope:** Raw observable match statistics only. No use of, reference to, or comparison against any previously discovered metric. Clean run.
**Core run API cost:** 0 (cached corpus + cached stats). **Heatmap probe (Step 5):** 4 live requests. Quota 5,518 → **5,514**.
**Held-out set:** untouched (nothing genuine survived to confirm).
**Cumulative FDR family:** 23,823 → **23,869** (this run tested 46 gate-passed candidates).
**Artifacts:** `scripts/raw_stats_discovery.py`, `data/discovery/raw_stats_discovery.json`, `scripts/heatmap_fetch.py`, `data/thestatsapi/heatmap/_probe_result.json`. Ledger entry **F020**.

---

## Headline

No genuine raw-stat predictive edge was found. The search produced 24 candidates that clear cumulative FDR **pooled across leagues**, but **0 of 24 are significant in even one individual league** — they are a between-league base-rate (Simpson's-paradox) artifact, not real within-league signal. Per the ground rule "report per league, never pooled," these are not results and were not promoted to held-out.

The most valuable output is methodological, and it is exactly what the sanity-gate discipline exists to produce (see Step 3).

---

## Step 1 — Raw feature inventory (population rates per source/league)

**FootyStats corpus:** 15,367 matches, 25 leagues × 2 seasons. Core observables — goals, corners (incl. fh/2h), yellow/red cards (incl. fh/2h), fouls, shots, shots on/off target, possession, offsides, attacks, dangerous attacks, xG, xG-prematch — are **99–100% populated in every league**. `refereeID` 90–99%. `attendance` is sparse and league-dependent (5–90%) → excluded where null. Set-piece counts (freekicks/throwins/goalkicks) are sparser and were excluded.

**TheStatsAPI rich fields** (blocked/inside-box/outside-box shots, woodwork; big-chances-missed, touches-in-penalty-area, fouled-in-final-third; throw-ins, accurate crosses/long-balls, final-third entries; duels won%/dispossessed/dribbles%/ground%/aerial%; tackles-won%/interceptions/clearances/ball-recoveries; saves/goals-prevented/high-claims/goal-kicks; npxG) are **99–100% populated but ONLY in the second-tier slice** — Championship (1,656), La Liga 2 (924), Ligue 2 (609) — plus 99 EPL matches. They are **absent from the 15k FootyStats corpus**. Notable gaps: `high_claims` 49–73%, `np_expected_goals` 38% (LL2)/61% (L2)/98% (Champ), `touches_in_penalty_area` 67% (Champ). Native first-half splits exist for most fields (not for goals_prevented/npxG/high_claims/touches).

Consequence: cross-team interactions built on the rich fields are only testable in the 2nd-tier slice, and only against outcomes those matches carry.

## Step 2 — Hypothesis space and true candidate count

Six mechanism families were enumerated (same-stat persistence; cross-stat within team; cross-team interaction; referee-conditioned; style/tempo composition; for-vs-against). Feature sets of size 1–3, windows w5/w10.

- **Naive full systematic search** (all size-1/2/3 combinations × 12 targets): **~159,000 candidates pooled**, **~4,000,000 if split per-league**.
- **Mechanism-restricted design:** ~70 candidates per target-league, ~464 distinct candidates total under a per-league accounting.

## Step 4 — FDR pre-decision (stated before running)

A naive search is a **guaranteed null**: at a family of ~183k–4M, BH requires the best candidate to reach p ≤ 2.7×10⁻⁷–1.2×10⁻⁸ (z ≥ 5.0–5.6), unreachable at per-league n. I therefore pre-specified the **mechanism-restricted trim** (require a statable mechanism; windows w5/w10 only; respect known structural nulls via the gate; don't multiply the FootyStats-core family by league). This keeps the family defensible (~24k cumulative) and honest.

Actual family added this run: **46 gate-passed candidates tested → cumulative 23,823 → 23,869.** BH rank-1 survival threshold at that family: **p ≤ 2.09×10⁻⁶**.

## Step 3 — Sanity gate and the mis-specified-instrument catch (key methodological finding)

The reused rolling features (`team_a_*`/`team_b_*` over slots) are **mis-specified as team instruments**: `team_a_xg_w5` is the average xG of *whoever was the home team* in that team's recent matches, conflating team identity with venue. The sanity gate correctly **FAILED even pooled** (known-good xG→goals correlation **0.004**; corners known-good BSS −0.06). This is the same class of failure that has stopped seven prior runs — the gate did its job.

**Fix (still raw, still point-in-time):** rebuild features **team-consistently** — each team's own rolling rate of each stat (and the rate it concedes), regardless of home/away slot. This restored the signal:

| Instrument | slot-based corr | team-consistent corr |
|---|---|---|
| rolling xG → total goals | 0.004 | **0.109** |
| rolling corners → total corners | 0.016 | **0.056** |

**Pooled sanity gate after the fix (n≈3,077 test):**

| Target | gate | BSS | p |
|---|---|---|---|
| goals 1.5 / 2.5 / 3.5 | PASS | +0.97% / +0.43% / +1.03% | ≤1.4×10⁻³ |
| cards 3.5 / 4.5 | PASS | +2.27% / +2.35% | ~1×10⁻¹⁶ |
| BTTS / clean sheet | PASS | +0.42% | 1.5×10⁻³ |
| **corners 9.5 / 10.5** | **FAIL** | −0.58% / −0.26% | 1.0 |

Corners fails the gate even pooled → **marked untestable**, matching the documented near-zero corners persistence. It was not searched.

**Per-league gates all FAIL (0/9 in every league).** At ~300 matches/league (train ~187, test ~217) the modest signal that is only significant at n≈3,077 is undetectable. This is a genuine power limitation, not a broken tool (the pooled gate proves the tool works).

## Step 6 — Results, per league/target (never pooled as a result)

Because per-league lacks power, the search was run **pooled** (where the gate passes) with a **per-league diagnostic breakdown** attached to every candidate. Pooled, the strongest raw-stat relationships are:

| Target | Mechanism | Pooled BSS | p | +BSS in / #leagues | sig in any league |
|---|---|---|---|---|---|
| cards 3.5 | referee card-tendency × both teams' foul rate | +4.30% | 1.6×10⁻²⁹ | 2/2 | **0** |
| cards 4.5 | referee card-tendency × both teams' foul rate | +3.98% | 8.1×10⁻²⁷ | 2/2 | **0** |
| cards 3.5 | both teams' rolling yellow-card rate (persistence) | +2.27% | 9.1×10⁻¹⁶ | **0/8** | **0** |
| cards 3.5 | referee card-tendency alone | +2.64% | 1.0×10⁻¹⁹ | 2/16 | **0** |
| goals 3.5 | both teams' rolling xG (persistence) | +1.03–1.42% | ≤5×10⁻¹⁰ | 1/8 | **0** |
| goals 2.5 | both teams' rolling SOT (persistence) | +0.99–1.20% | ≤7×10⁻⁹ | 0–1/8 | **0** |

**The pooling confound, stated plainly:** 24 candidates clear the cumulative BH threshold pooled. **Zero are significant in even one individual league.** The clearest case: cards-persistence, pooled BSS +2.27%, is **negative in all 8 leagues where it could be tested** (Italy −0.47%, Spain −1.89%, MLS −2.36%, England Championship −2.83%, EPL −4.31%). The pooled model is exploiting the fact that *some leagues card more than others* (a league fixed effect / different base rates), which is not a within-league predictive relationship and is not exploitable. Conditioning on league — which per-league evaluation does — makes it vanish or reverse. This is a textbook Simpson's paradox.

**Mechanism note (why the referee-cards result is seductive but still confounded):** "card-happy referee + two fouling teams → more cards" has a genuine football mechanism, and it tops the pooled table. But its per-league support is 2/2 leagues positive with **p=0.20 and p=0.97** — i.e. not significant anywhere. The pooled p=1.6×10⁻²⁹ is driven by cross-league card-rate variation (refs in high-card leagues officiate high-card matches), not by within-league referee discrimination at the sample sizes available.

**Held-out access count: 0.** Nothing genuine survived per-league, so promoting any pooled survivor to held-out would only validate a confound. The held-out (2025/26) set was not read.

## Step 5 — Heatmap spatial batch (gated; costs quota)

Before any batch, I probed whether a spatial endpoint exists. **All four candidate endpoints returned 404** on a live match: `/heatmap`, `/heatmaps`, `/positions`, `/touchmap`. TheStatsAPI exposes no heatmap/attack-zone endpoint on this plan (only `/shotmap`, shot x/y, which is already partially wired and is shot-location, not the attack-distribution data the hypothesis needs).

**Decision: do not scale.** The gate's first precondition — clean spatial data to reconcile against outcomes — cannot be met because the data does not exist here. No directional-relationship check was possible. **Cost: 4 live requests** (monthly_remaining 5,518 → 5,514). The probe-first fetcher is committed at `scripts/heatmap_fetch.py` (isolated budget dir, transposition-check discipline documented) for the day a heatmap endpoint becomes available; `/shotmap` is the only spatial fallback and is noted for future work.

## Honest summary

- **Required discipline worked:** the sanity gate caught a mis-specified instrument (an 8th catch), and per-league evaluation caught a pooling confound that formal FDR alone would have waved through. Both are wins for the process even though the substantive result is null.
- **What genuinely exists:** a small (~1–2% BSS) within-corpus signal for cards and goals from team-consistent rolling rates, detectable only at pooled n≈3,000 — too weak to confirm at per-league n≈300. Corners persistence is ~0 (untestable). This is consistent with everything measured before: raw stats carry faint, real, but small predictive information that does not survive per-league scrutiny at available sample sizes.
- **No edge claim, no held-out spend, no discovery entry.** Cumulative FDR family updated to 23,869.

## Ground-rules compliance

- Raw observable stats only; no reference to any prior discovered metric. ✓
- Sanity gate before searching; failing cells (corners; all per-league) reported untestable rather than searched. ✓
- Point-in-time / walk-forward throughout (team-consistent expanding histories; referee expanding rates emit-before-update). ✓
- Cumulative FDR at 23,823 → reported new total 23,869; all candidates incl. gate-skipped/insufficient logged in the JSON. ✓
- Step 5 validation gated a batch that (correctly) never ran; fetcher committed. ✓
- Held-out untouched (0 accesses). ✓
- Quota reported: core run 0; heatmap probe 4 (5,518 → 5,514). ✓
- **Shared/global config:** none changed. New files only: `scripts/raw_stats_discovery.py`, `scripts/heatmap_fetch.py`, `data/discovery/raw_stats_discovery.json`, `data/thestatsapi/heatmap/*` (probe cache), this report, and one append to `public_site/failure_ledger.json` (F020). The metric library, corpus, and model code were read-only.
