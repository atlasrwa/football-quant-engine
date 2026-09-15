"""V7 canonicalization + deduplication (`v7_canonical_v1`). Phases 2-3. STRUCTURAL ONLY.

Two generated hypotheses can express the SAME underlying statistical question in different
words. This module maps each hypothesis to a canonical statistical specification derived
DETERMINISTICALLY from its STRUCTURAL fields only -- never from wording, never from an LLM
judgement, never from any historical outcome. `canonical_hypothesis_id = SHA256(canonical_spec)`.

If equivalence cannot be established structurally, the hypotheses are KEPT SEPARATE rather
than merged subjectively (a NEAR_EQUIVALENT_NOT_MERGED is never collapsed).

Deduplication classes:
  * EXACT_DUPLICATE            same canonical spec AND same originating response.
  * STRUCTURAL_DUPLICATE       same canonical spec, different originating response/fixture/arm.
  * NEAR_EQUIVALENT_NOT_MERGED distinct canonical specs (kept separate; recorded for audit).

Origin multiplicity (how many raw hypotheses map to one canonical id) is preserved as
METADATA ONLY and must never inflate statistical evidence: one canonical statistical question
= one hypothesis-family identity for confirmatory accounting.

ZERO SPEND.
"""
from __future__ import annotations

import hashlib
import json

CANONICAL_VERSION = "v7_canonical_v1"

# Canonical target-metric vocabulary. Structural synonyms the model emitted are normalized to
# a single canonical token. This mapping is FROZEN and outcome-independent; it encodes only
# "these strings denote the same measured quantity", never anything about effects.
METRIC_SYNONYMS = {
    "total_shots": "shots", "shots": "shots",
    "shots_on_target": "shots_on_target", "sot": "shots_on_target",
    "shots_inside_box": "shots_inside_box", "shots_outside_box": "shots_outside_box",
    "blocked_shots": "blocked_shots",
    "touches_in_box": "touches_in_penalty_area",
    "touches_in_penalty_area": "touches_in_penalty_area",
    "xg": "xg", "expected_goals": "xg", "goals": "goals",
    "np_expected_goals": "np_xg", "npxg": "np_xg",
    "corners": "corner_kicks", "corner_kicks": "corner_kicks",
    "accurate_crosses": "accurate_crosses", "crosses": "accurate_crosses",
    "tackles": "tackles", "interceptions": "interceptions", "clearances": "clearances",
    "fouls": "fouls", "yellow_cards": "yellow_cards", "red_cards": "red_cards",
    "cards": "cards", "possession": "possession",
    "big_chances": "big_chances", "final_third_entries": "final_third_entries",
    "ball_recoveries": "ball_recoveries",
}


def _norm_metric(m):
    if m is None:
        return None
    key = str(m).strip().lower()
    return METRIC_SYNONYMS.get(key, key)


def canonical_spec(spec: dict) -> dict:
    """The deterministic canonical statistical specification for a hypothesis.

    Built ONLY from structural fields, order-normalized so wording/order cannot create a
    spurious distinction. Similarity/formation/half-state conditions are surfaced as explicit
    canonical slots so a reader sees the full statistical question.
    """
    metrics = sorted({_norm_metric(m) for m in (spec.get("target_metrics") or [])
                      if m is not None})
    conditions = spec.get("conditions") or []
    # conditions are structured tokens; normalize to sorted, lowercased, de-duplicated strings
    cond_norm = sorted({json.dumps(c, sort_keys=True) if isinstance(c, (dict, list))
                        else str(c).strip().lower() for c in conditions})
    caps = sorted({str(c).strip().lower()
                   for c in (spec.get("required_capabilities") or [])})
    # similarity dimensions, if the hypothesis is a similar-opponent one, are carried in
    # conditions/capabilities; we surface a dedicated slot deterministically.
    similarity_dims = sorted({c for c in caps if "similar" in c or "profile" in c})
    return {
        "TARGET": metrics,
        "SUBJECT": (spec.get("subject") or "").strip().upper() or None,
        "SIDE": (spec.get("side") or "").strip().upper() or None,
        "COMPARATOR": (spec.get("comparison") or "").strip().upper() or None,
        "CONDITIONS": cond_norm,
        "TIME_SCOPE": (spec.get("window") or "").strip().upper() or None,
        "SIMILARITY_DIMENSIONS": similarity_dims,
        "FAMILY": (spec.get("research_family") or "").strip().upper() or None,
        "PROVIDER_REQUIREMENTS": caps,
    }


