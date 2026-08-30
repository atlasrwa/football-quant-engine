# Raw Stats Prediction Engine — Clean Build

**Date:** 2026-08-30
**Scope:** Raw observable match statistics only. No invented composites. No use of, reference to, or comparison against any previously discovered metric. **Fresh multiple-testing family for this run only** — the inherited cumulative family (23,869) is explicitly NOT carried forward.
**API cost:** 0 (all cached; no spatial/heatmap attempted — 404 on this plan).
**Held-out access count:** 1 (single reserved season, used only to confirm the surviving relationship).
**Artifacts:** `scripts/clean_features.py`, `clean_verify.py`, `clean_stage1.py`, `clean_rich_loader.py`, `clean_stage1_rich.py`, `clean_heldout_confirm.py`, `clean_stage2_ev.py`; results in `data/discovery/clean_*.json`.

---

## Headline

**Stage 1 (prediction):** After building features fresh and team-consistently and passing all five verification checks, a mechanism-guided, per-league, walk-forward search found **exactly one relationship that survives fresh FDR over the combined family AND confirms out-of-time on a reserved held-out season:**

> **A team's shots-on-target rate (with the opponent's shots-on-target-conceded rate) predicts that team's shots on target next match, per side — England Championship.** Discovery BSS **+4.62%** (p=1.4×10⁻⁶, n=582); held-out (reserved 2025 season) BSS **+5.25%** (p=4.5×10⁻⁶, n=471). Mechanism: shots-on-target is a genuinely persistent team trait (attacking volume and finishing tempo carry match-to-match), and the per-side framing captures asymmetry that a match-total model averages away.

Everything else — corners, cards, goals totals, BTTS, clean sheet — produced **no survivor** of fresh FDR in either tier.

**Stage 2 (EV):** **Untestable on the survivor.** The surviving relationship is shots-on-target per side, and **no shots-on-target market is cached** for these leagues (rich-slice Bet365 covers match_odds, BTTS, total_goals, match_corners, total_cards, DNB, double chance, AH, first-half, first-team-to-score only). Per the ground rule, this is reported as a data gap, not substituted. An illustrative EV backtest on *bettable* markets (which did not survive Stage 1) shows no market beat — every ROI confidence interval spans zero.

**Rich-data verdict:** The TheStatsAPI-only fields (tackles, duels, box touches, big chances, saves, npxG, etc.) **do not beat the broad-tier stats.** The single winner (shots-on-target) exists in both tiers; the rich tier surfaced it only because pooling multiple seasons gave the per-league sample the statistical power the single-season broad tier lacked. This argues **against** acquiring the rich data at scale for prediction.

---

## Features built fresh, and verified before any search

Features are keyed on **team identity** (`homeID`/`awayID`), aggregating each team's own prior matches regardless of home/away slot — not the inherited slot-based code, which conflated team identity with venue. Windows w3/w5/w10/season-to-date; "for" and "against"; explicit labelled home/away venue splits; referee expanding card/foul rates; emit-before-update for strict point-in-time safety. (`scripts/clean_features.py`)

**All five verification checks passed before searching** (`data/discovery/clean_feature_verification.json`):

