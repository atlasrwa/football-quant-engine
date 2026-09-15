"""The frozen, balanced call sequence (`v6_schedule_v1`). §6, §27.

WHAT WENT WRONG, AND WHERE
--------------------------
It was not one bug but a seam between two files.

`_freeze_v5a2.py` emitted the manifest fixture-major, with repeats folded into a COUNT:

    for fid in PAIRED:
        for arm in ("base", "research"):
            manifest["calls"].append({... "n_calls": 1 + reps ...})

`_execute_v5a2.py` then expanded that count in place:

    for c in prereg["request_manifest"]["calls"]:
        for rep in range(c["n_calls"]):
            calls.append({**c, "rep": rep})

So the realised order was fixture1/base x4, fixture1/research x4, fixture2/base x4, ...
The stop rule became eligible at call 6. Calls 1-6 were ALL ONE FIXTURE. It fired on 2/2
research responses from a single fixture and halted a ten-fixture experiment. The V5A.2
report records this as one of two confounds a reader must hold onto.

Neither file is wrong on its own. The manifest never said what order to execute in, and the
driver invented one. So V6 freezes a FLAT LIST WITH AN EXPLICIT `seq`, and the driver
consumes it verbatim -- `n_calls` does not exist as a field and there is nothing left to
expand.

THE ORDERING
------------
Round-robin over fixtures, A and B ADJACENT within a fixture, repeats in LATER rounds:

    round 1   f1/A f1/B  f2/A f2/B  ...  f10/A f10/B      one primary pair per fixture
    round 2   g1/A g1/B  g2/A g2/B  g3/A g3/B  g4/A g4/B  repeat 1, on the repeat fixtures
    round 3   g1/A g1/B  ...                               repeat 2

A and B adjacent because the primary analysis is PAIRED per fixture (§21): if the run halts
mid-round, it halts having completed whole pairs, and a partial round is still a valid
paired sample. Repeats deferred to later rounds because a repeat teaches nothing about a
fixture that has not been observed once -- and because §7's eligibility must be reachable
from breadth, not from depth on one fixture.

The properties this gives are ASSERTED at freeze, not hoped for. `order_properties()`
reports them and `_freeze_v6.py` refuses to write a preregistration that fails them.

ZERO SPEND.
"""
from __future__ import annotations

SCHEDULE_VERSION = "v6_schedule_v1"

ARMS = ("base", "research")

# ----------------------------------------------------------------------------------------
# BATTERY SIZE (§27). Derived, not inherited -- V5A.2's 38 is not carried over.
#
#   paired primaries      10 fixtures x 2 arms                     = 20 calls
#   self-noise repeats     4 fixtures x 2 arms x 2 extra repeats   = 16 calls
#                                                                    --------
#                                                                    36 calls
#
# 10 paired fixtures: the packets already exist, are PIT-audited and evidence-identity
# audited against V5A.1, and span four competitions (epl, laliga, laliga2, champ). §27
# prefers fixture diversity over repeats on one fixture, and 10 is every eligible fixture
# the corpus selection yields -- the eleventh candidate, mt_013233190, was excluded
# pre-spend for too little prior history and is NOT reinstated.
#
# 4 repeat fixtures x 3 total calls each: §9 requires self-noise from MULTIPLE fixtures in
# BOTH arms, and V5A.2's single group per arm is what made its 0/6/7/0 spread unusable. Four
# groups per arm exceeds the V5A.2 minimum of three, so one lost fixture still leaves an
# estimate. 3 repeats per group is the smallest n giving more than one pairwise similarity
# comparison per group (3 pairs rather than 1).
#
# The repeat fixtures are the first four of the sorted paired list -- a deterministic,
# content-blind rule fixed before any response exists.
# ----------------------------------------------------------------------------------------
N_REPEAT_FIXTURES = 4
REPEATS_PER_GROUP = 3           # total calls per (repeat fixture, arm), primary included


def repeat_fixtures(paired: list) -> list:
    """The fixtures carrying self-noise repeats. Deterministic and content-blind."""
    return sorted(paired)[:N_REPEAT_FIXTURES]


def build_sequence(paired: list) -> list:
    """The frozen flat call list. One dict per CALL, with an explicit `seq`.

    There is deliberately no `n_calls` field. A count is an instruction to expand, and the
    expansion is where V5A.2's ordering was decided by the driver instead of by the freeze.
    """
    fixtures = sorted(paired)
    reps = repeat_fixtures(fixtures)
    calls: list = []

    for fid in fixtures:                                   # round 1: every paired primary
        for arm in ARMS:
            calls.append({"fixture_id": fid, "arm": arm, "rep": 0, "round": 1,
                          "role": "PAIRED_PRIMARY"})

    for r in range(1, REPEATS_PER_GROUP):                  # rounds 2..: self-noise repeats
        for fid in reps:
            for arm in ARMS:
                calls.append({"fixture_id": fid, "arm": arm, "rep": r, "round": 1 + r,
                              "role": "SELF_NOISE_REPEAT"})

    for i, c in enumerate(calls, start=1):
        c["seq"] = i
    return calls


