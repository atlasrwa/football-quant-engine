# Target-Aware Market Panel Protocol V1

**Status:** apparatus frozen. No outcome of the fresh cohort has been read, no model has been fit, no OOS comparison has been run and no LLM has been called.
**Next step:** hand the prepared requests to GPT-5.6 Sol.

**Question.** Can a frontier LLM, given rich pre-match evidence and an explicit forecast market, propose *transferable* contextual feature templates? And do those templates add incremental walk-forward predictive information beyond a deterministic baseline built on the **same** data?

## 1. Markets

`MARKET_CAPABILITY_REGISTRY_V1.json` is produced by scanning the provider cache (`registry.py`), not written by hand. The audit is `MARKET_CAPABILITY_AUDIT_V1.md`.

**Label capability and price capability are separate.**
- A label is supported when:
  - both sides are non-null in ≥ 90% of matches;
  - nulls are two-sided (the whole statistic missing, never "null means zero");
  - for half periods, first half + second half = full match in ≥ 99% of sides.
- A price is supported when:
  - raw pre-kickoff timestamped captures exist;
  - a validated adapter exists;
  - the priced quantity equals the label.

The **target universe** is every market eligible for both generation and modeling (`TARGET_UNIVERSE_V1.json`); odds are not required:

| Family | Targets |
|---|---|
| GOALS | TOTAL_GOALS, BTTS |
| CORNERS | TOTAL_CORNERS |
| TEAM_TOTALS | HOME/AWAY_GOALS, HOME/AWAY_CORNERS |
| BOOKINGS | TOTAL_YELLOW_CARDS: a provider-native **proxy** of the "cards" market, never compared with it |
| HALF_TIME | **not evaluable**: no bulk half-time score; half corners and yellows have no provider market |

**Lines** (`MARKET_LINE_POLICY_V1.json`):
- primary = the mode, over strictly pre-kickoff captures, of the most balanced half-line;
- secondary = primary ± 1.

Only market *structure* is used, never price levels, and never by the LLM.

## 2. Panel

- **Panel rows:** every finished TheStatsAPI league match in the cache, 2024-08 to the last complete bulk date, **2026-09-14**. That is about 5,600 matches across 6 competitions.
- **Excluded from the panel:** the operator gap fetches (`dpl_`, `tamp_`), which feed only the cohort packets, and conflicting stats payloads.
- **PIT rule:** every feature for fixture i uses only rows with kickoff < t_i. The panel store refuses queries beyond its end.
- **Scaling:** competition-relative robust z-scores (median / 1.4826 MAD) over strictly prior team-match values, with at least 200 reference values.
- **Strength:** mean goal difference over the last 10 same-competition matches. It is **never** a similarity dimension; it enters M0 and M1 as a separate covariate. Every similarity or profile dimension reports its style–strength correlation.

## 3. Hypotheses to features

**Sol requests** (`out/sol_requests/`):
- one per fixture × family, holding the family slice, targets, Prompt V2, schema and baseline coverage;
- no prices, p_model or outcomes;
- 12 fixtures × 4 families = 48 requests.
- **Primary-line targets only.** Templates don't depend on the line, so each compiled class-C template is instantiated for the secondary lines afterwards. That caps volume at 2 hypotheses per market per fixture.

**Novelty compiler** (`templates.py`). The deterministic class precedence is D > F > E > G > A/B/C:

| Class | Meaning |
|---|---|
| D_UNMEASURABLE | outside the grammar, unresolved refs, over the volume limit, or forbidden keys |
| F_SAME_MATCH_LEAKAGE | a window that is not strictly prior, or same-match information required |
| E_PROVIDER_UNSUPPORTED | a metric outside the slice or forbidden, or an unverified half metric |
| G_DUPLICATE_TEMPLATE | identical canonical template |
| A_BASELINE_EQUIVALENT | an M0 rolling mean, or a linear combination of them |
| B_SIMPLE_INTERACTION | a pairwise product or ratio, or a non-M0 single rolling mean |
| C_CONTEXTUAL_TEMPLATE | multi-dimension matchup, opponent-similarity conditional, or state deviation |

**Only class C enters M1.** The class-C set is fixed when the responses are compiled, before any panel outcome is read.

**Cohort-level compile** (`compile_cohort`):
- all 48 responses are compiled in a fixed order (fixture id, then family) with **one shared duplicate set**;
- a template's identity is (market, template), independent of the line and the fixture;
- so the same template proposed for several fixtures becomes a single M1 column.

