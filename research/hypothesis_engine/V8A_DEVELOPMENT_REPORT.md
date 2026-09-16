# V8A — Development Report (EFFECT BLIND)

**Classification:** development only. `V8A_HISTORICAL_EFFECTS_COMPUTED=false`, `V8A_FRESH_OOS_OPENED=false`, `V8A_PREDICTIVE_CLAIM=false`, `V8A_FEATURE_PROMOTION=false`.

No historical effect size appears anywhere in this report. Nothing here says which hypotheses worked, which arm has a higher effect, or which model won predictively — those questions are not asked and the data to answer them was never computed.

**Base:** V7.1 result head `4506600516184179ab26119d06489cd4761e0ea3`. **Fixtures:** 12, {"champ": 2, "epl": 2, "laliga": 2, "laliga2": 2, "ligue1": 2, "ligue2": 2}. **Model:** `us.anthropic.claude-sonnet-4-6` for both LLM arms.

**Spend:** $5.9223 actual against a $25.72 ceiling; 108 calls made of 120 planned maximum.

---

## 1. Arms

| Arm | Protocol | Status |
|---|---|---|
| A | genuine V6.1 incumbent (`v6_prompt_v1` + `v5a2_packet_v1` + `schema_v4`) | executed, 12 calls |
| B | V8A deep-football, two passes | executed, 108 calls |
| C | Terra | **NOT EXECUTED** |
| D | deterministic generic library, no LLM | scored, 0 calls |

**`V8A_TERRA_ARM_EXECUTED = false`.** Blocker: No model named Terra exists in this repository; no OpenAI or other non-Bedrock credential is present; no adapter exists. Substituting another model is forbidden by brief 19/33.

Arms A and B ran on the **same model, temperature and max_tokens**, so the A→B contrast isolates protocol rather than model.

---

## 2. Per-arm results (brief §30)

| Count | Arm A | Arm B | Arm D |
|---|---|---|---|
| fixtures | 12 | 12 | 0 |
| calls | 12 | 108 | 0 |
| raw candidates | 144 | 96 | 2000 |
| schema valid | 144 | 96 | 2000 |
| compiler valid | 143 | 84 | 2000 |
| provider valid | 144 | 88 | 2000 |
| **measurable** | 144 | 88 | 2000 |
| exact generic duplicates | 9 | 3 | 392 |
| structural generic equivalents | 86 | 39 | 1473 |
| **incremental structure** | 1 | 14 | 0 |
| invalid | 48 | 40 | 135 |
| unsupported metric | 0 | 0 | 0 |
| unknown metric (named gap) | 0 | 8 | 0 |
| tautology | 47 | 25 | 135 |
| cohort == baseline | 47 | 25 | 45 |
| excessive complexity | 37 | 4 | 709 |
| duplicate candidates (within arm) | 57 | 39 | 0 |
| hallucinated evidence refs | 0 | 11 | 0 |
| candidates with >=1 blocking firewall finding | 120 | 79 | 0 |

### Second pass (Arm B only)

KEEP **30** · REFINE **5** · ABSTAIN **61**

Fixtures where Arm B produced no candidate at a NATURAL stop (genuine abstention): **0**. Fixtures truncated at the output ceiling (apparatus fault, excluded from abstention): **0**.

### Rates