def canonical_id(spec: dict) -> str:
    cspec = canonical_spec(spec)
    blob = json.dumps(cspec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def canonicalize_universe(universe: dict) -> dict:
    """Attach a canonical spec + canonical_hypothesis_id to every universe entry."""
    rows = []
    for e in universe["hypotheses"]:
        cspec = canonical_spec(e["spec"])
        cid = canonical_id(e["spec"])
        rows.append({"v7_hypothesis_id": e["v7_hypothesis_id"], "arm": e["arm"],
                     "originating_fixture": e["originating_fixture"],
                     "response_seq": e["response_seq"],
                     "canonical_hypothesis_id": cid, "canonical_spec": cspec})
    return {"canonical_version": CANONICAL_VERSION,
            "rule": ("canonical_hypothesis_id = SHA256(canonical_spec); canonical_spec is a "
                     "deterministic function of STRUCTURAL fields only (metrics normalized "
                     "via a frozen synonym map; subject/side/comparator/window/family/"
                     "conditions/capabilities order-normalized). No wording, no LLM, no "
                     "outcome. Distinct canonical ids are never merged."),
            "n_rows": len(rows), "rows": rows}


def deduplicate(canon: dict) -> dict:
    """Deterministic dedup. One canonical id = one hypothesis-family; origins are metadata.

    A canonical-family key also records arm membership so the Base-vs-Research control (Phase
    20/21) can be matched on canonical statistical question rather than raw count.
    """
    families = {}
    for r in canon["rows"]:
        cid = r["canonical_hypothesis_id"]
        fam = families.setdefault(cid, {
            "canonical_hypothesis_id": cid, "canonical_spec": r["canonical_spec"],
            "origins": [], "arms": set()})
        fam["origins"].append({"v7_hypothesis_id": r["v7_hypothesis_id"], "arm": r["arm"],
                               "originating_fixture": r["originating_fixture"],
                               "response_seq": r["response_seq"]})
        fam["arms"].add(r["arm"])

    dup_classes = []
    for cid, fam in families.items():
        seen_response = {}
        for o in fam["origins"]:
            key = (o["originating_fixture"], o["response_seq"])
            if key in seen_response:
                dup_classes.append({"canonical_hypothesis_id": cid,
                                    "v7_hypothesis_id": o["v7_hypothesis_id"],
                                    "class": "EXACT_DUPLICATE",
                                    "same_response_as": seen_response[key]})
            elif len(fam["origins"]) > 1:
                dup_classes.append({"canonical_hypothesis_id": cid,
                                    "v7_hypothesis_id": o["v7_hypothesis_id"],
                                    "class": "STRUCTURAL_DUPLICATE"})
            seen_response[key] = o["v7_hypothesis_id"]

    fam_out = []
    for cid, fam in sorted(families.items()):
        fam_out.append({
            "canonical_hypothesis_id": cid,
            "canonical_spec": fam["canonical_spec"],
            "n_origins": len(fam["origins"]),
            "arms": sorted(fam["arms"]),
            "arm_membership": ("BOTH" if len(fam["arms"]) == 2
                               else next(iter(fam["arms"]))),
            "origins": sorted(fam["origins"], key=lambda o: o["response_seq"])})

    n_base_only = sum(1 for f in fam_out if f["arm_membership"] == "base")
    n_research_only = sum(1 for f in fam_out if f["arm_membership"] == "research")
    n_both = sum(1 for f in fam_out if f["arm_membership"] == "BOTH")
    return {"dedup_version": CANONICAL_VERSION,
            "policy": ("one canonical statistical question -> one hypothesis-family identity "
                       "for confirmatory accounting; origin multiplicity is metadata only "
                       "and never increases statistical evidence."),
            "n_raw_qualified": canon["n_rows"],
            "n_canonical_families": len(fam_out),
            "n_families_base_only": n_base_only,
            "n_families_research_only": n_research_only,
            "n_families_both_arms": n_both,
            "duplicate_classifications": dup_classes,
            "families": fam_out}


def version_stamp() -> dict:
    return {"canonical_version": CANONICAL_VERSION, "structural_only": True,
            "uses_llm": False, "reads_outcomes": False,
            "metric_synonyms_frozen": len(METRIC_SYNONYMS)}
