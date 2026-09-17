"""V8B.2 scorer battery. Includes the NON-NEGOTIABLE end-to-end SCORE_OK reachability proof
(section 9) against a synthetic-but-real PITIndex, one-failure-at-a-time mutation at the
score_fixture level (section 10), PIT tests (section 11), and determinism.

Every record here is CONSTRUCTED (no real corpus, no real outcome) so the scorer is never
tuned against a real target. The point is only to prove SCORE_OK is REACHABLE and the gates
behave, before the scorer is pointed at any real fixture.
"""
from __future__ import annotations

import pytest

from src.research.matchup import corpus as MC
from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import execution as EX
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v8b2 import scorer as SC
from src.research.hypothesis_v8b2 import support as SUP

SUBJECT = "tm_subject"
DAY = 86400
METRIC = "goals"
GOALS_CONTRACT = {"goals": CAP.METRIC_SEMANTICS["goals"]}
# Real competitions where `goals` is admissible (from the frozen V7 coverage matrix). Using
# real competition names keeps the frozen provider-coverage invariant (>=4 admissible
# competitions) satisfied without fabricating a coverage matrix.
COMPS = ("champ", "epl", "laliga", "laliga2", "ligue1", "ligue2")


def _rec(fid, kickoff, home, away, hg, ag, comp="champ"):
    return MC.MatchRecord(
        fixture_id=fid, competition=comp, competition_id="c1", season_id="s1",
        kickoff_unix=kickoff, home=home, away=away, home_id=home, away_id=away,
        base={"homeGoalCount": hg, "awayGoalCount": ag}, rich={}, extra={})


def _build_index(subject_goal_pattern, *, n_opponents=10, home=True):
    """Build a synthetic PITIndex where `subject` plays many DISTINCT opponents before a
    target fixture, with dispersed goal values so scale_var > 0. Returns (index, target_pos).

    The subject alternates HOME and AWAY in its prior matches so the venue-restricted cohort
    (its home matches) is a STRICT SUBSET of the all-prior baseline -- otherwise the two
    coincide and the query is (correctly) refused as contrastless. `home` selects whether the
    subject is home in the TARGET fixture (which venue the cohort restricts to).

    subject_goal_pattern indexes the subject's HOME prior matches (the venue cohort). We add an
    equal number of AWAY prior matches (with different goal values) so the baseline differs.
    """
    recs = []
    base_k = 1_600_000_000
    idx = 0
    for i, sg in enumerate(subject_goal_pattern):
        opp = f"tm_opp{i % n_opponents}"
        comp = COMPS[i % len(COMPS)]
        # a HOME prior match (subject scores sg at home)
        recs.append(_rec(f"mt_h{i}", base_k + idx * DAY, SUBJECT, opp, sg, 0, comp=comp))
        idx += 1
        # an AWAY prior match against a different opponent, different value, so the all-prior
        # baseline is not identical to the home-only cohort.
        aopp = f"tm_aopp{i % n_opponents}"
        recs.append(_rec(f"mt_a{i}", base_k + idx * DAY, aopp, SUBJECT, 1, (sg + 2) % 5,
                         comp=comp))
        idx += 1
    # target fixture AFTER all priors. `home` picks the subject's venue at the target.
    if home:
        recs.append(_rec("mt_TARGET", base_k + (idx + 5) * DAY, SUBJECT, "tm_target_opp",
                         3, 1, comp=COMPS[0]))
    else:
        recs.append(_rec("mt_TARGET", base_k + (idx + 5) * DAY, "tm_target_opp", SUBJECT,
                         1, 3, comp=COMPS[0]))
    index = CI.PITIndex(recs, ["goals"], GOALS_CONTRACT)
    return index, index.pos_of_fixture["mt_TARGET"]


