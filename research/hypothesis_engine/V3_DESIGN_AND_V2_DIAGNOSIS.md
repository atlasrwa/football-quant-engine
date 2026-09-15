# V2 Diagnosis and V3 Hypothesis-Research Design

**Status:** design + diagnosis only. Zero Bedrock spend. No inference was run. V2 is
untouched (`SONNET46_HYPOTHESIS_V2 = FAIL`, permanent). CHAMPION untouched. Nothing promoted.

All claims below are grounded in the frozen code under `src/research/hypothesis_engine/`
and the frozen artifacts under `research/hypothesis_engine/out/hypothesis_v1_sonnet46_v2/`.
Every number was recomputed read-only from those artifacts this session; where I recomputed
something, the command output is the source.

The V2 verdict is accepted permanently and nothing here reinterprets, rescores or reruns it.
This document diagnoses *why* V2 looked shallow and designs the next experiment; it does not
try to make Sonnet pass.

---

## 0. Two problems, kept separate

- **Compliance problem** — Gate E failed at zero tolerance because **one** reference
  response quoted a supplied percentage into a question's prose.
- **Research-depth problem** — even setting compliance aside, the normalized research was
  dominated by one shape: *"is subject's metric X different from its OVERALL baseline
  (usually split by venue)?"* (152/159 intents against `SUBJECT_OVERALL_BASELINE`).

These are not conflated anywhere below. The diagnosis shows they also have **different
root causes**, and one large contributor is neither of them: an **encoding/contract
mismatch** that made rich questions fail to compile and made depth look worse than it was.

---

## 1. Root-cause diagnosis of V2 shallowness

The task lists candidate causes A–G. Verdict per cause, with evidence.

### Headline finding (encoding contract mismatch) — the dominant mechanical cause

`schema.py:_condition_item()` types `conditions[].value` as a **free string** with no enum:

```python
"value": {"type": "string"},           # NOT constrained to the dimension's enum
"axis":  {"type": "string", "enum": list(vocabulary.PROFILE_AXES)},  # OPTIONAL at schema level
```

But `query_plan.compile_hypothesis()` checks the value against the dimension's **uppercase**
enum (`vocabulary.VENUE_VALUES = ("HOME","AWAY","ANY")`, `PROFILE_BANDS = ("LOW","MID","HIGH","ANY")`)
and **requires** `axis` for `opponent_profile`.

Recomputed from the 7 reference responses that survived the firewall:

- **43 compiler failures, ALL `UNSUPPORTED_DIMENSION`.**
- **40 of 43 are venue casing**: Sonnet emitted `venue=home` / `venue=away` (lowercase);
  legal values are `HOME`/`AWAY`. (`value 'home' is not legal for dimension 'venue'` ×22,
  `'away'` ×18.)
- 2 are `opponent_profile` conditions that used lowercase bands (`mid`, `high`) **and omitted
  the required `axis`** (all four raw `opponent_profile` conditions Sonnet emitted had
  `axis: None`, and one used `high_possession` — conflating band with axis).
- 1 is `competition=COMPETITION` (legal values: `SAME`/`ANY`).

Consequences, both mechanical:

1. **Query-compilability (Gate B, 0.488) is largely an artifact of case/enum mismatch**, not
   of unanswerable questions. The dimensions were supported; the *string casing* wasn't.
2. **Venue conditioning was Sonnet's most-used conditional structure (94 intents)** — the
   opposite of "shallow" on the conditioning axis — but almost none of it compiled, so the
   research looked both non-compilable *and* thin once the failures were stripped.

This is not one of A–G as written; it is a **contract defect between schema (free string)
and compiler (uppercase closed enum)**. It is the first thing V3 must fix, and it partially
confounds the depth reading.

### A. Evidence representation makes overall-baseline questions easiest — **CONTRIBUTING**

