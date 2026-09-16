# V8A — Deep Football Research Protocol: Specification

**Classification:** DEVELOPMENT ONLY. No confirmatory OOS sample is opened, no historical
effect is computed, no feature is promoted, no CHAMPION code changes, no `p_model` exists.

**Base:** frozen V7.1 result head `4506600516184179ab26119d06489cd4761e0ea3`.
**Branch:** `feat/v8a-deep-football-research-dev`, in an isolated `git worktree` so the dirty
primary checkout is not absorbed.

**V7.1 is immutable.** Its artifacts are read-only inputs here. Nothing in V8A modifies,
reinterprets, rescues, re-runs or overwrites them.

---

## 1. The question V8A asks

Not "does this predict better." The question is:

> Can a research protocol make an LLM study measurable team behaviour and matchup structure
> *before* hypothesising, and then ask questions that are both testable and genuinely
> different from what deterministic enumeration already covers?

The V6.1 input audit (`V8A_V61_INPUT_AUDIT.md`) establishes what changed and what did not:

* V6.1's research arm was **not evidence-starved** — 518 raw match rows across 10 fixtures,
  23 metrics × FOR/AGAINST aligned per row, plus venue, competition, opponent refs and
  formation.
* V6.1 forced **none** of behavioural analysis, attack×defense analysis, mechanism search,
  generic-baseline comparison or self-criticism, and `schema_v4` had no field on which any
  of them could be recorded.

So the active ingredient under test is **procedure**, not evidence depth. V8A must not claim
otherwise, and its packet is built to be at least as rich as V6.1's so the comparison isolates
protocol.

---

## 2. Architecture

```
PIT-safe raw football evidence
  -> deterministic descriptive navigation layer
  -> LLM behavioural reconnaissance          (phase 1)
  -> LLM matchup interaction analysis        (phase 2)
  -> candidate hard research questions       (phases 3-5 + self-critic)
  -> nearest generic hypotheses retrieved deterministically
  -> LLM novelty challenge                   (pass 2)
  -> KEEP / REFINE / ABSTAIN
  -> deterministic canonicalization
  -> deterministic structural novelty / measurability audit
  -> STOP
```

The LLM is a research-question generator throughout. It is never a predictor.

---

## 3. Arms

| Arm | Protocol | Status |
|---|---|---|
| **A** | The genuine V6.1 incumbent protocol | **RUNS.** Reproducibility proved: all 36 frozen V6.1 requests rebuild byte-identically. `v6_prompt_v1` + `v5a2_packet_v1` + `schema_v4`, unmodified, on the V8A fixtures |
| **B** | Sonnet, V8A deep-football protocol | **RUNS** |
| **C** | Terra, same protocol | **BLOCKED.** See §9 |
| **D** | Deterministic generic library, no LLM | **RUNS** (structural baseline; zero calls) |

A and B use the **same model** (`us.anthropic.claude-sonnet-4-6`), the same temperature and
the same max_tokens, so the A→B contrast isolates the protocol rather than the model.

---

## 4. Frozen parameters

| Parameter | Value |
|---|---|
| model | `us.anthropic.claude-sonnet-4-6` (ACTIVE, verified) |
| temperature | 0.0 |
| max_tokens pass 1 / pass 2 | 8192 / 2048 |
| max candidates per fixture | **8** (V6.1 allowed 12; fewer and zero are acceptable) |
| fixtures | 12, balanced 2 per competition across all six |
| pass-2 granularity | **one call per candidate** — batching would let the model see its own siblings while judging each |
| retries on the billable path | 0 |

---

## 5. Evidence and the numerical firewall

The packet carries deterministic descriptive navigation (long-run / recent-5 / recent-10 /
home / away, FOR and AGAINST) **and** the raw PIT-safe match rows.

PIT safety is structural: every read goes through `PITIndex.prior_entries(team, rec_i)`, keyed
by the target's own chronological record position. There is no code path that takes a date,
so there is none that can be off by a fixture. `pit_audit` re-proves it per fixture.

The LLM may quote a descriptive value the packet supplied. It may not author or derive
probabilities, `p_model`, effect sizes, predictive adjustments, odds, EV, edge, stakes, bets,
similarity scores, latent strength scores, or any new derived quantity. Derived quantities are
the deterministic engine's job. The firewall is driven over **every** V8A prose surface — see
§8.

---

## 6. The generic library, and what "novel" can mean here

The library is **structure only**, built from the frozen V7.1 grammar. It exposes no survival,
effect, quality score, p-value, candidate status, fold performance or confirmatory result. The
model is never shown generic hypotheses before its own analysis (brief §9) — retrieval happens
only after a candidate exists.

**Membership is analytic, not sampled.** Deciding EXACT_DUPLICATE / STRUCTURAL_EQUIVALENT
against a 2,000-draw sample would make the headline novelty rate a function of sampling luck.
V8A decides it against the generator's exact **image**, which is not the Cartesian product:
`enumerate_pool` normalises after picking slots, so mixed-kind condition sets and
three-condition cohorts are unreachable, and comparators with `requires_filter` are pinned.

### 6.1 The measurable space is narrow, and that is a finding in itself