def _subject_venue_ir():
    """A venue-conditioned cohort vs the subject's all-prior baseline: a real contrast whose
    cohort is the subject's home matches. The SUBJECT_VENUE_BASELINE comparator defines the
    venue cohort itself, so conditions is empty (same shape the frozen v8b1 test uses)."""
    spec = {"target_metrics": ["goals"], "subject": "HOME_TEAM", "side": "FOR",
            "comparison": "SUBJECT_VENUE_BASELINE", "window": "ALL_PRIOR", "conditions": [],
            "research_family": "SYNTH", "required_capabilities": []}
    ir = IRM.build_ir(spec)
    assert ir.status == IRM.OK, ir
    return ir


@pytest.fixture(scope="module")
def cap():
    return _synth_cap()


def _synth_cap():
    # Use the frozen real V7 coverage matrix: goals is SUPPORTED across 6 real competitions,
    # satisfying the >=4 admissible-competitions invariant. We only ever score the metric
    # `goals`; no real outcome is read (synthetic records only).
    import json
    return CAP.CapabilityContract(
        json.load(open("/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json")))


def test_score_ok_is_reachable_end_to_end():
    """NON-NEGOTIABLE (section 9): a synthetic cohort satisfying every support condition and
    carrying real dispersion MUST produce SCORE_OK with a non-None score. Unconditional."""
    # dispersed goals (0..4 cycling) over 30 prior home matches, 10 distinct opponents
    pattern = [(i % 5) for i in range(30)]
    index, tpos = _build_index(pattern, n_opponents=10, home=True)
    cap = _synth_cap()
    ctx = EX.build_context(index)
    ir = _subject_venue_ir()
    recency = EN.recency_family_for(ir)
    result = SC.score_fixture(ir, index, tpos, metric=METRIC, terciles=ctx.terciles,
                              axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                              recency=recency, capability=cap)
    assert result.status == SC.SCORE_OK, (result.status, result.reason, result.support_failures)
    assert result.score is not None
    assert result.unique_opponents >= SUP.MIN_UNIQUE_OPPONENTS


def test_unique_opponents_just_below_blocks_score_ok():
    """Section 10 at score_fixture level: a cohort with plenty of rows but too few DISTINCT
    opponents (<6) must fail specifically on unique_opponents, not raw_n. 12 home-pattern rows
    => 24 priors (raw_n ok), but only 2 home + 2 away = 4 distinct opponents (<6)."""
    pattern = [(i % 5) for i in range(12)]
    index, tpos = _build_index(pattern, n_opponents=2, home=True)  # 4 distinct opponents total
    cap = _synth_cap()
    ctx = EX.build_context(index)
    ir = _subject_venue_ir()
    recency = EN.recency_family_for(ir)
    result = SC.score_fixture(ir, index, tpos, metric=METRIC, terciles=ctx.terciles,
                              axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                              recency=recency, capability=cap)
    assert result.status == SC.SCORE_INSUFFICIENT_SUPPORT
    fields = [f["field"] for f in result.support_failures]
    assert "unique_opponents" in fields
    assert "raw_n" not in fields   # raw_n passed (24>=20): accurate reporting


def test_raw_n_just_below_blocks_on_raw_n():
    """Fewer than 20 prior rows => raw_n failure. 8 home-pattern rows => 16 priors (<20), with
    plenty of distinct opponents so opponents does NOT spuriously fail alongside... (raw_n is
    the point; opponents may or may not also fail, but raw_n MUST be listed)."""
    pattern = [(i % 5) for i in range(8)]   # 16 priors < 20
    index, tpos = _build_index(pattern, n_opponents=8, home=True)
    cap = _synth_cap()
    ctx = EX.build_context(index)
    ir = _subject_venue_ir()
    recency = EN.recency_family_for(ir)
    result = SC.score_fixture(ir, index, tpos, metric=METRIC, terciles=ctx.terciles,
                              axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                              recency=recency, capability=cap)
    assert result.status == SC.SCORE_INSUFFICIENT_SUPPORT
    assert "raw_n" in [f["field"] for f in result.support_failures]


