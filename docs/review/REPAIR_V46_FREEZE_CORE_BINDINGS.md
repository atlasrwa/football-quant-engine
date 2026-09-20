# Repair note — the 4.6 freeze now binds the scientific cores it delegates to

**Scope.** One defect: `freeze_v3_sonnet46.MODULES` omitted the extracted scientific cores, so
the freeze could report the same instrument across a change to the control definitions or the
eligibility rules. Nothing else is repaired. The model-identity, spend, locking, feature and
output-root findings stay open with their own evidence.

Base: `ff178345a2a74dc7f3dab1545238e28f5ab6cd6e` (accepted head of PR #20, unmerged — this is
stacked on it). Final SHA is reported in the PR; a commit cannot contain its own hash.

---

## 1. Root cause

`controls_v3_sonnet46.py` and `eligibility_v3_sonnet46.py` are **thin wrappers**:

```
controls_v3_sonnet46.py    -> from ...hardening import controls_v3_core as CORE
eligibility_v3_sonnet46.py -> from ...hardening import eligibility_v3_core as ECORE
```

When the shared logic was extracted into `*_core.py`, the freeze's source list kept the wrapper
names and never gained the cores. The freeze therefore hashed the delegating shell while the
scientific decisions — control definitions, eligibility rules — sat in files it did not cover.

Two defects in the same path, found while tracing it:

* **Silent omission.** `if os.path.exists(p): module_hashes[mod] = _sha256_file(p)` — a required
  source that was renamed, moved or deleted simply vanished from the manifest and the freeze
  still reported success over a shorter list.
* **Foreign source root.** `SRC_DIR = os.path.join(ROOT, "src/research/llm_matchup/hardening")`
  with `ROOT = "/home/ubuntu"`, so a freeze built or verified from any other checkout hashed the
  deployed tree while executing its own.

## 2. Required source set — before and after

| | count | |
|---|---|---|
| before | 19 | wrappers bound, cores not |
| after | 22 | `+ controls_v3_core.py`, `+ eligibility_v3_core.py`, `+ resume_golden_v3.py` |

`resume_golden_v3.py` is included on demonstrated evidence, not by association:
`controls_v3_core.py` records `RG.classify_bedrock_error(...)` into its control results at
lines **115** (`err_class`) and **135** (`error_class`), so that classification is an input to
control outcomes and must be bound.

`atomic_io.py` is a direct dependency of **both** cores and is deliberately **excluded**: it is
an atomic-write utility encoding no scientific decision and affecting no result value. The
exclusion is recorded in the module as `EXCLUDED_WITH_REASON` so it reads as a judgement rather
than an oversight.

This is the whole expansion. No repository-wide audit of the remaining unbound `hardening/*.py`
was performed, and the `aggregate.py` / `feature_matrix.py` items named in the earlier review
remain open — they are not reachable from either core and are not part of this demonstrated
defect.

## 3. Construction and verification call paths

**Construction.** `build_manifest()` → `current_module_hashes()`, which hashes every entry of
`REQUIRED_MODULES` from `SRC_DIR` and **raises `FreezeBindingError` if any is absent**.
`module_hashes` and the new `freeze_contract_version` both sit inside `version_payload`, which is
what `generation_hash` is taken over — so the required set is part of the hashed identity.

**Verification.** `verify_freeze(freeze_dict)` is **standalone and independent of
`build_manifest()`**. That is deliberate: `build_manifest()` reads eight result artifacts under
`OUT` (golden summary, controls, repeatability, counter-evidence, prespend audit, eligibility,
plus a glob), none of which bear on whether a source binding is intact. Binding integrity is a
question about source files, so verifying it must not require a golden batch to exist.

`verify_freeze` returns a report and never raises for a failed verification;
`verify_freeze_or_raise` is the enforcing wrapper. The failure order is declared, first match
wins, because each stage decides how the next is read:

| order | status | meaning |
|---|---|---|
| 1 | `MISSING_CONTRACT` | no `freeze_contract_version` |
| 2 | `UNSUPPORTED_CONTRACT` | a contract this verifier does not certify |
| 3 | `INCOMPLETE_BINDING` | a required hash is absent from the freeze |
| 4 | `FOREIGN_ORIGIN` | a covered module is loaded from another checkout |
| 5 | `BINDING_MISMATCH` | a recorded hash no longer matches this checkout |
| 6 | `OK` | |

