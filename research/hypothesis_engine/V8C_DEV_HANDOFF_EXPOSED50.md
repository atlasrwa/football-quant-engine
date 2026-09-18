# V8C development handoff — exposed-50 data dependency closure

`EVIDENCE_CLASS = DEVELOPMENT_APPARATUS_DIAGNOSTIC`

This records the **packaging and provenance** of the development-data bundle that lets another
environment repair and test V8C against the 50 already outcome-exposed V8B.1 pilot fixtures.
It is not an experiment run, a scientific repair, or evidence of any effect. No model was
called; no sealed-947 outcome was read, scored or exported; CHAMPION is unchanged.

The raw-data archive itself is **not** committed and **not** published — it is transferred
privately. This document is the committed record of what it contains and how it was built.

---

---

## 0. CORRECTION NOTICE — supersedes the claims in commit `e39fbe91a`

The first release of this handoff made two claims it had not earned. Both are corrected below,
and the corrected bundle is `V8C_DEV_EXPOSED50_HANDOFF_CORRECTED.tar.gz`. **No data changed** —
every data file is byte-identical to the first release. Only the claims, and the evidence
behind them, changed.

### Correction 1 — the seal claim was unqualified, and therefore wrong

The first release said "no sealed outcome read". Two operations materialised protected reserve
data in process memory, and one of them additionally **read** sealed fixtures' metric values.
The full record is `handoff/SEAL_DISCLOSURE.json`. Summary:

| | |
|---|---|
| Sealed rows materialised in memory during extraction | **Yes** — `json.load` on 13 mixed season files, `score` objects intact |
| Sealed `score` fields read during extraction | **No** — the filter dereferences `id` and `utc_date` only |
| Sealed statistics loaded **and read** by the full-corpus verification arm | **Yes** — `PITIndex.__init__` evaluates `_read(rec, metric)` for every record and every contract metric, and `comp_cum` accumulates those values |
| Sealed outcomes printed | **No** — 0 of 947 sealed ids in any of the four run logs |
| Sealed outcomes exported | **No** — 0 sealed ids in any output file; 0 sealed records in the bundle |
| Sealed outcomes scored | **No** — no scorer ever imported, asserted on `sys.modules` at entry and exit |
| Sealed values aggregated | **Internally yes, never emitted** — `comp_cum` sums in the full-corpus arm only |
| Any sealed value influenced an emitted number | **No** — empirically confirmed, see below |

The full-corpus verification arm was **avoidable**. The bundle-only arm plus a byte-level
source-vs-bundle file comparison would have carried the packaging claim without loading the
reserve at all. Running it was a process error, not a requirement of the task.

**No sealed value influenced any emitted number**, and this is demonstrated rather than argued:
the 441-record arm contains zero sealed records and produced byte-identical outputs to the
5,636-record arm on all 50 fixtures. Had a sealed value entered an emitted number, the two arms
would necessarily differ.

**The reserve is not hereby declared contaminated.** Memory residence and computation inside a
process that has since exited is a different event from researcher or model exposure. No sealed
value was rendered to a human, to a model, to any file, or to any model API.

**Open question, flagged rather than decided.** Does the seal contract treat an ad-hoc
whole-corpus load as a breach? Arguments both ways, neither resolved here:

* *Toward no breach* — the routine V8C path does exactly this. `harness.build()` →
  `corpus_index.load_records()` loads the whole corpus including the reserve, and the seal is
  enforced at **read** time by `blind_index.TargetBlindIndex`, not at load time.
* *Toward concern* — the full-corpus arm was an ad-hoc script, not a contract-governed path,
  and it did **not** wrap its reads in `TargetBlindIndex`.
  `_run_v8c_sealed947_preflight.py` states sealed outcomes are "NEVER read".

This belongs to whoever owns the seal, decided on this record — not to the agent that caused it.

### Correction 2 — the closure claim overstated what was verified

The first release said the closure was "proven complete", resting on packet-hash identity and
`n_prior_records` equality. That inference was unsound:

* **`n_prior_records` equality is COUNT equality** at each target position — the same *number*
  of records sorting before each target. It does not by itself establish that they are the same
  records or carry the same values.