def test_determinism_same_inputs_same_output():
    pattern = [(i % 5) for i in range(30)]
    index, tpos = _build_index(pattern, n_opponents=10, home=True)
    cap = _synth_cap()
    ctx = EX.build_context(index)
    ir = _subject_venue_ir()
    recency = EN.recency_family_for(ir)
    r1 = SC.score_fixture(ir, index, tpos, metric=METRIC, terciles=ctx.terciles,
                          axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                          recency=recency, capability=cap)
    r2 = SC.score_fixture(ir, index, tpos, metric=METRIC, terciles=ctx.terciles,
                          axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                          recency=recency, capability=cap)
    assert (r1.status, r1.score, r1.unique_opponents) == (r2.status, r2.score, r2.unique_opponents)


# ---- PIT tests (section 11) --------------------------------------------------------------
def test_home_and_away_opponent_identity_recomputed_both_directions():
    """unique_opponents_of_cohort must recover the opponent correctly whether the subject was
    home or away in each historical row. The builder gives home rows (vs tm_opp*) and away
    rows (vs tm_aopp*), so across all priors the subject faced 2*n_opponents distinct
    opponents, recovered from entry[4] in both directions."""
    pattern = [(i % 5) for i in range(24)]
    index, tpos = _build_index(pattern, n_opponents=8, home=True)
    ir = _subject_venue_ir()
    n = SC.unique_opponents_of_cohort(
        ir, index, tpos,
        cohort_fixtures=frozenset(str(r.fixture_id) for r in index.recs[:-1]))
    assert n == 16   # 8 home opponents + 8 away opponents, both directions recovered


def test_future_row_cannot_enter_cohort_opponent_count():
    """Opponent counting uses prior_entries (strictly before target), so a fixture at/after
    the target kickoff can never contribute an opponent."""
    pattern = [(i % 5) for i in range(24)]
    index, tpos = _build_index(pattern, n_opponents=8, home=True)
    ir = _subject_venue_ir()
    # ask for ALL fixtures including the target itself; the target must not add an opponent
    allf = frozenset(str(r.fixture_id) for r in index.recs)   # includes mt_TARGET
    n = SC.unique_opponents_of_cohort(ir, index, tpos, cohort_fixtures=allf)
    assert "tm_target_opp" not in _opponents_seen(index, tpos, ir, allf)
    assert n == 16   # target opponent excluded (future / not in prior_entries)


def _opponents_seen(index, tpos, ir, want):
    rec = index.recs[tpos]
    subj = rec.home_id if ir.subject == "HOME_TEAM" else rec.away_id
    seen = set()
    for e in index.prior_entries(str(subj), tpos):
        if str(index.recs[e[0]].fixture_id) in want and e[4]:
            seen.add(str(e[4]))
    return seen


def test_true_zero_observed_is_valid_not_missing():
    """A genuine 0 goals target is a real value, not missing. Build a target where subject
    scores 0 and confirm the scorer does NOT refuse for 'observed unavailable'."""
    pattern = [(i % 5) + 1 for i in range(30)]  # nonzero dispersed history
    recs = []
    base_k = 1_600_000_000
    idx = 0
    for i, sg in enumerate(pattern):
        recs.append(_rec(f"mt_h{i}", base_k + idx * DAY, SUBJECT, f"tm_opp{i % 10}", sg, 0,
                         comp=COMPS[i % len(COMPS)]))
        idx += 1
        recs.append(_rec(f"mt_a{i}", base_k + idx * DAY, f"tm_aopp{i % 10}", SUBJECT, 1,
                         (sg + 2) % 5, comp=COMPS[i % len(COMPS)]))
        idx += 1
    # target: subject scores a TRUE zero (subject at home)
    recs.append(_rec("mt_TARGET", base_k + (idx + 5) * DAY, SUBJECT, "tm_target_opp", 0, 2,
                     comp=COMPS[0]))
    index = CI.PITIndex(recs, ["goals"], GOALS_CONTRACT)
    tpos = index.pos_of_fixture["mt_TARGET"]
    obs = index.team_value(tpos, SUBJECT, "goals", "FOR")
    assert obs == 0.0    # true zero preserved, not None
    cap = _synth_cap()
    ctx = EX.build_context(index)
    ir = _subject_venue_ir()
    recency = EN.recency_family_for(ir)
    result = SC.score_fixture(ir, index, tpos, metric=METRIC, terciles=ctx.terciles,
                              axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                              recency=recency, capability=cap)
    # a true-zero target must not be refused for missing observation
    assert not (result.status == SC.SCORE_REFUSED and "unavailable" in result.reason)