| Rate | Arm A | Arm B | Arm D |
|---|---|---|---|
| schema valid | 100.0% | 100.0% | 100.0% |
| compiler valid | 99.3% | 87.5% | 100.0% |
| **measurable** | 100.0% | 91.7% | 100.0% |
| unsupported metric | 0.0% | 0.0% | 0.0% |
| tautology | 32.6% | 26.0% | 6.8% |
| exact generic duplicate | 6.2% | 3.1% | 19.6% |
| structural generic equivalent | 59.7% | 40.6% | 73.7% |
| **incremental structure** | 0.7% | 14.6% | 0.0% |
| invalid | 33.3% | 41.7% | 6.8% |
| attack x defense interaction | 21.5% | 17.7% | 18.4% |
| similar-opponent | 0.0% | 30.2% | 9.9% |
| recent vs long-run | 33.3% | 26.0% | 71.7% |
| venue interaction | 41.7% | 59.4% | 23.2% |
| formation used as context | 0.0% | 0.0% | 0.0% |
| half-state conditional | 0.0% | 0.0% | 0.0% |
| multi-kind interaction | 0.0% | 22.9% | 0.0% |
| excessive complexity | 25.7% | 4.2% | 35.5% |
| hallucinated evidence ref | 0.0% | 1.6% | n/a |
| candidates with >=1 blocking firewall finding | 83.3% | 82.3% | 0.0% |
| mean conditions / candidate | 0.66% | 1.09% | 0.91% |

*Arm D has no packet and makes no calls, so its evidence-grounding and firewall cells are not meaningful and should be read as n/a rather than as a perfect score.*

---

## 3. Reconnaissance — did Arm B actually analyse behaviour first?

- fixtures where all four reconnaissance blocks (A attack, A defense, B attack, B defense) were populated: **12/12**
- total behavioural observations written: **274**
- attack×defense interaction lines: **100**
- tensions **30** · asymmetries **35** · regime changes **33**

Arm A's protocol has no reconnaissance surface at all — `schema_v4` has no field for an observation, a mechanism or a falsifier — so these rows are structurally absent for Arm A rather than zero.

---

## 4. Diversity

- research-family concentration (largest family share): Arm A 13.9%, Arm B 13.5%
- distinct target metrics used: Arm A 15, Arm B 32

**Arm A families:** {"ATTACK_QUALITY": 14, "ATTACK_VOLUME": 12, "COMPETITION_ENVIRONMENT": 3, "DEFENSIVE_CONCESSION": 20, "DEFENSIVE_SUPPRESSION": 7, "DISCIPLINE": 13, "FORM_VS_BASELINE": 18, "OPPONENT_PROFILE_INTERACTION": 19, "SET_PIECE_GENERATION": 12, "TEMPO_AND_TERRITORY": 12, "VENUE_EFFECT": 14}

**Arm B families:** {"ATTACK_QUALITY": 13, "ATTACK_VOLUME": 12, "DEFENSIVE_CONCESSION": 13, "DEFENSIVE_SUPPRESSION": 10, "DISCIPLINE": 11, "FORM_VS_BASELINE": 5, "OPPONENT_PROFILE_INTERACTION": 7, "SET_PIECE_GENERATION": 11, "TEMPO_AND_TERRITORY": 10, "VENUE_EFFECT": 4}

---

## 5. Examples

### Strongest structurally novel questions (Arm B)

*"Strongest" means best structural compliance and novelty. It does NOT mean a larger historical effect — no effect was computed.*

**mt_367782066 / C3** — measurable and outside the generic generator's image

- verdict: `INCREMENTAL_STRUCTURE` — measurable, but outside the generic generator's image: conditions mix kinds (COMPETITION+VENUE); `_conditions_for` emits every condition with a single kind, so the generator can never emit this interaction
- compiles to: For big_chances, shots_on_target, xg: does the subject's concession, over all prior matches, restricted to matches where the match was in the same competition as the target fixture and the match was played HOME differ from the subject's concession, over all prior matches, restricted to matches where the match was played TARGET_VENUE?
- measurable: True; conditions: 2

**mt_367782066 / C4** — measurable and outside the generic generator's image

- verdict: `INCREMENTAL_STRUCTURE` — measurable, but outside the generic generator's image: conditions mix kinds (COMPETITION+OPPONENT_PROFILE); `_conditions_for` emits every condition with a single kind, so the generator can never emit this interaction
- compiles to: For fouls, yellow_cards: does the subject's production, over all prior matches, restricted to matches where the match was in the same competition as the target fixture and the opponent was in the HIGH tercile of possession differ from the subject's production, over all prior matches, excluding matches where the match was in the same competition as the target fixture and the opponent was in the HIGH tercile of possession?
- measurable: True; conditions: 2