def order_properties(calls: list, eligibility_seq: int) -> dict:
    """The §6 and §7 properties of a sequence, measured on the sequence itself.

    `eligibility_seq` is the earliest call at which a rate stop rule can fire (see
    `v6_stop`). Everything before it is the prefix a stop decision could be based on, and
    §6 requires that prefix to contain both arms and several fixtures.
    """
    prefix = calls[:eligibility_seq]
    fixtures_in_prefix = sorted({c["fixture_id"] for c in prefix})
    per_arm_prefix = {a: sum(1 for c in prefix if c["arm"] == a) for a in ARMS}
    per_fixture = {}
    for c in calls:
        per_fixture.setdefault(c["fixture_id"], []).append(c["arm"])

    # How far into the sequence before every paired fixture has been seen at least once.
    seen, first_full = set(), None
    for c in calls:
        seen.add(c["fixture_id"])
        if len(seen) == len({x["fixture_id"] for x in calls}) and first_full is None:
            first_full = c["seq"]

    groups = {}
    for c in calls:
        if c["role"] == "SELF_NOISE_REPEAT" or c["fixture_id"] in repeat_fixtures(
                sorted({x["fixture_id"] for x in calls})):
            groups.setdefault((c["fixture_id"], c["arm"]), 0)
            groups[(c["fixture_id"], c["arm"])] += 1

    return {
        "n_calls": len(calls),
        "n_fixtures": len({c["fixture_id"] for c in calls}),
        "eligibility_seq": eligibility_seq,
        "prefix_n_calls": len(prefix),
        "prefix_n_distinct_fixtures": len(fixtures_in_prefix),
        "prefix_fixtures": fixtures_in_prefix,
        "prefix_calls_per_arm": per_arm_prefix,
        "prefix_contains_both_arms": all(per_arm_prefix[a] > 0 for a in ARMS),
        "seq_at_which_all_fixtures_seen": first_full,
        "repeat_groups": {f"{k[0]}|{k[1]}": v for k, v in sorted(groups.items())},
        "n_repeat_groups_per_arm": {
            a: sum(1 for k, v in groups.items() if k[1] == a and v >= 2) for a in ARMS},
        "arms_adjacent_within_fixture": all(
            calls[i]["fixture_id"] == calls[i + 1]["fixture_id"]
            and {calls[i]["arm"], calls[i + 1]["arm"]} == set(ARMS)
            for i in range(0, len(calls) - 1, 2)),
        "no_fixture_dominates_prefix": (
            max((sum(1 for c in prefix if c["fixture_id"] == f)
                 for f in fixtures_in_prefix), default=0) <= max(2, len(prefix) // 2)),
    }


def freeze_assertions(calls: list, eligibility_seq: int, *,
                      min_prefix_fixtures: int, min_prefix_calls_per_arm: int,
                      min_repeat_groups_per_arm: int) -> list:
    """The §6/§7 hard checks. Returns problems; EMPTY means the sequence may be frozen.

    This function IS the test `balanced_call_order_contains_multiple_fixtures_before_stop`.
    A sequence that cannot satisfy it is not written into a preregistration, so §37's
    "call ordering is fixture-dominated" hard stop is enforced mechanically rather than by
    a reviewer noticing.
    """
    p = order_properties(calls, eligibility_seq)
    problems = []
    if p["prefix_n_distinct_fixtures"] < min_prefix_fixtures:
        problems.append(
            f"the first {eligibility_seq} calls span only "
            f"{p['prefix_n_distinct_fixtures']} fixture(s); a stop rule eligible there "
            f"could halt the run on one fixture's behaviour. Need "
            f">= {min_prefix_fixtures}.")
    for arm in ARMS:
        if p["prefix_calls_per_arm"][arm] < min_prefix_calls_per_arm:
            problems.append(
                f"the first {eligibility_seq} calls contain only "
                f"{p['prefix_calls_per_arm'][arm]} {arm}-arm call(s); a stop rule eligible "
                f"there would fire before the treatment comparison exists. Need "
                f">= {min_prefix_calls_per_arm}.")
    for arm in ARMS:
        if p["n_repeat_groups_per_arm"][arm] < min_repeat_groups_per_arm:
            problems.append(
                f"{arm} arm has {p['n_repeat_groups_per_arm'][arm]} repeat group(s) of "
                f"size >= 2; §9 needs >= {min_repeat_groups_per_arm} across MULTIPLE "
                f"fixtures or the self-noise design is underpowered by construction.")
    if not p["arms_adjacent_within_fixture"]:
        problems.append("A and B are not adjacent within each fixture; a mid-round halt "
                        "would leave an unpaired fixture.")
    return problems


def version_stamp() -> dict:
    return {"schedule_version": SCHEDULE_VERSION,
            "arms": list(ARMS),
            "n_repeat_fixtures": N_REPEAT_FIXTURES,
            "repeats_per_group": REPEATS_PER_GROUP,
            "ordering": "round-robin over fixtures; A/B adjacent; repeats in later rounds",
            "repeat_fixture_rule": "the first N_REPEAT_FIXTURES of the sorted paired list "
                                   "-- deterministic and content-blind",
            "driver_may_expand_counts": False}
