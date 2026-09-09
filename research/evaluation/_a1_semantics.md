# Phase A1 — xG / shots semantic validation

Grounded in the actual provider payloads and champion field maps, not vendor docs
(neither provider ships a machine-readable data dictionary in the corpus).

| field | FootyStats (corpus) | TheStatsAPI (/stats) | comparable? |
|---|---|---|---|
| shots | `team_a_shots` / `team_b_shots` (per team, match total) | `overview.total_shots.all.{home,away}` | concept same (total shots per team) but **counts differ**: PR#4 corr 0.80, MAD 2.24, FootyStats systematically ~2.1 lower → **different shot-inclusion rule** (likely blocked-shot handling). SEMANTICALLY_UNCERTAIN on exact definition. |
| shots_on_target | `team_a_shotsOnTarget` / `team_b_shotsOnTarget` | `overview.shots_on_target.all.{home,away}` | agree closely (PR#4 corr 0.994). Comparable. |
| xG | `team_a_xg` / `team_b_xg` (per team) | `overview.expected_goals.all.{home,away}`; also `np_expected_goals` (non-penalty) | concept same (team xG) but **different models**: PR#4 corr 0.55, MAD 0.69. Penalty inclusion differs — TheStatsAPI exposes BOTH `expected_goals` (incl. penalties) and `np_expected_goals` (excl.); FootyStats xG penalty treatment is undocumented → SEMANTICALLY_UNCERTAIN. |
| blocked shots | not a distinct corpus field | `shots.blocked_shots` | TheStatsAPI-only; not comparable. |

**Orientation:** both providers are team-oriented with home = team_a / `.home`, away =
team_b / `.away`. PR #4 verified home/away corr 0.996 on corners, so orientation is
consistent (no inversion).

**Team vs match:** all the above are per-team, per-match totals (not rolling, not
match-level aggregates). The champion consumes them as per-side rolling-window
features.

**Timestamp / missing / PIT semantics:** neither provider's stat payload carries a
capture timestamp (established in PR #4). These are POST-MATCH values. PIT usability
for the champion is via the fixture-date walk-forward: a stat from a PRIOR completed
fixture is legitimately known before a later fixture (date_unix < kickoff), which is
exactly the discipline `build_fixture_rows` + `FormWindowBuilder` already enforce.
Missing values are NULL (not zero) in both; the champion's form window drops missing
observations rather than zeroing them.

## Determination

- **shots_on_target**: semantically comparable across providers.
- **shots (total)** and **xG**: same concept, materially DIFFERENT measurement
  (different definitions / models). Marked **SEMANTICALLY_UNCERTAIN** for
  cross-provider blending — consistent with PR #4's low correlations. We therefore
  do NOT blend xG/shots across providers. Experiment A tests the *value of the
  champion's existing (FootyStats) xG/shots signal* via feature ablation, and relies
  on PR #4's already-established result that provider-switching xG/shots is
  non-credible.
