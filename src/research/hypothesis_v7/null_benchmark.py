"""V7 deterministic null benchmark -- Phase 20 Control B (`v7_null_v1`).

Phase 20 forbids testing V6.1 hypotheses in isolation and calling any surviving relationship
evidence of LLM value. V7 therefore needs a comparator. Control A (BASE arm vs RESEARCH arm)
is the preferred design, but it was proven INFEASIBLE as a matched endpoint before any OOS ran:
across the 10 V6.1 fixtures not one canonical specification was produced by both arms
(`n_families_both_arms = 0`), leaving 5 matched cells over 3 fixtures. So Control B is built.

WHAT THIS IS
------------
Generic football research hypotheses enumerated DETERMINISTICALLY from the same canonical
grammar the V6.1 hypotheses inhabit, with NO LLM and NO fixture-specific reasoning. They are
then pushed through the IDENTICAL downstream pipeline -- canonicalization, deduplication, the
measurability gate, support rules, folds, outcome classes -- so the ONLY difference between
the two origins is where the question came from.

If a V6.1 hypothesis survives OOS at no better a rate than a mechanically enumerated one, the
LLM added no football information, however well-formed its questions were.

FAIRNESS CONSTRAINTS (frozen before any OOS)
--------------------------------------------
* The null draws from the FULL contracted metric vocabulary, including the metrics that fail
  the coverage gate. It faces exactly the same measurability hazards as V6.1; it is not handed
  a pre-cleaned vocabulary.
* Slot values are restricted to those V6.1 actually inhabits (subject, side, comparator,
  time-scope, target-set size), so the null cannot lose on grammar it was never going to use.
* Target-set sizes are drawn across the same 1..5 range, because a null of single-metric
  hypotheses would clear the measurability gate more easily than V6.1's typical 3-metric ones.
* Randomness is a SHA-256 counter stream with a frozen seed -- never Python `hash()`, never
  `random` -- so the enumeration is byte-identical under any PYTHONHASHSEED.

ZERO SPEND. No LLM. No effects. No OOS outcomes.
"""
from __future__ import annotations

import hashlib

NULL_VERSION = "v7_null_v2"

#: frozen seed for the deterministic enumeration stream.
NULL_SEED = "V7_DETERMINISTIC_NULL_BENCHMARK_v2"

#: Pool sizes, frozen. The UNIFORM pool serves endpoint A (end-to-end yield and the
#: descriptive data-compatibility comparison); the MATCHED pool serves endpoint B, where a
#: large pool buys MATCHING FLEXIBILITY only -- weights still sum to 1 per LLM family, so the
#: pool size can never become nominal sample size (see matching.py).
NULL_POOL_SIZE = 2000              # UNIFORM pool (endpoint A)
NULL_MATCHED_POOL_SIZE = 24000     # MARGINAL-matched pool (endpoint B)

#: Slot vocabularies, restricted to the values the V6.1 canonical families actually inhabit
#: (measured from V7_DEDUPLICATION.json, a structural fact -- no outcome consulted).
NULL_SUBJECTS = ("HOME_TEAM", "AWAY_TEAM")
NULL_SIDES = ("FOR", "AGAINST")
NULL_COMPARATORS = ("SUBJECT_OVERALL_BASELINE", "SUBJECT_RECENT_VS_LONG_BASELINE",
                    "SUBJECT_VENUE_BASELINE")
NULL_TIME_SCOPES = ("ALL_PRIOR", "W5", "W10")
NULL_TARGET_SET_SIZES = (1, 2, 3, 4, 5)

# ---- v2 REPAIR: structured conditions drawn from the SHARED vocabulary ----------------
# v1 emitted plain-string conditions ("venue=home") and ALWAYS set `required_capabilities`
# to []. Three consequences, all generation defects rather than inconveniences:
#
#   1. `SIMILARITY_DIMENSIONS` is derived from capabilities containing "similar"/"profile",
#      so NO v1 null hypothesis could ever be a similar-opponent hypothesis. The LLM universe
#      has 33/132. That is an EMPTY CELL, not an imbalance -- a quarter of the LLM universe,
#      including the OPPONENT_PROFILE_INTERACTION family, had no possible comparator.
#   2. `PROVIDER_REQUIREMENTS` was never inhabited at all.
#   3. The canonicalizer normalizes dict conditions via json.dumps(sort_keys=True) and string
#      conditions via str().lower(), so a v1 string condition could NEVER collide with an LLM
#      structured condition -- the condition slot was comparable in count only, never in kind.
#
# v2 emits the SAME structured condition tokens the V6.1 families use, measured from
# V7_DEDUPLICATION.json (structure only -- no outcome was consulted):
#   {"dimension": "historical_venue_conditioning", "value": HOME|AWAY}
#   {"dimension": "opponent_profile", "axis": <axis>, "value": HIGH|MID|LOW}
NULL_VENUE_VALUES = ("HOME", "AWAY")
NULL_PROFILE_AXES = ("goals_against", "goals_for",
                     "shots_on_target_against", "shots_on_target_for")
