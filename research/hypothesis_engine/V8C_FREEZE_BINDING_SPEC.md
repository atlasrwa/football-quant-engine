# V8C freeze-binding and anchoring spec (`v8c_freeze_binding_v1`) — P0-A / P0-B / P1-F

## 1. P0-A — the frozen `rec_i` was not a binding

`score_frozen` did `pos = int(row["rec_i"])` against a **freshly supplied index**. Two distinct
failures follow, and only the first is obvious:

1. **Repointing.** A row inserted, backfilled or reordered between selection and scoring shifts
   every later position, so the frozen integer names a *different fixture*.
2. **Silent revision.** Even with fixture identity intact, a revised historical value changes
   the PIT context, cohort membership, support, baseline, similarity and profile bands. The
   scorer then evaluates a **different statistical question** than the one that was selected —
   and reports it under the frozen result's name.

The second is the dangerous one: nothing crashes, nothing looks wrong, and the number is wrong.

## 2. What process 1 freezes

Per target fixture:

| field | why |
|---|---|
| `fixture_metadata` — `fixture_id`, `kickoff_unix`, `competition`, `home_id`, `away_id` | identity, independent of position |
| `corpus_vintage_hash` | the data the measurement was allowed to see |
| `capability_hash` | the provider contract |
| `grammar_version` + `grammar_size_hash` | the declared search space |
| `pit_context_hash` | the fitted PIT frontier |
| `universe_hash` | the exact selectable candidate set |
| `similarity_version` | the cohort-construction contract |
| `rec_i` | **diagnostic only** — never used for resolution |

Plus, once per cohort, `inference_blocks` (§4).

### Vintage hashing is target-bounded, and that is deliberate

`corpus_vintage_before(t)` hashes the ordered identity rows and per-metric value rows **strictly
before `t`** — not the whole corpus. A corpus-wide hash would refuse scoring whenever any
*later* match was appended, which is routine corpus growth, not tampering. Binding a measurement
to the vintage of the data it is permitted to read is both tighter and more honest.

Verified: mutating a single prior value changes the hash; restoring it returns the original.

## 3. What process 2 verifies, in order, before any outcome read

```
1  EXTERNAL RECEIPT      freeze FILE BYTES vs a separate receipt        (P0-B)
2  FREEZE SELF-HASH      internal payload consistency
3  RESOLVE BY FIXTURE_ID never by the frozen integer                    (P0-A)
4  FIXTURE METADATA      kickoff / competition / home_id / away_id
5  CORPUS VINTAGE        the readable data is unchanged
6  CAPABILITY + GRAMMAR  contract and declared space
7  PIT CONTEXT           rebuilt, must hash EXACTLY equal
8  UNIVERSE              rebuilt, must match
--- only now may an outcome be read ---
```

Every fixture's binding is verified **before any fixture is scored**, so a mismatch in the last
fixture cannot follow outcome reads on the first.

`FIXTURE_NOT_IN_INDEX` and `FREEZE_BINDING_MISMATCH` are **distinct statuses**: a missing row and
a revised row are different problems and a reviewer must be able to tell them apart.

A shifted `rec_i` with identical identity and vintage is **not** fatal — that is precisely what
resolving by `fixture_id` buys, and there is a test asserting it survives.

## 4. P1-F — blocks are frozen, then consumed

Process 1 computes `fixture_id → block_id` from the frozen cohort order and writes it into the
freeze. Process 2 **consumes** that mapping and recomputes it only as a verification check;
a mismatch aborts.

The implementation lives in `aggregate_blocks.py` rather than `aggregate.py` so process 1 can
freeze the blocks **without importing anything that can read an outcome** — the P0 seal holds.
`aggregate.py` imports them back, so there is exactly one implementation and the two processes
cannot drift.

## 5. P0-B — the anchor is outside the payload

A self-hashed JSON is tamper-**evident** only if its claimed hash lives somewhere the editor
does not control. It did not: anyone could edit the freeze and recompute `freeze_hash`.

`FreezeReceipt` is a **separate artifact** recording `freeze_sha256` (over the freeze's **file
bytes**), `producer_git_commit`, `producer_code_hashes` for 18 V8C modules, `corpus_hash`,
`capability_hash`, `manifest_cohort_hash`, `created_utc`, `classification`, and its own
`receipt_hash`.

The decisive test: edit the freeze, recompute its internal `freeze_hash` so its own check
passes, and the receipt still refuses.

**Stated limitation.** This is a two-file anchor, not a notary. It defeats accidental and casual
tampering, and makes deliberate tampering require editing two artifacts consistently — which a
reviewer can detect, because the receipt names the producing commit and that commit's code
hashes must reproduce. Committing the receipt to git strengthens it to an append-only history.
That is an operational step, not a code guarantee, and it is not claimed as one here.

## 6. Tests

17 in `test_freeze_binding.py`, all passing: one success case, one identity-completeness case,
seven P0-A refusals (inserted row, reordered index, mutated prior value, mutated metadata,
mutated capability, mutated grammar, mutated PIT context, missing fixture), five P0-B cases
(self-rehashed tamper, edited receipt, wrong commit, missing receipt, provenance completeness),
and two P1-F cases (blocks frozen; post-freeze block change refused).
