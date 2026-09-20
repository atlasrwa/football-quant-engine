# Repair note — the V3 generation fingerprint now describes the executing code

**Scope.** One defect: `golden_manifest.current_generation_fingerprint()` hashed scientific
sources through hardcoded `/home/ubuntu` paths. Nothing else is repaired here. The other
provenance findings in `REPOSITORY_MAP.md` §D stay open with their own evidence.

Baseline: `097335c6e3d127bdfcf673d6a3d4136a4e29ede0` (accepted organization snapshot).
Final SHA is reported in the PR and the handoff — a commit cannot contain its own hash.

---

## 1. Defect and root cause

`src/research/llm_matchup/hardening/golden_manifest.py` resolved two covered scientific
sources through a module-level literal:

```python
_SRC = "/home/ubuntu/src/research/llm_matchup/hardening"
SAMPLING_MODULE_PATH   = os.path.join(_SRC, "sampling.py")
NEUTRALIZE_MODULE_PATH = os.path.join(_SRC, "neutralize_v3.py")
```

The fingerprint's other scientific inputs are taken from **loaded state** —
`PR4.prompt_content_hash()`, `SCH3.schema_content_hash()`, `ONT.to_dict()` — so those already
described the running code. These two did not: they described whatever sat at a fixed
absolute path. A third input, `formation_structure._STRUCTURE_JSON`, had the same shape
(`/home/ubuntu/research/llm_matchup/FORMATION_STRUCTURE_V1.json`).

Root cause: an *executing-code* attestation was built from *filesystem-location* constants.
Those two things coincide only on the deployed host.

## 2. The executing path actually affected

`resume_golden_v3.py` imports `sampling` and `neutralize_v3` **and** calls
`current_generation_fingerprint()` in its preflight. That is the real consumer: the modules in
`sys.modules` could come from one checkout while the hashes came from another.
`controls_v3_core.py` and `golden_v3_sonnet46.py` additionally hash
`GM.NEUTRALIZE_MODULE_PATH` directly, so they inherited the same binding.

## 3. Reproduction — before

In an independent checkout (`src/`, `scripts/` and the structure table copied out of this
tree) with a single line appended to its own `sampling.py`:

```
executing sampling.py : <independent checkout>/src/research/llm_matchup/hardening/sampling.py
fingerprint hash      : 29a9bd2c95b67962…        <- the DEPLOYED tree's bytes
EXECUTING bytes       : dcb204f4a07cca53…
fingerprint == DEPLOYED  -> True
fingerprint == EXECUTING -> False
```

And the consequence that matters:

```
check_compatible(frozen, current) -> {'compatible': True, 'mismatches': []}
```

The neutralization/sampling source had changed in the checkout that would run the batch, and
the generation-compatibility gate certified it as the same generation.

## 4. Repair and the precise guarantee

`current_generation_fingerprint()` now calls `verify_source_binding()` first. For each covered
module it takes the **loaded module object**, canonicalises `module.__file__`, requires that it
equal `<this checkout>/src/research/llm_matchup/hardening/<name>.py`, and only then hashes that
verified file. The root is derived by walking up from `golden_manifest.py`'s own
`os.path.realpath(__file__)` and is re-checked against the expected repository-relative layout,
so a relocated package fails explicitly instead of fingerprinting an unexpected directory.

`formation_structure._STRUCTURE_JSON` is derived the same way. This is a deliberate widening
beyond the two source modules, because acceptance criterion 1 — generation succeeds without the
deployed tree — is unsatisfiable while an unconditional `open("/home/ubuntu/…")` remains inside
the fingerprint. It is a frozen scientific *input* hashed into the fingerprint, not output
configuration.

