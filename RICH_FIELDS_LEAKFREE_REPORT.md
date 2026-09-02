# Rich Fields Through the Leak-Free Path — Report

**Verdict: same null.** The TheStatsAPI rich fields carry no prior-only signal the
FootyStats-schema baseline lacks. Fed through the identical leak-free count-regression
path, adding them ranges from **neutral** (small mechanism groups) to **actively
harmful** (the full rich set), never beneficial. No cell where rich beats baseline.

Pre-registered before running: bootstrap seed **20260902**; markets {corners, cards,
shots-on-target}; leagues {Championship, La Liga 2, Ligue 2}; within-league only
(pooling is a documented Simpson's-paradox trap); fresh **BH FDR family = 9** (3
markets × 3 leagues); window 10, min-prior 3.

---

## 1. Construction (leak-free, structural guard extended)

Extended `src/research/models/prior_only_features.py` with a rich-corpus builder
(`build_rich_prior_only_features`) using the **identical discipline** as the
FootyStats path: rolling means over each team's **strictly-prior** matches,
team-identity keyed (`home_id`/`away_id`), compute-before-update, "for" variants per
team-side. The FootyStats path is untouched; `CountRegressionModel` math is untouched.

The structural anti-leakage guard was **extended to cover the rich fields**
(`assert_no_same_match_leakage_rich`) and runs before every fit: (a) no raw
same-match key (`team_a_*`/`team_b_*` or a bare rich field name) may appear as a
feature; (b) every `<field>_<side>` feature must equal an **independent
strictly-prior recomputation**. Tests (`tests/test_prior_only_features.py`, 11 pass)
include the decisive check that the guard **raises** when a fixture's own realized
`tackles` is injected as a feature. Nothing is exempted.

## 2. Field availability (buildability first; excluded, not zero-filled)

A field is *buildable* for a match-slot only if that team has ≥3 earlier matches with
the field populated. Included when ≥80% of predictable slots are buildable in that
league; otherwise **excluded per league (never zero-filled)**.

| Field | Championship | La Liga 2 | Ligue 2 |
|---|---|---|---|
| baseline `xg` | ✓ 100% | ✗ 0% | ✗ 0% |
| `touches_in_penalty_area` | ✗ 72.5% | ✓ 100% | ✓ 100% |
| `np_expected_goals` | ✓ 99.7% | ✗ (<80%) | ✓ 94.5% |
| `high_claims` | ✗ 70.1% | ✓ ~98% | ✓ ~98% |
| `goals_prevented` | ✓ 100% | ✗ 0% | ✗ 0% |
| all other rich fields + `fouls`, `shots_on_target` | ✓ | ✓ | ✓ |

**Corrections to prior assumptions** (measured, not assumed): `goals_prevented` is
**not** 0% everywhere — it is 100% buildable in the Championship, 0% in La Liga 2 /
Ligue 2. `touches_in_penalty_area` is 72.5% in the Championship now (not ~5%), still
below threshold so excluded there. Ligue 2 baseline xG confirmed 0%. Result: baseline
in La Liga 2 / Ligue 2 is {fouls, shots-on-target} only; Championship adds xG.

## 3. Rich-augmented vs baseline (same corpus, same folds, within-league)

Difference = (rich BSS − baseline BSS), paired bootstrap over common scored matches,
seed 20260902. Negative = rich is worse.

| League | Market | Baseline BSS | Rich BSS | Δ (rich−base) | 95% CI | p | BH |
|---|---|---|---|---|---|---|---|
| Championship | corners | −1.68% | −6.31% | **−3.97%** | [−6.47, −1.54] | 0.001 | reject (worse) |
| Championship | cards | −1.25% | −4.75% | **−3.96%** | [−6.34, −1.60] | 0.001 | reject (worse) |
| Championship | SOT | +0.72% | −5.25% | **−5.61%** | [−8.20, −3.06] | ~0 | reject (worse) |
| La Liga 2 | corners | −0.87% | −8.92% | **−8.74%** | [−13.09, −4.59] | ~0 | reject (worse) |
| La Liga 2 | cards | +0.91% | −9.62% | **−9.29%** | [−14.50, −4.33] | ~0 | reject (worse) |
| La Liga 2 | SOT | +3.52% | −7.25% | **−10.87%** | [−15.36, −6.43] | ~0 | reject (worse) |
| Ligue 2 | corners | −0.81% | −14.92% | **−17.17%** | [−25.64, −8.98] | ~0 | reject (worse) |
| Ligue 2 | cards | +0.75% | −13.72% | **−15.78%** | [−22.64, −9.07] | ~0 | reject (worse) |
| Ligue 2 | SOT | −2.20% | −13.27% | **−11.92%** | [−19.22, −4.93] | ~0 | reject (worse) |