**Panel compiler** (`panel.py`). `instantiate(template, panel, fixture)` computes a template for any fixture id. Opponent-similarity uses:
- the style profile over the last 10 venue-matched matches, needing at least 5 values per dimension;
- RMS distance;
- the nearest tercile of the subject team's prior matches, with at least 5 neighbours and at least 15 prior matches;
- a shrunk neighbour-minus-overall mean, with κ = 5.

## 4. Walk-forward OOS

**Models.**
- **M0:** elastic-net logistic regression, one model per target. For both teams and every metric in the family context, rolling FOR/AGAINST means over W5, W10, season-to-date and venue season-to-date, plus strength and competition.
  - M0 also includes the **same half-level rolling means** (FIRST_HALF and SECOND_HALF) for the family's half-level metrics, so half-level data can never reach M1 alone.
  - A single half-level rolling mean therefore classifies as A.
- **M1:** M0 plus the family's class-C template features. **Nothing else differs.**
- Both use the Item 6 machinery unchanged:
  - saga solver, `max_iter` 4000, `random_state` 0;
  - C grid {0.003, 0.01, 0.03, 0.1}, l1_ratio grid {0.2, 0.5, 0.8};
  - nested TimeSeriesSplit(4) inside each training fold, selecting on negative log loss;
  - a 60% coverage screen fit on training rows only;
  - median imputation and standardization inside the pipeline;
  - isotonic calibration on inner out-of-fold predictions, then a clip to [0.01, 0.99].

**Folds.** 5 expanding chronological folds on match-count quantiles, with 20% minimum training history, and retraining once per fold.

The fold manifest is **frozen and hashed now**: `TARGET_AWARE_FOLD_MANIFEST_V1.json` holds ids, kickoffs, competitions, folds and cohort-team flags, with no outcomes.

| | Rows |
|---|---|
| Panel | 5,620 |
| OOS, all rows | 4,496 |
| OOS, **primary scoring set** (no cohort team) | **3,057** (68%) |

Primary OOS rows per fold: 626, 649, 588, 589, 605. Excluding the 24 cohort teams costs about a third of the OOS rows. That power cost is accepted and stated here in advance.

**Metrics.**
- Primary: log loss.
- Also reported: Brier score and ECE with 10 equal-width bins. Hit rate is never primary.

**Scoring sets.**
- **Primary:** OOS rows involving **no cohort team**. The LLM saw those 24 teams' histories, and their rows would score templates the LLM was inspired by.
- **Secondary:** all rows.
- Early folds predate data the LLM saw; only the prospective phase is fully clean.

**Per family**, each family is scored separately, and one family cannot rescue another:
- the primary is the mean over its targets of the per-fixture paired log-loss delta (M0 − M1, positive = M1 better) at the **primary lines**;
- the null is a paired ISO-week block bootstrap, 10,000 resamples, seed 0, percentile CI;
- a family passes only if the delta > 0, the CI's lower bound > 0, the delta ≥ 0.001 nats, and ECE_M1 ≤ ECE_M0 + 0.005.

**Multiplicity.**
- The family set is fixed at **GOALS, CORNERS, TEAM_TOTALS and BOOKINGS**, with Holm–Bonferroni at α = 0.05 on one-sided bootstrap p-values.
- HALF_TIME is reported as `NOT_EVALUABLE`.
- The family never shrinks at runtime. A non-evaluable family enters with p = 1 for bookkeeping only, recorded with `primary_p_value = null` and `multiplicity_placeholder = true`.
- Secondary lines and individual templates are exploratory, with BH q = 0.10 over the fixed class-C set.

## 5. Market comparison and prospective phase

- **Market comparison** happens only after OOS probabilities are frozen. It covers only markets with validated, timestamped pre-kickoff prices: TOTAL_GOALS, and BTTS pre-match. The genuine close (`LAST_BEFORE_KICKOFF`, the latest capture strictly before kickoff) is TOTAL_GOALS only. `cma last_seen` is never a close.
- **Coverage inside the panel is tiny:** only **57** of 5,620 panel matches have a validated pre-kickoff capture for TOTAL_GOALS or BTTS. The captures begin in September 2026, and the panel ends on 2026-09-14. Market comparison is therefore **effectively prospective-only**; the ~274 captured matches are mostly outside the panel window.
- **Prospective phase:** only if a family passes. It uses fixtures after the freeze and is never back-labelled.

## 6. Three possible outcomes

1. The class-C share is negligible, so the LLM's hypothesis-generation value is not demonstrated.
2. Class-C templates exist but no family passes, so the research space expanded but no predictive value was shown.
3. A family passes on the primary scoring set. Only this supports moving to prospective market evaluation.
