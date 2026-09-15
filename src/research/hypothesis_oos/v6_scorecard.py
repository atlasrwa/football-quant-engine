"""Per-hypothesis and per-response scorecards (`v6_scorecard_v1`). §19, §20.

    "Do not collapse failures too early. This should make later diagnostics possible
     without reinterpretation."

THE ZERO/UNMEASURED DISTINCTION, WHICH V5A.2 COULD NOT EXPRESS
---------------------------------------------------------------
`v5a2_evaluator.score_response` returns `_blank_score()` -- a dict of ZEROS -- on a
whole-response failure, and then returns early. So a research arm whose two responses were
rejected whole showed `n_valid_refs = 0`, `compilability = 0`, `opponent_profile_use = 0`.
Its own execution report had to spend a paragraph saying so:

    "Any table that prints research-arm zeros here is printing a placeholder."

A number whose meaning has to be supplied by a footnote is not a measurement. Every count
in this module is therefore paired with a `measured` flag, and every rate is `None` rather
than `0.0` when its denominator is empty. `unmeasured_keys()` lists what was not measured,
so an aggregation layer can refuse to pool a placeholder instead of averaging it in.

WHAT IS COUNTED AND WHAT IS DELIBERATELY NOT
---------------------------------------------
Counted: every §19 boolean, every §8 class, grounding, compiler, conditioning, comparator,
evidence-family coverage (§13) and the normalized intent set (§9, §20).

NOT counted, anywhere, in anything: `priority`. §23 -- "Do not treat LLM confidence as
data". It is retained in the schema because the workflow reads it as a research-budget
hint, and it is excluded from every scientific metric here, from `_intent_key`'s
redundancy relation in `validator_v5`, and from `v6_repeatability`'s normalization.
`test_priority_is_never_a_scientific_metric` asserts the exclusion holds across all three.

ZERO SPEND.
"""
from __future__ import annotations

from src.research.hypothesis_engine import capability
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v6_classes as K
from src.research.hypothesis_oos import v6_conditioning as CD
from src.research.hypothesis_oos import v6_qualified as Q

SCORECARD_VERSION = "v6_scorecard_v1"

#: §13's football-research families, tracked for CONCENTRATION and REDUNDANCY, never
#: rewarded. "Track but do not automatically reward diversity." A model that asks twelve
#: good corner questions is not worse than one that asks twelve mediocre questions across
#: twelve metrics, and nothing here decides otherwise -- the numbers are reported and the
#: §25 gate does not read them.
METRIC_FAMILIES = {
    "shots": ("total_shots", "shots_on_target", "shots_off_target", "shots_inside_box",
              "shots_outside_box", "blocked_shots"),
    "chance_quality": ("big_chances", "xg", "npxg", "goals"),
    "set_pieces": ("corners", "throw_ins", "offsides"),
    "crossing": ("accurate_crosses",),
    "territory": ("possession", "attacks", "dangerous_attacks", "final_third_entries",
                  "touches_in_box"),
    "defensive_actions": ("tackles", "interceptions", "clearances", "saves"),
    "discipline": ("fouls", "yellow_cards", "red_cards", "total_bookings"),
}


def metric_family(metric: str) -> str:
    for fam, members in sorted(METRIC_FAMILIES.items()):
        if metric in members:
            return fam
    return "OTHER"


def _ref_kind(ref: str) -> str:
    return ref.split(":")[0] if ":" in ref else "OTHER"


def score_hypothesis(adj) -> dict:
    """The §19 scorecard for one adjudicated hypothesis. Annotates `qualified` in place."""
    Q.annotate(adj)
    sc = adj.scorecard
    return {
        "index": adj.index,
        "hypothesis_id": adj.hypothesis_id,
        "outcome_class": adj.outcome_class,
        "schema_valid": sc.get("schema_valid"),
        "numeric_contract_valid": sc.get("numeric_contract_valid"),
        "evidence_grounded": sc.get("evidence_grounded"),
        "evidence_refs_valid": sc.get("evidence_refs_valid"),
        "availability_valid": sc.get("availability_valid"),
        "firewall_valid": sc.get("firewall_valid"),
        "comparator_valid": sc.get("comparator_valid"),
        "nondegenerate": sc.get("nondegenerate"),
        "nonredundant": sc.get("nonredundant"),
        "redundant": sc.get("redundant"),
        "compiler_valid": sc.get("compiler_valid"),
        "contextually_supported": sc.get("contextually_supported"),
        "qualified": sc.get("qualified"),
        "qualified_conjuncts": sc.get("qualified_conjuncts"),
        "evidence_specific": Q.evidence_specific(adj),
        "abstaining": adj.abstaining,
        "n_refs": adj.n_refs, "n_valid_refs": adj.n_valid_refs,
        "n_fabricated_refs": adj.n_fabricated_refs,
        "conditioning_class": adj.conditioning.get("conditioning_class"),
        "absorption_class": adj.comparator.get("absorption_class"),
        "unconditioned_self_comparison":
            adj.comparator.get("unconditioned_self_comparison"),
        "reasons": {k: list(v) for k, v in sorted(adj.reasons.items())},
    }


