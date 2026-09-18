"""V8C target-blind index (`v8c_blind_index_v2`) -- P1 BLIND-SEAL, defense in depth for P0.

THE SEAL IS PROCESS SEPARATION. This wrapper is the SECOND layer, not the first: the primary
guarantee is that the pre-T selection process (`select_freeze.py`) never imports a scorer and
exits before the scoring process (`score_frozen.py`) starts. See V8C_OUTCOME_SEAL_SPEC.md.

WHAT V1 GOT WRONG
-----------------
V1 guarded `team_value` but re-exported `.recs`, `.vals`, `.series`, `.pos` and `.comp_idx` as
plain passthrough properties. `vals[metric][target_pos]` is the target's own (home, away) pair
-- the outcome, handed over directly -- and `recs[target_pos].base` carries the same numbers in
raw provider form. The wrapper announced a seal it did not have.

WHAT V2 DOES
------------
  * `team_value` at a sealed position returns None (or raises, under strict).
  * `.vals` is a SEALED VIEW: indexing metric -> position at a sealed position yields None.
  * `.recs` returns a SANITIZED record at a sealed position: `fixture_id`, `competition`,
    `kickoff_unix`, `home`/`away`, `home_id`/`away_id` preserved (the compiler genuinely needs
    them for entity resolution and the PIT cutoff), while `base`, `rich` and `extra` -- every
    observed statistic -- are EMPTY.
  * every read is counted, and any SERVED sealed observation sets `target_outcomes_viewed`.

`compile_query` needs `index.recs[rec_i].competition/kickoff_unix/home_id/away_id`, and so do
`_entity_id`, `_select` and `unique_opponents_of_cohort`. All of those are metadata, so the
sanitized record satisfies every legitimate pre-T consumer while carrying no statistic.

ZERO SPEND. No network. No CHAMPION.
"""
from __future__ import annotations

from dataclasses import dataclass

BLIND_INDEX_VERSION = "v8c_blind_index_v2"

#: Record attributes that are pure metadata and may be served for a sealed fixture.
SAFE_RECORD_FIELDS = ("fixture_id", "competition", "competition_id", "season_id",
                      "kickoff_unix", "home", "away", "home_id", "away_id")
#: Record attributes that carry observed statistics and must be emptied for a sealed fixture.
SEALED_RECORD_FIELDS = ("base", "rich", "extra")


class TargetOutcomeReadAttempt(Exception):
    """A caller tried to read a sealed target's observations under strict mode."""


@dataclass(frozen=True)
class SanitizedRecord:
    """A sealed fixture's METADATA. Every statistic block is empty, by construction."""
    fixture_id: str
    competition: str
    competition_id: str
    season_id: str
    kickoff_unix: int
    home: str
    away: str
    home_id: str
    away_id: str
    base: dict
    rich: dict
    extra: dict
    sealed: bool = True


def sanitize(rec) -> SanitizedRecord:
    return SanitizedRecord(
        fixture_id=str(rec.fixture_id), competition=rec.competition,
        competition_id=getattr(rec, "competition_id", ""),
        season_id=getattr(rec, "season_id", ""), kickoff_unix=int(rec.kickoff_unix),
        home=rec.home, away=rec.away, home_id=str(rec.home_id), away_id=str(rec.away_id),
        base={}, rich={}, extra={})


class _SealedRecs:
    """`index.recs` with sealed positions replaced by sanitized records."""

    def __init__(self, recs, sealed, audit, strict):
        self._recs, self._sealed, self._audit, self._strict = recs, sealed, audit, strict

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self._recs)))]
        if int(i) in self._sealed:
            self._audit["sanitized_record_reads"] += 1
            if self._strict:
                raise TargetOutcomeReadAttempt(f"record read at sealed position {i}")
            return sanitize(self._recs[i])
        return self._recs[i]

    def __len__(self):
        return len(self._recs)

    def __iter__(self):
        for i in range(len(self._recs)):
            yield self[i]