**mt_367782066 / C5** — measurable and outside the generic generator's image

- verdict: `INCREMENTAL_STRUCTURE` — measurable, but outside the generic generator's image: conditions mix kinds (COMPETITION+VENUE); `_conditions_for` emits every condition with a single kind, so the generator can never emit this interaction
- compiles to: For final_third_entries, shots, shots_inside_box: does the subject's production, over all prior matches, against opponents similar to the fixture opponent, restricted to matches where the match was in the same competition as the target fixture and the match was played HOME differ from the subject's production, over all prior matches, against opponents NOT similar to the fixture opponent, restricted to matches where the match was in the same competition as the target fixture and the match was played HOME?
- measurable: True; conditions: 2

### Rejected as generic-equivalent (Arm B)

**mt_196560745 / C2** — the same statistical question blind enumeration already represents

- verdict: `STRUCTURAL_EQUIVALENT` — different prose, but the structure lies inside the generic generator's image: enumeration already represents this statistical question
- compiles to: For big_chances, shots, shots_inside_box: does the subject's concession, over its last 10 prior matches, restricted to matches where the match was in the same competition as the target fixture, weighted toward recent matches differ from the subject's concession, over all prior matches, restricted to matches where the match was in the same competition as the target fixture?
- measurable: True; conditions: 1

**mt_196560745 / C3** — the same statistical question blind enumeration already represents

- verdict: `STRUCTURAL_EQUIVALENT` — different prose, but the structure lies inside the generic generator's image: enumeration already represents this statistical question
- compiles to: For goals, shots_on_target, xg: does the subject's production, over its last 10 prior matches, restricted to matches where the match was in the same competition as the target fixture, weighted toward recent matches differ from the subject's production, over all prior matches, restricted to matches where the match was in the same competition as the target fixture?
- measurable: True; conditions: 1

**mt_196560745 / C4** — the same statistical question blind enumeration already represents

- verdict: `STRUCTURAL_EQUIVALENT` — different prose, but the structure lies inside the generic generator's image: enumeration already represents this statistical question
- compiles to: For big_chances, shots, shots_on_target: does the subject's production, over all prior matches, against opponents similar to the fixture opponent, restricted to matches where the match was played HOME differ from the subject's production, over all prior matches, against opponents NOT similar to the fixture opponent, restricted to matches where the match was played HOME?
- measurable: True; conditions: 1

### Invalid / caught cases

**mt_196560745 / H01** — rejected by the deterministic compiler / capability / tautology layer

- verdict: `INVALID` — compiler rejected the candidate: TAUTOLOGY_OR_DEGENERATE_COHORT
- compiles to: For big_chances, shots, shots_on_target, touches_in_penalty_area, xg: does the subject's production, over all prior matches, restricted to matches where the match was played HOME differ from the subject's production, over all prior matches, restricted to matches where the match was played TARGET_VENUE?
- measurable: True; conditions: 1

**mt_196560745 / H02** — rejected by the deterministic compiler / capability / tautology layer

- verdict: `INVALID` — compiler rejected the candidate: TAUTOLOGY_OR_DEGENERATE_COHORT
- compiles to: For shots, shots_inside_box, shots_on_target, touches_in_penalty_area: does the subject's concession, over all prior matches, restricted to matches where the match was played AWAY differ from the subject's concession, over all prior matches, restricted to matches where the match was played TARGET_VENUE?
- measurable: True; conditions: 1

**mt_196560745 / H07** — rejected by the deterministic compiler / capability / tautology layer

- verdict: `INVALID` — compiler rejected the candidate: TAUTOLOGY_OR_DEGENERATE_COHORT
- compiles to: For corner_kicks: does the subject's production, over all prior matches, restricted to matches where the match was played HOME differ from the subject's production, over all prior matches, restricted to matches where the match was played TARGET_VENUE?
- measurable: True; conditions: 1

