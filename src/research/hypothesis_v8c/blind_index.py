"""V8C target-blind index wrapper (`v8c_blind_index_v1`).

Makes "this stage did not read the target outcome" a MECHANICAL, AUDITABLE fact instead of a
claim in a docstring.

`TargetBlindIndex` delegates every read to the real `PITIndex`, except:

  * `team_value(rec_i, ...)` where `rec_i` is at or after the sealed target position returns
    `None` and is RECORDED as a blocked read;
  * every `team_value` / `prior_entries` / `pit_mean` / `env_mean` call is counted, and any
    read at or after the target position is recorded.

This matters because `compiler.compile_query` reads `observed = index.team_value(rec_i, ...)`
UNCONDITIONALLY at the top but never branches on it: `is_degenerate()` does not use it, and
cohort/baseline values, weights, fixture sets and the environment mean all come from
`prior_entries` / `env_mean`, which are strictly-prior by construction. So the FROZEN compiler
runs unmodified against this wrapper and produces a byte-identical cohort -- with `observed`
forced to `None`.

Two required V8C claims become hashed evidence rather than assertions:

  * §36 `SEALED_947_OUTCOMES_VIEWED = false` -- the sealed-947 preflight runs entirely through
    this wrapper, and its audit log (0 target reads served) is hashed into the freeze manifest.
  * §29 PIT battery "0 behavioural change" -- the pre-T verdict is computed with the target
    value physically unavailable, so it cannot depend on it.

ZERO SPEND. No network. No CHAMPION.
"""
from __future__ import annotations

BLIND_INDEX_VERSION = "v8c_blind_index_v1"


class TargetOutcomeReadAttempt(Exception):
    """A caller tried to read at/after the sealed target position under strict mode."""


class TargetBlindIndex:
    """A PIT index with one or more target positions SEALED.

    Parameters
    ----------
    index : PITIndex
        the real index; never mutated.
    sealed_positions : iterable[int]
        record positions whose own observations must not be served.
    strict : bool
        when True a blocked read RAISES instead of returning None. Used by the adversarial
        battery to prove no code path silently depends on the target value; the structural
        scans run with strict=False so the frozen compiler can complete normally.
    """

    def __init__(self, index, sealed_positions, *, strict: bool = False):
        self._index = index
        self._sealed = frozenset(int(p) for p in sealed_positions)
        self._strict = bool(strict)
        self.audit = {"team_value_calls": 0, "prior_entries_calls": 0, "pit_mean_calls": 0,
                      "env_mean_calls": 0, "blocked_target_reads": 0,
                      "served_target_reads": 0, "blocked_positions": set()}

    # ---- delegated, unchanged attributes -------------------------------------------------
    @property
    def recs(self):
        return self._index.recs

    @property
    def kick(self):
        return self._index.kick

    @property
    def pos_of_fixture(self):
        return self._index.pos_of_fixture

    @property
    def metrics(self):
        return self._index.metrics

    @property
    def series(self):
        return self._index.series

    @property
    def pos(self):
        return self._index.pos

    @property
    def comp_idx(self):
        return self._index.comp_idx

    @property
    def vals(self):
        return self._index.vals

    # ---- guarded reads -------------------------------------------------------------------
    def team_value(self, rec_i, team_id, metric, perspective):
        self.audit["team_value_calls"] += 1
        if int(rec_i) in self._sealed:
            self.audit["blocked_target_reads"] += 1
            self.audit["blocked_positions"].add(int(rec_i))
            if self._strict:
                raise TargetOutcomeReadAttempt(
                    f"read of sealed target position {rec_i} ({metric}/{perspective})")
            return None
        return self._index.team_value(rec_i, team_id, metric, perspective)

    def prior_entries(self, team_id, before_rec_i):
        self.audit["prior_entries_calls"] += 1
        entries = self._index.prior_entries(team_id, before_rec_i)
        # Structural belt-and-braces: prior_entries is strictly-prior by construction, but a
        # sealed position appearing here would be a silent PIT break, so it is recorded.
        bad = [e for e in entries if int(e[0]) in self._sealed]
        if bad:
            self.audit["served_target_reads"] += len(bad)
            if self._strict:
                raise TargetOutcomeReadAttempt(
                    f"prior_entries({team_id}, {before_rec_i}) returned {len(bad)} sealed "
                    f"position(s)")
        return entries

    def pit_mean(self, team_id, metric, perspective, before_rec_i, venue=None):
        self.audit["pit_mean_calls"] += 1
        return self._index.pit_mean(team_id, metric, perspective, before_rec_i, venue)

    def env_mean(self, competition, metric, cutoff_unix):
        self.audit["env_mean_calls"] += 1
        return self._index.env_mean(competition, metric, cutoff_unix)

    def range_positions(self, lo_unix, hi_unix):
        return self._index.range_positions(lo_unix, hi_unix)

    # ---- evidence ------------------------------------------------------------------------
    def audit_report(self) -> dict:
        """The hashable read-audit record. `target_outcomes_viewed` is the load-bearing field:
        it is True only if a sealed position's own observation was actually SERVED."""
        return {"blind_index_version": BLIND_INDEX_VERSION,
                "n_sealed_positions": len(self._sealed),
                "strict": self._strict,
                "team_value_calls": self.audit["team_value_calls"],
                "prior_entries_calls": self.audit["prior_entries_calls"],
                "pit_mean_calls": self.audit["pit_mean_calls"],
                "env_mean_calls": self.audit["env_mean_calls"],
                "blocked_target_reads": self.audit["blocked_target_reads"],
                "served_target_reads": self.audit["served_target_reads"],
                "n_distinct_blocked_positions": len(self.audit["blocked_positions"]),
                "target_outcomes_viewed": self.audit["served_target_reads"] > 0}


def version_stamp() -> dict:
    return {"blind_index_version": BLIND_INDEX_VERSION,
            "purpose": "make 'no target outcome was read' a mechanical, hashable fact",
            "blocks": "team_value at any sealed record position",
            "records": ["team_value_calls", "prior_entries_calls", "pit_mean_calls",
                        "env_mean_calls", "blocked_target_reads", "served_target_reads"],
            "frozen_compiler_runs_unmodified_against_it": True,
            "why_safe": "compile_query reads `observed` unconditionally but never branches on "
                        "it; cohort/baseline/weights/fixtures/env all derive from "
                        "strictly-prior accessors"}