Every diagnostic field — `missing_bindings`, `missing_required_cores`, `foreign_origins`,
`mismatched` — is populated on **every** return path, contract failures included. A historical
freeze must stay *readable*: naming what it lacks is the point of inspecting it, so a contract
refusal never blanks the binding detail.

**Loaded origins are validated, not just file paths.** Hashing the file at the expected path
proves nothing about which module object is executing. `loaded_origin_violations()` checks
`sys.modules[dotted]` (the import registry — what a later import resolves to) **and** each
wrapper's own bound attribute (`controls_v3_sonnet46.CORE`, `eligibility_v3_sonnet46.ECORE` —
what the science actually calls, captured at the wrapper's import time).

**These two can disagree, and both are retained.** An earlier version of this repair collected
the registry entry and then *overwrote* it with the wrapper's, so only one was ever checked —
the code did `found[core] = bound` while the comment claimed neither reference was preferred.
A reviewer exploited exactly that: foreign object in `sys.modules`, local object on the wrapper,
verdict `OK` over all 22 hashes. `_loaded_covered_objects()` now returns **every distinct
reference**, deduplicated by object *identity* so the ordinary case (both names, same object) is
checked once while genuinely different objects are both kept. A conflict cannot be resolved by
preferring one reference, because either being foreign is a defect; the report names which one
(`reference: "sys.modules"` or `"controls_v3_sonnet46.CORE"`).

The comparison itself is delegated to `golden_manifest._verified_source_path`, the mechanism
accepted in the preceding repair, rather than a second implementation with its own rules.

Construction and verification run the same code: `current_module_hashes()` raises on a foreign
origin, and `verify_freeze` calls the same helper with `check_origins=False` only so it can
*report* rather than raise.

**Enforcement, and its honest limit.** `freeze()`'s reverify branch previously computed a drift
flag, wrote it to a side file and to stdout, and then `return existing` — the answer was
discarded, so re-running the freeze over changed sources handed back the stale manifest as
though it still applied. It now calls `verify_freeze_or_raise(existing)` **after** writing the
side file, so the evidence is preserved either way but an unverified binding is an error.

**Generation drift is now refused too.** Source bindings can be entirely valid while the
instrument is a different one: `generation_hash` is taken over `version_payload`, which also
covers the contract, the version stamp, `content_hashes`, the Bedrock configuration and the
fixture manifest hash. `freeze()` previously printed `instrument_drift_detected: true` and then
returned the existing manifest as accepted. It now raises `FreezeGenerationMismatch` — a
distinct type, so a caller can tell "the bindings are wrong" from "this is a different
instrument". **No field is excluded from the comparison**; inventing an exclusion to make it
pass would manufacture the assurance the freeze exists to provide. The side file is written
*before* every refusal, and the historical freeze is never rewritten. `force=True` is not a
workaround and is not offered as one.

**There is no consumer that reads this freeze as evidence.** Nothing in the repository opens
`FREEZE_LLM_MATCHUP_V3_SONNET46.json` and gates on it. The two references in
`battery_v2.py:257` and `battery_v3.py:426` are **string literals** in an `identifier_source`
provenance field, not reads. `freeze()` is the *constructor*, not a consumer; wiring enforcement
there is the smallest sound thing available and it is real, but it does **not** demonstrate that
anything downstream refuses stale evidence, because nothing downstream reads it. The delivered
guarantee is therefore: **freeze construction, and explicit verification on demand.**

## 4. Compatibility policy

`FREEZE_CONTRACT_VERSION = "v3_sonnet46_freeze_contract_v2_core_bound"`, and
`SUPPORTED_CONTRACTS` is the set this verifier will certify. The bump is necessary because the
required set grew: a freeze written before this repair cannot satisfy the new contract, and must
not be made to look as though it does.

**Contract compatibility is never inferred from hashes.** A manifest can carry every current
hash and still describe a different required set — which is exactly what a pre-repair freeze
looks like once the cores are required. An absent contract is `MISSING_CONTRACT`; an unlisted
one is `UNSUPPORTED_CONTRACT`. Neither is a generic failure, and neither is inferred away.

* A pre-repair freeze **remains readable** as historical evidence — `verify_freeze` inspects it
  and reports on it; nothing rewrites it.
* It is **not certified complete**: verification returns `INCOMPLETE_BINDING` and names the
  missing cores in `missing_required_cores`.
* Missing hashes are **never filled in from today's files**, no old freeze is rebaselined, and
  absence is never read as compatibility.