Calibration worsens in lockstep: ECE ~0.02–0.06 (baseline) → ~0.07–0.17 (rich). The
damage **scales with corpus smallness** (Ligue 2, n=612, worst) — the signature of a
lightly-regularised model overfitting ~21–23 correlated prior-only rolling features.

**Mechanism-group check** (to avoid conflating "too many features" with "no signal"):
small 4–5-field targeted additions per market do far less damage (Δ −0.5% to −2.7%),
and several are statistically indistinguishable from baseline (CI spans 0:
Championship corners/cards/SOT; Ligue 2 corners/cards/SOT). But **none beats baseline
positively** — the best is Championship SOT +0.33% (CI [−0.77, +1.40], spans 0).

**Which fields the model leans on:** the largest rich weights are consistently
`np_expected_goals`, `big_chances`, `big_chances_missed` (plausible attacking-quality
proxies). They attract weight in-sample but do not improve out-of-sample calibration
or sharpness — weight ≠ signal here.

**Power framing (honest):** the audit detection floor is a ~1.89% CI half-width; a
true ~1% edge would read as "CI spans 0". Here the rich additions do not merely fail
to clear that floor — the full-set differences are **significantly negative**, well
outside the floor. This is not "underpowered to confirm a small gain"; it is a
measured degradation. The baseline-on-rich-corpus figures themselves hover around zero
(corners −1.7 to −0.8%, cards −1.3 to +0.9%, SOT −2.2 to +3.5%), consistent with the
established FootyStats-only null (corners −1.83%, cards −1.82%).

## 4. Formation / lineup availability (scoped, report only)

- **Cached corpus: no lineup/formation data in either source.** TheStatsAPI `/stats`
  payloads contain only aggregate stat groups (overview/shots/attack/passes/duels/
  defending/goalkeeping/npxg); its fixture objects carry no lineup/formation. The
  FootyStats corpus was built from the League-Matches/schedule endpoint, which has
  zero lineup/formation fields. An exhaustive grep of the cache found none.
- **API capability:** FootyStats offers lineups only via its separate **Match Details**
  endpoint ("Trends and Lineups"), not the schedule endpoint used for the corpus, and
  it does not list formation as a field. TheStatsAPI's coverage metadata carries a
  per-league `lineups: available` capability flag, so lineups are obtainable, but
  formation is not a confirmed field and none is cached.
- **Timing/retention:** official lineups publish ~1 hour before kickoff (per industry
  docs; ~20–40 min elsewhere), and minor competitions may have none pre-match — the
  same near-kickoff-only pattern as opening odds / Betfair. No confirmed historical
  formation feed.
- **Which case applies:** formations/lineups can at best be a **near-kickoff display
  feature on imminent fixtures, not a backtestable modelling input.** The cached corpus
  has none, lineups are only known ~1h pre-kickoff, and formation is not a confirmed
  historical field. Backfilling historical lineups via FootyStats Match Details would
  cost per-match API calls and still leave formation to be derived from positions, with
  no confirmed historical formation source.

---

## Direct verdict

**Do the rich fields add anything? No — this is the same null.** Through the leak-free
prior-only path, TheStatsAPI's rich fields (tackles, duels, big chances, npxG, touches
in box, blocks, crosses, and the rest) provide no signal the FootyStats-schema baseline
lacks. In every market × league the full rich set is significantly *worse* than
baseline (overfitting), and no targeted mechanism group beats baseline. This is
consistent with everything measured to date: raw per-feature correlations ~0.016,
published prior-only effects ~1%, and the earlier 866-feature build that added variance
rather than signal. The corners/cards (and SOT) prior-only null stands, and the rich
fields do not change it. Formations/lineups are not a backtestable input for this
corpus, so they cannot rescue it either.

Scope: this is a *diagnostic* result. No model math, scope, or ledger was changed. The
`prior_only_features.py` extension is additive (the FootyStats path is untouched) and
its structural guard now covers the rich fields, so this bug class cannot silently
return on the rich path.

---
*Artifacts: `scripts/rich_field_availability.py`, `scripts/rich_leakfree_test.py`,
`src/research/models/prior_only_features.py` (extended), `tests/test_prior_only_features.py`
(11 pass), `data/results/rich_field_availability.json`, `data/results/rich_leakfree_test.json`.
Seed 20260902; BH family 9; zero API.*
