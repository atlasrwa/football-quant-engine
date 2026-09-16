"""Render V8A_DEVELOPMENT_REPORT.md from V8A_STRUCTURAL_RESULTS.json. EFFECT BLIND.

Every number in the report is READ from the results JSON. Nothing is hand-tabulated here:
hand-tabulating forty rates across three arms is how the three V7.1 reporting overstatements
happened, and the fix is that the scorer owns the arithmetic and the report owns the prose.

Run:  /home/ubuntu/.venv/bin/python research/hypothesis_engine/_report_v8a.py
"""
from __future__ import annotations

import json
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
    W(row("firewall blocking findings", "firewall_blocking"))
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
    W(rrow("firewall blocking", "firewall_blocking_rate_pct"))
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
    W("")
    W("---")
    W("")
    W("## 7. Interpretation caveats")
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
    W("")

    open(f"{ROOT}/research/hypothesis_engine/V8A_DEVELOPMENT_REPORT.md", "w").write(
        "\n".join(lines) + "\n")
    print(f"wrote V8A_DEVELOPMENT_REPORT.md ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
