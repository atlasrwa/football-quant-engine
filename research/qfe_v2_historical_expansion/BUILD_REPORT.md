# QFE V2 Historical Expansion — Cached Corpus Build Report

Status: **FROZEN RESEARCH CANDIDATE — NOT MODEL INPUT**

## Result

- Network/API calls used: **0**
- TheStatsAPI core before protected cutoff: **5,323** fixtures; **5,292** corner-complete.
- Cached FootyStats auxiliary extension: **8,562** fixtures; **8,548** corner-complete.
- Candidate combined scope: **13,885** fixtures across **18** competitions.
- Missing from the 20-competition target: **EFL League One and EFL League Two**.
- The 317 protected V2 outcomes were not opened or consumed.

## Cross-provider semantic validation

- Identity-only matched fixtures: **2,413**.
- Regulation goals exact agreement: **99.751%**.
- Corner side-count exact agreement: **99.519%**; mean signed FS−TSA difference **0.0044**.
- Shots exact agreement: **77.09%**.
- SoT exact agreement: **94.88%**.
- Possession exact agreement: **89.21%**.
- Fouls exact agreement: **95.23%**.
- Yellow cards exact agreement: **93.79%**.
- xG exact agreement: **0.64%**.

## Governance decision

- **No implicit provider blending.** Cached FootyStats remains a separately tagged auxiliary provider.
- Only goals and home/away corner counts are admitted to the auxiliary count-extension artifact.
- Shots, SoT, possession, fouls, cards, xG, odds and provider potential fields are excluded from the normalized extension.
- The expanded corpus may challenge the frozen Layer 4 model only through a new versioned experiment.
- Promotion requires chronological TheStatsAPI-only OOS/calibration evidence; larger historical N alone is not evidence of improvement.

## API-spend decision

- The planned 150–250-call semantic panel is **not needed**: the cache produced 2,413 identity-matched validation fixtures at zero cost.
- League One/League Two backfill is deferred. One complete season of each would be roughly 1,104 per-match stats calls and is not justified before testing whether the 13,885-fixture candidate improves OOS scoring.

Manifest SHA-256: dc283028e381ef99f1b689d5bc65a93f1d3b3f8ad443ce804388de84b976f803
