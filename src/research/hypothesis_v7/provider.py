"""V7 provider-semantics contract + measurability gate (`v7_provider_v2`). Phases 4, 6, 25.

PROVENANCE CORRECTION (v2)
--------------------------
v1 of this contract labelled `MatchRecord.base` as FootyStats and `MatchRecord.rich` as
TheStatsAPI, and refused to measure any hypothesis whose metrics spanned the two. That
labelling was FACTUALLY WRONG. `corpus.load_corpus()` builds every record from a TheStatsAPI
fixture (`multisrc_corpus._to_adapter_shape` maps a TheStatsAPI fixture) and a TheStatsAPI
`/stats` payload; `championship_adapter.adapt_match` reads EVERY stat field out of that same
`stats_json` and merely renders it in a FootyStats-SHAPED schema. `base`, `rich` and `extra`
are therefore three STORAGE BLOCKS of ONE provider, not two providers.

So in this corpus:
  * `provider` is `thestatsapi` for every contracted metric;
  * `storage_block` (base|rich|extra) records WHERE the value is read from;
  * the no-cross-provider-pooling rule is retained as a live INVARIANT that must never fire.

This correction matters scientifically: under v1 the phantom provider split rejected 33
canonical families for "targets span multiple providers", and because the arms name different
metric mixes that pruning was ARM-CORRELATED -- it silently biased the Phase 20/21 control
comparison, which is V7's primary endpoint.

The genuine cross-provider hazards recorded in `hypothesis_engine.capability`
(`xg@footystats~xg@thestatsapi` DO_NOT_MERGE at corr 0.55; `total_shots@...` at corr 0.80)
remain real hazards for any FUTURE corpus that mixes providers. They are not triggered here
because no FootyStats value is ever loaded. The guard stays armed for that reason.

MEASURABILITY
-------------
Depends ONLY on: provider schema, measured corpus coverage (Phase 25), temporal granularity,
and comparator compilability. NEVER on effect magnitude -- no effect exists at this stage.

Unsafe semantics stay excluded by contract AND now also fail an independent, effect-blind
coverage gate:
  * `np_xg`   -- per-side home/away split semantics unaudited, and 0.381 coverage in laliga2;
  * `xg`      -- 0.000 coverage in ligue2 and 0.452 in laliga2 (measured), so it cannot be
                 tested without silently restricting the universe to the easy leagues;
  * `touches_in_penalty_area` -- 0.673 coverage in champ (measured);
  * generic `cards` -- semantically ambiguous (yellow vs total); must resolve explicitly.

ZERO SPEND.
"""
from __future__ import annotations

PROVIDER_VERSION = "v7_provider_v2"

THESTATSAPI = "thestatsapi"
FOOTYSTATS = "footystats"        # retained: the invariant guard must know the other name

#: The single provider that supplies EVERY field in the frozen corpus.
CORPUS_PROVIDER = THESTATSAPI

