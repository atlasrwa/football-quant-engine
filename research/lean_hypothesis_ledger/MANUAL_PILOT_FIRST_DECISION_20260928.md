# Manual pilot first — user decision, 28 September 2026

Status: active operating direction for the manual pilot.

## Decision

Complete the existing 40-declaration pilot manually before revisiting champion replacement or expanding the lean-champion implementation. The user supplies Scores365 / 365Scores snapshots of upcoming fixtures. The assistant analyzes the evidence, identifies supported market disagreements, and freezes selected hypotheses in the append-only ledger before kickoff.

This is a workflow and priority decision, not a new probability formula, model promotion or authorization to bet. Preserve the existing source-of-truth scientific requirements, historical model versions, declarations and outcomes. Do not silently switch formulas or tune them to completed matches.

## Working process

1. Read the supplied snapshots, identify the fixture and kickoff, retain sample sizes and filters, and distinguish unavailable evidence from zero.
2. Research relevant pre-match context and findable online market prices, as already requested by the user. Review goals, BTTS/team goals, team/total corners and bookings where evidence supports them; do not restrict the manual scan to corners. Assess venue, opposition, competition, recent history, H2H and referee/weather when relevant and verifiable; never invent adjustments.
3. Use documented deterministic calculations for numerical probabilities. Record the exact inputs, formula/version, source limitations and any sensitivity. An unrecoverable estimator remains unreproduced; exploratory diagnostics are not silently promoted into a frozen model.
4. Present the strongest supported disagreements with exact market, side, threshold, price, break-even, no-vig benchmark when opposing quotes exist, and estimated EV where supported. Keep statistical disagreement distinct from executable-price value. Preserve abstentions and contrary evidence.
5. The user may supply Rushbet screenshots for comparison on the identified lines. Record actual quote source and observation time; never label online reference odds as executable Rushbet prices.
6. Freeze the chosen supported hypothesis in the ledger before kickoff, including its exact line, odds when available, numerical method, rationale and limitations. The user's standing instruction authorizes routine analysis and ledger freezing without a repeated permission step. An unpriced/unresolved candidate stays a research candidate rather than being presented as a priced edge.
7. Append settlement separately, distinguishing user-reported outcomes from independently verified results. Keep all losses, correlated selections and unavailable information. No backdating or replacement of a declaration after outcomes.
8. At 40 declared tests, review the full pilot and decide the next architecture step with the user. Assess market families, prices/EV where evidenced, calibration/proper scores where probabilities were captured, dependence, closing comparisons where available, missingness and settlements—not hit rate alone.

## Count and continuity at this decision

- Existing declarations: 11 of 40.
- Existing settlements: 7 wins, 4 losses, zero pending.
- Remaining declarations to the fixed horizon: 29.
- The Türkiye–Italy, Sweden–Poland and Romania–Bosnia retrospective review and reported outcomes do not increase the pilot count.
- Forty refers to the existing declared-test horizon, not forty new fixtures. Multiple declarations from one fixture remain correlated.
- Historical provenance is mixed and must remain labeled; this decision does not convert the earlier records into one uniformly preregistered experiment.

## Champion work

Defer further champion-rework implementation and replacement decisions until the pilot review, unless the user explicitly changes this direction. Preserve the existing local prototype and production champion. This record does not stop remote processes, change services, disable capture jobs, or deploy anything; no operational shutdown is claimed.

The separate offline development restrictions still apply to any future code work. User-authorized manual web research for the pilot is a distinct activity; it does not authorize live provider APIs, paid LLM calls, automatic ingestion, betting or publishing predictions.

## Explicit exclusion

The user subsequently excluded today’s Türkiye–Italy, Sweden–Poland and Romania–Bosnia analyses as incorrect. Do not promote their research candidates into pilot declarations or use their retrospective outcomes as performance evidence. Retained records are audit-only. The pilot remains 11/40 with 29 declarations remaining.