Each reference packet carries **76 evidence items across 38 distinct metric/scope
combinations**, and inspection of the ids shows they are overwhelmingly *subject-level
overall* facts (`HOME_*` / `AWAY_*` aggregates). The evidence surface a model is handed is a
menu of "team's own overall rate" facts, so the lowest-friction grounded question is
"is this overall rate different from the overall baseline?". The packet does **not**
pre-compute any cohort-conditioned evidence (e.g. "corners in fixtures vs BACK_THREE"),
so a conditional question requires the model to *invent the cohort structure* with no
matching evidence item to cite. Grounded + conditional is therefore harder to express than
grounded + unconditional, purely from the evidence layout. **Real contributor.**

### B. Prompt implicitly favors simple comparisons — **MINOR CONTRIBUTING**

`prompt.py` *does* ask for conditional questions ("It is CONDITIONAL: it compares a specific
cohort against a named baseline") and lists the rich corpus. But it gives **no worked example
of a conditional cohort**, never mentions `opponent_profile` / `axis` / formation-family as
first-class moves, and never states the **casing** of condition values. The single strongest
instruction it repeats is distinctness ("five restatements … worth less than two genuinely
different ideas"), which rewards *breadth of metric* over *depth of conditioning*. So the
prompt permits depth but neither demonstrates nor scaffolds it. **Contributor, secondary.**

### C. Schema / comparison enum structurally favors overall baseline — **PARTLY**

`vocabulary.COMPARISONS` offers five baselines and the schema allows all of them, so overall
baseline is not *structurally* forced. But two things tilt it:
(1) `SUBJECT_OVERALL_BASELINE` is the first listed and the only one needing no extra context;
(2) the richer baselines pair naturally with conditions that (per the headline finding) were
failing to compile. Not a hard structural bias, a soft default. **Partial.**

### D. Compiler rejects or makes richer cohorts difficult — **NO (capability) / YES (contract)**

The compiler *fully supports* `opponent_profile` (with `axis`), `own/opponent_formation_family`,
`period`, `half_score_state`, `competition`, `venue`, and all five comparisons — verified in
`query_plan.compile_hypothesis`. So richer cohorts are **not** capability-blocked. What the
compiler *does* do is fail closed on a wrong-cased value or a missing `axis` — which, given
the free-string schema (headline finding), is exactly what happened. So "the compiler makes
richer cohorts difficult" is true **only** via the contract mismatch, not via missing
capability.

### E. Packets lack usable contextual evidence — **PARTIALLY TRUE, AND DECISIVE FOR SOME DIMENSIONS**

This is the cause that must protect Sonnet from being blamed. Recomputed per fixture from
`MATERIALIZED_PACKETS_sonnet46_v2.json`:

- `half_score_state` and `period` were **withheld in ALL 12** fixtures — manifest note:
  *"half-level metrics unavailable for this fixture's history; period and half_score_state
  dimensions withheld"* (the TheStatsAPI-adapted corpus carries no half-time goals, per
  `capability.py`). **Score-state / period research was genuinely impossible.** Sonnet using
  it zero times is *correct behaviour*, not shallowness.
- Formation dimensions were **withheld in 3 of 12** (coverage < 0.15 floor:
  `mt_010243537` 0.123, `mt_012232295` 0.0135, `mt_012232411` 0.037).
- In the **9** fixtures where formation *was* offered, the observed formation distribution is
  thin and near-degenerate (e.g. `HOME_TEAM: ['BACK_FOUR']`, `AWAY_TEAM: ['BACK_FOUR']`), so a
  formation *interaction* has almost no contrast to exploit even when the dimension is present.
- `opponent_profile`, `venue`, `competition` were available in **all 12**.

So: **opponent-profile shallowness cannot be excused by availability** (it was always
available), but **score-state absence must not be counted against Sonnet at all**, and
formation depth was availability- and contrast-limited in a third to a half of cases.

### F. Normalization collapses richer intent into baseline — **NO**

`normalize.py` preserves `comparison`, all non-`ANY` conditions (with `axis`), `period`, side,
window and family in the intent tuple. It drops only `ANY`-valued conditions (correct: they
place no restriction) and free-text. It does **not** collapse a richer question into an
overall-baseline one. The 152/159 count reflects what Sonnet *emitted*, not a normalization
artifact. **Ruled out.**

### G. Sonnet chooses shallow questions despite clearly-available richer options — **TRUE, RESIDUAL, BUT SMALLER THAN IT FIRST APPEARED**

After removing (headline) the venue-casing confound and (E) the genuinely-unavailable
dimensions, a real residual remains: **`opponent_profile` was available in all 12 fixtures and
used in only 7 intents, always mis-encoded**; formation interaction used 3 times; recent-vs-long
regime once. Even the richer questions Sonnet *did* form were malformed (no axis, wrong case),
which suggests it did not treat the conditional vocabulary as a precise contract. So G is real,
but it is entangled with A (evidence layout), B (no scaffolding) and the headline contract
defect. It is **not** a clean "the model is just shallow" result.

### Diagnosis summary

| Cause | Verdict | Weight |
|---|---|---|
| **Contract mismatch** (free-string value vs uppercase compiler enum; optional-vs-required axis) | **CONFIRMED** | **Dominant mechanical cause of low compile rate; confounds depth reading** |
| A evidence layout favors overall-baseline | CONFIRMED | Major |
| B prompt doesn't scaffold conditioning | CONFIRMED | Secondary |
| C comparison enum soft default | PARTIAL | Minor |
| D compiler blocks richer cohorts | NO (capability) / via contract only | — |
| E packet lacked contextual evidence | CONFIRMED for score-state (all 12) + some formation | **Protective: do not blame Sonnet for score-state** |
| F normalization collapses intent | RULED OUT | — |
| G Sonnet chose shallow despite options | TRUE but entangled/residual | Moderate |

---

## 2. Fixture × available research-dimension matrix

Deterministically inventoried from each frozen reference packet's `capability_manifest`,
`formation_distribution`, and evidence. `Y` = offered by the manifest (usable); `y` = offered
but low-contrast; `—` = withheld by the manifest for this fixture; `used` = Sonnet actually
conditioned on it in a normalized intent.

| Fixture | venue | competition | opp_profile | own_form | opp_form | half_state | period | recent/long | Notes |
|---|---|---|---|---|---|---|---|---|---|
| mt_010243515 | Y | Y | Y | y (0.175) | y | — | — | Y | forms ~single-family |
| mt_010243537 | Y | Y | Y | — (0.123) | — | — | — | Y | formation withheld |
| mt_010243938 | Y | Y | Y | y (0.151) | y | — | — | Y | |
| mt_010244159 | Y | Y | Y | y (0.176) | y | — | — | Y | |
| mt_010244193 | Y | Y | Y | y (0.157) | y | — | — | Y | |
| mt_010441320 | Y | Y | Y | y (0.188) | y | — | — | Y | |
| mt_010441491 | Y | Y | Y | y (0.216) | y | — | — | Y | |
| mt_010443150 | Y | Y | Y | y (0.202) | y | — | — | Y | |
| mt_010444904 | Y | Y | Y | y (0.229) | y | — | — | Y | |
| mt_012232295 | Y | Y | Y | — (0.0135) | — | — | — | Y | formation withheld |
| mt_012232411 | Y | Y | Y | — (0.037) | — | — | — | Y | formation withheld |
| mt_013233190 | Y | Y | Y | y (0.25) | y | — | — | Y | best formation coverage |

**Reading of the matrix (what V3 may fairly ask for):**
- **venue / competition / opponent_profile / recent-vs-long**: available in **all 12** → fair
  game to expect intelligent use.
- **formation**: available in **9/12**, but coverage 0.12–0.25 and near-degenerate
  distributions → expect *occasional, justified* use, not routine use.
- **half_score_state / period**: available in **0/12** → **must not be scored against Sonnet
  at all** for these fixtures. If V3 wants to test score-state, it must first build a
  provenance-tracked FootyStats HT-goals join (separate work), or draw fixtures whose history
  comes through the FootyStats path.

The matrix is the guardrail against the opposite failure (§5, §9): depth can only be *expected*
where the column is `Y`.

---

## 3. Query-compiler capability matrix

For each conditional/interaction family the project wants, verified against
`query_plan.compile_hypothesis`, `vocabulary.DIMENSIONS`, `similarity.resolve_band` and
`capability.CONTEXT_SOURCES`:

| Desired research family | Representable today? | Mechanism / gap |
|---|---|---|
| Team A behavior vs opponents defensively similar to Team B | **PARTIALLY_SUPPORTED** | `opponent_profile` band on a defensive `axis` (e.g. `corners_against`, `shots_on_target_against`) compiles and `similarity.resolve_band` resolves it deterministically. Gap: the band is a **within-competition tercile**, *not* "similar to Team B" specifically. There is no "similar-to-named-team" cohort primitive; `EUCLIDEAN/EMBEDDING` distance is `PENDING_VALIDATION` and refuses. So "defensively HIGH-conceding opponents" is expressible; "opponents *like B*" is not. |
| Team B concessions vs opponents offensively similar to Team A | **PARTIALLY_SUPPORTED** | Same: `opponent_profile` band on an offensive axis (`shots_for`, `corners_for`, `possession_for`). Same "similar-to-A" gap. |
| formation × opponent-profile interaction | **SUPPORTED** (where formation offered) | Two conditions on one hypothesis: `own_formation_family` + `opponent_profile(axis=…)`. Both compile. Limited by formation coverage (matrix §2). |
| venue × opponent-profile interaction | **SUPPORTED** | `venue` + `opponent_profile(axis=…)`; both compile in all 12. |
| formation × raw-behavior interaction | **SUPPORTED** (where formation offered) | `own_formation_family` (or `opponent_formation_family`) condition + any target metric. |
| trailing-at-HT → second-half output | **UNSUPPORTED (data)** | `half_score_state` + `period=SECOND_HALF` are in the vocabulary and *would* compile, but `half_time_score_state` is withheld by every fixture manifest here and the TheStatsAPI corpus lacks HT goals. Needs a FootyStats HT-goals join first. |
| recent-vs-long-run regime comparison | **SUPPORTED** | `comparison = SUBJECT_RECENT_VS_LONG_BASELINE` with `window ∈ {W5,W10}`; compiles. |
| competition environment | **SUPPORTED** | `competition` dimension + `LEAGUE_ENVIRONMENT_BASELINE`. |

Net: the compiler is **richer than V2 exercised**. The only truly unsupported items are
(a) score-state/period for these fixtures (data gap, not compiler gap) and (b) a
*named-team-similarity* cohort (deliberately `PENDING_VALIDATION` in `similarity.py`). **V3
must not propose hypotheses in those two shapes.**

---

## 4. Gate E diagnosis (compliance problem, isolated)

Recomputed by running the frozen `firewall.scan` over the 12 reference responses:

- Reference-set firewall hits: **6 total = 5 `probability_claim` + 1 `percentage`**.
- **All 5 `probability_claim` are the substring `"chances at"`** matching the prose pattern
  `\b(?:probabilit|likelihood|chance|odds)\w*\s+(?:of|is|are|at)\b`. `big_chances` is an
  **approved metric** in `capability.METRICS`, so a disciplined grounded question —
  *"Does the home team generate more big chances at home compared to its overall baseline?"* —
  is falsely flagged. This is an **instrumentation false positive**, exactly analogous to the
  `\bback\b` / "back three" collision the firewall author already special-cased.
- **The 1 genuine violation** is `seq03::reference::mt_010243938`, family `TEMPO_AND_TERRITORY`,
  question: *"Does the home team record lower possession per match compared to their opponents
  across all prior fixtures, given their possession-for average of **44.6%** versus
  possession-against of **55.4%**?"*

Classification of the genuine violation (the distinction the task asks for):
- **It is evidence citation, not effect estimation.** Sonnet copied two *supplied* evidence
  values (44.6% / 55.4% possession) into the question prose. It did **not** predict an outcome,
  quote odds, state an edge, or assert an effect size — the question itself is direction-free
  ("does it differ"). The firewall's `percentage` pattern cannot tell "quoting a supplied
  observation" from "predicting a probability", so it correctly (under a zero-tolerance rule)
  but bluntly rejected it.
- Under the mandate this is still a real discipline breach ("Do NOT output a … percentage …
  not in a field, not in a question"), so **E is a true FAIL** and V2 stands. But the *nature*
  of the breach is important for V3: the model wanted to **reference** an observed statistic,
  and the only channel it had was free prose, where any number is forbidden.

**Design implication:** the system currently gives the model no legitimate way to say *"I am
conditioning on this observed value"* except prose, which is a numerical minefield. The cleanest
fix is to make evidence *reference* structural (ids only, already in `evidence_refs`) and to
keep prose number-free — see §6.

---

## 5. Proposed V3 hypothesis-search ontology

The ontology already exists implicitly in `vocabulary.py`; V3 should make the **conditional
tuple a first-class, typed selection space** and expose it explicitly. Conceptually:

```
SUBJECT × TARGET_METRIC × SIDE × WINDOW × PERIOD × {CONDITIONS} × COMPARISON
```

with `{CONDITIONS}` drawn from a typed condition space, each condition gated by the fixture
manifest:

| Condition family | Vocabulary today | V3 exposure |
|---|---|---|
| venue | `HOME/AWAY/ANY` | keep; fix casing contract |
| own / opponent formation family | `BACK_THREE/FOUR/FIVE/OTHER/ANY` | keep; only when manifest offers it |
| opponent attacking profile | `opponent_profile` axis ∈ {`shots_for`,`shots_on_target_for`,`corners_for`,`possession_for`,`accurate_crosses_for`} band ∈ {LOW,MID,HIGH} | **promote to first-class; require axis** |
| opponent defensive profile | axis ∈ {`shots_against`,`shots_on_target_against`,`corners_against`,`accurate_crosses_against`,`goals_against`} | **promote; require axis** |
| competition | `SAME/ANY` | keep |
| recent-vs-long horizon | via `comparison=SUBJECT_RECENT_VS_LONG_BASELINE` + `window` | keep; surface as its own move |
| HT score-state / period | `half_score_state`, `period` | **only if a FootyStats HT join is built first; otherwise leave withheld** |

Supported interactions (compiler-verified, §3): formation×profile, venue×profile,
formation×raw-behavior, recent×long. Unsupported (do not propose): named-team-similarity
cohorts (similarity `PENDING_VALIDATION`), any score-state on the current corpus.

The LLM **selects** from this space. It never supplies a similarity score, a band cut, a
probability or an effect — those remain deterministic (`similarity.resolve_band`) or owned by
the quant engine.

---

## 6. Proposed schema / prompt changes

**Schema (`hypothesis_set_schema_v1` → v2) — the highest-leverage change:**

1. **Constrain `conditions[].value` to a per-dimension enum.** Today it is a free string,
   which let 40 wrong-cased venue conditions pass schema and die at compile. Options:
   (a) a single union enum of all legal condition values (uppercase), or (b) an
   `oneOf`/conditional schema keyed on `dimension`. Either makes a wrong-cased or illegal
   value a **schema** rejection with a precise path, caught before compile, and — crucially —
   surfaced to the model as a contract it can satisfy.
2. **Make `axis` required whenever `dimension == "opponent_profile"`** (JSON-Schema
   `if/then`, or a dedicated `opponent_profile` condition object). The compiler already
   requires it; the schema should too, so "profile without axis" cannot be emitted.
3. Keep everything else closed and number-free. No new free-text surface.

These three are the fix for the compliance-adjacent *compilability* collapse and remove most
of the confound between "shallow" and "mis-encoded".

**Prompt (`hypothesis_analyst_prompt_v1` → v2):**

4. **State the casing/enum contract explicitly** and show **one worked conditional example**
   per supported interaction (venue×profile, formation×profile, recent-vs-long) using exact
   enum tokens — without prescribing *which* fixture should use them (see §9).
5. **Introduce `opponent_profile` + `axis` as a first-class move**, explaining that the LLM
   names the *axis and band* and the engine resolves membership deterministically. V2's
   prompt never mentioned axis, and 0/4 profile conditions carried one.
6. **Give a legitimate evidence-reference channel and forbid numeric prose harder.** Restate:
   to condition on or point at an observed value, cite its **`evidence_refs` id** — never write
   the number in the `question`. This directly addresses the genuine Gate E breach (§4): the
   model wanted to reference 44.6%, and prose was the only channel it had.
7. Rebalance the distinctness instruction so it rewards *conditional depth where justified*,
   not only metric breadth — while explicitly permitting a plain baseline question when that is
   genuinely the best-supported one (§5 restraint).

**Firewall (`numerical_authority_firewall_v1` → v2):**

8. **Special-case the `"chances at"` collision** exactly as `\bback\b` was, so the approved
   metric `big_chances` cannot be misread as a probability claim. This is an instrumentation
   fix; it does **not** relax the ban on genuine percentages/odds/EV.
9. Keep the zero-tolerance percentage ban in prose (the genuine violation stays caught), now
   paired with the structural evidence-reference channel (#6) so discipline and expressiveness
   stop being in tension.

**Evaluation (`hypothesis_evaluation_v1` → v2):**

10. **Define abstention so an empty hypothesis set counts as full abstention** (V2 mapped
    Sonnet's ideal `{"hypotheses": []}` on starved packets to 0.0 — the worst score).
11. **Establish the same-input repeatability floor first, and express identity/irrelevant
    invariance relative to it** rather than against an absolute Jaccard the generator cannot
    reach against itself (V2 floor was 0.333).
12. Add explicit **depth metrics** as *reported, availability-gated* quantities (see §7),
    separate from the discipline gates.

---

## 7. Proposed V3 controls and measurement split

Measure three axes **separately** and never average them into one score.

**Discipline (hard gates, unchanged philosophy):**
- schema validity; evidence grounding (structural refs only); numerical firewall (with the
  `big_chances` false-positive fixed); query-compilability (now meaningful because casing is a
  schema error, not a silent compile death); non-invention under starvation; capability
  awareness.

**Research depth (reported, each gated on availability from the §2 matrix — never penalize an
unavailable dimension):**
- opponent-profile use rate **among fixtures where it was offered** (all 12 here);
- formation use rate **among fixtures where formation coverage ≥ floor** (9 here);
- score-state use **only if the HT-join is built** (else excluded, not scored 0);
- recent-vs-long regime use rate;
- justified-interaction rate (a 2-condition hypothesis whose two conditions are both
  manifest-available);
- comparison-cohort diversity (Shannon entropy over `COMPARISONS`, to detect the 152/159
  `SUBJECT_OVERALL_BASELINE` collapse quantitatively);
- evidence-driven vs generic classifier: does the intent *materially* use a
  manifest/formation/profile field, or is it a bare overall-baseline question that needed no
  fixture evidence?

**Restraint (reported, guards against §5/§9 over-forcing):**
- gratuitous-interaction rate (conditions on dimensions the manifest withheld, or `ANY`-padded
  conditions dressed as depth);
- unsupported-complexity rate (proposing score-state / named-similarity when unavailable);
- appropriate-abstention rate on starved packets (with the fixed definition, #10).

**Controls to carry over from V2 (they worked):** profile_perturbation with the *meaningful-
sensitivity* rule (delta must touch the `corners_against`/`accurate_crosses_against` wide-play
surface — reused verbatim from `_analyze_v2.intent_touches_profile`), identity_alias,
irrelevant_field, formation_ablation, evidence_starvation, unsupported_data_trap, venue_flip.
**New control:** a **profile-axis perturbation** that raises an *offensive* opponent axis
(e.g. `shots_on_target_for`) to test whether Sonnet's opponent-profile *axis selection* (not
just band) responds to the evidence — this directly probes the §1-G residual.

---

## 8. How V3 differs scientifically from V2

- **V2 asked:** "left entirely to itself under a permissive free-string contract, does Sonnet
  spontaneously produce deep conditional research?" Answer: disciplined yes, deep no — but the
  answer was **confounded** by (a) a schema/compiler casing mismatch that killed its most
  common conditional structure and (b) a firewall false positive that rejected legitimate
  `big_chances` questions.
- **V3 asks:** "when the supported conditional research space is **exposed as a precise, typed,
  correctly-cased contract**, and the instrumentation false-positive is removed, can Sonnet
  **select** relevant, grounded, nontrivial fixture-specific hypotheses — using depth **where
  the evidence justifies it** and abstaining from depth **where it doesn't** — without being
  told which football story to tell?"
- **The key scientific change is removing confounds, not lowering the bar.** V3 does not make
  the depth target easier; it makes the *measurement of depth* valid by (1) letting rich
  questions actually compile, (2) not blaming Sonnet for unavailable score-state, (3)
  separating discipline / depth / restraint so a compliance failure can't masquerade as a
  depth failure and vice versa.

---

## 9. Risk of accidentally forcing desired hypotheses

The central design hazard: if V3 pushes "use opponent-profile / formation / interactions", we
risk **encoding our preferred hypotheses into the prompt** and then "discovering" them — a
circular result that proves nothing about the model's judgement.

Mitigations, built into §5–§7:
- **Availability gating from the §2 matrix**: depth is only *expected*, and only *scored as
  present-or-absent-reported*, where the dimension is genuinely offered. We never reward a
  formation hypothesis on a fixture whose formation coverage is 1.35%.
- **Restraint metrics are first-class** (§7): gratuitous interactions and unsupported
  complexity *lower* the restraint reading, so "always emit an interaction" is not a winning
  strategy.
- **A plain baseline question is explicitly acceptable** when it is the best-supported one
  (prompt change #7). The objective is *intelligent conditional research*, not maximum
  interaction count.
- **Worked examples are structural, not fixture-specific** (change #4): they show the *token
  grammar* of a conditional, never "for this matchup, ask about back-three corners".
- **The profile-axis perturbation control** (§7) tests whether depth is *evidence-driven*: if
  Sonnet's profile axis choice moves with the perturbed axis, its depth is responsive to
  evidence; if it emits the same interaction regardless, that is prompt-induced boilerplate and
  the control will reveal it.

If, after these mitigations, Sonnet still only produces depth because the prompt scaffolds the
grammar, the depth metrics will co-move with the *restraint* violations and the profile-axis
control will show insensitivity — and V3 would then be honestly reported as inconclusive on
depth, not as a pass.

---

## 10. Recommendation: is V3 worth running?

**Yes — but only after the zero-spend contract and instrumentation fixes land, and only scoped
to dimensions the corpus actually supports.**

Reasoning:
- V2's headline failures are **substantially mechanical and fixable at zero cost**: a
  free-string schema value vs an uppercase compiler enum (40/43 compile failures), a firewall
  regex collision on an approved metric (5/6 Gate-E hits), and an abstention metric that scores
  ideal behaviour as 0.0. Re-running Sonnet **without** fixing these would just re-buy the same
  confounded result — a waste of spend.
- Once fixed, there is a **genuine open scientific question** (the §1-G residual): with a
  correct, typed conditional contract, does Sonnet select depth intelligently and with
  restraint? V2 could not answer this because the contract was broken. That question is worth a
  bounded paid run.
- **Scope constraint:** V3 must **not** test score-state/period on the current corpus (data
  gap, §2/§3). Either build the provenance-tracked FootyStats HT-goals join first (separate,
  zero-inference work) and then include it, or explicitly exclude score-state from V3's depth
  claims. Testing a dimension the packets withhold would repeat V2's Gate-L mistake of scoring
  the unmeasurable.
- **Pre-run gate:** before any spend, the schema-v2 + firewall-v2 + prompt-v2 changes should be
  validated by **re-compiling V2's already-recorded raw responses** (zero Bedrock) to confirm
  the venue-casing and `big_chances` artifacts disappear and compile-rate rises for the *same*
  outputs. Only if that offline check passes is a paid V3 justified. This keeps the decision
  evidence-based and cheap.

Net: the shallowness V2 exposed is real but was over-stated by fixable instrumentation, and the
residual depth question is scientifically meaningful. A properly de-confounded, availability-
scoped V3 is worth running.

**V3_HYPOTHESIS_RESEARCH_DESIGN_RECOMMENDED**