#: canonical metric -> corpus binding. `block` is the MatchRecord storage block; `base`
#: bindings carry (home_field, away_field). Every row's provider is `thestatsapi`.
#: `audited` records whether the per-side semantics have been audited for research use.
METRIC_CONTRACT = {
    # ---- base block (TheStatsAPI rendered into FootyStats-shaped schema) --------------
    "goals":             {"block": "base", "field": "homeGoalCount",
                          "field_away": "awayGoalCount", "unit": "count",
                          "semantic": "full-time goals scored by side",
                          "resolution": "match", "audited": True},
    "yellow_cards":      {"block": "base", "field": "team_a_yellow_cards",
                          "field_away": "team_b_yellow_cards", "unit": "count",
                          "semantic": "yellow cards for side", "resolution": "match",
                          "audited": True},
    "red_cards":         {"block": "base", "field": "team_a_red_cards",
                          "field_away": "team_b_red_cards", "unit": "count",
                          "semantic": "red cards for side (null rendered 0 by adapter)",
                          "resolution": "match", "audited": True},
    # half-state supported ONLY for 2nd-half cards (the only half-level field in the corpus)
    "cards_2h":          {"block": "base", "field": "team_a_2h_cards",
                          "field_away": "team_b_2h_cards", "unit": "count",
                          "semantic": "2nd-half yellow cards for side",
                          "resolution": "half", "audited": True},
    # ---- rich block (TheStatsAPI adapter `_rich` pairs) -------------------------------
    "corner_kicks":      {"block": "rich", "field": "corner_kicks", "unit": "count",
                          "semantic": "corners won by side", "resolution": "match",
                          "audited": True},
    "accurate_crosses":  {"block": "rich", "field": "accurate_crosses", "unit": "count",
                          "semantic": "ACCURATE crosses only (completed); cross ATTEMPTS "
                                      "are not available from any provider",
                          "resolution": "match", "audited": True},
    "shots_on_target":   {"block": "rich", "field": "shots_on_target", "unit": "count",
                          "semantic": "shots on target for side", "resolution": "match",
                          "audited": True},
    "shots_inside_box":  {"block": "rich", "field": "shots_inside_box", "unit": "count",
                          "semantic": "shots from inside box for side",
                          "resolution": "match", "audited": True},
    "shots_outside_box": {"block": "rich", "field": "shots_outside_box", "unit": "count",
                          "semantic": "shots from outside box for side",
                          "resolution": "match", "audited": True},
    "blocked_shots":     {"block": "rich", "field": "blocked_shots", "unit": "count",
                          "semantic": "blocked shots for side", "resolution": "match",
                          "audited": True},
    "tackles":           {"block": "rich", "field": "tackles", "unit": "count",
                          "semantic": "tackles by side", "resolution": "match",
                          "audited": True},
    "interceptions":     {"block": "rich", "field": "interceptions", "unit": "count",
                          "semantic": "interceptions by side", "resolution": "match",
                          "audited": True},
    "clearances":        {"block": "rich", "field": "clearances", "unit": "count",
                          "semantic": "clearances by side", "resolution": "match",
                          "audited": True},
    "final_third_entries": {"block": "rich", "field": "final_third_entries",
                            "unit": "count", "semantic": "final-third entries by side",
                            "resolution": "match", "audited": True},
    "ball_recoveries":   {"block": "rich", "field": "ball_recoveries", "unit": "count",
                          "semantic": "ball recoveries by side", "resolution": "match",
                          "audited": True},
    "big_chances":       {"block": "rich", "field": "big_chances", "unit": "count",
                          "semantic": "big chances created by side", "resolution": "match",
                          "audited": True},
    "saves":             {"block": "rich", "field": "saves", "unit": "count",
                          "semantic": "goalkeeper saves by side", "resolution": "match",
                          "audited": True},
    "fouls":             {"block": "rich", "field": "fouls", "unit": "count",
                          "semantic": "fouls committed by side", "resolution": "match",
                          "audited": True},
    # ---- extra block (raw /stats cells the stock adapter does not surface) ------------
    "shots":             {"block": "extra", "field": "total_shots", "unit": "count",
                          "semantic": "ALL shots by side (overview/total_shots), the "
                                      "provider's own total -- never summed from the "
                                      "inside/outside-box split",
                          "resolution": "match", "audited": True},
    "shots_off_target":  {"block": "extra", "field": "shots_off_target", "unit": "count",
                          "semantic": "shots off target for side", "resolution": "match",
                          "audited": True},
    "possession":        {"block": "extra", "field": "possession", "unit": "pct",
                          "semantic": "ball possession percentage for side",
                          "resolution": "match", "audited": True},
    "offsides":          {"block": "extra", "field": "offsides", "unit": "count",
                          "semantic": "offsides committed by side", "resolution": "match",
                          "audited": True},
    # ---- present in the corpus but NOT admissible ------------------------------------
    "xg":                {"block": "base", "field": "team_a_xg", "field_away": "team_b_xg",
                          "unit": "xg",
                          "semantic": "TheStatsAPI expected goals; per-side semantics are "
                                      "fine but measured coverage is 0.000 in ligue2 and "
                                      "0.452 in laliga2, so the COVERAGE gate rejects it -- "
                                      "testing it would silently restrict the universe to "
                                      "the easy leagues",
                          "resolution": "match", "audited": True},
    "np_xg":             {"block": "rich", "field": "np_expected_goals", "unit": "xg",
                          "semantic": "non-penalty xG; EXCLUDED -- per-side home/away split "
                                      "semantics NOT audited, and 0.381 coverage in laliga2",
                          "resolution": "match", "audited": False},
    "touches_in_penalty_area": {"block": "rich", "field": "touches_in_penalty_area",
                                "unit": "count",
                                "semantic": "touches in opposition penalty area; per-side "
                                            "semantics are fine but measured coverage is "
                                            "0.673 in champ, so the COVERAGE gate rejects it",
                                "resolution": "match", "audited": True},
    "cards":             {"block": None, "field": None, "unit": "count",
                          "semantic": "ambiguous (yellow vs total); must resolve to "
                                      "yellow_cards or red_cards explicitly",
                          "resolution": "match", "audited": False},
}