NULL_PROFILE_VALUES = ("HIGH", "MID", "LOW")

#: condition KIND, drawn per hypothesis. NONE / venue conditioning / opponent-profile
#: conditioning -- matching the three shapes the LLM universe exhibits.
NULL_CONDITION_KINDS = ("NONE", "VENUE", "OPPONENT_PROFILE")

#: The ONE capability relationship that is deterministic in the V6.1 universe: the
#: `opponent_profile` capability appears if and only if an opponent_profile condition is
#: present (33 of 33, zero false positives, zero false negatives). The other capability
#: tokens are NOT structurally derivable -- `xg` co-occurs with an xg target only 53/63 of
#: the time, `target_fixture_venue_context` never co-occurs with a venue comparator (0/30),
#: and `match_level_observations` appears in only 65/132 -- so they are LLM self-description
#: rather than properties of the statistical question. v2 reproduces the deterministic rule
#: and does not fabricate the others; the covariate layer excludes raw capability lists for
#: exactly this reason (see `covariates.py`).
CAP_OPPONENT_PROFILE = "opponent_profile"

#: metric -> research family, so the null gets the same multiplicity-family treatment.
METRIC_FAMILY = {
    "goals": "ATTACK_QUALITY", "xg": "ATTACK_QUALITY", "np_xg": "ATTACK_QUALITY",
    "big_chances": "ATTACK_QUALITY", "shots_inside_box": "ATTACK_QUALITY",
    "shots": "ATTACK_VOLUME", "shots_on_target": "ATTACK_VOLUME",
    "shots_off_target": "ATTACK_VOLUME", "shots_outside_box": "ATTACK_VOLUME",
    "corner_kicks": "SET_PIECE_GENERATION", "accurate_crosses": "SET_PIECE_GENERATION",
    "possession": "TEMPO_AND_TERRITORY", "final_third_entries": "TEMPO_AND_TERRITORY",
    "touches_in_penalty_area": "TEMPO_AND_TERRITORY", "offsides": "TEMPO_AND_TERRITORY",
    "tackles": "DEFENSIVE_SUPPRESSION", "interceptions": "DEFENSIVE_SUPPRESSION",
    "clearances": "DEFENSIVE_SUPPRESSION", "blocked_shots": "DEFENSIVE_SUPPRESSION",
    "ball_recoveries": "DEFENSIVE_SUPPRESSION", "saves": "DEFENSIVE_CONCESSION",
    "fouls": "DISCIPLINE", "yellow_cards": "DISCIPLINE", "red_cards": "DISCIPLINE",
    "cards_2h": "DISCIPLINE",
}


# ---- v2: TWO frozen control pools, one per endpoint ----------------------------------
# A single control pool cannot serve both V7 endpoints, because the two endpoints need
# opposite things from it:
#
#   NULL_UNIFORM  -- slots drawn UNIFORMLY over the shared grammar. This is the Phase-20
#                    "generic football question" null. It is the comparator for the
#                    END_TO_END_RESEARCH_YIELD endpoint and for DATA_COMPATIBILITY_RATE,
#                    where the LLM's metric preferences MUST NOT be conditioned away -- the
#                    whole point is that the LLM named low-coverage metrics more often.
#
#   NULL_MATCHED  -- slots drawn from the V6.1 universe's own STRUCTURAL MARGINALS (metric
#                    frequencies, target-set size, comparator, window, subject, side,
#                    condition kind). This is the comparator for CONDITIONAL_SIGNAL_QUALITY,
#                    where structural comparability is required so the contrast isolates
#                    WHICH combination was asked rather than what kind of thing was asked.
#
# NULL_MATCHED samples INDEPENDENTLY from those marginals, so it reproduces the LLM's
# structural composition without reproducing its joint choices -- the joint choice is exactly
# the LLM contribution under test. The marginals are read from canonical STRUCTURE only
# (V7_DEDUPLICATION families); no outcome, effect or OOS quantity is consulted.
SAMPLING_UNIFORM = "UNIFORM_GRAMMAR"
SAMPLING_MARGINAL = "V6_1_STRUCTURAL_MARGINALS"