**The declared contract** (also stated in the function's docstring):

* A covered source **edited inside this checkout** → its hash changes → `check_compatible`
  reports a mismatch → a resume aborts `ABORT_RESUME_GENERATION_MISMATCH`. Ordinary drift.
* A covered module **loaded from a different checkout** → `SourceBindingError` is raised
  before any fingerprint exists — including when the foreign bytes are byte-identical,
  because origin, not content, is what is being established.

A stale fingerprint is never silently retained. There is no fallback: no `/home/ubuntu`, no
environment-selected root, no second candidate directory. Equivalent spellings of the same
directory (symlinks) canonicalise to one root and do not raise.

**What is proven:** the covered modules were imported from this checkout's own `hardening/`
directory, and the bytes hashed are the bytes of those verified files on disk at call time.

**What is NOT proven:** that the in-memory code objects still correspond to those bytes. A
module reloaded or monkeypatched after import would still pass, and a source file could be
rewritten after the call. Source-file hashing cannot establish in-memory code identity and this
repair does not claim it does.

**Rejection is an exception, not an `ABORT_*` status.** Every other gate in `_resume_locked`
returns a structured dict; `SourceBindingError` deliberately propagates instead. A foreign
source root is not a run outcome to be recorded in a ledger — recording it would write a row
attributed to code whose identity is unknown. This is a considered choice, not an oversight.

## 5. Compatibility

**Schema unchanged.** Same keys, same meanings; no version bump, no rebaselining, no
compatibility check bypassed. Historical manifests, receipts and frozen evidence are untouched.

This is safe because the repair is value-neutral on this host, verified three ways:

| | sha256 |
|---|---|
| `sampling.py` — tracked vs deployed | identical (`29a9bd2c…`) |
| `neutralize_v3.py` — tracked vs deployed | identical (`15f3e87a…`) |
| `FORMATION_STRUCTURE_V1.json` — tracked vs deployed vs frozen manifest | identical (`377f697c…`) |

Proof against the real frozen 4.5 artifact, run from this review checkout **after** the repair:

```
check_compatible(golden_v3_fixture_manifest.json, current) -> {'compatible': True, 'mismatches': []}
```

A historical record remaining inspectable is not permission to resume execution. This repair
restores the *meaning* of the compatibility check; it does not authorise a resume, which stays
blocked by the §D items (live model resolution, spend enforcement, K=8 feasibility).

## 6. Reproduction — after

Same independent checkout, same appended line:

```
fingerprint == EXECUTING -> True
fingerprint == DEPLOYED  -> False
```

## 7. Tests

New: `tests/research/test_golden_manifest_source_binding.py` — 7 tests, offline, zero Bedrock
calls, each import-resolution assertion in an isolated subprocess with `cwd` set to the checkout
under test and `PYTHONPATH` unset.

| # | Criterion | Test |
|---|---|---|
| 1 | independent checkout | audits every `open()`; no deployed-tree path may be read |
| 2 | correct attribution | hashes equal that checkout's source bytes (uniquely marked, so it cannot pass by coincidence) |
| 3 | foreign rejection | foreign `sampling` preloaded under its real dotted name → refused |
| 4 | identical bytes | byte-identical foreign copy → still refused |
| 5 | source change | edit moves the hash and `check_compatible` reports the mismatch |
| 6 | canonical paths | symlinked spelling produces an identical fingerprint, no false failure |
| 7 | real consumer | `resume()` with the genuine verifier refuses; the injected `call_fn` proves no model call is reached |

The verifier is never mocked. `call_fn` is injected only to prove no call happens.

**Mutation-checked.** Against the unrepaired modules, **6 of the 7 fail**, with the defect's own
signatures — `fingerprint read deployed-tree files: ['/home/ubuntu/src/…']`, `byte-identical
foreign source bypassed the origin check`, `resume() accepted a foreign-sourced generation
instead of refusing`. Only the canonical-path test passes, correctly: it is a
must-not-regress guard, not a statement of the defect.

`tests/research/test_golden_v3_resume.py` also had `sys.path.insert(0, "/home/ubuntu")` at line 9.
Removed: it put the deployed tree ahead of the checkout under test, which would have let the new
origin assertions compare a deployed path against a deployed root and pass vacuously. The file's
14 tests pass unchanged before and after removal.

## 8. Remaining limitations — none of them closed here

* **In-memory code identity is not established** (§4).
* **`golden_manifest.OUT` is still `/home/ubuntu/research/llm_matchup/out/hardening_v3`.** The
  *output/manifest* root is deliberately out of scope for a source-binding repair, so an
  independent checkout still reads and writes the deployed tree's manifest and ledger. Tracked as
  its own §D row; it does not affect what the fingerprint attests to.
* **Only the two modules the fingerprint already covered are verified.** This repair does not
  widen fingerprint coverage — that is the separate, still-open `freeze_v3_sonnet46.py`
  missing-core-module-bindings finding.
* **`adapter_v4.py` requested-vs-resolved model identity** and **`freeze_v3_sonnet46.py` module
  coverage** are untouched and remain **P1 — OPEN**.
* No live Bedrock call was made; no paid path was exercised.
