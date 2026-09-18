# V8C independent-audit response (`v8c_audit_response_v1`)

**Start** `8aa4a7a81` · **Branch** `feat/v8c-experiment-repair`
**CHAMPION** `0b8f5ff3…` unchanged · **Sonnet calls** 0 · **Sealed-947 preflight** NOT run

The previous pass claimed `P0_OPEN = 0 / P1_OPEN = 0`. That did not survive independent audit.
This document records what was closed in this pass, what remains open, and — importantly — what
the audit's own framing got right that I had missed.

---

## 1. Dispositions

### Closed, with adversarial tests

| id | root cause | repair |
|---|---|---|
| **P0-A** data-vintage binding | `score_frozen` trusted a frozen integer `rec_i` against a fresh index: an inserted/backfilled/reordered row repoints it, and a *revised historical value* silently changes the statistical question with nothing crashing | freeze full binding identity; resolve by `fixture_id`; verify 8 bindings for **every** fixture before **any** is scored |
| **P0-B** external anchor | a self-hashed JSON is tamper-evident only if its hash is anchored outside the payload | `FreezeReceipt` — separate artifact over the freeze's **file bytes**, plus producer commit and 18 module hashes |
| **P1-K** historical profile self-inclusion | a historical match H was classified by its opponent's profile *as of T*, which contained post-H matches **and H itself** | `HistoricalProfileIndex` — profile **and** tercile bounds both strictly before H |
| **P1-L** resolver key collision | `len(condition_set)` used as identity | content fingerprint, canonicalised at both nesting levels |
| **P1-F** blocks after scoring | blocks built in process 2 | computed and frozen in process 1, consumed in process 2 |
| **P1-C** live reachability | `unreachable == 0` proven by unlimited pagination | addressability under the real 6×50 protocol, computed, cap not relaxed |
| **P1-D** submission contract | mixed valid/invalid silently became a clean partial treatment | `MAX_SELECTIONS = 8`, `PARTIAL_ACCEPTANCE = False`, `INVALID_SUBMISSION` with zero accepted |
| **P1-G** gate self-certification | the evidence generator *wrote* `p0_open = 0` and the gate believed it; artifacts bound to current code rather than proven produced by it | `P0/P1_OPEN` derived from `defect_ledger.evaluate(passed_node_ids)`; every artifact must embed provenance |
| **P1-J** pilot rule | not preregistered | `N = 60` derived from the frozen inference floor, frozen **before** any 947 scan |
| **W5/W10** | claimed as confirmatory space | declared outside the selectable estimand; **no threshold changed** |

### Still open — not attempted or not finished in this pass

| id | what is needed |
|---|---|
| **P1-A** real Sonnet runner | the Bedrock Converse orchestration itself. The session/validation/cache surface exists; the multi-turn loop does not. |
| **P1-B** prompt/tool contract | one versioned confirmatory prompt with frozen `PROMPT_SHA256` |
| **P1-E** treatment provenance | the all-arm freeze carries binding identity but not the full per-fixture treatment record (converse counts, termination reason, response hash, cache hit/miss) |
| **P1-H** real-corpus endpoint reachability | exposed-50 S/R/H `SCORE_OK` and paired endpoints, classified `DEVELOPMENT_REAL_CORPUS` |
| **P1-I** R action-space coverage | coverage over the whole S action space + set-level matching up to `MAX_SELECTIONS` |

`P1-A/B/E` are interdependent — the prompt contract and provenance fields are defined *by* the
runner — so partial work on any one of them would have to be redone. They are left whole.

---

## 2. Where the audit was right and I was wrong

**The `rec_i` finding is the one I should have caught.** I built the two-process seal and then
had process 2 dereference a frozen integer into a freshly-supplied index. The seal was real; the
binding across it was not. A seal that guarantees "selection happened before scoring" is worth
little if the thing being scored is not provably the thing that was selected.

**Self-certification is subtler and I walked straight into it.** I wrote a generator that
emitted `p0_open = 0`, then a gate that read it, and reported "no pass by definition" — while
the single most load-bearing boolean *was* a definition. Running the new gate against last
session's artifacts now refuses 18 of 19 conditions that previously passed 17 of 18. That
regression is the repair.

---

## 3. New findings raised by this pass

### N1 — similarity self-inclusion (`P1_CANDIDATE`, deferred to audit)

`similar_opponent_ids` builds every team's profile as of T. A historical match H between the
subject and opponent X therefore contributes to X's profile, which helps decide whether X counts
as similar to the target's opponent — so **H participates in deciding its own cohort
membership**. Structurally the same family as P1-K.

**Not repaired here, and the reason matters.** The similar-set is *one* set used to filter every
H. Leave-H-out is incoherent by construction: it would need a different set per H, and "similar
to today's opponent" would stop denoting anything. The conditioning variable is a property of
the **target's** opponent, not of H, and uses only data `< T` — which is why I classify it as a
target-time construct rather than the P1-K defect.

The clean alternative — excluding the subject's own matches from every opponent's similarity
profile — removes the self-inclusion without incoherence, but changes the **frozen V7.1
similarity contract**. That is not a call to make mid-mission. Recorded with its candidate
repair for the auditor to rule on.

### N2 — P1-K's cost (informational)

H-time classification costs **~23%** of profile-conditioned evaluable candidates at a data-rich
fixture (879 → 674 on `mt_626333016`). At a thin fixture the count is 0 under **both** semantics,
so this is not a P1-K regression. The lost candidates were evaluable only by hindsight.

---

## 4. Invariants held

```
CHAMPION                 0b8f5ff3…  before and after
NEW_SONNET_CALLS         0
SEALED_947_PREFLIGHT_RUN false
SEALED_947_OUTCOMES_VIEWED false
thresholds changed       none
V8B.1 / V8B.2 artifacts  untouched
```

`READY_FOR_947_PREFLIGHT = false` and `READY_FOR_PAID_FRESH_PILOT = false`. Five P1s remain
open; the paid treatment path does not yet exist.