**mt_196560745 / H09** — rejected by the deterministic compiler / capability / tautology layer

- verdict: `INVALID` — compiler rejected the candidate: TAUTOLOGY_OR_DEGENERATE_COHORT
- compiles to: For possession: does the subject's production, over all prior matches, restricted to matches where the match was played HOME differ from the subject's production, over all prior matches, restricted to matches where the match was played TARGET_VENUE?
- measurable: True; conditions: 1

**Hallucinated evidence references:** 6 candidates cited at least one reference their packet does not contain.

- `mt_257018027/C3`: ['TEAM_B.raw_historical_rows.ROW:01', 'TEAM_B.raw_historical_rows.ROW:07']
- `mt_629405468/C5`: ['TEAM_B.raw_historical_rows.ROW:09']
- `mt_629405468/C7`: ['TEAM_A.raw_historical_rows.ROW:11', 'TEAM_A.raw_historical_rows.ROW:12']

---

## 6. Integrity

| Check | Result |
|---|---|
| CHAMPION composite before | `778339321631f0a15e42738977c810c055aaeb65315c52852e0370618b8baef8` |
| CHAMPION composite after | `778339321631f0a15e42738977c810c055aaeb65315c52852e0370618b8baef8` |
| **CHAMPION unchanged** | **True** |
| prompts frozen before first paid call | True |
| Arm A prompt reconstructed or approximated | False |
| generic library exposes any effect / survival / p-value | false |
| predictive claims made in the novelty pass | 0 |
| execution errors | 0 |
| **PIT-clean packets** | **12/12** |
| historical rows checked against the cutoff | 405 |
| rows at or after the information cutoff | 0 |
| packets containing the target outcome | 0 |

---

## 7. Numerical firewall (brief §7)

The raw firewall counts in §2 are *findings*, not breaches: the overwhelming majority are `UNFRAMED_NUMERIC` — the model reproducing a packet value in prose without the framing the scanner wants. A separate, **symmetric** adjudicator (`adjudicate_numeric_sentence`, applied to both arms with no masking on either) classifies every numeric sentence and quotes each flagged one verbatim so the call can be checked rather than trusted.

| | Arm A | Arm B |
|---|---|---|
| numeric sentences describing prior behaviour (permitted) | 561 | 486 |
| FUTURE_CLAIM sentences (breach) | 1 | 3 |
| DERIVED_QUANTITY sentences (breach) | 0 | 1 |
| **candidates with a genuine breach** | **1** | **4** |

Every genuine breach, verbatim:

- **Arm A · FUTURE_CLAIM** · `mt_196560745/H12` — "Does AWAY_TEAM's attacking and defensive output differ between matches played in COMPETITION (the upcoming fixture's competition) and matches played in other competitions (COMP_002)?"
- **Arm B · FUTURE_CLAIM** · `mt_361718124/C2` — "However the magnitude of the split (7.8 home vs 4.75 away) is large and directly relevant to the upcoming fixture where Villa are away."
- **Arm B · FUTURE_CLAIM** · `mt_408750601/C5` — "In the upcoming fixture TEAM_B plays AWAY, so their crossing output is expected to be much lower than their overall avg of 5.6."
- **Arm B · FUTURE_CLAIM** · `mt_972834336/C6` — "TEAM_A's structural low-possession profile means it will likely be below its recent 45.6% average in this match."
- **Arm B · DERIVED_QUANTITY** · `mt_408756224/C1` — "Derby concede corners at a rate of 5.56 long-run all and 5.63 away, which is above the league average implied by Leeds' long-run home mean of 7.41 — Derby are not a low-corner-conceding side."

**This is a cost of the new protocol, and it is charged to Arm B.** Arm B breaches on 4 candidates against Arm A's 1. The mechanism is structural, not a model defect: V8A deliberately asks for flowing behavioural prose across seven surfaces, while `schema_v4` gives Arm A two terse fields. More prose surface is more opportunity to stray. No breach entered the numerical path — these are research questions, never predictions, and `V8A_PREDICTIVE_CLAIM=false` — but a protocol that invites prose invites this, and a future revision should tighten the observation field rather than assume the firewall will absorb it.