class _SealedVals:
    """`index.vals` with sealed positions yielding None."""

    def __init__(self, vals, sealed, audit, strict):
        self._vals, self._sealed, self._audit, self._strict = vals, sealed, audit, strict

    def __getitem__(self, metric):
        return _SealedMetricVals(self._vals[metric], self._sealed, self._audit, self._strict,
                                 metric)

    def __contains__(self, metric):
        return metric in self._vals

    def keys(self):
        return self._vals.keys()


class _SealedMetricVals:
    def __init__(self, row, sealed, audit, strict, metric):
        self._row, self._sealed, self._audit = row, sealed, audit
        self._strict, self._metric = strict, metric

    def __getitem__(self, i):
        if int(i) in self._sealed:
            self._audit["blocked_vals_reads"] += 1
            if self._strict:
                raise TargetOutcomeReadAttempt(
                    f"vals[{self._metric!r}][{i}] at sealed position")
            return None
        return self._row[i]

    def __len__(self):
        return len(self._row)


class TargetBlindIndex:
    """A PIT index with one or more target positions SEALED at every accessor."""

    def __init__(self, index, sealed_positions, *, strict: bool = False):
        self._index = index
        self._sealed = frozenset(int(p) for p in sealed_positions)
        self._strict = bool(strict)
        self.audit = {"team_value_calls": 0, "prior_entries_calls": 0, "pit_mean_calls": 0,
                      "env_mean_calls": 0, "blocked_target_reads": 0,
                      "served_target_reads": 0, "sanitized_record_reads": 0,
                      "blocked_vals_reads": 0, "blocked_positions": set()}

    # ---- sealed structural views ---------------------------------------------------------
    @property
    def recs(self):
        return _SealedRecs(self._index.recs, self._sealed, self.audit, self._strict)

    @property
    def vals(self):
        return _SealedVals(self._index.vals, self._sealed, self.audit, self._strict)

    # ---- delegated, genuinely PIT-safe structure ------------------------------------------
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
    def sealed_positions(self):
        return self._sealed

    # ---- guarded reads -------------------------------------------------------------------
    def team_value(self, rec_i, team_id, metric, perspective):
        self.audit["team_value_calls"] += 1
        if int(rec_i) in self._sealed:
            self.audit["blocked_target_reads"] += 1
            self.audit["blocked_positions"].add(int(rec_i))
            if self._strict:
                raise TargetOutcomeReadAttempt(
                    f"team_value at sealed position {rec_i} ({metric}/{perspective})")
            return None
        return self._index.team_value(rec_i, team_id, metric, perspective)

    def prior_entries(self, team_id, before_rec_i):
        self.audit["prior_entries_calls"] += 1
        entries = self._index.prior_entries(team_id, before_rec_i)
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
        return {"blind_index_version": BLIND_INDEX_VERSION,
                "n_sealed_positions": len(self._sealed), "strict": self._strict,
                "team_value_calls": self.audit["team_value_calls"],
                "prior_entries_calls": self.audit["prior_entries_calls"],
                "pit_mean_calls": self.audit["pit_mean_calls"],
                "env_mean_calls": self.audit["env_mean_calls"],
                "blocked_target_reads": self.audit["blocked_target_reads"],
                "blocked_vals_reads": self.audit["blocked_vals_reads"],
                "sanitized_record_reads": self.audit["sanitized_record_reads"],
                "served_target_reads": self.audit["served_target_reads"],
                "n_distinct_blocked_positions": len(self.audit["blocked_positions"]),
                "target_outcomes_viewed": self.audit["served_target_reads"] > 0}


def version_stamp() -> dict:
    return {"blind_index_version": BLIND_INDEX_VERSION,
            "successor_to": "v8c_blind_index_v1",
            "repairs": ["P1-BLIND-SEAL"],
            "primary_seal": "process separation (select_freeze.py / score_frozen.py)",
            "this_layer": "defense in depth",
            "v1_hole": ("`.recs`, `.vals`, `.series` were plain passthroughs, so "
                        "vals[metric][target_pos] and recs[target_pos].base handed over the "
                        "target's own observations"),
            "sealed_accessors": ["team_value", "vals", "recs", "prior_entries"],
            "safe_record_fields": list(SAFE_RECORD_FIELDS),
            "sealed_record_fields": list(SEALED_RECORD_FIELDS),
            "frozen_compiler_runs_unmodified_against_it": True}
