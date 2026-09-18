"""V8C synthetic end-to-end golden environment (`v8c_golden_v1`) -- §16, the single most
important V8C test fixture.

Builds a fully synthetic, PIT-safe fixture environment designed to satisfy EVERY valid
experimental requirement at once, so the complete composed experiment can be driven end to end
with no real corpus, no real outcome and no Sonnet call:

    target fixture exists
    non-empty ADMISSIBLE universe
    non-empty PRE_T_EVALUABLE universe
    an S-style selection exists
    a DISTINCT R selection exists, R_ID != S_ID
    an H selection exists
    all three canonical, all three frozen before the outcome is read
    S / R / H each reach SCORE_OK
    S / R / H arm scores exist
    S-R and S-H paired differences exist
    aggregation succeeds and the inference path accepts the structure

CONSTRUCTION
------------
Every record is fabricated. No real match, no real outcome, no CHAMPION.

The subject plays a long, dispersed prior history against MANY DISTINCT OPPONENTS, alternating
HOME and AWAY so that a venue-restricted cohort is a STRICT SUBSET of the all-prior baseline
(otherwise the compiler correctly refuses the query as contrastless). Several base-block
metrics are populated, each with its own dispersion pattern, so the evaluable universe is
large enough for three arms to make genuinely different selections rather than restating one
another.

Real competition tags are used so the frozen capability contract's >=4-admissible-competitions
invariant is satisfied without fabricating a coverage matrix. The metric values are invented;
the coverage semantics are the real frozen ones.

`n_prior_blocks`, `n_opponents` and the per-metric patterns are the knobs the §17 NEGATIVE
battery mutates, ONE AT A TIME, to drive each named failure state.

ZERO SPEND. No network. No CHAMPION. No real outcome.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import ir as IRM
from src.research.matchup import corpus as MC

GOLDEN_VERSION = "v8c_golden_v1"

DAY = 86400
BASE_KICKOFF = 1_600_000_000
SUBJECT = "tm_subject"
TARGET_FIXTURE_ID = "mt_GOLDEN_TARGET"
TARGET_OPPONENT = "tm_target_opp"

#: Real competition tags from the frozen coverage matrix.
COMPS = ("champ", "epl", "laliga", "laliga2", "ligue1", "ligue2")

#: Base-block metrics this environment populates. All five are `block == "base"` and audited
#: in the frozen capability contract. `xg` is RESTRICTED (not admissible in laliga2/ligue2),
#: which is exactly what the competition-admissibility negative case needs.
GOLDEN_METRICS = ("goals", "yellow_cards", "cards_2h", "red_cards", "xg")

_FIELD = {m: (CAP.METRIC_SEMANTICS[m]["field"], CAP.METRIC_SEMANTICS[m]["field_away"])
          for m in GOLDEN_METRICS}

#: Per-metric (home, away) value generators. Dispersed (never constant) so `scale_var` clears
#: ZERO_VARIANCE_FLOOR, and different across metrics so the arms are not forced into one shape.
_PATTERNS = {
    "goals":        lambda i: ((i % 5), (i + 2) % 4),
    "yellow_cards": lambda i: ((i % 4) + 1, (i + 1) % 5),
    "cards_2h":     lambda i: ((i % 3), (i + 2) % 4),
    "red_cards":    lambda i: ((i % 2), (i + 1) % 3),
    "xg":           lambda i: (round(0.4 + (i % 7) * 0.31, 3), round(0.3 + (i % 5) * 0.27, 3)),
}

COVERAGE_MATRIX = "/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json"


@dataclass(frozen=True)
class GoldenEnvironment:
    index: object
    target_pos: int
    target_fixture_id: str
    capability: object
    metrics: tuple
    n_prior_matches: int
    n_distinct_opponents: int
    target_fixture_ids: tuple = ()
    target_positions: tuple = ()


def _base_dict(i, *, metrics, drop_metric=None, constant_metric=None, target_null=False):
    """One record's base block.

    `drop_metric`     omits exactly that metric (provider NULL, which is NOT zero)
    `constant_metric` collapses dispersion for exactly THAT metric, leaving every other
                      metric dispersed
    `target_null`     omits every metric (the NULL-target case)

    P1 GOLDEN repair: the previous signature took a boolean `constant` and applied it to
    EVERY metric, so a `constant_metric="goals"` negative case silently mutated all five
    metrics at once. A one-failure-at-a-time battery whose mutation changes several
    dimensions cannot attribute the resulting failure to the dimension under test.
    """
    base = {}
    for m in metrics:
        if m == drop_metric:
            continue
        if target_null:
            continue
        hf, af = _FIELD[m]
        h, a = _PATTERNS[m](0 if m == constant_metric else i)
        base[hf] = h
        base[af] = a
    return base


def _rec(fid, kickoff, home, away, base, comp):
    return MC.MatchRecord(fixture_id=fid, competition=comp, competition_id="c_golden",
                          season_id="s_golden", kickoff_unix=kickoff, home=home, away=away,
                          home_id=home, away_id=away, base=base, rich={}, extra={})


def build_environment(*, n_prior_blocks: int = 40, n_opponents: int = 14,
                      metrics=GOLDEN_METRICS, drop_metric=None, constant_metric=None,
                      target_metric_null: bool = False, subject_home_at_target: bool = True,
                      single_competition: bool = False,
                      target_competition: str | None = None,
                      inject_future_rows: int = 0, n_targets: int = 1) -> GoldenEnvironment:
    """Construct the golden environment.

    Each `n_prior_blocks` iteration adds TWO prior matches: one with the subject at HOME
    against `tm_opp{i % n_opponents}` and one with the subject AWAY against a DIFFERENT
    opponent `tm_aopp{i % n_opponents}`. So the venue cohort is a strict subset of the
    all-prior baseline, and the cohort sees `n_opponents` distinct opponent identities.

    Keyword knobs exist ONLY so the §17 negative battery can mutate exactly one dimension at a
    time; the default call is the known-good case.

    `inject_future_rows` appends matches AFTER the target kickoff -- the §29 adversarial
    injection. A PIT-correct apparatus must produce byte-identical pre-T verdicts with and
    without them.
    """
    metrics = tuple(metrics)
    recs, idx = [], 0
    for i in range(n_prior_blocks):
        comp = COMPS[0] if single_competition else COMPS[i % len(COMPS)]
        opp = f"tm_opp{i % n_opponents}"
        aopp = f"tm_aopp{i % n_opponents}"
        base_h = _base_dict(i, metrics=metrics, drop_metric=drop_metric,
                            constant_metric=constant_metric)
        recs.append(_rec(f"mt_h{i}", BASE_KICKOFF + idx * DAY, SUBJECT, opp, base_h, comp))
        idx += 1
        base_a = _base_dict(i + 7, metrics=metrics, drop_metric=drop_metric,
                            constant_metric=constant_metric)
        recs.append(_rec(f"mt_a{i}", BASE_KICKOFF + idx * DAY, aopp, SUBJECT, base_a, comp))
        idx += 1
        # Opponent-side history, so opponent profiles and terciles can be formed and the
        # OPPONENT_* comparators have something to read.
        base_o = _base_dict(i + 3, metrics=metrics, drop_metric=drop_metric,
                            constant_metric=constant_metric)
        recs.append(_rec(f"mt_o{i}", BASE_KICKOFF + idx * DAY, opp, TARGET_OPPONENT,
                         base_o, comp))
        idx += 1
        base_p = _base_dict(i + 5, metrics=metrics, drop_metric=drop_metric,
                            constant_metric=constant_metric)
        recs.append(_rec(f"mt_p{i}", BASE_KICKOFF + idx * DAY, TARGET_OPPONENT, aopp,
                         base_p, comp))
        idx += 1

    tcomp = target_competition or COMPS[0]
    tk = BASE_KICKOFF + (idx + 5) * DAY
    target_ids = []
    for t in range(max(1, n_targets)):
        # Each target gets its own opponent so a later target's cohort is not dominated by one
        # identity, and they are spaced a week apart so the chronological blocking has a real
        # kickoff order to work with.
        topp = TARGET_OPPONENT if t == 0 else f"tm_target_opp{t}"
        tfid = TARGET_FIXTURE_ID if t == 0 else f"{TARGET_FIXTURE_ID}_{t:03d}"
        target_ids.append(tfid)
        tbase = _base_dict(99 + t, metrics=metrics, drop_metric=drop_metric,
                           target_null=target_metric_null)
        tkick = tk + t * 7 * DAY
        if subject_home_at_target:
            recs.append(_rec(tfid, tkick, SUBJECT, topp, tbase, tcomp))
        else:
            recs.append(_rec(tfid, tkick, topp, SUBJECT, tbase, tcomp))
        if t > 0:
            # Give each extra target opponent its own prior history, so opponent-role
            # comparators remain evaluable at the later targets too.
            for j in range(8):
                recs.append(_rec(f"mt_t{t}o{j}", BASE_KICKOFF + (idx + j) * DAY, topp,
                                 f"tm_opp{j % n_opponents}",
                                 _base_dict(j + t, metrics=metrics, drop_metric=drop_metric,
                                            constant_metric=constant_metric),
                                 COMPS[j % len(COMPS)] if not single_competition else COMPS[0]))
    tk = tk + max(0, n_targets - 1) * 7 * DAY

    for j in range(inject_future_rows):
        # ADVERSARIAL: matches strictly AFTER the target. Extreme values, so any leak into a
        # tercile band, an axis mean or a cohort would be unmissable.
        fbase = {}
        for m in metrics:
            hf, af = _FIELD[m]
            fbase[hf] = 99
            fbase[af] = 99
        recs.append(_rec(f"mt_FUTURE{j}", tk + (j + 1) * DAY, SUBJECT,
                         f"tm_future_opp{j}", fbase, tcomp))

    index = CI.PITIndex(recs, list(metrics), CAP.METRIC_SEMANTICS)
    capability = CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))
    return GoldenEnvironment(index=index, target_pos=index.pos_of_fixture[TARGET_FIXTURE_ID],
                             target_fixture_id=TARGET_FIXTURE_ID, capability=capability,
                             metrics=metrics, n_prior_matches=n_prior_blocks * 2,
                             n_distinct_opponents=n_opponents,
                             target_fixture_ids=tuple(target_ids),
                             target_positions=tuple(index.pos_of_fixture[f]
                                                    for f in target_ids))


def venue_baseline_ir(metric="goals", subject="HOME_TEAM", side="FOR"):
    """The simplest non-degenerate shape: a venue-restricted cohort against the subject's
    all-prior baseline. `SUBJECT_VENUE_BASELINE` defines the venue cohort itself, so
    `conditions` is empty -- the same shape the frozen V8B.2 reachability test uses."""
    ir = IRM.build_ir({"target_metrics": [metric], "subject": subject, "side": side,
                       "comparison": "SUBJECT_VENUE_BASELINE", "window": "ALL_PRIOR",
                       "conditions": [], "research_family": "V8C_GOLDEN",
                       "required_capabilities": []})
    assert ir.status == IRM.OK, ir
    return ir


def version_stamp() -> dict:
    return {"golden_version": GOLDEN_VERSION,
            "purpose": "§16 synthetic end-to-end golden case",
            "all_records_synthetic": True,
            "reads_real_corpus": False,
            "reads_real_outcome": False,
            "metrics": list(GOLDEN_METRICS),
            "competitions": list(COMPS),
            "uses_frozen_coverage_matrix": True,
            "negative_battery_knobs": ["n_prior_blocks", "n_opponents", "drop_metric",
                                       "constant_metric", "target_metric_null",
                                       "single_competition", "target_competition",
                                       "inject_future_rows"]}
