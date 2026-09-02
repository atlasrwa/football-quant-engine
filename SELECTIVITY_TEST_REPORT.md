# Selectivity Test — Is Skill Concentrated in an Identifiable Prior-Only Subset?

**Verdict: plain null.** Skill is **not** concentrated in any identifiable,
strictly-prior-computable subset tested. Across a pre-registered family of **72 cells**
(8 selection rules × 3 markets × 3 leagues), **zero** cells show the selected subset
beating the all-matches baseline with a bootstrap CI excluding zero **and** surviving
Benjamini–Hochberg correction. Where selection moves skill at all, it moves it *down*:
among the 47 cells large enough to test, 6 had a CI entirely **below** zero (subset
*worse*) versus only 2 entirely above — and neither of those 2 survives BH.

This is the "a bettor doesn't bet every match" framing. The answer here is that the
leak-free model does not become skilful on any prior-only slice we can name in advance.
Combined with the schema audit, the literature benchmark, and the rich-field null, this
closes the "the data is being used wrongly" question for corners/cards/SOT on this
corpus.

Pre-registered **before running**: bootstrap seed **20260902** (primary), stability
seeds **{1, 7, 42}** reported separately; **minimum subset size 60** settled
predictions; markets {corners@9.5, cards@3.5, SOT@8.5}; leagues {Championship, La Liga
2, Ligue 2}; **within-league only**; fresh **BH FDR family = 72**, q = 0.10.

---

## 1. What is new here

Every prior test measured **average skill across all fixtures** (leak-free,
within-league: corners −1.83% BSS, cards −1.82%). This test asks a structurally
different question: does the *same unchanged model* become skilful on a subset that can
be identified **strictly before kickoff**? A model can sit at zero on average yet be
genuinely skilful where the signal is unusually clear — *if* such a slice exists and is
nameable ex-ante.

The leakage discipline is identical to everywhere else, applied to the **selection
criterion** rather than to the features: a subset chosen using match outcomes is
worthless.

## 2. Construction (reuses the leak-free path; model untouched)

`scripts/selectivity_test.py` reuses the leak-free machinery verbatim:

- Features: `build_rich_prior_only_features` (strictly-prior rolling means), with the
  structural feature guard `assert_no_same_match_leakage_rich` run **before every fit**.
- Model: **unchanged** `CountRegressionModel` on the **baseline** feature set (fouls,
  shotsOnTarget, xg-where-buildable). The rich fields were already shown to hurt, so the
  baseline is the honest model. No model math is touched.
- Walk-forward: MIN_TRAIN = 100, REFIT = 50, window 10 — identical to the rich test.

At each **scored** fixture the harness records a `SelectionContext` built **only** from
data strictly before that fixture (compute-before-update, mirroring the feature
builder): per-team prior in-window match counts, per-team rolling mean and variance of
the **target metric**, |home_rate − away_rate|, the model's `p_over`, the strictly-prior
base rate, and the fixture's ordinal position within its season. **The fixture's own
outcome is never in that context.**

## 3. Structural anti-outcome-leak guard on the selectors

The same "prove it, don't promise it" discipline used for features is applied to the
**selectors**:

- `SelectionContext` is a **frozen** dataclass that, by construction, exposes **no**
  outcome / label / post-match attribute.
- `assert_selector_prior_only(selector, ctx)` runs each rule against a probe that
  **raises** if the selector reads any forbidden (outcome) attribute, any unknown
  (non-prior) attribute, or attempts to mutate the context. This guard runs in-loop for
  all 8 rules in every one of the 9 (market × league) cells before any evaluation.
- `tests/test_selectivity_selectors.py` (**18 pass**) proves every pre-registered rule
  is prior-only and that a selector touching the outcome, an unknown field, or mutating
  the context **raises** `AttributeError`.

## 4. The selection-rule family (all prior-only) — this IS the multiple-testing family

Rule thresholds (terciles) are **frozen from a warmup window strictly prior to every
scored fixture** (variance/gap terciles from the first MIN_TRAIN contexts; the
confidence tercile from the oldest 20% of scored fixtures), never by ranking a test
fixture against future fixtures.

| # | Rule | Definition (computable before kickoff) |
|---|---|---|
| 1 | `data_conf_N5` | both teams ≥ 5 prior in-window matches |
| 2 | `data_conf_N8` | both teams ≥ 8 prior |
| 3 | `data_conf_N12` | both teams ≥ 12 prior |
| 4 | `stable` | combined recent rolling-rate **variance** in bottom tercile (both teams behaving consistently) |
| 5 | `extreme_diff` | \|home_rate − away_rate\| on the target metric in top tercile |
| 6 | `high_conf` | \|p_over − base\| in top tercile (model far from base rate) |
| 7 | `mid_late_season` | fixture in the second half of its season |
| 8 | `stable_AND_extreme` | rule 4 **and** rule 5 |