---

## 8. Scorer amendments made after the outputs existed

Two scorer defects were found and fixed **after** the model responses were on disk. Both are recorded in `V8A_BUG_LEDGER.json` (`V8A-D2`, `V8A-D3`). Neither touches the prompt, the packets, the fixture sample or the generic library — all of which stayed frozen and hash-verified — but a scorer change made with the outputs in view is exactly the shape of change that can silently favour an arm, so its effect is **measured per arm** rather than argued.

**V8A-D2 — evidence-reference index.** The first version hand-wrote an abbreviated citation form while the model cited the genuine dotted packet path. Every reference scored as hallucinated, which would have reported a well-grounded arm as 100% ungrounded on the single most important grounding metric. The fix walks the packet and emits real paths. This *raised* Arm B's grounding score, and Arm B is the arm under test — so the corrected figure (1.6% hallucinated refs, 11 of 705) is reported with the 6 offending candidates named in §5.

**V8A-D3 — metric-name collision.** `firewall_v5`'s predictive-marker set contains "chance", which collides with this corpus's `big_chances` metric name. `normalise_metric_prose` rewrites the space-separated spelling of approved metric names to the underscore form before scanning. It is wired into Arm B's scan path only; Arm A keeps `FW.scan_hypothesis` verbatim. The asymmetry is therefore measured both ways:

| | Arm A | Arm B |
|---|---|---|
| mask applied when scored | False | True |
| blocking findings as scored | 641 | 379 |
| blocking findings under the opposite mask state | 641 | 416 |
| predictive-intent findings as scored | 1 | 25 |
| predictive-intent findings under the opposite mask state | 1 | 41 |

**Reading:** the mask is immaterial for Arm A — applying it changes Arm A's totals by nothing at all (641 → 641, predictive 1 → 1), because Arm A's terse prose almost never triggered the collision. For Arm B it rescues 37 findings and 16 predictive-intent classifications. Crucially it does **not** flip the direction of the comparison: Arm B carries more predictive-intent findings than Arm A both with the mask (25 vs 1) and without it (41 vs 1). The amendment could not have manufactured a favourable result for the arm under test on this axis, and §7's breach count — which uses the symmetric adjudicator and no mask at all — is independent of it.

---

## 9. Interpretation caveats

- **N = 12 fixtures.** Every rate here is a small-sample descriptive statistic. No confidence interval is attached because none is warranted at this N, and no inferential claim is made.
- **The measurable space is narrow by construction.** The compiler honours exactly three filter dimensions, the similarity engine's five dimensions are frozen, and the generic generator emits all conditions with a single kind. The only channels for genuine incremental structure are a mixed-kind condition set or three-plus conditions. This was recorded in the protocol spec before any call.
- **Formation-conditioned and half-state-conditioned cohorts are impossible for every arm alike** — formation is not resolvable per prior match in this corpus, and half-time score state is populated on 0 of 5,636 records. Zero rates on those rows are properties of the corpus, not of a model.
- **Arm D's rates are not a model's behaviour.** Arm D is blind enumeration scored through the same audit path, present as a structural floor.
- **Generator self-noise bounds every A-vs-B comparison.** `v6_selfnoise_v1` records that four byte-identical requests at temperature 0.0, with the same `serialized_request_sha256`, produced qualified rates of 0.75 / 0.00 / 0.70 / 0.00 — pooled within-cell SD 0.363. That is measured in this repository, not asserted here. This design runs ONE call per fixture per arm, so a small gap between arms is inside documented generator variance and no such gap is claimed as a difference.
- **LLM output is not bitwise reproducible on this provider at temperature 0.** Determinism claims in this report apply to the deterministic layers — packets, library, retrieval, canonicalisation and scoring — never to the model's text.