def unmeasured_keys(rows: list) -> list:
    """Scorecard keys that were `None` for at least one hypothesis. §20's honesty check."""
    keys = set()
    for r in rows:
        for k, v in r.items():
            if v is None and k not in ("qualified_conjuncts", "conditioning_class",
                                       "absorption_class"):
                keys.add(k)
    return sorted(keys)


def score_response(res, packet, raw_payload=None) -> dict:
    """The §20 response scorecard. `res` is a `validator_v5.ResponseAdjudication`.

    A response-fatal call produces a scorecard whose every measurement is `None`, with
    `measured=False` and the counts it CAN honestly state (how many hypotheses were
    proposed, if that is even recoverable). It never produces zeros.
    """
    from src.research.hypothesis_oos import v6_repeatability as RP

    fatal = res.fatal
    out = {
        "scorecard_version": SCORECARD_VERSION,
        "response_class": res.response_class,
        "response_fatal": fatal,
        "response_fatal_reasons": list(res.reasons),
        "measured": not fatal,
        "n_proposed": res.n_proposed,
        "n_recoverable": len(res.hypotheses),
        "n_apparatus_defects": len(res.apparatus_defects),
        "apparatus_defects": list(res.apparatus_defects),
        "fixture_id": (packet or {}).get("fixture_id"),
        "packet_hash": (packet or {}).get("packet_hash"),
    }
    blank_counts = ("n_qualified", "n_evidence_specific_qualified", "n_abstentions",
                    "n_abstentions_with_refs", "n_refs", "n_valid_refs",
                    "n_fabricated_refs", "n_nonabstaining", "n_compiler_valid",
                    "n_meaningful_interactions", "n_interactions", "n_redundant",
                    "n_degenerate", "n_absorbed", "n_unconditioned_self_comparison")
    if fatal:
        for k in blank_counts:
            out[k] = None
        out["qualified_rate"] = None
        out["class_counts"] = None
        out["per_hypothesis"] = []
        out["unmeasured"] = ["ALL -- response was fatal, nothing was measured"]
        out["class_counts_by_class"] = {c: (None) for c in K.HYPOTHESIS_CLASSES}
        out["conditioning_classes"] = None
        out["metric_families"] = None
        out["ref_kinds"] = None
        out["dimension_uses"] = None
        out["normalized_intents"] = None
        return out

    rows = [score_hypothesis(a) for a in res.hypotheses]
    valid_ids = E.resolve_evidence_ids(packet)

    counts = {c: 0 for c in K.HYPOTHESIS_CLASSES}
    for a in res.hypotheses:
        counts[a.outcome_class] = counts.get(a.outcome_class, 0) + 1

    cond_classes = {c: 0 for c in CD.CONDITIONING_CLASSES}
    fams, ref_kinds, target_metrics = {}, {}, {}
    uses = {name: {"used": 0, "supported": 0, "exposed": None}
            for name in CD.USE_DIMENSIONS}

    n_abst = n_abst_refs = n_refs = n_valid = n_fab = 0
    n_qual = n_evspec = n_nonabst = n_comp_ok = 0
    n_inter = n_meaning = n_redundant = n_degen = n_absorbed = n_selfcmp = 0

    for a, r in zip(res.hypotheses, rows):
        n_refs += a.n_refs
        n_valid += a.n_valid_refs
        n_fab += a.n_fabricated_refs
        if a.abstaining:
            n_abst += 1
            if a.n_valid_refs:
                n_abst_refs += 1
        else:
            n_nonabst += 1
        if r["qualified"]:
            n_qual += 1
        if r["evidence_specific"]:
            n_evspec += 1
        if a.scorecard.get("compiler_valid") is True:
            n_comp_ok += 1
        if a.scorecard.get("redundant"):
            n_redundant += 1
        if a.scorecard.get("nondegenerate") is False:
            n_degen += 1
        if a.comparator.get("absorbed"):
            n_absorbed += 1
        if a.comparator.get("unconditioned_self_comparison"):
            n_selfcmp += 1
        cc = a.conditioning.get("conditioning_class")
        if cc:
            cond_classes[cc] = cond_classes.get(cc, 0) + 1
        if a.conditioning.get("is_interaction"):
            n_inter += 1
            if a.conditioning.get("is_meaningful_interaction"):
                n_meaning += 1
        for name, rec in (a.conditioning.get("dimension_uses") or {}).items():
            if rec.get("used"):
                uses[name]["used"] += 1
                if rec.get("supported_by_refs") is True:
                    uses[name]["supported"] += 1
            uses[name]["exposed"] = rec.get("exposed")

    # Diversity is read off EVERY recovered hypothesis, accepted or rejected. What the
    # model chose to ask about is a fact about the model, and discarding it for rejected
    # hypotheses is exactly how V5A.2 ended up with research-arm diversity counts that were
    # `_blank_score` placeholders rather than measurements (§13, §20).
    for a in res.hypotheses:
        h = a.hypothesis or {}
        for m in h.get("target_metrics") or []:
            if isinstance(m, str):
                target_metrics[m] = target_metrics.get(m, 0) + 1
                fam = metric_family(m)
                fams[fam] = fams.get(fam, 0) + 1
        for ref in h.get("evidence_refs") or []:
            if isinstance(ref, str):
                kind = _ref_kind(ref)
                ref_kinds[kind] = ref_kinds.get(kind, 0) + 1

    out.update({
        "n_qualified": n_qual,
        "n_evidence_specific_qualified": n_evspec,
        "n_nonabstaining": n_nonabst,
        "n_abstentions": n_abst,
        "n_abstentions_with_refs": n_abst_refs,
        "n_refs": n_refs, "n_valid_refs": n_valid, "n_fabricated_refs": n_fab,
        "n_compiler_valid": n_comp_ok,
        "n_interactions": n_inter, "n_meaningful_interactions": n_meaning,
        "n_redundant": n_redundant, "n_degenerate": n_degen,
        "n_absorbed": n_absorbed,
        "n_unconditioned_self_comparison": n_selfcmp,
        # THE PRIMARY UNIT. `None`, never 0.0, when the model abstained on everything --
        # a rate with an empty denominator is not zero, it is absent.
        "qualified_rate": (n_qual / n_nonabst) if n_nonabst else None,
        "evidence_specific_qualified_rate": (n_evspec / n_nonabst) if n_nonabst else None,
        "valid_evidence_reference_rate": (n_valid / n_refs) if n_refs else None,
        "fabricated_evidence_rate": (n_fab / n_refs) if n_refs else None,
        "abstention_rate": (n_abst / len(rows)) if rows else None,
        "grounded_abstention_rate": (n_abst_refs / n_abst) if n_abst else None,
        "meaningful_interaction_rate": (n_meaning / n_inter) if n_inter else None,
        "redundancy_rate": (n_redundant / len(rows)) if rows else None,
        "discipline_violation_rate": (
            sum(1 for a in res.hypotheses
                if a.outcome_class in (K.MODEL_FIREWALL_VIOLATION,
                                       K.MODEL_NUMERIC_CONTRACT_VIOLATION,
                                       K.MODEL_GROUNDING_VIOLATION,
                                       K.MODEL_AVAILABILITY_VIOLATION)) / len(rows))
            if rows else None,
        "class_counts": counts,
        "conditioning_classes": cond_classes,
        "metric_families": dict(sorted(fams.items())),
        "target_metrics": dict(sorted(target_metrics.items())),
        "ref_kinds": dict(sorted(ref_kinds.items())),
        "dimension_uses": {k: uses[k] for k in sorted(uses)},
        "evidence_family_coverage": len(fams),
        "metric_concentration": _concentration(fams),
        "normalized_intents": RP.normalized_intents(res),
        "per_hypothesis": rows,
        "unmeasured": unmeasured_keys(rows),
    })
    return out


def _concentration(fams: dict) -> float:
    """Herfindahl concentration of research families (§13). 1.0 = every hypothesis in one
    family. Reported, never rewarded and never penalised -- §13 asks for it as a FINDING."""
    total = sum(fams.values())
    if not total:
        return 0.0
    return round(sum((v / total) ** 2 for v in fams.values()), 6)


def version_stamp() -> dict:
    return {"scorecard_version": SCORECARD_VERSION,
            "metric_families": {k: list(v) for k, v in sorted(METRIC_FAMILIES.items())},
            "n_capability_metrics": len(capability.metric_names()),
            "priority_used_in_any_metric": False,
            "zeros_never_substituted_for_unmeasured": True,
            **Q.version_stamp()}
