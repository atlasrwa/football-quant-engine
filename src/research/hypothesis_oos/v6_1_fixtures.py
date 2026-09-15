"""V6.1 fresh confirmatory fixture universe + deterministic selection (`v6_1_fixtures_v1`).

WHY THIS MODULE EXISTS (Task 10, 12, 13)
----------------------------------------
V6's scientific verdict is non-confirmatory (decisive evaluator defect). V6.1 answers the
SAME question with a corrected evaluator on FRESH model observations. Re-sampling the exact
V6 fixtures would make V6.1 a stochastic re-run over a set whose V6 outcomes are now known;
Task 10 requires, when fresh eligible fixtures exist, a HELD-OUT fresh set chosen by a rule
fixed BEFORE any generation and provably independent of V6 outcomes.

THE SELECTION RULE, FIXED BEFORE GENERATION AND INDEPENDENT OF V6 OUTCOMES
--------------------------------------------------------------------------
1. ELIGIBLE UNIVERSE (deterministic, PIT-safe, outcome-blind):
     * competition in the SAME four V6 competitions (epl, laliga, laliga2, champ) so the
       population matches V6's -- not chosen to favour any arm;
     * both teams have >= MIN_PRIOR_MATCHES_PER_TEAM PIT-safe prior matches at the fixture
       cutoff (the identical V5A.1/V5A.2 eligibility criterion, `v5a1_packet`);
     * a packet builds in BOTH arms (symmetry, exactly as V5A.1 required);
     * the fixture is NOT any V5A/V6 fixture (held-out): the V6 set and the V5A.1 excluded
       fixture are removed.
   None of these criteria reads a hypothesis, a qualified rate, an Arm-B result, a primary
   difference, or the corrected replay. They are structural facts about the evidence only.

2. ORDERING (deterministic, content-addressed, outcome-blind):
     candidates are ordered by SHA-256(fixture_id) -- a fixed hash of the IDENTIFIER, which
     cannot encode any V6 result. This is a preregistered pseudo-random permutation with no
     tunable seed and no dependence on outcomes.

3. STRATIFIED TAKE (matches the V6 design size, no power inflation):
     take the SAME NUMBER of fixtures per competition as V6 used, in the hash order, so the
     competition mix and the fixture count equal V6's. Task 13 forbids enlarging N because
     V6's observed primary was < benchmark; V6.1 reuses the V6 sample size exactly.

The rule is a pure function of (index, eligibility criteria, V6 competition mix). Given the
frozen index it is byte-reproducible. It is frozen here BEFORE `_freeze_v6_1` builds packets
and BEFORE any model call.

ZERO SPEND. No network, no model. Reads the same local match index V5A.1 read.
"""
from __future__ import annotations

import hashlib

from src.research.hypothesis_engine import corpus_adapter as CA
from src.research.hypothesis_oos import v5a1_packet as PK

FIXTURES_VERSION = "v6_1_fixtures_v1"

# The V6 fixtures (the immutable executed set) and the V5A.1 excluded fixture. HELD OUT:
# V6.1 must not reuse any of these as a "fresh" observation.
V6_FIXTURES = (
    "mt_010243515", "mt_010243537", "mt_010243938", "mt_010244159", "mt_010244193",
    "mt_010441320", "mt_010441491", "mt_010444904", "mt_012232295", "mt_012232411")
V5A1_EXCLUDED = ("mt_013233190",)
HELD_OUT = frozenset(V6_FIXTURES) | frozenset(V5A1_EXCLUDED)

# The V6 competition mix, taken from the executed V6 fixtures. V6.1 matches it exactly so the
# fresh set has the same population composition and the same total size (10). This mix is a
# fact about V6's DESIGN (which competitions, how many each), NOT about V6's RESULTS.
V6_COMPETITION_MIX = {"epl": 5, "laliga": 1, "laliga2": 2, "champ": 2}
ELIGIBLE_COMPETITIONS = tuple(sorted(V6_COMPETITION_MIX))

MIN_PRIOR_MATCHES_PER_TEAM = PK.MIN_PRIOR_MATCHES_PER_TEAM   # = 6, one source of truth


def _hash_order_key(fixture_id: str) -> str:
    """Deterministic, outcome-blind ordering key: SHA-256 of the fixture IDENTIFIER only."""
    return hashlib.sha256(fixture_id.encode()).hexdigest()


def _eligible_by_priors(idx, rec) -> bool:
    """Cheap PIT-safe eligibility screen (no packet build): both teams have >= MIN prior
    PIT-safe matches at the cutoff. Identical criterion to V5A.1's packet gate."""
    ph = PK.full_prior(idx, rec, rec.home)
    pa = PK.full_prior(idx, rec, rec.away)
    return len(ph) >= MIN_PRIOR_MATCHES_PER_TEAM and len(pa) >= MIN_PRIOR_MATCHES_PER_TEAM


