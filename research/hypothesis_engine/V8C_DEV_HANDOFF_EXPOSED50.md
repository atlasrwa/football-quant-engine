# V8C development handoff — exposed-50 data dependency closure

`EVIDENCE_CLASS = DEVELOPMENT_APPARATUS_DIAGNOSTIC`

This records the **packaging and provenance** of the development-data bundle that lets another
environment repair and test V8C against the 50 already outcome-exposed V8B.1 pilot fixtures.
It is not an experiment run, a scientific repair, or evidence of any effect. No model was
called; no sealed-947 outcome was read, scored or exported; CHAMPION is unchanged.

The raw-data archive itself is **not** committed and **not** published — it is transferred
privately. This document is the committed record of what it contains and how it was built.

---

## 1. The problem

The receiving checkout has code and reports, but `src.research.matchup.corpus.load_corpus()`
returns zero records: the underlying TheStatsAPI match caches are absent. Every V8C stage —
`hypothesis_v8c.harness.build()` → `corpus_index.load_records()` → `PITIndex` — is cache-only,
and the loaders do not raise on a missing cache. They `os.path.exists(...) -> False` and skip
the season, so an empty corpus looks like a successful load.

## 2. Dependency closure

Entry point `hypothesis_v8c.harness.build()` needs exactly:

| Need | Resolved by |
|---|---|
| the 50 development fixture IDs | `V8B1_PILOT50_SELECTION_FREEZE.json` → `pilot_fixture_ids_ordered` |
| strictly pre-fixture history | `_all_fixtures_*.json` season rows + per-fixture `*stats_*.json` |
| opponent profiles, similarity scaling, competition baselines | the same corpus rows, league-wide — `pit_context` fits `(team, competition, axis, T)` from the prefix |
| provider capability contract and field mappings | `research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json` |

History is taken **league-wide**, not merely matches involving the 50 fixtures' teams, because
competition baselines and tercile bands are fitted over every team in the competition.

**Closure size: 441 fixture rows + 441 stats files across 13 league-seasons.** That is the
whole corpus prior to the cutoff — all six leagues are represented in the source config, but
only `champ` season `sn_343481` has any row before the cutoff. This is a property of the
corpus, not an omission: the other eleven league-seasons begin after the exposed-50 window.
It is consistent with the manifest's own `home_prior_n`/`away_prior_n` for these 50 fixtures,
which range 20–36 against a `min_raw_n_threshold` of 20.

## 3. Reserve boundary

The sealed reserve is `1000 manifest − 50 exposed pilot − 3 T2 infrastructure canaries = 947`,
derived at build time exactly as `_run_v8c_sealed947_preflight.sealed_947_ids()` derives it.
The sealed-reserve ID manifest was used **only to enforce exclusion**. No sealed outcome field
was read, scored, printed, exported or aggregated, and the structural preflight was not run.

**No reserve observation is required as historical context.** The exposed-50 are the 50
earliest fixtures in the manifest:

```
latest exposed-50 kickoff    1710072000   2024-03-10T12:00:00Z
earliest sealed  kickoff     1710601200   2024-03-16T15:00:00Z     buffer 529,200 s
```

Every V8C historical read is strictly earlier than its target's kickoff, so the closure is a
temporal **prefix** and no sealed fixture falls inside it. Nothing was omitted and no
equivalence is claimed in place of a missing dependency.

### Mixed files

All 13 `_all_fixtures_*.json` season files span both sides of the cutoff and are therefore the
mixed case. The extraction path decides inclusion from **`id` and `utc_date` only**, appends an
included row verbatim, and never reads, copies or writes an excluded row's `score` object.

*Honest limit:* `json.load` materialises the source array in the producing process before the
filter runs, so excluded rows' bytes were resident in memory. They were never accessed,
emitted, aggregated or printed. The claim is **non-export of sealed outcomes, not
non-residence**. Per-fixture stats files are already fixture-level; sealed ones were simply not
copied.

## 4. Closure verified empirically

The same code path was run twice, differing only in the cache root `multisrc_corpus.CACHE`
points at. Nothing under `src/` was modified. Both runs asserted `sys.modules` free of
`scorer` and `score_frozen` at entry and exit.

