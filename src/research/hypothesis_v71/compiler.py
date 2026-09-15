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
    """The result of compiling one IR at one target fixture.

    `cohort_n` / `baseline_n` are the OBSERVATION COUNTS behind each side. They are carried
    explicitly because an unrestricted, un-decayed, all-prior selector is served from an O(1)
    prefix cache as a single aggregate rather than as a list of values -- a list would make the
    cost of every fixture linear in the team's whole history.
    """
    cohort_values: tuple
    baseline_values: tuple
    cohort_weights: tuple
    baseline_weights: tuple
    environment_mean: float | None
    observed: float | None
    fixtures_read: frozenset
    cohort_fixtures: frozenset
    baseline_fixtures: frozenset
    cohort_n: int = 0
    baseline_n: int = 0
    fixtures_collected: bool = True
    notes: tuple = ()

    def mean(self, side: str) -> float:
        vals = self.cohort_values if side == "cohort" else self.baseline_values
        wts = self.cohort_weights if side == "cohort" else self.baseline_weights
        return sum(w * v for w, v in zip(wts, vals)) / sum(wts)

    def is_degenerate(self) -> bool:
        """True iff the two sides read the SAME observations with the SAME weights.

        When fixture sets were not collected (the engine's hot path), the equivalent test is
        that both sides carry the same observation count AND the same weighted mean.
        """
        if self.fixtures_collected:
            return (self.cohort_fixtures == self.baseline_fixtures
                    and self.cohort_weights == self.baseline_weights)
        return (self.cohort_n == self.baseline_n and self.cohort_n > 0
                and abs(self.mean("cohort") - self.mean("baseline")) <= 1e-15)


def is_plain(sel) -> bool:
    """A selector that is the entity's whole un-decayed prior history: no restriction, no
    complement, no similarity, all-prior, uniform. These are O(1) from the prefix cache."""
    return (not sel.filters and not sel.complement and not sel.similar_to_opponent
            and sel.window == "ALL_PRIOR" and sel.weighting == "UNIFORM")


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

    if sel.filters:
        entries = [e for e in entries
                   if _passes_filters(e, sel.filters, entity_id=entity_id,
                                      target_is_home=target_is_home, rec=rec,
                                      terciles=terciles, axis_cache=axis_cache,
                                      complement=sel.complement)]
    elif sel.complement:
        # the complement of "no restriction" is the empty set
        entries = []
    if sel.window == "W5":
        entries = entries[-5:]
    elif sel.window == "W10":
        entries = entries[-10:]
    return entries, entity_id, frozenset(str(index.recs[e[0]].fixture_id) for e in entries)


def compile_query(ir, index, rec_i, *, metric, terciles, axis_cache, similarity,
                  recency, capability=None, collect_fixtures=True) -> CompiledQuery:
    """Compile ONE metric of a validated IR at one target fixture.

    Raises `InvariantViolation` for a structurally invalid query and `CompileRefused` when the
    query is valid but this fixture cannot support it.

    `collect_fixtures=False` skips materialising the identifier set of a plain selector, which
    is the only reason a fixture would cost time proportional to the team's whole history. The
    point-in-time proof runs with it ON, so nothing about the guarantee is traded away.
    """
    INV.assert_valid(ir, capability=capability)

    rec = index.recs[rec_i]
    subject_id = str(rec.home_id) if ir.subject == "HOME_TEAM" else str(rec.away_id)
    observed = index.team_value(rec_i, subject_id, metric, ir.perspective)
    env = index.env_mean(rec.competition, metric, int(rec.kickoff_unix))

    def values_of(entries, entity_id, weighting):
        vals, wts = [], []
        ref = int(rec.kickoff_unix)
        if weighting != "TIME_DECAY":
            for e in entries:
                v = index.team_value(e[0], entity_id, metric, ir.perspective)
                if v is not None:
                    vals.append(v)
                    wts.append(1.0)
            return tuple(vals), tuple(wts)
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
            out[name] = ((env,), (1.0,), frozenset(), 1)
            continue
        if is_plain(sel) and not collect_fixtures:
            entity_id = _entity_id(sel.entity_role, rec, subject_id)
            mean, n = index.pit_mean(entity_id, metric, sel.perspective, rec_i)
            if mean is None or n == 0:
                raise CompileRefused(f"{name} selector matched no OBSERVED value")
            out[name] = ((mean,), (1.0,), frozenset(), n)
            continue
        entries, entity_id, fixtures = _select(index, sel, ir, rec, rec_i, subject_id,
                                               terciles, axis_cache, similarity)
        if not entries:
            raise CompileRefused(f"{name} selector matched no prior observation")
        vals, wts = values_of(entries, entity_id, sel.weighting)
        if not vals:
            raise CompileRefused(f"{name} selector matched no OBSERVED value")
        out[name] = (vals, wts, fixtures, len(vals))

    cv, cw, cf, cn = out["cohort"]
    bv, bw, bf, bn = out["baseline"]
    # A comparator can be structurally sound in the IR and still COLLAPSE at a particular
    # fixture -- e.g. SUBJECT_COMPETITION_BASELINE when the subject's entire prior history
    # happens to sit in one competition, so the same-competition cohort IS the all-prior
    # baseline. That fixture carries no contrast, and emitting a zero-valued feature for it
    # would put a structural zero into an out-of-sample distribution. Refuse instead.
    q = CompiledQuery(cohort_values=cv, baseline_values=bv,
                      cohort_weights=cw, baseline_weights=bw,
                      environment_mean=env, observed=observed,
                      fixtures_read=cf | bf, cohort_fixtures=cf, baseline_fixtures=bf,
                      cohort_n=cn, baseline_n=bn, fixtures_collected=collect_fixtures)
    if q.is_degenerate():
        raise CompileRefused(
            "cohort and baseline coincide at this fixture: no contrast exists here")
    return q


def version_stamp() -> dict:
    return {"compiler_version": COMPILER_VERSION,
            "executes_every_declared_comparator": True,
            "asserts_invariants_before_measurement": True,
            "emits_zero_feature_for_invalid_query": False,
            "reports_fixtures_read": True,
            "profile_filters_read_the_opponent": True}