def derive_marginals(llm_families) -> dict:
    """Structural marginals of the V6.1 canonical universe. Outcome-blind by construction.

    Reads ONLY canonical_spec slots. Returns, for each slot, the observed values with integer
    counts, so the sampler can reproduce the composition deterministically.
    """
    from collections import Counter
    metric_c, size_c = Counter(), Counter()
    comp_c, win_c, subj_c, side_c, kind_c = (Counter(), Counter(), Counter(),
                                             Counter(), Counter())
    axis_c, pval_c, venue_c = Counter(), Counter(), Counter()
    for fam in llm_families:
        cs = fam["canonical_spec"]
        tg = cs.get("TARGET") or []
        for m in tg:
            metric_c[m] += 1
        size_c[len(tg)] += 1
        comp_c[cs.get("COMPARATOR")] += 1
        win_c[cs.get("TIME_SCOPE")] += 1
        subj_c[cs.get("SUBJECT")] += 1
        side_c[cs.get("SIDE")] += 1
        conds = cs.get("CONDITIONS") or []
        if not conds:
            kind_c["NONE"] += 1
        else:
            blob = " ".join(conds)
            if "opponent_profile" in blob:
                kind_c["OPPONENT_PROFILE"] += 1
                for ax in NULL_PROFILE_AXES:
                    if f'"axis": "{ax}"' in blob:
                        axis_c[ax] += 1
                for pv in NULL_PROFILE_VALUES:
                    if f'"value": "{pv}"' in blob:
                        pval_c[pv] += 1
            elif "historical_venue_conditioning" in blob:
                kind_c["VENUE"] += 1
                for vv in NULL_VENUE_VALUES:
                    if f'"value": "{vv}"' in blob:
                        venue_c[vv] += 1
            else:
                kind_c["NONE"] += 1

    def _pairs(c, fallback):
        items = sorted((str(k), int(v)) for k, v in c.items() if k is not None)
        return items or [(str(x), 1) for x in fallback]

    return {
        "source": "V7 canonical families (structure only; no outcome consulted)",
        "n_families": len(llm_families),
        "metrics": _pairs(metric_c, ()),
        "target_set_sizes": _pairs(size_c, NULL_TARGET_SET_SIZES),
        "comparators": _pairs(comp_c, NULL_COMPARATORS),
        "time_scopes": _pairs(win_c, NULL_TIME_SCOPES),
        "subjects": _pairs(subj_c, NULL_SUBJECTS),
        "sides": _pairs(side_c, NULL_SIDES),
        "condition_kinds": _pairs(kind_c, NULL_CONDITION_KINDS),
        "profile_axes": _pairs(axis_c, NULL_PROFILE_AXES),
        "profile_values": _pairs(pval_c, NULL_PROFILE_VALUES),
        "venue_values": _pairs(venue_c, NULL_VENUE_VALUES),
    }


def _weighted_pick(index: int, slot: str, pairs):
    """Deterministically pick a value from [(value, count)] proportional to count."""
    total = sum(c for _, c in pairs)
    if total <= 0:
        return pairs[0][0]
    r = _stream_int(index, slot, total)
    acc = 0
    for val, cnt in pairs:
        acc += cnt
        if r < acc:
            return val
    return pairs[-1][0]