def _builds_in_both_arms(idx, rec) -> bool:
    """Symmetry gate: a packet must build in BOTH arms (as V5A.1 required)."""
    a = PK.build_packet(idx, rec, arm="base")
    if a is None:
        return False
    b = PK.build_packet(idx, rec, arm="research")
    return b is not None


def _priors_eligible_candidates(idx) -> list:
    """The hash-ordered candidates that pass the CHEAP screens (held-out, competition,
    priors) -- no packet build yet. Almost all pruning happens here."""
    out = []
    for rec in idx.records:
        fid = rec.fixture_id
        if fid in HELD_OUT:
            continue
        if rec.competition not in ELIGIBLE_COMPETITIONS:
            continue
        if not _eligible_by_priors(idx, rec):
            continue
        out.append({"fixture_id": fid, "competition": rec.competition,
                    "cutoff_unix": int(rec.kickoff_unix),
                    "order_key": _hash_order_key(fid), "_rec": rec})
    out.sort(key=lambda r: r["order_key"])
    return out


def eligible_universe(idx=None, *, verify_build=True) -> list:
    """The FULL deterministic eligible, held-out universe (exhaustive), sorted by hash-of-id.

    Structural and outcome-blind. `verify_build` runs the both-arms packet build over every
    priors-eligible candidate (exact but slower). Use `select_fresh_fixtures` for the frozen
    set -- it verifies builds lazily and does not need the exhaustive count.
    """
    idx = idx or CA.load_index()
    out = []
    for row in _priors_eligible_candidates(idx):
        if verify_build and not _builds_in_both_arms(idx, row["_rec"]):
            continue
        out.append({k: v for k, v in row.items() if k != "_rec"})
    return out


def select_fresh_fixtures(idx=None, *, mix=None, verify_build=True) -> dict:
    """Deterministically select the fresh held-out V6.1 fixture set.

    Per competition, walk the hash-ordered priors-eligible candidates and take the first
    `mix[comp]` that also build in both arms. Because the take is prefix-based in a fixed
    order, only enough candidates to fill each quota are ever build-verified -- the result is
    identical to filtering the exhaustive universe, at a fraction of the cost. Pure function
    of the frozen index and the frozen mix; contains no V6 outcome.
    """
    idx = idx or CA.load_index()
    mix = dict(mix or V6_COMPETITION_MIX)
    candidates = _priors_eligible_candidates(idx)
    n_priors_eligible_by_comp = {}
    for row in candidates:
        n_priors_eligible_by_comp[row["competition"]] = \
            n_priors_eligible_by_comp.get(row["competition"], 0) + 1

    selected, shortfalls = [], {}
    taken_by_comp = {c: [] for c in mix}
    for c in sorted(mix):
        need = mix[c]
        for row in candidates:                      # hash order
            if row["competition"] != c:
                continue
            if len(taken_by_comp[c]) >= need:
                break
            if verify_build and not _builds_in_both_arms(idx, row["_rec"]):
                continue
            taken_by_comp[c].append({k: v for k, v in row.items() if k != "_rec"})
        selected.extend(taken_by_comp[c])
        if len(taken_by_comp[c]) < need:
            shortfalls[c] = {"need": need,
                             "priors_eligible": n_priors_eligible_by_comp.get(c, 0)}
    selected.sort(key=lambda r: r["order_key"])
    return {
        "fixtures_version": FIXTURES_VERSION,
        "selection_rule": (
            "eligible = competition in V6 mix AND both teams >= "
            f"{MIN_PRIOR_MATCHES_PER_TEAM} PIT-safe priors AND packet builds in both arms "
            "AND fixture not in the held-out V5A/V6 set; ordered by SHA-256(fixture_id); "
            "take V6's per-competition count. Fixed before generation; independent of V6 "
            "outcomes (no hypothesis/rate/primary/replay is read)."),
        "held_out": sorted(HELD_OUT),
        "competition_mix": mix,
        "n_priors_eligible_by_competition": {
            c: n_priors_eligible_by_comp.get(c, 0) for c in sorted(mix)},
        "n_selected": len(selected),
        "shortfalls": shortfalls,
        "selected_fixtures": [r["fixture_id"] for r in selected],
        "selected_detail": selected,
        "independence_assertion": {
            "reads_v6_hypotheses": False, "reads_v6_qualified_rate": False,
            "reads_v6_primary_difference": False, "reads_corrected_replay": False,
            "reads_arm_b_outcome": False,
            "ordering_is_hash_of_identifier_only": True},
    }


def version_stamp() -> dict:
    return {"fixtures_version": FIXTURES_VERSION,
            "held_out_count": len(HELD_OUT),
            "eligible_competitions": list(ELIGIBLE_COMPETITIONS),
            "competition_mix": dict(V6_COMPETITION_MIX),
            "min_prior_matches_per_team": MIN_PRIOR_MATCHES_PER_TEAM,
            "ordering": "sha256(fixture_id) ascending",
            "outcome_independent": True,
            "sample_size_equals_v6": True}