| # | Check | Result |
|---|---|---|
| 1 | Team-identity trace | Feature = manual recompute from source matches for all sampled teams; every source involves the team; home+away appearances both included. (One team's `None` correctly reflected a genuine −1 missing value.) |
| 2 | Known-signal | goals-scored persistence **0.167**, cards persistence **0.161**, xG→goals **0.182** — all healthy (vs the old broken 0.004). |
| 3 | Orientation | home-team feature corr **+0.20** with home outcome vs **−0.07** with away — correct alignment, no transposition. |
| 4 | Look-ahead | strictly-prior recompute matches the feature across 20 sampled fixtures. |
| 5 | Shuffle null | true |corr| 0.20 vs shuffled max 0.035 — collapses to chance, no leakage. |

A verification-harness bug was found and fixed (the check oracle initially treated the −1 missing-sentinel as data); the feature engine itself was correct.

## Stage 1 — search design and results

**Restriction rule (documented before running):** only candidates with a statable football mechanism (same-stat persistence, cross-stat within team, cross-team interaction, referee-conditioned, style composition), sizes 1–3, windows w5/w10. An unrestricted all-combinations search (~159k candidates) is a guaranteed null and was not run. The fresh FDR family = exactly the (candidate × target × league) cells actually tested.

**Validity rule:** per-league, walk-forward; a candidate is a finding only if significant **within a league** after fresh FDR. Pooled-only significance is reported as an artifact, never a finding (this is what caught the prior run's Simpson's-paradox result).

**Gate:** per league/target, a known-good persistence instrument must show signal before same-stat-persistence candidates are searched. Corners persistence fails the gate (documented near-zero) — but per the spec, **cross-stat corners predictors (e.g. dangerous attacks → corners) are still tested** regardless. (An initial gate-design error that wrongly blocked cross-stat candidates was found and fixed; it had also produced a spurious "4 survivors" purely by shrinking the family to 6 and making BH trivially lenient. Correcting it both added power and set the right family size — after which the broad tier yields zero survivors.)

**Dispersion check (empirical):** corners var/mean = 1.15, cards 1.01 (Poisson-appropriate), shots-on-target 1.24 (mild overdispersion). Over/under targets were modelled with L2 logistic on the binarized outcome.

### Broad tier — FootyStats, 25 leagues (`clean_stage1_broad.json`)
- Fresh family: **182** within-league cells tested.
- **Within-league FDR survivors: 0.** Smallest p = 1.24×10⁻³ vs BH rank-1 threshold 2.75×10⁻⁴.
- Per-league gates mostly fail at n≈300 (train ~187 / test ~217) — genuine low power, reported as such, not worked around with pooling.
- Strongest uncorrected leads (per league; CIs span zero; **not** findings): corners "away corner-for × home corner-conceded → away corners" (Championship +6.09%, p=1.2×10⁻³); SOT "home SOT-for × away SOT-conceded" (Spain +7.83%, p=1.8×10⁻³); "dangerous attacks → corners" (USA/Spain +2.4–3.5%); referee foul/card tendency (Turkey/Italy/USA +1.8–3.2%).

### Rich tier — Championship / La Liga 2 / Ligue 2 (`clean_stage1_rich.json`)
- Fresh family: **92** within-league cells tested. Per-league n much larger (Championship 582, La Liga 2 360–370) via multi-season pooling → more power.
- Within-tier FDR survivors: **4**, all core shots-on-target persistence:

| League | Target | Mechanism | Discovery BSS | p | n |
|---|---|---|---|---|---|
| England Championship | home SOT o3.5 | home SOT-for × away SOT-conceded | +4.62% | 1.4×10⁻⁶ | 582 |
| La Liga 2 | away SOT o3.5 | away SOT-for × home SOT-conceded | +3.78% | 9.4×10⁻⁴ | 360 |
| England Championship (w10) | home SOT o3.5 | " | +2.81% | 5.1×10⁻⁴ | 510 |
| England Championship | away SOT o3.5 | away SOT-for × home SOT-conceded | +2.59% | 1.3×10⁻³ | 510 |

- **Rich-only fields do not survive anything.** Best rich-only mechanism: "home box touches × away clearances → home goals" (La Liga 2 +1.66%, p=0.053). None clear FDR.

### Combined fresh family and the conservative survivor
Pooling both tiers into one honest fresh family (**274** candidates), BH rejects **exactly 1**: the England Championship home-SOT relationship (p=1.4×10⁻⁶). The other three rich-tier rejections do not survive the combined family. So the single defensible Stage-1 finding is that one relationship.

### Held-out confirmation (the only held-out access)
Reserving the **newest season (2025)** as held-out and fitting only on older seasons (`clean_heldout_confirm.json`):

| League | Target | Held-out result |
|---|---|---|
| England Championship | home SOT o3.5 | **CONFIRMED** — held-out BSS +5.25%, p=4.5×10⁻⁶, n=471 |
| La Liga 2 | away SOT o3.5 | **CONFIRMED** — held-out BSS +3.40%, p=5.7×10⁻⁴, n=431 |
| England Championship | away SOT o3.5 | not confirmed — held-out BSS +1.12%, p=0.079 |

The home-SOT Championship relationship is genuine and out-of-time robust. Held-out access count = **1** (single reserved season).

## Stage 2 — EV vs market

**The survivor is not bettable.** Shots-on-target has no cached market in these leagues. EV on the survivor is therefore **untestable — reported as a gap, not substituted.**

Illustrative EV on bettable markets that did **not** survive Stage 1 (`clean_stage2_ev.json`), rich slice, walk-forward, with the mandatory reliability filter (both teams' rolling history present; flag |edge| ≥ 3pp; edges net of overround):

| League | Market | Overround | Median edge | Flags | Flat ROI | 95% CI |
|---|---|---|---|---|---|---|
| Championship | goals O2.5 | 5.26% | −0.17pp | 113 | +19.8% | [−0.5, +39.5] |
| Championship | corners O9.5 | 8.01% | +1.20pp | 40 | +10.9% | [−17.5, +38.4] |
| Championship | corners O10.5 | 8.21% | −2.66pp | 45 | −8.5% | [−34.0, +18.2] |
| Championship | cards O3.5 | 8.17% | +8.32pp | 69 | +9.2% | [−11.9, +29.7] |

**Every ROI confidence interval spans zero.** No market beat. These are backtest-only leads on non-surviving candidates; the positive point ROIs are noise at these flag counts (n≈40–113), and the cards O3.5 "+8.32pp median edge" is the familiar model-overshoot miscalibration, not real edge. The reliability filter removed few flags here (w5 history is almost always present); the prior −0.56 divergence-degradation concern is not separately re-established on this small, non-significant set.

## Honest summary

- **Best predictor of shots on target:** a team's own SOT rate × opponent's SOT-conceded rate (per side) — held-out confirmed in the Championship (+5.25% BSS). This is the run's one real finding.
- **Best predictor of corners / goals / cards:** nothing survives fresh FDR. Leads exist (dangerous-attacks→corners, xG→goals, referee→cards) but all have CIs spanning zero at available per-league n.
- **Beating naive ≠ beating the market:** the SOT relationship beats naive out-of-sample, but there is no SOT market to beat; on markets that do exist, nothing beats the book.
- **Rich data does not earn its keep** for prediction here — the winner is a broad-tier stat, and rich-only fields add no surviving signal.
- **Fresh FDR family this run:** 182 (broad) + 92 (rich) = **274**; 1 survivor under the combined family, held-out confirmed. The inherited 23,869 was not used.

## Ground-rules compliance

Raw observables only, no composites, no prior-metric reference ✓ · fresh FDR family (not 23,869) ✓ · features built fresh & team-consistently, slot-based code not reused ✓ · all 5 verification checks reported before searching ✓ · point-in-time absolute (emit-before-update, walk-forward) ✓ · sanity gate per league/target ✓ · within-league significance required, pooled treated as artifact ✓ · zero API, no spatial attempts ✓ · held-out used only to confirm the survivor, access count 1 ✓ · code committed ✓ · **no shared/global config changed** — all new files under `scripts/` and `data/discovery/`; the metric library, corpus, and `src/` were read-only.