**What remains valid historically:** the stored freeze's record of what was observed at freeze
time — its results, counts, model identities and the 19 hashes it did record — is untouched and
still inspectable. **What must be regenerated before future execution:** the freeze itself, under
the repaired contract, because it carries no binding for the cores that contain the scientific
decisions.

## 5. Before/after evidence

Verifying the **stored** freeze against the repaired contract returns `INCOMPLETE_BINDING`. Its
findings fall into three causes, which are separated here because a combined "drift detected"
would hide which of them this repair actually found:

**(a) Missing required bindings — this repair's finding.** The stored freeze records 19 module
hashes and no `freeze_contract_version`:

```
controls_v3_core.py       eligibility_v3_core.py       resume_golden_v3.py
```

**(b) Mismatched because of PR #20 — not this repair.** `formation_structure.py` and
`golden_manifest.py` were edited by the stacked parent PR, so once `SRC_DIR` follows the
executing checkout they no longer match the stored hashes.

**(c) Pre-existing staleness — present on the deployed host, independent of both PRs.**
Comparing the stored freeze against the **deployed tree it was built from**, with no review
branch involved:

```
controls_v3_sonnet46.py      HASH CHANGED
eligibility_v3_sonnet46.py   HASH CHANGED

2 of 19 bound modules already drifted on the deployed host.
```

This is the defect's practical consequence, demonstrated rather than argued: the freeze has been
stale since before any of this work, and nothing noticed, because `freeze()` computed the flag
and returned the stale manifest anyway. None of (a), (b) or (c) is a reason to rebaseline the
stored freeze, and none of them was rebaselined.

## 5b. Reviewer counterexamples — three gaps in the first version of this repair

All three were reproduced against the committed code before it was changed, and all three had
passed the original suite. They are recorded here because each one falsified a claim this note
previously made.

| # | Counterexample | Root cause | Before | After |
|---|---|---|---|---|
| 1 | A foreign `controls_v3_core.py` preloaded under its real dotted name; the wrapper demonstrably used it | `current_module_hashes()` hashed the **local file** and never asked which module object was loaded. The attribution test compared two checkouts *independently*, which cannot express a mixed-checkout process | `verify_freeze → OK` | `FOREIGN_ORIGIN`; construction raises |
| 2 | Manifest with every current hash but (a) no `freeze_contract_version`, (b) an unsupported string | the contract was **recorded but never checked**; completeness was inferred from matching hashes | both `OK` | `MISSING_CONTRACT` / `UNSUPPORTED_CONTRACT` |
| 3 | Existing freeze with current hashes and a supported contract, recomputed `generation_hash` differing | `freeze()` verified *bindings* only; the drift flag was computed, printed, and discarded | `instrument_drift_detected: true`, then returned the old manifest | `FreezeGenerationMismatch`; side file preserved, historical freeze unchanged |

Counterexample 1 is the most serious: it meant the earlier claim that criterion 7 established
checkout attribution was **wrong**. Two independent single-checkout runs prove that two trees
produce different hashes; they do not prove that a process running a foreign module is refused.

**Counterexample 4 — the two references disagree.** The first attempt at counterexample 1 fixed
only half of it. `_loaded_covered_objects()` recorded the `sys.modules` object and then replaced
it with the wrapper's, so a *foreign registry with a local wrapper* verified `OK` and
construction returned all 22 hashes. Measured against the previous module (`2ff9faea5`):

| direction | registry | wrapper | before | after |
|---|---|---|---|---|
| `registry_foreign` | foreign | local | **`OK`** — the real gap | `FOREIGN_ORIGIN` via `sys.modules` |
| `wrapper_foreign` | local | foreign | `FOREIGN_ORIGIN` — already caught | `FOREIGN_ORIGIN` via `<wrapper>.<attr>` |

Only `registry_foreign` was genuinely unprotected; the `wrapper_foreign` cases are regression
guards for the direction that already worked. Both are now covered for both cores, and
construction fails closed in every case.

## 6. Tests

New: `tests/research/test_v46_freeze_core_bindings.py` — 8 tests, offline, no corpus, no Bedrock
call, no artifact assembly. Each assertion runs in a subprocess with `cwd` set to the checkout
under test and `PYTHONPATH` unset.

| # | Criterion | Result |
|---|---|---|
| 1 | both cores required; hashes match this checkout's files | pass |
| 2 | changing only `controls_v3_core.py` rejects the freeze | pass — sole mismatch |
| 3 | changing only `eligibility_v3_core.py` rejects the freeze | pass — sole mismatch |
| 4 | a missing required source fails explicitly | pass — `FreezeBindingError` |
| 5 | removing either required hash fails verification | pass — `INCOMPLETE_BINDING` |
| 6 | a pre-repair freeze stays readable, is not certified | pass — nothing back-stamped |
| 7 | two checkouts produce different hashes | pass — but see the correction below |
| 8 | `freeze()` refuses instead of returning the stale freeze | pass — side file still written |