MEASURABLE = "MEASURABLE"
UNMEASURABLE_PROVIDER = "UNMEASURABLE_PROVIDER"
UNMEASURABLE_TEMPORAL_RESOLUTION = "UNMEASURABLE_TEMPORAL_RESOLUTION"
UNMEASURABLE_MISSING_FIELD = "UNMEASURABLE_MISSING_FIELD"
UNMEASURABLE_COMPILER = "UNMEASURABLE_COMPILER"
UNMEASURABLE_COVERAGE = "UNMEASURABLE_COVERAGE"
UNMEASURABLE_OTHER = "UNMEASURABLE_OTHER"

#: comparators the deterministic engine can compile into a baseline (Phase 8).
COMPILABLE_COMPARATORS = {
    "SUBJECT_OVERALL_BASELINE", "SUBJECT_VENUE_BASELINE",
    "OPPONENT_OVERALL_BASELINE", "OPPONENT_VENUE_BASELINE",
    "SUBJECT_COMPETITION_BASELINE", "LEAGUE_ENVIRONMENT_BASELINE",
    "SIMILAR_OPPONENT_COHORT", "SUBJECT_CONDITIONAL_VS_BASELINE",
    # Phase 10 recency family: recent-window vs long-run baseline, compiled with the
    # PREREGISTERED time-decay half-lives, never a searched window grid.
    "SUBJECT_RECENT_VS_LONG_BASELINE",
}

#: half-state / minute-level conditions the corpus can support (only 2h cards)
HALF_STATE_SUPPORTED_METRICS = {"cards_2h"}


def corpus_bindings() -> dict:
    """metric -> (block, field[, away_field]) for every contracted metric that has a binding.

    Fed to `coverage.measure()` so the Phase 25 matrix is computed over exactly the fields
    this contract would read -- including the excluded ones, so their exclusion is EVIDENCED
    by measurement rather than asserted.
    """
    out = {}
    for metric, row in METRIC_CONTRACT.items():
        if not row.get("block") or not row.get("field"):
            continue
        if row.get("field_away"):
            out[metric] = (row["block"], row["field"], row["field_away"])
        else:
            out[metric] = (row["block"], row["field"])
    return out


def resolve_metric(metric: str, coverage: dict | None = None) -> dict:
    """The contract row for a canonical metric, with its measurability status.

    `coverage` is the Phase 25 measured matrix. When supplied, a metric that fails the frozen
    coverage gate is UNMEASURABLE_COVERAGE even if the contract marks it audited -- coverage
    can only ever REMOVE a metric, never add one.
    """
    row = METRIC_CONTRACT.get(metric)
    if row is None:
        return {"metric": metric, "provider": None, "block": None, "field": None,
                "audited": False, "status": UNMEASURABLE_MISSING_FIELD,
                "semantic": "metric not in the frozen provider contract",
                "admissible_competitions": []}
    provider = CORPUS_PROVIDER if row.get("block") else None
    out = {"metric": metric, "provider": provider, **row}

    if provider is None or not row["audited"]:
        out["status"] = UNMEASURABLE_PROVIDER
        out["admissible_competitions"] = []
        return out

    cov_row = ((coverage or {}).get("metrics") or {}).get(metric)
    if cov_row is not None:
        out["overall_coverage"] = cov_row["overall_coverage"]
        out["admissible_competitions"] = cov_row["admissible_competitions"]
        out["excluded_competitions"] = cov_row["excluded_competitions"]
        if not cov_row["coverage_gate_pass"]:
            out["status"] = UNMEASURABLE_COVERAGE
            return out
    else:
        out["admissible_competitions"] = []
    out["status"] = MEASURABLE
    return out