- **Two PIT scan notes, both checked by hand.** The per-candidate `pit_valid` counter in `per_arm_counts` is vestigial — it is initialised and never incremented, because PIT is enforced upstream at packet construction and audited per fixture in `V8A_PIT_AUDIT.json` (the §6 rows above). Read the counter as n/a, not as zero. Separately, `no_banned_tokens` reads false on every packet because the substring `market_price` matches the capability envelope's own key `market_prices`, whose value is `"status": "UNAVAILABLE", "reason": "not provided by source; the research path is price-blind by design"`. Every occurrence in all 12 packets was inspected: that declaration is the only one. No price, odds, line or settlement value is present.

---

## 10. The ten questions, answered plainly (brief §31)

Structural evidence only. No predictive claim is made or implied anywhere below.

**1. Did the new protocol make Sonnet actually analyse football behaviour before hypothesising?**

Yes, and this is the clearest positive result. All **12/12** fixtures returned all four reconnaissance blocks populated, with **274 behavioural observations**, **100 attack×defense interaction lines**, and explicitly labelled **30 tensions**, **35 asymmetries** and **33 regime changes**. The caveat is that the schema *required* these fields, so compliance is not proof of insight — what it proves is that the model could fill them from the packet without hallucinating: only 11 of 705 citations were unresolvable.

**2. Did measurability improve substantially relative to the old behaviour?**

**No — it fell.** Arm A 100.0% vs Arm B 91.7%, on the same 12 fixtures and the same model. Arm B named 8 metrics the capability layer could not resolve; Arm A named none. This is the honest headline and it goes against the protocol. The mechanism is visible: Arm A's schema constrained the model to a closed metric vocabulary, while V8A's richer packet invited it to name quantities the compiler does not implement. V7.1's 38.6% measurability is **not** the comparator here — different sample, different compiler, confirmatory fixtures — and is quoted only as uncontrolled context. The controlled comparison is A vs B above.

**3. Is it still mostly generating generic recency/baseline questions?**

Less so, but the bulk is still generic. Structural generic equivalence fell from 59.7% (A) to 40.6% (B), and exact duplicates from 6.2% to 3.1%. Pure recent-vs-long-run questions fell from 33.3% to 26.0%. So roughly two in five Arm B candidates still ask a question blind enumeration already represents.

**4. Did it produce genuine attack × defense interactions?**

Only partly. The *reconnaissance* is full of them (100 interaction lines), but that reasoning largely failed to survive into hypothesis structure: the deterministic attack×defense classification is 21.5% for A and 17.7% for B — a *decrease*, and both sit near blind enumeration's 18.4%. The model reasons about the matchup in prose and then compiles a question that does not encode the interaction. That gap is the single most actionable finding here.

**5. Did it use formation as context tied to raw behaviour rather than stereotype?**

Unanswerable from this run, and not the model's fault. Formation-conditioned cohorts are **impossible for every arm alike**: formation is not resolvable per prior match in this corpus, so the capability envelope marks it unavailable and both arms score 0.0%. The protocol's Phase 3 was never actually exercised. Any future test of it needs corpus work first, not prompt work.

**6. Did similar-opponent reasoning become materially richer?**

**Yes — the largest clean gain.** Arm A produced 0 similar-opponent hypotheses (0.0%). Arm B produced 29 (30.2%), against blind enumeration's 9.9%. A capability the incumbent protocol never touched is now routinely used, and used within the deterministic similarity engine rather than computed by the model.

**7. Did the generic novelty challenge cause useful refinement or mostly abstention?**

**Overwhelmingly abstention:** ABSTAIN 61, KEEP 30, REFINE 5 of 96 second-pass decisions. Roughly 64% of candidates were withdrawn once the model saw structurally comparable generic hypotheses. Per §21 abstention is successful behaviour, and the challenge is clearly doing work rather than being rubber-stamped. But REFINE at 5 shows the model mostly cannot convert a generic candidate into a distinct one — it either keeps or gives up. Note also that the model's own self-grading is **not** the label: §16's deterministic canonicalisation is.