Criterion 7's description has been **corrected**: it compares two checkouts run independently,
which shows that different trees hash differently. It does **not** establish that a process
running a foreign module is refused — that is counterexample 1, and it is now covered by the
cases below.

Added by this amendment (8 further cases):

| Case | Covers | Result |
|---|---|---|
| foreign loaded core, both cores (parametrised) | counterexample 1 | `FOREIGN_ORIGIN`, construction raises |
| byte-identical foreign core | counterexample 1 | `FOREIGN_ORIGIN` — origin, not content |
| contract: missing / unsupported / current (parametrised) | counterexample 2 | `MISSING_CONTRACT` / `UNSUPPORTED_CONTRACT` / `OK` |
| generation drift with valid bindings | counterexample 3 | `FreezeGenerationMismatch`, side file kept, freeze unchanged |
| matching generation identity | the positive control | returns the existing freeze |
| disagreeing references, 2 directions × 2 cores | counterexample 4 | `FOREIGN_ORIGIN`, naming the offending reference |
| identical references deduplicated | counterexample 4 | recorded once, both names credited |

Each foreign-core case asserts the wrapper **actually holds the foreign object**
(`wrapper_uses_foreign`) before asserting the refusal, so it cannot pass because the preload
silently failed. Each contract-failure case asserts `missing_bindings == []` and
`mismatched == []`, so the refusal cannot be attributed to anything but the contract.

For 2 and 3 the assertion is `mismatched == [that core]` — the change is confined to one file, so
exactly one binding may break; a test that merely asserted "not ok" would pass for the wrong
reason.

For 8 the verifier is **genuine**. Only `build_manifest()` is replaced, because it assembles
eight result artifacts unrelated to source binding. The reverify branch, the side-file write and
the refusal are the real code path.

**Mutation-checked:** against the unrepaired module all 8 original cases fail. Against the
**pre-amendment** module (`7d7d76bd3`), 6 of the 8 new cases fail — the two that pass are the
positive controls (supported contract → `OK`, matching identity → returns existing), which
should pass in both.

Focused existing freeze/provenance tests, run together with the new suite:

```
# original repair
pytest test_v46_freeze_core_bindings.py test_golden_v3_sonnet46.py test_controls_v3_core.py -q
-> 64 passed in 426.11s

# this amendment
pytest tests/research/test_v46_freeze_core_bindings.py \
       tests/research/test_golden_manifest_source_binding.py -q
-> 28 passed in 6.06s        (21 freeze-binding, 7 source-binding)
```

`test_golden_manifest_source_binding.py` is included because this amendment reuses
`golden_manifest._verified_source_path`, so it is the regression surface for that shared helper.
The 64-test battery was **not** re-run for the amendment: `test_controls_v3_core.py` and
`test_golden_v3_sonnet46.py` do not exercise the contract, origin or drift paths, and a larger
pass count would not be evidence about them.

## 7. Remaining limitations

* **No consumer enforces this freeze** (§3). The guarantee is construction plus explicit
  verification, not end-to-end refusal by a downstream pipeline.
* **`ROOT`, `OUT` and `PROTECTED` still point at the deployed tree.** Only `SRC_DIR` was
  rebound; artifact/output roots are out of scope and tracked in their own open row.
* **Source-file hashing does not establish in-memory code identity** — the same limit stated in
  the preceding repair. Origin validation narrows this but does not remove it: it proves where a
  loaded module was *imported from*, not that its in-memory objects still match those bytes.
* **The guarantee is "no covered module was loaded from a foreign origin"**, not "every hashed
  file corresponds to a loaded module". A covered module that nothing has imported has no origin
  to check, and its file is hashed as before.
* **Fingerprint coverage beyond the demonstrated defect is unchanged.** The remaining unbound
  `hardening/*.py` modules, including `aggregate.py` and `feature_matrix.py`, stay open.
* **Requested-vs-observed model identity, spend enforcement, lock/preflight coverage and the
  temporal feature defects are untouched** and remain **P1 — OPEN**.
* The stored freeze on the deployed host is stale (§5c) and was **not** regenerated — doing so
  is an execution decision, not a repository-organization one.