| Comparison, full corpus (5636 records) vs bundle alone (441 records) | Result |
|---|---|
| exposed-50 fixtures resolved in the index | 50 / 50 both arms |
| identical `hypothesis_v8c.packet` `packet_hash` | **50 / 50** |
| identical `pit_context` `cut_unix` | **50 / 50** |
| identical `n_prior_records` (target's index position) | **50 / 50** |
| identical full universe ledger + evaluable-ID hash | 3 / 3 compared |
| fixtures differing in any compared field | **0** |
| packet `reads_target_outcome` | `False` for every fixture, both arms |

`n_prior_records` is the count of records strictly preceding the target in chronological
order. Its identity across both arms for all 50 fixtures proves the bundle holds **every**
record the full corpus holds before every exposed-50 target — not a subset that happens to
agree.

The full grammar-enumeration universe (~202k admissible shapes per fixture, ~140 s each) was
compared on 3 of 50 fixtures for runtime reasons, and was identical on those. The packet-hash
and prior-record identity above hold for all 50 and are what prove the data closure; the
universe comparison additionally exercises the capability contract and the pre-T support path.

## 5. Known non-equivalence — V8B.1 `packet_hash` will not reproduce

The `packet_hash` values frozen per fixture in `V8B1_PILOT50_SELECTION_FREEZE.json` came from
`hypothesis_v8b1.packet` over `hypothesis_v71.execution.build_context(index)`, which fits
terciles and the axis cache at a **single global cut at the 70th percentile of the whole
corpus** (`index.kick[int(len(index.kick) * 0.7)]`). That cut is a function of total corpus
length and cannot be reproduced from a temporal prefix.

This is not a bundle defect — it is precisely the defect V8C repaired (`D-V8C-P0-CTXCUT`:
50/50 exposed pilot fixtures kick off before that global cut, so their band assignments read
matches that had not happened at T). V8C's `pit_context.build_pit_context(index, rec_i)` cuts
at `index.kick[rec_i]` with strict `<`, which is prefix-closed — and that is the path verified
in §4.

## 6. Provenance limits

Provider identity (TheStatsAPI), original field names and shapes, and NULLs are preserved;
**NULL is not zero and NULL is not mid.** Nothing was imputed, re-normalised or synthesised.
Season-file top-level keys are preserved verbatim except `n`, restated as the filtered array
length; no new key was injected into any provider file.

**Vintage / availability evidence is absent.** The source cache carries no ingestion timestamp,
no provider response header and no as-of stamp for any record. Filesystem mtimes were not
preserved as evidence and would be copy times, not availability times. The archive's export
timestamp records **when the archive was written** and is **not** a historical availability
timestamp for any provider record. The only time evidence is each fixture's `utc_date` kickoff
— schedule metadata, which is what the strict-`<` PIT rule keys on.

## 7. Receiving-environment setup

The engine hardcodes `/home/ubuntu` in `corpus.CACHE`, `corpus._SCRIPTS`, `corpus_index`'s
`sys.path.insert` and `harness.ROOT`. A byte-perfect extraction still yields zero records if
the checkout is elsewhere. The bundle therefore ships a development-only adapter
(`loader_adapter/v8c_dev_paths.py`) that redirects `multisrc_corpus.CACHE` — the single choke
point every loader path funnels through — **without patching the apparatus**. That adapter is
deliberately not committed here; patching the constants in-tree would touch the scientific
apparatus.

Bundle contents, extraction, configuration and the outcome-safe integrity check are documented
in the archive's own `README.md`, with per-file SHA256, sizes, source commit, record counts and
fixture IDs in `MANIFEST.sha256.json`, and the §4 result in `EQUIVALENCE.json`.

## 8. Scope

Packaging and provenance only. Zero model calls (no Sonnet, no Bedrock, no paid model). No
sealed-947 structural preflight. No sealed outcome inspected, scored, printed or exported. No
OOS evaluation and no inspection of S-versus-R/H effect direction. No fresh provider data
downloaded and no historical data refreshed. CHAMPION, support thresholds, scientific contracts
and frozen artifacts are unchanged — CHAMPION re-verified at
`0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9`.