def _stream_int(index: int, slot: str, modulus: int) -> int:
    """A deterministic integer from a SHA-256 counter stream.

    Never uses Python's `hash()` or the `random` module, so the enumeration is identical under
    every PYTHONHASHSEED and on every interpreter.
    """
    digest = hashlib.sha256(f"{NULL_SEED}|{index}|{slot}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def enumerate_null_pool(metric_vocabulary, pool_size: int = NULL_POOL_SIZE,
                       sampling: str = SAMPLING_UNIFORM, marginals: dict = None) -> list:
    """Deterministically enumerate `pool_size` generic hypotheses over the canonical grammar.

    `metric_vocabulary` is the FULL contracted metric list (sorted), coverage-failing metrics
    included, so the null faces the same measurability hazards as V6.1.
    """
    vocab = sorted(metric_vocabulary)
    marg = marginals if sampling == SAMPLING_MARGINAL else None
    if sampling == SAMPLING_MARGINAL and not marg:
        raise ValueError("SAMPLING_MARGINAL requires marginals from derive_marginals()")
    out = []
    for i in range(pool_size):
        if marg:
            k = int(_weighted_pick(i, "size", marg["target_set_sizes"]))
            chosen, cursor = [], 0
            while len(chosen) < k and cursor < 8 * k + 32:
                m = _weighted_pick(i, f"metric{cursor}", marg["metrics"])
                if m not in chosen:
                    chosen.append(m)
                cursor += 1
            subject = _weighted_pick(i, "subject", marg["subjects"])
            side = _weighted_pick(i, "side", marg["sides"])
            comparator = _weighted_pick(i, "comparator", marg["comparators"])
            window = _weighted_pick(i, "window", marg["time_scopes"])
            kind = _weighted_pick(i, "cond_kind", marg["condition_kinds"])
        else:
            k = NULL_TARGET_SET_SIZES[_stream_int(i, "size", len(NULL_TARGET_SET_SIZES))]
            # choose k distinct metrics deterministically, without replacement
            chosen, cursor = [], 0
            while len(chosen) < k and cursor < 4 * k + 16:
                m = vocab[_stream_int(i, f"metric{cursor}", len(vocab))]
                if m not in chosen:
                    chosen.append(m)
                cursor += 1
            subject = NULL_SUBJECTS[_stream_int(i, "subject", len(NULL_SUBJECTS))]
            side = NULL_SIDES[_stream_int(i, "side", len(NULL_SIDES))]
            comparator = NULL_COMPARATORS[_stream_int(i, "comparator",
                                                      len(NULL_COMPARATORS))]
            window = NULL_TIME_SCOPES[_stream_int(i, "window", len(NULL_TIME_SCOPES))]
            kind = NULL_CONDITION_KINDS[_stream_int(i, "cond_kind",
                                                    len(NULL_CONDITION_KINDS))]
        conditions, caps = [], []
        if kind == "VENUE":
            vv = (_weighted_pick(i, "venue_val", marg["venue_values"]) if marg
                  else NULL_VENUE_VALUES[_stream_int(i, "venue_val",
                                                     len(NULL_VENUE_VALUES))])
            conditions = [{"dimension": "historical_venue_conditioning", "value": vv}]
        elif kind == "OPPONENT_PROFILE":
            ax = (_weighted_pick(i, "prof_axis", marg["profile_axes"]) if marg
                  else NULL_PROFILE_AXES[_stream_int(i, "prof_axis",
                                                     len(NULL_PROFILE_AXES))])
            pv = (_weighted_pick(i, "prof_val", marg["profile_values"]) if marg
                  else NULL_PROFILE_VALUES[_stream_int(i, "prof_val",
                                                       len(NULL_PROFILE_VALUES))])
            conditions = [{"dimension": "opponent_profile", "axis": ax, "value": pv}]
            # the one deterministic V6.1 capability rule, reproduced faithfully
            caps = [CAP_OPPONENT_PROFILE]
        primary = sorted(chosen)[0]
        out.append({
            "null_index": i,
            "origin": "DETERMINISTIC_NULL",
            "spec": {
                "target_metrics": sorted(chosen),
                "subject": subject,
                "side": side,
                "comparison": comparator,
                "conditions": list(conditions),
                "window": window,
                "research_family": ("OPPONENT_PROFILE_INTERACTION" if caps
                                    else METRIC_FAMILY.get(primary, "ATTACK_VOLUME")),
                "required_capabilities": list(caps),
                "evidence_refs": [],
                "candidate_confounders": [],
                "evidence_summary": None,
                "priority": None,
                "sufficiency": None,
                "question": (f"Generic enumerated question {i}: {subject} {side} "
                             f"{'/'.join(sorted(chosen))} vs {comparator} over {window}"),
            },
        })
    return out