* **A packet hash covers a bounded projection** — up to `MAX_RAW_ROWS_PER_TEAM = 40` raw prior
  rows per team for the fixture's two teams, navigation summaries, recency, opponent banding and
  similarity membership. Not every byte of the prefix.

Corrected verification scope (full detail in `handoff/EQUIVALENCE.json`):

| Verified | Scope | Result |
|---|---|---|
| V8C `packet_hash` identity, full corpus vs bundle | 50/50 | identical |
| `pit_context` `cut_unix` identity | 50/50 | identical |
| Prior-record **count** equality | 50/50 | identical |
| Universe ledger + evaluable-id hash | 3/50 | identical |
| **Per-fixture stats files, source vs bundle, byte level** | **441/441** | **byte-identical** |
| **Side files (freeze, manifest, capability contract), source vs bundle** | **3/3** | **byte-identical** |

The last two rows are new in the correction. They are genuine **source-anchored** value
equivalence — bytes hashed, nothing parsed, no mixed season file opened — and they cover the
entire per-fixture statistics layer: every match statistic the packet, profile, similarity,
compiler and scorer paths consume from a stats payload.

| Not established | Status |
|---|---|
| **L1** Season-row source comparison — `id`, `utc_date`, teams, `status`, `score`, flags for the 441 rows of `_all_fixtures_sn_343481.json` | **PENDING, deliberately not performed.** Hashing the source rows needs `json.load` on a mixed file, re-materialising sealed rows. That verification was **stopped** rather than weakening the seal. A source-file **byte** hash is recorded in `handoff/SOURCE_COMPARISON.json` as a provenance anchor instead. The other 12 season files hold zero rows, so nothing is pending in them. |
| **L2** Universe/pre-T equivalence beyond 3 of 50 | PARTIAL — ~140 s/fixture, ~2 h/arm; not run |
| **L3** Full prefix identity, element-by-element | NOT ESTABLISHED — the rows above are strong circumstantial evidence, not this claim |

Closing L1 would need a row-at-a-time incremental parse (e.g. `ijson`) hashing only permitted
rows. That still transiently parses excluded rows, so it is a granularity improvement rather
than an elimination — **the seal owner should decide whether that trade is acceptable before it
is run.**

### Artifacts

* `handoff/SEAL_DISCLOSURE.json` — materialisation / access / disclosure record
* `handoff/EQUIVALENCE.json` — corrected verification scope and limits `L1`–`L3`
* `handoff/SOURCE_COMPARISON.json` — byte-level source-vs-bundle comparison, permitted files only
* `handoff/verify_bundle.py` — outcome-safe integrity checker
* `handoff/v8c_dev_paths.py` — development-only loader path adapter

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
The sealed-reserve ID manifest was used **only to enforce exclusion**. No sealed outcome was
printed, exported or scored, and the structural preflight was not run — but sealed rows **were**
materialised in memory during extraction, and the full-corpus verification arm **did** read
sealed fixtures' metric values. That is disclosed in full in §0 and
`handoff/SEAL_DISCLOSURE.json`; the unqualified claim in the first release was wrong.

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

*Materialisation limit, stated plainly:* `json.load` materialises the whole source array —
sealed rows included, `score` objects intact — in the producing process before the filter runs.
Python's stdlib has no streaming JSON parser, so this was unavoidable with the tools used. No
excluded row's `score` was dereferenced, emitted or printed by the extraction. The claim is
**non-export of sealed outcomes, not non-residence**. Per-fixture stats files are already fixture-level; sealed ones were simply not
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
order. Its equality across both arms for all 50 fixtures establishes **count** equality, not
record identity or value equality. The earlier claim that it "proves the bundle holds every
record the full corpus holds" was unsound and is withdrawn — see the CORRECTION NOTICE, §0.

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
sealed-947 structural preflight. No sealed outcome printed, exported or scored — qualified by
the materialisation and read disclosure in §0. No
OOS evaluation and no inspection of S-versus-R/H effect direction. No fresh provider data
downloaded and no historical data refreshed. CHAMPION, support thresholds, scientific contracts
and frozen artifacts are unchanged — CHAMPION re-verified at
`0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9`.