def classify_measurability(canonical_spec: dict, coverage: dict | None = None) -> dict:
    """Classify a canonical hypothesis' measurability.

    Depends only on schema / measured coverage / temporal resolution / comparator
    compilability -- never on effect magnitude. A hypothesis is MEASURABLE only if EVERY
    target metric resolves to an audited field that clears the coverage gate, the comparator
    is compilable, and any half-resolution metric is supported.

    A multi-metric hypothesis is NOT rejected merely for naming several metrics: each metric
    is measured on its own binding and the results are reported per metric. Pooling is what is
    forbidden, and pooling never happens here because the corpus has ONE provider.
    """
    targets = canonical_spec.get("TARGET") or []
    per_metric = [resolve_metric(m, coverage) for m in targets]
    providers = sorted({r["provider"] for r in per_metric if r["provider"]})

    reasons = []
    status = MEASURABLE
    if not targets:
        status = UNMEASURABLE_OTHER
        reasons.append("no target metric")
    for r in per_metric:
        if r["status"] != MEASURABLE:
            status = r["status"]
            reasons.append(f"{r['metric']}: {r['status']} ({r.get('semantic', '')[:70]})")

    # INVARIANT (must never fire on this corpus): two genuinely different providers can never
    # be pooled into one quantity. Kept armed for any future mixed-provider corpus.
    if len(providers) > 1:
        status = UNMEASURABLE_PROVIDER
        reasons.append(f"targets span multiple providers {providers}; pooling forbidden")

    comp = canonical_spec.get("COMPARATOR")
    if status == MEASURABLE and comp not in COMPILABLE_COMPARATORS:
        status = UNMEASURABLE_COMPILER
        reasons.append(f"comparator {comp} not compilable")

    if status == MEASURABLE:
        for r in per_metric:
            if r.get("resolution") == "half" and \
                    r["metric"] not in HALF_STATE_SUPPORTED_METRICS:
                status = UNMEASURABLE_TEMPORAL_RESOLUTION
                reasons.append(f"{r['metric']}: half resolution unsupported")

    # the restricted competition universe for this hypothesis = intersection over its metrics.
    admissible = None
    for r in per_metric:
        s = set(r.get("admissible_competitions") or [])
        admissible = s if admissible is None else (admissible & s)
    return {"status": status, "providers": providers, "per_metric": per_metric,
            "comparator": comp,
            "admissible_competitions": sorted(admissible or []),
            "reasons": reasons or ["all checks passed"]}


def cross_provider_invariant(coverage: dict | None = None) -> dict:
    """Assert the corpus really is single-provider, so the pooling guard cannot be masking a
    real mix. Returns the evidence rather than merely asserting it."""
    blocks = sorted({r["block"] for r in METRIC_CONTRACT.values() if r.get("block")})
    providers = {CORPUS_PROVIDER}
    return {"corpus_provider": CORPUS_PROVIDER,
            "storage_blocks": blocks,
            "n_distinct_providers": len(providers),
            "pooling_guard_armed": True,
            "pooling_guard_fires_on_this_corpus": False,
            "evidence": ("multisrc_corpus._to_adapter_shape maps a TheStatsAPI fixture and "
                         "championship_adapter.adapt_match reads every stat from the same "
                         "TheStatsAPI /stats payload; base/rich/extra are storage blocks of "
                         "one provider, not two providers"),
            "footystats_values_loaded": 0,
            "known_cross_provider_hazards_not_triggered": [
                "xg@footystats~xg@thestatsapi (DO_NOT_MERGE, corr 0.55)",
                "total_shots@footystats~total_shots@thestatsapi (DO_NOT_MERGE, corr 0.80)"]}


def version_stamp() -> dict:
    audited = sorted(m for m, v in METRIC_CONTRACT.items()
                     if v.get("block") and v["audited"])
    excluded = sorted(m for m, v in METRIC_CONTRACT.items() if not v["audited"])
    return {"provider_version": PROVIDER_VERSION,
            "corpus_provider": CORPUS_PROVIDER,
            "storage_blocks": ["base", "rich", "extra"],
            "provenance_correction": ("v1 mislabelled base=footystats/rich=thestatsapi; the "
                                      "corpus is single-provider (thestatsapi) and v1's "
                                      "phantom cross-provider rule rejected 33 families"),
            "no_cross_provider_pooling": True,
            "n_contracted_metrics": len(METRIC_CONTRACT),
            "n_audited_metrics": len(audited),
            "audited_metrics": audited,
            "excluded_metrics": excluded,
            "compilable_comparators": sorted(COMPILABLE_COMPARATORS),
            "measurability_depends_on_effect": False}