def build(metric_vocabulary, canonical_mod, pool_size: int = NULL_POOL_SIZE,
          sampling: str = SAMPLING_UNIFORM, marginals: dict = None) -> dict:
    """Enumerate the null pool and canonicalize it with the SAME canonicalizer as V6.1.

    Returns the pool plus its canonical families. Nothing here is special-cased: if the null
    needed different downstream handling the comparison would be contaminated.
    """
    pool = enumerate_null_pool(metric_vocabulary, pool_size, sampling, marginals)
    families = {}
    for entry in pool:
        cid = canonical_mod.canonical_id(entry["spec"])
        cspec = canonical_mod.canonical_spec(entry["spec"])
        fam = families.setdefault(cid, {"canonical_hypothesis_id": cid,
                                        "canonical_spec": cspec,
                                        "origins": [], "arms": ["null"],
                                        "arm_membership": "null"})
        fam["origins"].append({"v7_hypothesis_id": f"null_{entry['null_index']:04d}",
                               "arm": "null",
                               "originating_fixture": "NONE_DETERMINISTIC",
                               "response_seq": entry["null_index"]})
    fam_out = []
    for cid, fam in sorted(families.items()):
        fam["n_origins"] = len(fam["origins"])
        fam_out.append(fam)
    return {
        "null_version": NULL_VERSION,
        "null_seed": NULL_SEED,
        "sampling": sampling,
        "marginals": marginals if sampling == SAMPLING_MARGINAL else None,
        "pool_size": pool_size,
        "n_pool": len(pool),
        "n_canonical_families": len(fam_out),
        "generation": ("deterministic SHA-256 counter stream over the canonical grammar; "
                       "no LLM, no fixture-specific reasoning, no outcome consulted"),
        "slot_vocabularies": {
            "subjects": list(NULL_SUBJECTS), "sides": list(NULL_SIDES),
            "comparators": list(NULL_COMPARATORS), "time_scopes": list(NULL_TIME_SCOPES),
            "target_set_sizes": list(NULL_TARGET_SET_SIZES),
            "condition_kinds": list(NULL_CONDITION_KINDS),
            "venue_values": list(NULL_VENUE_VALUES),
            "profile_axes": list(NULL_PROFILE_AXES),
            "profile_values": list(NULL_PROFILE_VALUES)},
        "v1_superseded": {
            "reason": ("v1 emitted plain-string conditions and empty capabilities, so it "
                       "could never inhabit SIMILARITY_DIMENSIONS or PROVIDER_REQUIREMENTS; "
                       "33/132 LLM families use similarity against 0/400 v1 null families "
                       "-- an empty cell, not a weightable imbalance"),
            "defect_class": "GENERATION_DEFECT",
            "regenerated_before_any_oos": True},
        "metric_vocabulary": sorted(metric_vocabulary),
        "families": fam_out,
        "pool": pool,
    }


def balanced_measurable_subset(null_families, measurable_ids, cap: int) -> list:
    """Hash-ordered take-N of the MEASURABLE null families, for a count-balanced comparison.

    The cap is set to the V6.1 measurable-family count so neither origin is rewarded for
    sheer volume. Measurability is an effect-blind schema/coverage property, so selecting on
    it -- and ordering by canonical id, which is a content hash -- consults no outcome.
    """
    keep = set(measurable_ids)
    eligible = sorted([f for f in null_families if f["canonical_hypothesis_id"] in keep],
                      key=lambda f: f["canonical_hypothesis_id"])
    return eligible[:cap]


def version_stamp() -> dict:
    return {"null_version": NULL_VERSION, "null_seed": NULL_SEED,
            "pool_size": NULL_POOL_SIZE,
            "matched_pool_size": NULL_MATCHED_POOL_SIZE,
            "two_pools": {"UNIFORM": "endpoint A (end-to-end yield + data compatibility)",
                          "MARGINAL": "endpoint B (conditional signal quality)"},
            "uses_llm": False, "fixture_specific_reasoning": False,
            "reads_outcomes": False,
            "same_pipeline_as_v6_1": True,
            "draws_coverage_failing_metrics_too": True,
            "rng": "sha256 counter stream (PYTHONHASHSEED-independent)",
            "slot_vocabularies_restricted_to_v6_1_inhabited": True,
            "emits_structured_conditions": True,
            "can_inhabit_similarity_slot": True,
            "deterministic_capability_rule": ("opponent_profile capability iff an "
                                              "opponent_profile condition is present "
                                              "(33/33 in the V6.1 universe)"),
            "fabricates_non_deterministic_capabilities": False}