**FDR family size = 8 rules × 3 markets × 3 leagues = 72.** Counted honestly; BH applied
across all cells that meet the minimum-n bar.

## 5. Results

All-matches baseline BSS (own-base reference), per cell, for orientation:

| League | corners | cards | SOT |
|---|---|---|---|
| Championship | −1.68% | −1.25% | +0.72% |
| La Liga 2 | −0.87% | +0.91% | +3.52% |
| Ligue 2 | −0.81% | +0.75% | −2.20% |

**Family-level outcome:**

- Cells contributing a p-value (n ≥ 60): **47 / 72**. The other 25 were correctly
  excluded for small-n — `data_conf_N12` selected 0 fixtures in this 10-match window,
  and `stable` / `stable_AND_extreme` mostly selected a handful.
- **BH-rejections (any direction): 0.**
- **Positive findings (subset > all-matches, CI > 0, BH-reject): 0.**
- Among the 47 tested cells, **6 had a CI entirely below zero** (subset *worse* than
  betting everything) and only **2 entirely above** — neither survives BH.

**The small-n guard did real work.** The eye-catching subset figures — Ligue 2 cards
`stable` +22.6%, Ligue 2 corners `stable_AND_extreme` −46.1%, Championship cards
`stable_AND_extreme` +12.4%, Ligue 2 cards `stable_AND_extreme` +33.4% — all came from
cells selecting ≤ 10 fixtures and were excluded before BH. Reporting any of them would
have been a small-n artefact.

**The "model confidence" dimension failed as forewarned.** The disagreement-decile work
predicted performance *degrades* where the model is most confident relative to base rate.
Confirmed: where `high_conf` was even nominally significant it was **worse** —
Championship corners −6.82% vs −1.68% (p = 0.017), Ligue 2 SOT −11.68% vs −2.20%
(p = 0.050). Confidence anti-selects.

**Profile stability was worse, not better.** `stable`, where it selected enough to test
(Championship corners, n = 64), was −10.79% vs −1.68% (p = 0.006) — the consistent-team
subset was markedly *worse*.

**The only positive-looking nominal p-values die under correction.** La Liga 2 SOT
`high_conf` (subset +7.70% vs +3.52%, p = 0.030) and `mid_late_season` (+6.25%, p =
0.022) look tempting in isolation but do **not** survive BH across the family of 72.
Because zero cells survived, seed-stability adjudication was moot (there was nothing to
re-check at seeds {1, 7, 42}).

Full per-cell numbers (selection rate, subset BSS, complement BSS, n, CI, p) are in
`data/results/selectivity_test.json` (git-ignored).

## 6. What this closes

Nothing survives the four honesty gates simultaneously: **min-n ≥ 60**, **subset beats
all-matches**, **CI excludes zero**, and **BH across the family of 72**. The direction of
what little signal exists is *negative* — selecting on these prior-only dimensions makes
the model worse, not better. There is no prior-only slice on this corpus where the
leak-free model is skilful.

Honest null. Failure-ledger-worthy. Per the ground rules, this pass does **not** modify
`scope.py`, the models, or any ledger, and does not touch Pilot C, Pipeline A, the manual
path, or the scanner. Zero API calls were made.

## 7. If a future pass wants to revisit

A negative result here is conditional on the rule family and corpus. A genuine
confirmation of *any* concentrated-skill hypothesis would require: (a) a rule stated
precisely enough to apply to a future fixture, (b) subset **and** complement performance
with n and CI, (c) BH survival within its declared family, (d) stability across the
pre-registered seeds, and critically (e) **forward or held-out validation on fixtures not
used to discover the rule**. No rule in this pass reached even step (c), so none is
promotable.

---

### Reproduce

```
cd /home/ubuntu && source .venv/bin/activate
python3 -m pytest tests/test_selectivity_selectors.py -q      # 18 pass (selector guard)
python3 scripts/selectivity_test.py                            # prints family verdict; writes JSON
```

**Shared/global config touched: none.** New files only — `scripts/selectivity_test.py`,
`tests/test_selectivity_selectors.py`, this report. The reused
`src/research/models/prior_only_features.py` and `src/research/models/count_regression.py`
are unmodified.