The compiler honours exactly **three** filter dimensions (`historical_venue_conditioning`,
`opponent_profile`, `competition`), **10** comparators, 2 subjects, 2 perspectives, 3 windows
and 24 metrics. The similarity engine's five dimensions are **frozen** — a model may request a
similar-opponent cohort but cannot choose, weight or extend the dimensions.

Consequently the only channels through which genuine incremental structure can appear are:

1. a **mixed-kind** condition set (venue AND opponent-profile together), or
2. **three or more** conditions.

Both are two-variable interactions — exactly what §12 Phase 2 asks the model to find.

### 6.2 Pre-registered possible outcome

**It is entirely possible that the incremental-structure rate is near zero for every LLM arm.**
If so, the honest conclusion is *about the engine, not the protocol or the model*: the
compiler's filter vocabulary is three dimensions wide, so there is very little room outside
enumeration to reach. That would be one of the most useful things V8A could tell us, and it is
recorded here **before any call** so it cannot be reframed afterwards as the protocol failing.

### 6.3 Structural zeros that fall on every arm alike

* **Formation-conditioned cohorts:** `v71_ontology.KNOWN_UNSUPPORTED_DIMENSIONS` —
  "formation is not resolvable per prior match in this corpus." Formation is therefore
  *context* only (§12 Phase 3). Neither the generic generator nor an LLM can produce a
  measurable formation-conditioned hypothesis. Capability-blocked, not generator-incapable.
* **Half-state cohorts:** half-time score state is populated on **0 of 5,636** corpus records
  (measured, not assumed). A half-state rate of zero in the report is a property of the
  corpus.

---

## 7. Deterministic final judgment

The LLM's `incremental_structure` prose is **audit evidence only**. Labels are assigned by
code:

| Label | Meaning |
|---|---|
| `EXACT_DUPLICATE` | canonical structural key identical to an enumerated generic |
| `STRUCTURAL_EQUIVALENT` | different prose, structure inside the generator's image |
| `INCREMENTAL_STRUCTURE` | measurable, but outside the generator's image |
| `INVALID` | compiler / provider / PIT / comparator / tautology failure |
| `ABSTAINED` | the model correctly declined |

---

## 8. Why the firewall is re-pointed

`firewall_v5.scan_hypothesis` iterates `v6_numeric_contract.PROSE_FIELDS`, which is exactly
`("question", "evidence_summary")` — V6.1's fields. The V8A schema has neither. Calling it
unchanged would scan nothing, return no findings, and present as a *flawless firewall record
for an arm that was never checked*. V8A names its own seven prose surfaces and drives
`scan_prose_field` over each; the pipeline battery plants a probability in every one and
asserts each is caught.

---

## 9. Terra

`V8A_TERRA_ARM_EXECUTED = false`.

`V8A_TERRA_BLOCKER`: *No model named "Terra" exists anywhere in this repository, no OpenAI (or
other non-Bedrock) credential is present in the environment, and no provider adapter for such
a model exists. Brief §19 and §33 forbid substituting another model or calling another model
"Terra", so Arm C is stopped rather than approximated.*

Arms A, B and D are unaffected and proceed.

---

## 10. Pre-registered answer threshold for Question 10

Brief §31 Q10 asks whether the protocol is promising enough to justify a fresh OOS experiment,
answered from **structural evidence only**. Fixed here, before any call:

**YES** requires all four, at N = 12 fixtures:

1. **Measurability** — Arm B measurable rate ≥ **60%** of schema-valid candidates, and
   materially above Arm A's rate on the same fixtures. (V7.1's measurability was 38.6%; a
   protocol that does not clear that comfortably has not fixed the binding problem.)
2. **Non-degeneracy** — Arm B produces ≥ **1 INCREMENTAL_STRUCTURE** candidate that is also
   measurable and firewall-clean, i.e. the protocol can reach outside enumeration at all.
3. **Grounding** — Arm B hallucinated-evidence-reference rate ≤ **5%** of cited refs, and
   zero blocking firewall findings.
4. **Discipline** — Arm B abstains (pass 2 ABSTAIN, or fewer than 8 candidates) on at least
   **one** fixture, showing the protocol does not simply fill slots.

**QUALIFIED** — 1, 3 and 4 hold but 2 fails. Reported as: *the protocol produces
better-formed, more measurable research inside the enumerable space, but the engine's
three-dimension filter vocabulary leaves almost nothing outside it.* The recommended next step
is then widening the **compiler**, not re-prompting the model.

**NO** — 1, 3 or 4 fails.

No predictive claim may be attached to any of these outcomes.

---

## 11. Freeze discipline

The prompt and both schemas are hashed before the first paid call. If the structural results
disappoint, **the result is recorded as it stands.** A prompt revision becomes **V8A.1** with
its own frozen development sample. We are testing a protocol, not demonstrating that we can
eventually prompt-engineer outputs we like.

## 12. Stop condition

After implementation, deterministic tests, prompt freeze, development calls, structural
analysis, report, commit and push: **STOP.** No new OOS sample. No prompt tuning after seeing
results. No V8B design. The optional secondary historical measurement (brief §28) is NOT
performed and is left as a separate decision.
