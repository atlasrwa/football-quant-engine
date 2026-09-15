"""V7 corpus coverage matrix + coverage gate (`v7_coverage_v1`). Phase 25.

Phase 25 forbids silently dropping difficult leagues and then reporting results over an
easier subset. This module MEASURES, from the real corpus, the per-field availability of
every contracted metric across provider x competition x season, and turns that measurement
into a FROZEN, effect-independent gate.

The gate is deliberately a COVERAGE rule, never an effect rule: a metric is admissible only
where the corpus actually carries it at or above a frozen rate, in at least a frozen number
of competitions. Where a metric is admissible in only SOME competitions, the restricted
universe is recorded explicitly on the contract row and reported, never applied silently.

ZERO SPEND. Reads only the local historical corpus. No effects, no p_model, no CHAMPION.
"""
from __future__ import annotations

COVERAGE_VERSION = "v7_coverage_v1"

# ---- frozen coverage gate (Phase 25), set BEFORE any effect is examined ---------------
#: a metric must reach this non-null rate WITHIN a competition to be usable THERE.
MIN_COMPETITION_COVERAGE_RATE = 0.95
#: a metric usable in fewer than this many competitions is not admissible at all.
MIN_ADMISSIBLE_COMPETITIONS = 6          # = every competition in the frozen corpus
#: a metric must also clear this rate over the WHOLE corpus.
MIN_OVERALL_COVERAGE_RATE = 0.95


def _is_present(rec, block: str, key, key_away=None) -> bool:
    """True iff the record carries a usable value for this field binding.

    `base` bindings are (home_field, away_field) pairs and require BOTH sides; `rich`/`extra`
    bindings store a single (home, away) tuple which the loader sets to None when either side
    is missing. NULL is never silently read as ZERO.
    """
    if block == "base":
        b = rec.base or {}
        return b.get(key) is not None and b.get(key_away) is not None
    return (getattr(rec, block, None) or {}).get(key) is not None


def measure(records, bindings: dict) -> dict:
    """Measure provider x competition x season x metric coverage over the real corpus.

    `bindings` maps canonical metric -> (block, key[, away_key]). Returns per-metric overall
    and per-competition/per-season rates plus the frozen gate decision. Purely descriptive of
    AVAILABILITY -- it never reads an outcome or computes an effect.
    """
    n_total = len(records)
    comps = sorted({r.competition for r in records})
    seasons = sorted({f"{r.competition}:{r.season_id}" for r in records})
    comp_n = {c: sum(1 for r in records if r.competition == c) for c in comps}
    season_n = {s: sum(1 for r in records
                       if f"{r.competition}:{r.season_id}" == s) for s in seasons}

    rows = {}
    for metric, bind in sorted(bindings.items()):
        block, key = bind[0], bind[1]
        key_away = bind[2] if len(bind) > 2 else None
        hit_total = 0
        hit_comp = {c: 0 for c in comps}
        hit_season = {s: 0 for s in seasons}
        for r in records:
            if _is_present(r, block, key, key_away):
                hit_total += 1
                hit_comp[r.competition] += 1
                hit_season[f"{r.competition}:{r.season_id}"] += 1
        comp_rate = {c: (hit_comp[c] / comp_n[c] if comp_n[c] else 0.0) for c in comps}
        season_rate = {s: (hit_season[s] / season_n[s] if season_n[s] else 0.0)
                       for s in seasons}
        admissible = sorted([c for c in comps
                             if comp_rate[c] >= MIN_COMPETITION_COVERAGE_RATE])
        excluded = sorted([c for c in comps if c not in admissible])
        overall = hit_total / n_total if n_total else 0.0
        gate_pass = (overall >= MIN_OVERALL_COVERAGE_RATE
                     and len(admissible) >= MIN_ADMISSIBLE_COMPETITIONS)
        rows[metric] = {
            "storage_block": block,
            "field": key if key_away is None else f"{key}|{key_away}",
            "overall_coverage": round(overall, 4),
            "competition_coverage": {c: round(comp_rate[c], 4) for c in comps},
            "season_coverage": {s: round(season_rate[s], 4) for s in seasons},
            "admissible_competitions": admissible,
            "excluded_competitions": excluded,
            "n_admissible_competitions": len(admissible),
            "coverage_gate_pass": gate_pass,
        }
    return {
        "coverage_version": COVERAGE_VERSION,
        "gate": {"min_competition_coverage_rate": MIN_COMPETITION_COVERAGE_RATE,
                 "min_admissible_competitions": MIN_ADMISSIBLE_COMPETITIONS,
                 "min_overall_coverage_rate": MIN_OVERALL_COVERAGE_RATE,
                 "rule": "coverage-only; never a function of any effect",
                 "restricted_universes_reported": True},
        "corpus": {"n_records": n_total, "competitions": comps, "seasons": seasons,
                   "n_by_competition": comp_n, "n_by_season": season_n},
        "metrics": rows,
    }


def version_stamp() -> dict:
    return {"coverage_version": COVERAGE_VERSION,
            "min_competition_coverage_rate": MIN_COMPETITION_COVERAGE_RATE,
            "min_admissible_competitions": MIN_ADMISSIBLE_COMPETITIONS,
            "min_overall_coverage_rate": MIN_OVERALL_COVERAGE_RATE,
            "measured_from_real_corpus": True,
            "depends_on_effect": False,
            "silent_league_dropping_prevented": True}