def test_null_observed_is_unavailable():
    """A target fixture with NO goals value for the subject metric => observed is None =>
    SCORE_REFUSED 'observed unavailable', never a fabricated 0."""
    pattern = [(i % 5) + 1 for i in range(30)]
    recs = []
    base_k = 1_600_000_000
    idx = 0
    for i, sg in enumerate(pattern):
        recs.append(_rec(f"mt_h{i}", base_k + idx * DAY, SUBJECT, f"tm_opp{i % 10}", sg, 0,
                         comp=COMPS[i % len(COMPS)]))
        idx += 1
        recs.append(_rec(f"mt_a{i}", base_k + idx * DAY, f"tm_aopp{i % 10}", SUBJECT, 1,
                         (sg + 2) % 5, comp=COMPS[i % len(COMPS)]))
        idx += 1
    # target with MISSING base goals (None) -> observed unavailable (subject at home)
    tgt = MC.MatchRecord(fixture_id="mt_TARGET", competition=COMPS[0], competition_id="c1",
                         season_id="s1", kickoff_unix=base_k + (idx + 5) * DAY, home=SUBJECT,
                         away="tm_target_opp", home_id=SUBJECT, away_id="tm_target_opp",
                         base={"homeGoalCount": None, "awayGoalCount": None}, rich={}, extra={})
    recs.append(tgt)
    index = CI.PITIndex(recs, ["goals"], GOALS_CONTRACT)
    tpos = index.pos_of_fixture["mt_TARGET"]
    assert index.team_value(tpos, SUBJECT, "goals", "FOR") is None
    cap = _synth_cap()
    ctx = EX.build_context(index)
    ir = _subject_venue_ir()
    recency = EN.recency_family_for(ir)
    result = SC.score_fixture(ir, index, tpos, metric=METRIC, terciles=ctx.terciles,
                              axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                              recency=recency, capability=cap)
    assert result.status == SC.SCORE_REFUSED
    assert "unavailable" in result.reason


def test_degenerate_scale_is_undefined_not_score_ok():
    """If the cohort has zero dispersion (all identical goal values) scale_var<=floor =>
    SCORE_UNDEFINED, never SCORE_OK, never an exception. Build a corpus where EVERY subject
    goal value (home and away rows) is identical, so the cohort has no dispersion."""
    recs = []
    base_k = 1_600_000_000
    idx = 0
    for i in range(20):
        # subject scores exactly 2 in every prior match, home and away, many opponents
        recs.append(_rec(f"mt_h{i}", base_k + idx * DAY, SUBJECT, f"tm_opp{i % 10}", 2, 0,
                          COMPS[i % len(COMPS)]))
        idx += 1
        recs.append(_rec(f"mt_a{i}", base_k + idx * DAY, f"tm_aopp{i % 10}", SUBJECT, 0, 2,
                          COMPS[i % len(COMPS)]))
        idx += 1
    recs.append(_rec("mt_TARGET", base_k + (idx + 5) * DAY, SUBJECT, "tm_target_opp", 3, 1,
                      COMPS[0]))
    index = CI.PITIndex(recs, ["goals"], GOALS_CONTRACT)
    tpos = index.pos_of_fixture["mt_TARGET"]
    cap = _synth_cap()
    ctx = EX.build_context(index)
    ir = _subject_venue_ir()
    recency = EN.recency_family_for(ir)
    result = SC.score_fixture(ir, index, tpos, metric=METRIC, terciles=ctx.terciles,
                              axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                              recency=recency, capability=cap)
    assert result.status in (SC.SCORE_UNDEFINED, SC.SCORE_REFUSED)
    assert result.status != SC.SCORE_OK
