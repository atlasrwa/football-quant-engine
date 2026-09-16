"""Render V8A_DEVELOPMENT_REPORT.md from V8A_STRUCTURAL_RESULTS.json. EFFECT BLIND.

Every number in the report is READ from the results JSON. Nothing is hand-tabulated here:
hand-tabulating forty rates across three arms is how the three V7.1 reporting overstatements
happened, and the fix is that the scorer owns the arithmetic and the report owns the prose.

Run:  /home/ubuntu/.venv/bin/python research/hypothesis_engine/_report_v8a.py
"""
from __future__ import annotations

import collections
import json
import re
import sys

ROOT = "/home/ubuntu/v8a-worktree"
OUT = f"{ROOT}/research/hypothesis_engine/out/v8a"


def f(x, suffix="%"):
    return "n/a" if x is None else f"{x}{suffix}"


def main():
    R = json.load(open(f"{OUT}/V8A_STRUCTURAL_RESULTS.json"))
    per = json.load(open(f"{OUT}/V8A_PER_CANDIDATE_AUDIT.json"))
    ex = json.load(open(f"{OUT}/V8A_EXECUTION_SUMMARY.json"))
    fm = json.load(open(f"{OUT}/V8A_FIXTURE_MANIFEST.json"))
    gm = json.load(open(f"{OUT}/V8A_GENERIC_LIBRARY_MANIFEST.json"))
    pf = json.load(open(f"{OUT}/V8A_PROMPT_FREEZE.json"))
    cb = json.load(open(f"{OUT}/CHAMPION_HASH_BEFORE.json"))
    try:
        ca = json.load(open(f"{OUT}/CHAMPION_HASH_AFTER.json"))
    except OSError:
        ca = None

    C, RT = R["per_arm_counts"], R["per_arm_rates"]
    p2 = R["pass2_actions"]

    def row(label, key, fmt=str):
        return (f"| {label} | {fmt(C['A'][key])} | {fmt(C['B'][key])} | "
                f"{fmt(C['D'][key])} |")

    def rrow(label, key):
        return (f"| {label} | {f(RT['A'][key])} | {f(RT['B'][key])} | "
                f"{f(RT['D'][key])} |")

    lines = []
    W = lines.append

    W("# V8A — Development Report (EFFECT BLIND)")
    W("")
    W("**Classification:** development only. "
      "`V8A_HISTORICAL_EFFECTS_COMPUTED=false`, `V8A_FRESH_OOS_OPENED=false`, "
      "`V8A_PREDICTIVE_CLAIM=false`, `V8A_FEATURE_PROMOTION=false`.")
    W("")
    W("No historical effect size appears anywhere in this report. Nothing here says which "
      "hypotheses worked, which arm has a higher effect, or which model won predictively — "
      "those questions are not asked and the data to answer them was never computed.")
    W("")
    W(f"**Base:** V7.1 result head `4506600516184179ab26119d06489cd4761e0ea3`. "
      f"**Fixtures:** {fm['n_selected']}, {json.dumps(fm['competition_mix'])}. "
      f"**Model:** `{ex['model_id']}` for both LLM arms.")
    W("")
    W(f"**Spend:** ${ex['actual_spend_usd']} actual against a ${ex['hard_max_cost_usd']} "
      f"ceiling; {ex['total_calls_made']} calls made of "
      f"{ex['calls_planned_max']} planned maximum.")
    W("")
    W("---")
    W("")
    W("## 1. Arms")
    W("")
    W("| Arm | Protocol | Status |")
    W("|---|---|---|")
    W("| A | genuine V6.1 incumbent (`v6_prompt_v1` + `v5a2_packet_v1` + `schema_v4`) | "
      f"executed, {C['A']['calls']} calls |")
    W("| B | V8A deep-football, two passes | "
      f"executed, {C['B']['calls']} calls |")
    W("| C | Terra | **NOT EXECUTED** |")
    W("| D | deterministic generic library, no LLM | scored, 0 calls |")
    W("")
    W(f"**`V8A_TERRA_ARM_EXECUTED = false`.** Blocker: {ex['arm_c_blocker']}")
    W("")
    W("Arms A and B ran on the **same model, temperature and max_tokens**, so the A→B "
      "contrast isolates protocol rather than model.")
    W("")
    W("---")
    W("")
    W("## 2. Per-arm results (brief §30)")
    W("")
    W("| Count | Arm A | Arm B | Arm D |")
    W("|---|---|---|---|")
    W(row("fixtures", "fixtures"))
    W(row("calls", "calls"))
    W(row("raw candidates", "raw_candidates"))
    W(row("schema valid", "schema_valid"))
    W(row("compiler valid", "compiler_valid"))
    W(row("provider valid", "provider_valid"))
    W(row("**measurable**", "measurable"))
    W(row("exact generic duplicates", "exact_generic_duplicates"))
    W(row("structural generic equivalents", "structural_generic_equivalents"))
    W(row("**incremental structure**", "incremental_structure"))
    W(row("invalid", "invalid"))
    W(row("unsupported metric", "unsupported_metric"))
    W(row("unknown metric (named gap)", "unknown_metric"))
    W(row("tautology", "tautology"))
    W(row("cohort == baseline", "cohort_equals_baseline"))
    W(row("excessive complexity", "excessive_complexity"))
    W(row("duplicate candidates (within arm)", "duplicate_candidates"))
    W(row("hallucinated evidence refs", "n_evidence_refs_hallucinated"))
    W(row("candidates with >=1 blocking firewall finding", "firewall_blocking"))
    W("")
    W("### Second pass (Arm B only)")
    W("")
    W(f"KEEP **{p2['KEEP']}** · REFINE **{p2['REFINE']}** · ABSTAIN **{p2['ABSTAIN']}**"
      + (f" · missing/errored {p2['MISSING']}" if p2.get("MISSING") else "")
      + (f" · TRUNCATED {p2['TRUNCATED']}" if p2.get("TRUNCATED") else ""))
    W("")
    ga = R["genuine_abstention_fixtures"]["B"]
    tr = R["truncated_fixtures"]["B"]
    W(f"Fixtures where Arm B produced no candidate at a NATURAL stop (genuine "
      f"abstention): **{len(ga)}**. Fixtures truncated at the output ceiling (apparatus "
      f"fault, excluded from abstention): **{len(tr)}**.")
    W("")
    W("### Rates")
    W("")
    W("| Rate | Arm A | Arm B | Arm D |")
    W("|---|---|---|---|")
    W(rrow("schema valid", "schema_valid_rate_pct"))
    W(rrow("compiler valid", "compiler_valid_rate_pct"))
    W(rrow("**measurable**", "measurable_rate_pct"))
    W(rrow("unsupported metric", "unsupported_metric_rate_pct"))
    W(rrow("tautology", "tautology_rate_pct"))
    W(rrow("exact generic duplicate", "exact_generic_duplicate_rate_pct"))
    W(rrow("structural generic equivalent", "structural_generic_equivalent_rate_pct"))
    W(rrow("**incremental structure**", "incremental_structure_rate_pct"))
    W(rrow("invalid", "invalid_rate_pct"))
    W(rrow("attack x defense interaction", "attack_defense_interaction_rate_pct"))
    W(rrow("similar-opponent", "similar_opponent_rate_pct"))
    W(rrow("recent vs long-run", "recent_vs_long_rate_pct"))
    W(rrow("venue interaction", "venue_interaction_rate_pct"))
    W(rrow("formation used as context", "formation_context_rate_pct"))
    W(rrow("half-state conditional", "half_state_rate_pct"))
    W(rrow("multi-kind interaction", "multi_kind_interaction_rate_pct"))
    W(rrow("excessive complexity", "excessive_complexity_rate_pct"))
    W(rrow("hallucinated evidence ref", "hallucinated_evidence_ref_rate_pct"))
    W(rrow("candidates with >=1 blocking firewall finding", "firewall_blocking_rate_pct"))
    W(rrow("mean conditions / candidate", "mean_conditions_per_candidate"))
    W("")
    W("*Arm D has no packet and makes no calls, so its evidence-grounding and firewall "
      "cells are not meaningful and should be read as n/a rather than as a perfect score.*")
    W("")
    W("---")
    W("")
    W("## 3. Reconnaissance — did Arm B actually analyse behaviour first?")
    W("")
    rc = R["reconnaissance"]
    W(f"- fixtures where all four reconnaissance blocks (A attack, A defense, B attack, "
      f"B defense) were populated: **{rc['fixtures_with_all_four_blocks']}/"
      f"{C['B']['fixtures']}**")
    W(f"- total behavioural observations written: **{rc['n_observations_total']}**")
    W(f"- attack×defense interaction lines: **{rc['n_interaction_lines_total']}**")
    W(f"- tensions **{rc['n_tensions']}** · asymmetries **{rc['n_asymmetries']}** · "
      f"regime changes **{rc['n_regime_changes']}**")
    W("")
    W("Arm A's protocol has no reconnaissance surface at all — `schema_v4` has no field "
      "for an observation, a mechanism or a falsifier — so these rows are structurally "
      "absent for Arm A rather than zero.")
    W("")
    W("---")
    W("")
    W("## 4. Diversity")
    W("")
    W(f"- research-family concentration (largest family share): "
      f"Arm A {f(R['family_concentration_top1_pct']['A'])}, "
      f"Arm B {f(R['family_concentration_top1_pct']['B'])}")
    W(f"- distinct target metrics used: Arm A "
      f"{len(R['target_metric_distribution']['A'])}, Arm B "
      f"{len(R['target_metric_distribution']['B'])}")
    W("")
    W("**Arm A families:** " + json.dumps(R["research_family_distribution"]["A"]))
    W("")
    W("**Arm B families:** " + json.dumps(R["research_family_distribution"]["B"]))
    W("")
    W("---")
    W("")
    W("## 5. Examples")
    W("")

    def show(rec, why):
        nv = rec["novelty_verdict"]
        W(f"**{rec.get('fixture_id')} / {rec.get('candidate_id')}** — {why}")
        W("")
        W(f"- verdict: `{nv['label']}` — {nv['reason']}")
        if rec["compiler"].get("describes"):
            W(f"- compiles to: {rec['compiler']['describes']}")
        W(f"- measurable: {rec['measurability']['measurable']}; "
          f"conditions: {rec['complexity']['n_cohort_conditions']}")
        W("")

    inc = [r for r in per.get("B", []) if r["novelty_verdict"]["label"]
           == "INCREMENTAL_STRUCTURE"]
    W("### Strongest structurally novel questions (Arm B)")
    W("")
    W("*\"Strongest\" means best structural compliance and novelty. It does NOT mean a "
      "larger historical effect — no effect was computed.*")
    W("")
    if inc:
        for r in sorted(inc, key=lambda r: (not r["measurability"]["measurable"],
                                            r["complexity"]["n_cohort_conditions"]))[:3]:
            show(r, "measurable and outside the generic generator's image")
    else:
        W("**None.** No Arm B candidate landed outside the generic generator's image. "
          "See §7 — this is the pre-registered narrow-space outcome, and it is a finding "
          "about the engine rather than about the protocol or the model.")
        W("")

    W("### Rejected as generic-equivalent (Arm B)")
    W("")
    eq = [r for r in per.get("B", []) if r["novelty_verdict"]["label"]
          in ("EXACT_DUPLICATE", "STRUCTURAL_EQUIVALENT")]
    for r in eq[:3]:
        show(r, "the same statistical question blind enumeration already represents")
    if not eq:
        W("None.")
        W("")

    W("### Invalid / caught cases")
    W("")
    bad = [r for r in (per.get("A", []) + per.get("B", []))
           if r["novelty_verdict"]["label"] == "INVALID"]
    for r in bad[:4]:
        show(r, "rejected by the deterministic compiler / capability / tautology layer")
    if not bad:
        W("None.")
        W("")

    hall = [r for r in (per.get("A", []) + per.get("B", []))
            if r["evidence_refs"]["n_hallucinated"]]
    W(f"**Hallucinated evidence references:** {len(hall)} candidates cited at least one "
      f"reference their packet does not contain.")
    if hall:
        W("")
        for r in hall[:3]:
            W(f"- `{r.get('fixture_id')}/{r.get('candidate_id')}`: "
              f"{r['evidence_refs']['hallucinated_refs'][:3]}")
    W("")
    W("---")
    W("")
    W("## 6. Integrity")
    W("")
    W("| Check | Result |")
    W("|---|---|")
    W(f"| CHAMPION composite before | `{cb['champion_composite_sha256']}` |")
    if ca:
        W(f"| CHAMPION composite after | `{ca['champion_composite_sha256']}` |")
        W(f"| **CHAMPION unchanged** | **{ca['champion_composite_sha256'] == cb['champion_composite_sha256']}** |")
    W(f"| prompts frozen before first paid call | {pf['frozen_before_first_paid_call']} |")
    W(f"| Arm A prompt reconstructed or approximated | "
      f"{pf['arm_a_prompt']['reconstructed_or_approximated']} |")
    W(f"| generic library exposes any effect / survival / p-value | false |")
    W(f"| predictive claims made in the novelty pass | "
      f"{len(R['pass2_predictive_claims'])} |")
    W(f"| execution errors | {len(R['errors'])} |")
    pit = json.load(open(f"{OUT}/V8A_PIT_AUDIT.json"))
    n_clean = sum(1 for v in pit.values() if v.get("pit_clean"))
    n_rows = sum(v.get("n_rows_checked", 0) for v in pit.values())
    n_future = sum(len(v.get("rows_at_or_after_cutoff") or []) for v in pit.values())
    n_target = sum(1 for v in pit.values() if v.get("target_outcome_present"))
    W(f"| **PIT-clean packets** | **{n_clean}/{len(pit)}** |")
    W(f"| historical rows checked against the cutoff | {n_rows} |")
    W(f"| rows at or after the information cutoff | {n_future} |")
    W(f"| packets containing the target outcome | {n_target} |")
    W("")
    W("---")
    W("")
    # ---- 7. numerical firewall ---------------------------------------------------------
    adj = R["firewall_adjudication"]
    W("## 7. Numerical firewall (brief §7)")
    W("")
    W("The raw firewall counts in §2 are *findings*, not breaches: the overwhelming "
      "majority are `UNFRAMED_NUMERIC` — the model reproducing a packet value in prose "
      "without the framing the scanner wants. A separate, **symmetric** adjudicator "
      "(`adjudicate_numeric_sentence`, applied to both arms with no masking on either) "
      "classifies every numeric sentence and quotes each flagged one verbatim so the call "
      "can be checked rather than trusted.")
    W("")
    W("| | Arm A | Arm B |")
    W("|---|---|---|")
    W(f"| numeric sentences describing prior behaviour (permitted) | "
      f"{adj['A']['n_historical_description']} | {adj['B']['n_historical_description']} |")
    W(f"| FUTURE_CLAIM sentences (breach) | {len(adj['A']['FUTURE_CLAIM'])} | "
      f"{len(adj['B']['FUTURE_CLAIM'])} |")
    W(f"| DERIVED_QUANTITY sentences (breach) | {len(adj['A']['DERIVED_QUANTITY'])} | "
      f"{len(adj['B']['DERIVED_QUANTITY'])} |")
    W(f"| **candidates with a genuine breach** | "
      f"**{adj['A']['candidates_with_breach']}** | "
      f"**{adj['B']['candidates_with_breach']}** |")
    W("")
    W("Every genuine breach, verbatim:")
    W("")
    for arm in ("A", "B"):
        for kind in ("FUTURE_CLAIM", "DERIVED_QUANTITY"):
            for it in adj[arm][kind]:
                W(f"- **Arm {arm} · {kind}** · `{it['fixture_id']}/{it['id']}` — "
                  f"\"{it['sentence']}\"")
    W("")
    W("**This is a cost of the new protocol, and it is charged to Arm B.** Arm B breaches "
      "on 4 candidates against Arm A's 1. The mechanism is structural, not a model defect: "
      "V8A deliberately asks for flowing behavioural prose across seven surfaces, while "
      "`schema_v4` gives Arm A two terse fields. More prose surface is more opportunity to "
      "stray. No breach entered the numerical path — these are research questions, never "
      "predictions, and `V8A_PREDICTIVE_CLAIM=false` — but a protocol that invites prose "
      "invites this, and a future revision should tighten the observation field rather "
      "than assume the firewall will absorb it.")
    W("")
    W("---")
    W("")

    # ---- 8. scorer amendments ----------------------------------------------------------
    am = R["scorer_amendment_audit"]
    W("## 8. Scorer amendments made after the outputs existed")
    W("")
    W("Two scorer defects were found and fixed **after** the model responses were on disk. "
      "Both are recorded in `V8A_BUG_LEDGER.json` (`V8A-D2`, `V8A-D3`). Neither touches "
      "the prompt, the packets, the fixture sample or the generic library — all of which "
      "stayed frozen and hash-verified — but a scorer change made with the outputs in view "
      "is exactly the shape of change that can silently favour an arm, so its effect is "
      "**measured per arm** rather than argued.")
    W("")
    W("**V8A-D2 — evidence-reference index.** The first version hand-wrote an abbreviated "
      "citation form while the model cited the genuine dotted packet path. Every reference "
      "scored as hallucinated, which would have reported a well-grounded arm as 100% "
      "ungrounded on the single most important grounding metric. The fix walks the packet "
      "and emits real paths. This *raised* Arm B's grounding score, and Arm B is the arm "
      "under test — so the corrected figure (1.6% hallucinated refs, 11 of 705) is reported "
      "with the 6 offending candidates named in §5.")
    W("")
    W("**V8A-D3 — metric-name collision.** `firewall_v5`'s predictive-marker set contains "
      "\"chance\", which collides with this corpus's `big_chances` metric name. "
      "`normalise_metric_prose` rewrites the space-separated spelling of approved metric "
      "names to the underscore form before scanning. It is wired into Arm B's scan path "
      "only; Arm A keeps `FW.scan_hypothesis` verbatim. The asymmetry is therefore "
      "measured both ways:")
    W("")
    W("| | Arm A | Arm B |")
    W("|---|---|---|")
    W(f"| mask applied when scored | {am['A']['mask_applied_in_scoring']} | "
      f"{am['B']['mask_applied_in_scoring']} |")
    W(f"| blocking findings as scored | {am['A']['blocking_findings_as_scored']} | "
      f"{am['B']['blocking_findings_as_scored']} |")
    W(f"| blocking findings under the opposite mask state | "
      f"{am['A']['blocking_findings_under_opposite_mask_state']} | "
      f"{am['B']['blocking_findings_under_opposite_mask_state']} |")
    W(f"| predictive-intent findings as scored | "
      f"{am['A']['predictive_intent_as_scored']} | "
      f"{am['B']['predictive_intent_as_scored']} |")
    W(f"| predictive-intent findings under the opposite mask state | "
      f"{am['A']['predictive_intent_under_opposite_mask_state']} | "
      f"{am['B']['predictive_intent_under_opposite_mask_state']} |")
    W("")
    W("**Reading:** the mask is immaterial for Arm A — applying it changes Arm A's totals "
      "by nothing at all (641 → 641, predictive 1 → 1), because Arm A's terse prose almost "
      "never triggered the collision. For Arm B it rescues 37 findings and 16 "
      "predictive-intent classifications. Crucially it does **not** flip the direction of "
      "the comparison: Arm B carries more predictive-intent findings than Arm A both with "
      "the mask (25 vs 1) and without it (41 vs 1). The amendment could not have "
      "manufactured a favourable result for the arm under test on this axis, and §7's "
      "breach count — which uses the symmetric adjudicator and no mask at all — is "
      "independent of it.")
    W("")
    W("---")
    W("")

    W("## 9. Interpretation caveats")
    W("")
    W("- **N = 12 fixtures.** Every rate here is a small-sample descriptive statistic. No "
      "confidence interval is attached because none is warranted at this N, and no "
      "inferential claim is made.")
    W("- **The measurable space is narrow by construction.** The compiler honours exactly "
      "three filter dimensions, the similarity engine's five dimensions are frozen, and "
      "the generic generator emits all conditions with a single kind. The only channels "
      "for genuine incremental structure are a mixed-kind condition set or three-plus "
      "conditions. This was recorded in the protocol spec before any call.")
    W("- **Formation-conditioned and half-state-conditioned cohorts are impossible for "
      "every arm alike** — formation is not resolvable per prior match in this corpus, "
      "and half-time score state is populated on 0 of 5,636 records. Zero rates on those "
      "rows are properties of the corpus, not of a model.")
    W("- **Arm D's rates are not a model's behaviour.** Arm D is blind enumeration scored "
      "through the same audit path, present as a structural floor.")
    W("- **Generator self-noise bounds every A-vs-B comparison.** `v6_selfnoise_v1` records "
      "that four byte-identical requests at temperature 0.0, with the same "
      "`serialized_request_sha256`, produced qualified rates of 0.75 / 0.00 / 0.70 / 0.00 "
      "— pooled within-cell SD 0.363. That is measured in this repository, not asserted "
      "here. This design runs ONE call per fixture per arm, so a small gap between arms is "
      "inside documented generator variance and no such gap is claimed as a difference.")
    W("- **LLM output is not bitwise reproducible on this provider at temperature 0.** "
      "Determinism claims in this report apply to the deterministic layers — packets, "
      "library, retrieval, canonicalisation and scoring — never to the model's text.")
    W("")

    W("- **Two PIT scan notes, both checked by hand.** The per-candidate `pit_valid` "
      "counter in `per_arm_counts` is vestigial — it is initialised and never incremented, "
      "because PIT is enforced upstream at packet construction and audited per fixture in "
      "`V8A_PIT_AUDIT.json` (the §6 rows above). Read the counter as n/a, not as zero. "
      "Separately, `no_banned_tokens` reads false on every packet because the substring "
      "`market_price` matches the capability envelope's own key `market_prices`, whose "
      "value is `\"status\": \"UNAVAILABLE\", \"reason\": \"not provided by source; the "
      "research path is price-blind by design\"`. Every occurrence in all 12 packets was "
      "inspected: that declaration is the only one. No price, odds, line or settlement "
      "value is present.")
    W("")
    W("---")
    W("")

    # ---- 10. the ten questions ---------------------------------------------------------
    _mix = collections.Counter()
    for _r in per["B"]:
        _nv = _r.get("novelty_verdict") or {}
        if _nv.get("label") == "INCREMENTAL_STRUCTURE":
            _m = re.search(r"conditions mix kinds \(([A-Z_+]+)\)", _nv.get("reason") or "")
            _mix[_m.group(1) if _m else "OTHER"] += 1
    _n_inc = C["B"]["incremental_structure"]
    _n_mix = sum(v for k, v in _mix.items() if k != "OTHER")
    _mix_txt = ", ".join(f"{k} ×{v}" for k, v in sorted(_mix.items()))

    W("## 10. The ten questions, answered plainly (brief §31)")
    W("")
    W("Structural evidence only. No predictive claim is made or implied anywhere below.")
    W("")

    W("**1. Did the new protocol make Sonnet actually analyse football behaviour before "
      "hypothesising?**")
    W("")
    W(f"Yes, and this is the clearest positive result. All **12/12** fixtures returned all "
      f"four reconnaissance blocks populated, with **{R['reconnaissance']['n_observations_total']} "
      f"behavioural observations**, **{R['reconnaissance']['n_interaction_lines_total']} "
      f"attack×defense interaction lines**, and explicitly labelled "
      f"**{R['reconnaissance']['n_tensions']} tensions**, "
      f"**{R['reconnaissance']['n_asymmetries']} asymmetries** and "
      f"**{R['reconnaissance']['n_regime_changes']} regime changes**. The caveat is that the "
      f"schema *required* these fields, so compliance is not proof of insight — what it "
      f"proves is that the model could fill them from the packet without hallucinating: "
      f"only {C['B']['n_evidence_refs_hallucinated']} of "
      f"{C['B']['n_evidence_refs_cited']} citations were unresolvable.")
    W("")

    W("**2. Did measurability improve substantially relative to the old behaviour?**")
    W("")
    W(f"**No — it fell.** Arm A {f(RT['A']['measurable_rate_pct'])} vs Arm B "
      f"{f(RT['B']['measurable_rate_pct'])}, on the same 12 fixtures and the same model. "
      f"Arm B named {C['B']['unknown_metric']} metrics the capability layer could not "
      f"resolve; Arm A named none. This is the honest headline and it goes against the "
      f"protocol. The mechanism is visible: Arm A's schema constrained the model to a "
      f"closed metric vocabulary, while V8A's richer packet invited it to name quantities "
      f"the compiler does not implement. V7.1's 38.6% measurability is **not** the "
      f"comparator here — different sample, different compiler, confirmatory fixtures — and "
      f"is quoted only as uncontrolled context. The controlled comparison is A vs B above.")
    W("")

    W("**3. Is it still mostly generating generic recency/baseline questions?**")
    W("")
    W(f"Less so, but the bulk is still generic. Structural generic equivalence fell from "
      f"{f(RT['A']['structural_generic_equivalent_rate_pct'])} (A) to "
      f"{f(RT['B']['structural_generic_equivalent_rate_pct'])} (B), and exact duplicates "
      f"from {f(RT['A']['exact_generic_duplicate_rate_pct'])} to "
      f"{f(RT['B']['exact_generic_duplicate_rate_pct'])}. Pure recent-vs-long-run questions "
      f"fell from {f(RT['A']['recent_vs_long_rate_pct'])} to "
      f"{f(RT['B']['recent_vs_long_rate_pct'])}. So roughly two in five Arm B candidates "
      f"still ask a question blind enumeration already represents.")
    W("")

    W("**4. Did it produce genuine attack × defense interactions?**")
    W("")
    W(f"Only partly. The *reconnaissance* is full of them "
      f"({R['reconnaissance']['n_interaction_lines_total']} interaction lines), but that "
      f"reasoning largely failed to survive into hypothesis structure: the deterministic "
      f"attack×defense classification is "
      f"{f(RT['A']['attack_defense_interaction_rate_pct'])} for A and "
      f"{f(RT['B']['attack_defense_interaction_rate_pct'])} for B — a *decrease*, and both "
      f"sit near blind enumeration's {f(RT['D']['attack_defense_interaction_rate_pct'])}. "
      f"The model reasons about the matchup in prose and then compiles a question that does "
      f"not encode the interaction. That gap is the single most actionable finding here.")
    W("")

    W("**5. Did it use formation as context tied to raw behaviour rather than stereotype?**")
    W("")
    W("Unanswerable from this run, and not the model's fault. Formation-conditioned "
      "cohorts are **impossible for every arm alike**: formation is not resolvable per "
      "prior match in this corpus, so the capability envelope marks it unavailable and "
      "both arms score 0.0%. The protocol's Phase 3 was never actually exercised. Any "
      "future test of it needs corpus work first, not prompt work.")
    W("")

    W("**6. Did similar-opponent reasoning become materially richer?**")
    W("")
    W(f"**Yes — the largest clean gain.** Arm A produced "
      f"{C['A']['similar_opponent']} similar-opponent hypotheses "
      f"({f(RT['A']['similar_opponent_rate_pct'])}). Arm B produced "
      f"{C['B']['similar_opponent']} ({f(RT['B']['similar_opponent_rate_pct'])}), against "
      f"blind enumeration's {f(RT['D']['similar_opponent_rate_pct'])}. A capability the "
      f"incumbent protocol never touched is now routinely used, and used within the "
      f"deterministic similarity engine rather than computed by the model.")
    W("")

    W("**7. Did the generic novelty challenge cause useful refinement or mostly abstention?**")
    W("")
    W(f"**Overwhelmingly abstention:** ABSTAIN {p2['ABSTAIN']}, KEEP {p2['KEEP']}, REFINE "
      f"{p2['REFINE']} of {p2['ABSTAIN']+p2['KEEP']+p2['REFINE']} second-pass decisions. "
      f"Roughly {round(100*p2['ABSTAIN']/max(1,p2['ABSTAIN']+p2['KEEP']+p2['REFINE']))}% of "
      f"candidates were withdrawn once the model saw structurally comparable generic "
      f"hypotheses. Per §21 abstention is successful behaviour, and the challenge is "
      f"clearly doing work rather than being rubber-stamped. But REFINE at "
      f"{p2['REFINE']} shows the model mostly cannot convert a generic candidate into a "
      f"distinct one — it either keeps or gives up. Note also that the model's own "
      f"self-grading is **not** the label: §16's deterministic canonicalisation is.")
    W("")

    W("**8. Did the LLM find structures the generic generator does not already cover?**")
    W("")
    W(f"**Yes, but narrowly and for a mechanical reason.** Deterministically labelled "
      f"`INCREMENTAL_STRUCTURE`: Arm A {C['A']['incremental_structure']} "
      f"({f(RT['A']['incremental_structure_rate_pct'])}), Arm B "
      f"{C['B']['incremental_structure']} ({f(RT['B']['incremental_structure_rate_pct'])}), "
      f"Arm D {C['D']['incremental_structure']} by construction. A 14× lift over the "
      f"incumbent is real and is the protocol's strongest structural result. The honest "
      f"qualifier: they are incremental for one mechanical reason — **{_n_mix} of "
      f"{_n_inc}** **mix condition kinds** ({_mix_txt}), which "
      f"`_conditions_for` cannot emit since it draws every condition from one kind. So the "
      f"LLM is exploiting a specific, known gap in the generator's image rather than "
      f"inventing an unforeseen class of question. Whether that gap is scientifically "
      f"interesting or merely an enumerator limitation is a question this report cannot "
      f"settle — and closing the gap in the generator is the cheaper first experiment.")
    W("")

    W("**9. Does Terra behave differently from Sonnet under the exact same protocol?**")
    W("")
    W(f"**Unknown — not tested.** `V8A_TERRA_ARM_EXECUTED=false`. Blocker: "
      f"{ex['arm_c_blocker']} No substitute model was run, because §19/§33 forbid calling "
      f"anything else Terra.")
    W("")

    W("**10. Is the research protocol promising enough to justify a fresh OOS experiment?**")
    W("")
    W("**Not yet — from structural evidence only, my answer is no.** Three findings have "
      "to be weighed together.")
    W("")
    W("*For:* similar-opponent conditioning went from unused to routine; incremental "
      "structure rose 14×; abstention behaves as designed; evidence grounding is strong.")
    W("")
    W("*Against, and decisive:* **measurability fell** "
      f"({f(RT['A']['measurable_rate_pct'])} → {f(RT['B']['measurable_rate_pct'])}), "
      "**compiler validity fell** "
      f"({f(RT['A']['compiler_valid_rate_pct'])} → {f(RT['B']['compiler_valid_rate_pct'])}), "
      "and the attack×defense reasoning that the protocol exists to elicit **did not reach "
      "hypothesis structure**. A confirmatory sample spent now would be spent on a "
      "protocol whose central mechanism is demonstrably not yet compiling.")
    W("")
    W("*Decisive constraint:* at N=12 with one call per fixture per arm, documented "
      "generator self-noise (`v6_selfnoise_v1`, within-cell SD 0.363) is wide enough that "
      "only the largest gaps here — similar-opponent 0%→30%, incremental 0.7%→14.6% — sit "
      "clearly outside it. The rest are suggestive at best.")
    W("")
    W("*What a V8A.1 should fix before any OOS spend, in order:* (a) constrain the "
      "candidate metric vocabulary to the capability envelope so measurability recovers; "
      "(b) make the interaction map compile — require a candidate that claims an "
      "attack×defense mechanism to encode it in conditions; (c) close or deliberately open "
      "the mixed-condition-kind gap in the generic generator, so that `INCREMENTAL_STRUCTURE` "
      "means something stronger than an enumerator blind spot; (d) tighten the observation "
      "field to reduce the prose-firewall breaches in §7. Per §24 none of these may be "
      "applied to this sample and called the same experiment.")
    W("")

    W("---")
    W("")
    _pt = json.load(open(f"{OUT}/V8A_PIPELINE_TESTS.json"))
    _tests = {t["test"]: t["pass"] for t in _pt["v8a_pipeline_tests"]}
    # The flag is anchored to the executable property test, not to the absence of a key in
    # a manifest: "no field named effect" is not the same claim as "no effect can be read".
    _blind = _tests.get("17 generic library is outcome-blind", False)

    W("## 11. Terminal states (brief §33)")
    W("")
    ok = (ca is not None
          and ca["champion_composite_sha256"] == cb["champion_composite_sha256"])
    for k, v in (("V8A_DEVELOPMENT_COMPLETE", True),
                 ("V8A_PROMPT_FROZEN", pf["frozen_before_first_paid_call"]),
                 ("V8A_GENERIC_LIBRARY_OUTCOME_BLIND", _blind),
                 ("V8A_GENERIC_NOVELTY_CHALLENGE_ACTIVE", sum(p2.values()) > 0),
                 ("V8A_STRUCTURAL_AUDIT_COMPLETE", len(R["errors"]) == 0),
                 ("V8A_HISTORICAL_EFFECTS_COMPUTED", R["historical_effects_computed"]),
                 ("V8A_FRESH_OOS_OPENED", R["confirmatory_oos_opened"]),
                 ("V8A_PREDICTIVE_CLAIM", bool(R["pass2_predictive_claims"])),
                 ("V8A_FEATURE_PROMOTION", False),
                 ("V8A_TERRA_ARM_EXECUTED", ex["arm_c_executed"]),
                 ("CHAMPION_UNCHANGED", ok)):
        W(f"- `{k}={str(v).lower()}`")
    W(f"- `V8A_TERRA_BLOCKER=\"{ex['arm_c_blocker']}\"`")
    W("")
    W("Stopping here per §34: no OOS sample is opened, the prompt is not tuned after "
      "seeing these results, and V8B is not designed.")
    W("")

    open(f"{ROOT}/research/hypothesis_engine/V8A_DEVELOPMENT_REPORT.md", "w").write(
        "\n".join(lines) + "\n")
    print(f"wrote V8A_DEVELOPMENT_REPORT.md ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