**8. Did the LLM find structures the generic generator does not already cover?**

**Yes, but narrowly and for a mechanical reason.** Deterministically labelled `INCREMENTAL_STRUCTURE`: Arm A 1 (0.7%), Arm B 14 (14.6%), Arm D 0 by construction. A 14× lift over the incumbent is real and is the protocol's strongest structural result. The honest qualifier: they are incremental for one mechanical reason — **14 of 14** **mix condition kinds** (COMPETITION+OPPONENT_PROFILE ×2, COMPETITION+VENUE ×11, OPPONENT_PROFILE+VENUE ×1), which `_conditions_for` cannot emit since it draws every condition from one kind. So the LLM is exploiting a specific, known gap in the generator's image rather than inventing an unforeseen class of question. Whether that gap is scientifically interesting or merely an enumerator limitation is a question this report cannot settle — and closing the gap in the generator is the cheaper first experiment.

**9. Does Terra behave differently from Sonnet under the exact same protocol?**

**Unknown — not tested.** `V8A_TERRA_ARM_EXECUTED=false`. Blocker: No model named Terra exists in this repository; no OpenAI or other non-Bedrock credential is present; no adapter exists. Substituting another model is forbidden by brief 19/33. No substitute model was run, because §19/§33 forbid calling anything else Terra.

**10. Is the research protocol promising enough to justify a fresh OOS experiment?**

**Not yet — from structural evidence only, my answer is no.** Three findings have to be weighed together.

*For:* similar-opponent conditioning went from unused to routine; incremental structure rose 14×; abstention behaves as designed; evidence grounding is strong.

*Against, and decisive:* **measurability fell** (100.0% → 91.7%), **compiler validity fell** (99.3% → 87.5%), and the attack×defense reasoning that the protocol exists to elicit **did not reach hypothesis structure**. A confirmatory sample spent now would be spent on a protocol whose central mechanism is demonstrably not yet compiling.

*Decisive constraint:* at N=12 with one call per fixture per arm, documented generator self-noise (`v6_selfnoise_v1`, within-cell SD 0.363) is wide enough that only the largest gaps here — similar-opponent 0%→30%, incremental 0.7%→14.6% — sit clearly outside it. The rest are suggestive at best.

*What a V8A.1 should fix before any OOS spend, in order:* (a) constrain the candidate metric vocabulary to the capability envelope so measurability recovers; (b) make the interaction map compile — require a candidate that claims an attack×defense mechanism to encode it in conditions; (c) close or deliberately open the mixed-condition-kind gap in the generic generator, so that `INCREMENTAL_STRUCTURE` means something stronger than an enumerator blind spot; (d) tighten the observation field to reduce the prose-firewall breaches in §7. Per §24 none of these may be applied to this sample and called the same experiment.

---

## 11. Terminal states (brief §33)

- `V8A_DEVELOPMENT_COMPLETE=true`
- `V8A_PROMPT_FROZEN=true`
- `V8A_GENERIC_LIBRARY_OUTCOME_BLIND=true`
- `V8A_GENERIC_NOVELTY_CHALLENGE_ACTIVE=true`
- `V8A_STRUCTURAL_AUDIT_COMPLETE=true`
- `V8A_HISTORICAL_EFFECTS_COMPUTED=false`
- `V8A_FRESH_OOS_OPENED=false`
- `V8A_PREDICTIVE_CLAIM=false`
- `V8A_FEATURE_PROMOTION=false`
- `V8A_TERRA_ARM_EXECUTED=false`
- `CHAMPION_UNCHANGED=true`
- `V8A_TERRA_BLOCKER="No model named Terra exists in this repository; no OpenAI or other non-Bedrock credential is present; no adapter exists. Substituting another model is forbidden by brief 19/33."`

Stopping here per §34: no OOS sample is opened, the prompt is not tuned after seeing these results, and V8B is not designed.

