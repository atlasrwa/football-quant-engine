# GPT-5.6 Sol V1 — Deterministic Novelty Audit

**Source freeze:** `7463e1dcce4584a3772aa10c6c3dc07b32803e4d`  
**Outcomes read:** no  
**Panel instantiated:** no  
**Model fit / OOS:** no

## Structural result

The 48 frozen Sol responses contain **132 raw hypotheses**. Under the already-frozen canonical identity `(market, structured feature template)`:

- **124** are first-seen **C_CONTEXTUAL_TEMPLATE** instances.
- **8** are **G_DUPLICATE_TEMPLATE** exact repeats.
- **0** classify as A, B, D, E or F in this structural freeze.

This means the generated set is structurally valid under the closed grammar, but it does **not** mean Sol discovered 124 conceptually independent football mechanisms.

## Conceptual concentration

The 124 exact unique templates use only **two** grammar types:

- OPPONENT_SIMILARITY_CONDITIONAL: **116**
- MULTI_DIMENSION_MATCHUP: **8**

So the dominant pattern is opponent-profile conditioning with fixture-specific metric combinations. The exact-template count is high because the selected profile dimensions differ across fixtures/markets.

## Unique templates by market

- AWAY_CORNERS: 12
- AWAY_GOALS: 12
- BTTS: 24
- HOME_CORNERS: 12
- HOME_GOALS: 12
- TOTAL_CORNERS: 24
- TOTAL_GOALS: 8
- TOTAL_YELLOW_CARDS: 20

## Exact duplicate provenance

- `mt_511922498_YC_HOME_SIM` duplicates `mt_155833431_YC_HOME_SIM`
- `mt_511922498_YC_AWAY_SIM` duplicates `mt_155833431_YC_AWAY_SIM`
- `mt_511922498_GOALS_RECIPROCAL_CHANCE_MATCHUP` duplicates `mt_200175799_GOALS_RECIPROCAL_CHANCE_MATCHUP`
- `mt_644680453_YC_HOME_SIM` duplicates `mt_155833431_YC_HOME_SIM`
- `mt_644680453_YC_AWAY_SIM` duplicates `mt_155833431_YC_AWAY_SIM`
- `mt_644680453_GOALS_RECIPROCAL_CHANCE_MATCHUP` duplicates `mt_377400501_GOALS_RECIPROCAL_CHANCE_MATCHUP`
- `mt_899703080_GOALS_RECIPROCAL_CHANCE_MATCHUP` duplicates `mt_155833431_GOALS_RECIPROCAL_CHANCE_MATCHUP`
- `mt_988903840_GOALS_RECIPROCAL_CHANCE_MATCHUP` duplicates `mt_200175799_GOALS_RECIPROCAL_CHANCE_MATCHUP`

## Interpretation before outcomes

The generation stage cleared the first structural bar: its outputs are pre-match contextual templates rather than same-match descriptions or trivial rolling means.

However, conceptual breadth is narrower than the raw count suggests. This freeze therefore supports the next deterministic question—**do these contextual shells have adequate panel support and stable coverage?**—but does not yet establish predictive value or broad LLM creativity.

The next permitted stage is panel instantiation/support diagnostics only. OOS fitting should remain blocked until the frozen class-C registry is instantiated, coverage/support/style-strength diagnostics are recorded, and the eligible feature set is frozen.
