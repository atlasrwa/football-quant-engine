"""V7.1 deterministic compiler (`v71_compiler_v1`). Sections 5 and 6.

Turns a validated semantic IR into the two observation sets it names -- cohort and baseline --
over a PIT index, at one target fixture.

What is different from V7, and why it matters:

  * **Every declared comparator is executed.** V7's executor branched on two comparators and
    fell through to a single generic subject-vs-subject contrast for the other seven, so a
    `LEAGUE_ENVIRONMENT_BASELINE` question would have been measured as a subject baseline
    question. (No such hypothesis survived V6.1's own qualification filter, so V7 never
    mis-measured one in practice -- but the compiler would have, silently.)
  * **An invalid query never reaches the fold loop.** `assert_valid` runs first and RAISES.
    V7 emitted `signal == 0` for a structurally degenerate hypothesis and let a full
    walk-forward run before classifying it TAUTOLOGICAL.
  * **Unsupported restrictions cannot become empty cohorts.** The IR fails closed upstream;
    by the time a filter reaches this module it is guaranteed executable.
  * **Roles are checked, not assumed.** An `opponent_profile` filter is evaluated against the
    OPPONENT of each prior match. `assert_profile_reads_opponent` makes that a contract, so a
    role inversion is a raised error rather than a plausible-looking number.
  * **Every read is reported.** `fixtures_read` lets the leakage red team prove empirically
    which observations moved a feature, and which could not have.

ZERO SPEND. No network. No CHAMPION.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import invariants as INV
from . import ir as IRM

COMPILER_VERSION = "v71_compiler_v1"

HIGH, MID, LOW = "HIGH", "MID", "LOW"


class CompileRefused(Exception):
    """The query is structurally valid but cannot be evaluated at this fixture."""


@dataclass
class CompiledQuery:
    """The result of compiling one IR at one target fixture."""
    cohort_values: tuple
    baseline_values: tuple
    cohort_weights: tuple
    baseline_weights: tuple
    environment_mean: float | None
    observed: float | None
    fixtures_read: frozenset
    cohort_fixtures: frozenset
    baseline_fixtures: frozenset
    notes: tuple = ()

    def is_degenerate(self) -> bool:
        """True iff the two sides read the SAME observations with the SAME weights."""
        return (self.cohort_fixtures == self.baseline_fixtures
                and self.cohort_weights == self.baseline_weights)


def axis_tercile_band(value, bounds):
    lo, hi = bounds
    return LOW if value < lo else (HIGH if value > hi else MID)


def assert_profile_reads_opponent(entry, subject_id) -> str:
    """An opponent_profile filter must be evaluated on the OPPONENT of the prior match.

    `entry` is a series row `(rec_i, kickoff, competition, is_home, opponent_id)`. Returning
    the opponent id through a checked accessor makes a role inversion impossible to write by
    accident: passing the subject's own id raises instead of producing a plausible number.
    """
    opponent_id = entry[4]
    if str(opponent_id) == str(subject_id):
        raise INV.InvariantViolation(
            [INV.INVALID_ROLE_BINDING],
            "opponent profile would be evaluated on the subject's own observations")
    return str(opponent_id)


def _entity_id(role, rec, subject_id):
    if role == "SUBJECT":
        return subject_id
    if role == "FIXTURE_OPPONENT":
        return str(rec.away_id) if str(rec.home_id) == str(subject_id) else str(rec.home_id)
    return None      # COMPETITION_ENVIRONMENT has no entity


def _passes_filters(entry, filters, *, entity_id, target_is_home, rec,
                    terciles, axis_cache, complement):
    """True iff the prior match satisfies EVERY filter (or, when `complement`, fails any)."""
    if not filters:
        # The complement of "no restriction" is the empty set. Returning False here makes the
        # caller refuse the fixture rather than quietly measuring an unrestricted cohort.
        return not complement
    ok = True
    for f in filters:
        if f.dimension == "historical_venue_conditioning":
            want = f.value
            if want == "TARGET_VENUE":
                got = entry[3] == target_is_home
            elif want == "TARGET_VENUE_OPPONENT":
                got = entry[3] == (not target_is_home)
            else:
                got = entry[3] == (want == "HOME")
        elif f.dimension == "competition":
            got = entry[2] == rec.competition
        elif f.dimension == "opponent_profile":
            opponent_id = assert_profile_reads_opponent(entry, entity_id)
            mv = axis_cache.get((opponent_id, f.axis))
            bounds = terciles.get((entry[2], f.axis))
            if mv is None or not bounds:
                return False          # cannot evaluate this prior match: exclude it
            got = axis_tercile_band(mv, bounds) == f.value
        else:                                          # unreachable: IR fails closed upstream
            raise INV.InvariantViolation(
                [INV.SEMANTICALLY_AMBIGUOUS],
                f"filter dimension {f.dimension!r} reached the compiler")
        ok = ok and got
    return (not ok) if complement else ok


def _select(index, sel, ir, rec, rec_i, subject_id, terciles, axis_cache, similarity):
    """The observation set + weights named by one Selector. Strictly PIT."""
    if sel.entity_role == "COMPETITION_ENVIRONMENT":
        return None, None, frozenset()

    entity_id = _entity_id(sel.entity_role, rec, subject_id)
    target_is_home = (str(rec.home_id) == str(subject_id))
    entries = index.prior_entries(entity_id, rec_i)
    if not entries:
        return (), (), frozenset()

    if sel.similar_to_opponent:
        opponent_id = _entity_id("FIXTURE_OPPONENT", rec, subject_id)
        similar = similarity.similar_opponent_ids(index, opponent_id, rec, rec_i)
        want = sel.similar_to_opponent == "SIMILAR"
        entries = [e for e in entries
                   if (assert_profile_reads_opponent(e, entity_id) in similar) == want]

    entries = [e for e in entries
               if _passes_filters(e, sel.filters, entity_id=entity_id,
                                  target_is_home=target_is_home, rec=rec,
                                  terciles=terciles, axis_cache=axis_cache,
                                  complement=sel.complement)]
    if sel.window == "W5":
        entries = entries[-5:]
    elif sel.window == "W10":
        entries = entries[-10:]
    return entries, entity_id, frozenset(str(index.recs[e[0]].fixture_id) for e in entries)


def compile_query(ir, index, rec_i, *, metric, terciles, axis_cache, similarity,
                  recency, capability=None) -> CompiledQuery:
    """Compile ONE metric of a validated IR at one target fixture.

    Raises `InvariantViolation` for a structurally invalid query and `CompileRefused` when the
    query is valid but this fixture cannot support it.
    """
    INV.assert_valid(ir, capability=capability)

    rec = index.recs[rec_i]
    subject_id = str(rec.home_id) if ir.subject == "HOME_TEAM" else str(rec.away_id)
    observed = index.team_value(rec_i, subject_id, metric, ir.perspective)
    env = index.env_mean(rec.competition, metric, int(rec.kickoff_unix))

    def values_of(entries, entity_id, weighting):
        vals, wts = [], []
        ref = int(rec.kickoff_unix)
        for e in entries:
            v = index.team_value(e[0], entity_id, metric, ir.perspective)
            if v is None:
                continue
            vals.append(v)
            wts.append(recency.weight(e[1], ref) if weighting == "TIME_DECAY" else 1.0)
        return tuple(vals), tuple(wts)

    out = {}
    for name, sel in (("cohort", ir.cohort), ("baseline", ir.baseline)):
        if sel.entity_role == "COMPETITION_ENVIRONMENT":
            if env is None:
                raise CompileRefused("competition environment mean is unavailable")
            out[name] = ((env,), (1.0,), frozenset())
            continue
        entries, entity_id, fixtures = _select(index, sel, ir, rec, rec_i, subject_id,
                                               terciles, axis_cache, similarity)
        if not entries:
            raise CompileRefused(f"{name} selector matched no prior observation")
        vals, wts = values_of(entries, entity_id, sel.weighting)
        if not vals:
            raise CompileRefused(f"{name} selector matched no OBSERVED value")
        out[name] = (vals, wts, fixtures)

    cv, cw, cf = out["cohort"]
    bv, bw, bf = out["baseline"]
    # A comparator can be structurally sound in the IR and still COLLAPSE at a particular
    # fixture -- e.g. SUBJECT_COMPETITION_BASELINE when the subject's entire prior history
    # happens to sit in one competition, so the same-competition cohort IS the all-prior
    # baseline. That fixture carries no contrast, and emitting a zero-valued feature for it
    # would put a structural zero into an out-of-sample distribution. Refuse instead.
    if cf == bf and cw == bw:
        raise CompileRefused(
            "cohort and baseline coincide at this fixture: no contrast exists here")
    return CompiledQuery(cohort_values=cv, baseline_values=bv,
                         cohort_weights=cw, baseline_weights=bw,
                         environment_mean=env, observed=observed,
                         fixtures_read=cf | bf, cohort_fixtures=cf, baseline_fixtures=bf)


def version_stamp() -> dict:
    return {"compiler_version": COMPILER_VERSION,
            "executes_every_declared_comparator": True,
            "asserts_invariants_before_measurement": True,
            "emits_zero_feature_for_invalid_query": False,
            "reports_fixtures_read": True,
            "profile_filters_read_the_opponent": True}
