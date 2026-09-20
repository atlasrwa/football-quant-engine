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

`verify_freeze` returns a report — `OK`, `INCOMPLETE_BINDING`, or `BINDING_MISMATCH` — and never
raises for a failed verification. `verify_freeze_or_raise` is the enforcing wrapper.

**Enforcement, and its honest limit.** `freeze()`'s reverify branch previously computed a drift
flag, wrote it to a side file and to stdout, and then `return existing` — the answer was
discarded, so re-running the freeze over changed sources handed back the stale manifest as
though it still applied. It now calls `verify_freeze_or_raise(existing)` **after** writing the
side file, so the evidence is preserved either way but an unverified binding is an error.

**There is no consumer that reads this freeze as evidence.** Nothing in the repository opens
`FREEZE_LLM_MATCHUP_V3_SONNET46.json` and gates on it. The two references in
`battery_v2.py:257` and `battery_v3.py:426` are **string literals** in an `identifier_source`
provenance field, not reads. `freeze()` is the *constructor*, not a consumer; wiring enforcement
there is the smallest sound thing available and it is real, but it does **not** demonstrate that
anything downstream refuses stale evidence, because nothing downstream reads it. The delivered
guarantee is therefore: **freeze construction, and explicit verification on demand.**

## 4. Compatibility policy

`FREEZE_CONTRACT_VERSION = "v3_sonnet46_freeze_contract_v2_core_bound"`. The bump is necessary
because the required set grew: a freeze written before this repair cannot satisfy the new
contract, and must not be made to look as though it does.

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
| 7 | sources are not taken from another checkout | pass |
| 8 | `freeze()` refuses instead of returning the stale freeze | pass — side file still written |

For 2 and 3 the assertion is `mismatched == [that core]` — the change is confined to one file, so
exactly one binding may break; a test that merely asserted "not ok" would pass for the wrong
reason.

For 8 the verifier is **genuine**. Only `build_manifest()` is replaced, because it assembles
eight result artifacts unrelated to source binding. The reverify branch, the side-file write and
the refusal are the real code path.

**Mutation-checked:** against the unrepaired module **all 8 fail**.

Focused existing freeze/provenance tests, run together with the new suite:

```
pytest tests/research/test_v46_freeze_core_bindings.py \
       tests/research/test_golden_v3_sonnet46.py \
       tests/research/test_controls_v3_core.py -q
-> 64 passed in 426.11s
```

`test_controls_v3_core.py` is included because it holds the assertion that the 4.6 freeze file
is not modified by any of this — relevant here, since `freeze()`'s failure behaviour changed.
The full research battery was **not** re-run: this repair does not touch it, and a larger pass
count would not be evidence about source binding.

## 7. Remaining limitations

* **No consumer enforces this freeze** (§3). The guarantee is construction plus explicit
  verification, not end-to-end refusal by a downstream pipeline.
* **`ROOT`, `OUT` and `PROTECTED` still point at the deployed tree.** Only `SRC_DIR` was
  rebound; artifact/output roots are out of scope and tracked in their own open row.
* **Source-file hashing does not establish in-memory code identity** — the same limit stated in
  the preceding repair.
* **Fingerprint coverage beyond the demonstrated defect is unchanged.** The remaining unbound
  `hardening/*.py` modules, including `aggregate.py` and `feature_matrix.py`, stay open.
* **Requested-vs-observed model identity, spend enforcement, lock/preflight coverage and the
  temporal feature defects are untouched** and remain **P1 — OPEN**.
* The stored freeze on the deployed host is stale (§5c) and was **not** regenerated — doing so
  is an execution decision, not a repository-organization one.
