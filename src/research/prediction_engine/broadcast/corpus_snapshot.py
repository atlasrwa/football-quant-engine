"""The training corpus as a provenanced, immutable, prior-only snapshot.

WHY THIS MODULE EXISTS
======================
The broadcast engine used to call ``pilotC_stat_mixer.load_corpus()`` directly and
fit on whatever came back. That worked, and it was silently wrong for three months:
the loader returns whatever is on disk, and nothing on disk was newer than
2026-05-31 while forecasts were being published in September. Nothing in the code
path had an opinion about *when* the data ended, so nobody found out.

This module makes the corpus a first-class artifact with three properties the raw
loader cannot provide:

CONTENT IDENTITY
    :func:`fingerprint_matches` hashes the *set of observations* — every match id
    paired with its kick-off — not the files, not their modification times, and not
    the moment the corpus was built. Rebuilding the same seasons from scratch
    reproduces the same hash; adding one match changes it. This is what makes
    ``model_version`` a statement about data rather than about a build.

    A count-and-max-date summary is not sufficient for this. Two corpora can agree
    on both while containing different matches (swap one observation for another
    of the same date). The hash is over the full sorted observation set precisely so
    that no such substitution is invisible.

AN EXPLICIT CUTOFF
    :func:`build_snapshot` takes a cutoff and admits only matches that had certainly
    finished before it. The cutoff is chosen once per run and recorded, so "what did
    the model know" has an answer that does not depend on when someone re-reads the
    directory.

STRUCTURAL LEAKAGE REFUSAL
    :func:`assert_prior_only_snapshot` and :func:`assert_fixture_absent_from_history`
    raise. They do not warn and they do not filter-and-continue. A result from the
    fixture being forecast, or from any match not yet finished at snapshot time, is
    an integrity failure and has to stop the run — this project has already paid for
    one full re-validation over exactly this class of bug, and the lesson recorded at
    the time was that a convention which is merely documented gets violated.

WHAT "FINISHED" MEANS HERE
==========================
The provider gives kick-off, not final whistle. A match is therefore treated as
finished :data:`MATCH_COMPLETION_SECONDS` after kick-off. That constant is
deliberately generous (longer than any 90-minute match plus stoppages, half-time,
and provider settlement lag) because the failure modes are asymmetric: waiting an
extra hour to admit a result costs nothing, while admitting one an hour early is
leakage.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

#: Bumping this changes every corpus content hash, and therefore every
#: ``model_version``. That is correct: a fingerprint computed under different rules
#: is not comparable to one computed under the old rules.
CORPUS_SNAPSHOT_CONTRACT = "corpus-snapshot/v1"

#: How long after kick-off a match is treated as certainly finished and therefore
#: admissible as a feature input. Generous on purpose — see the module docstring on
#: asymmetric failure modes. 210 minutes covers 90 minutes plus half-time, stoppage,
#: and provider settlement lag without reaching into extra time territory that would
#: matter for a league fixture.
MATCH_COMPLETION_SECONDS = 210 * 60


class CorpusIntegrityError(RuntimeError):
    """The corpus snapshot violates a structural guarantee.

    Raised, never logged-and-continued. Every condition that produces this error
    means a forecast would be computed from data it must not have seen.
    """


class SameMatchLeakageError(CorpusIntegrityError):
    """A fixture's own result is present in the history used to forecast it.

    The specific failure this module exists to make impossible: today's completed
    match being ingested and then used to recompute today's forecast, which turns a
    forecast into a postdiction and is undetectable in the published output.
    """


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(obj: Any) -> bytes:
    """Canonical JSON, matching :mod:`src.persistence.hashing` rules."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _iso(unix: float) -> str:
    return datetime.fromtimestamp(float(unix), timezone.utc).isoformat()


def _match_identity(match: Mapping[str, Any]) -> Optional[tuple[str, int]]:
    """``(match_id, kickoff_unix)`` for one corpus row, or ``None`` if unusable.

    The provider's row id is used when present. When it is absent the identity falls
    back to the natural key (kick-off plus both team names), because a row with no
    stable id must still contribute to the content hash — dropping it would let an
    id-less match change the corpus without changing its fingerprint.
    """
    try:
        kickoff = int(float(match["date_unix"]))
    except (KeyError, TypeError, ValueError):
        return None
    raw_id = match.get("id")
    if raw_id in (None, "", 0, "0"):
        home = str(match.get("home_name") or "")
        away = str(match.get("away_name") or "")
        if not home or not away:
            return None
        return (f"natural:{kickoff}:{home}:{away}", kickoff)
    return (str(raw_id), kickoff)


@dataclass(frozen=True, slots=True)
class CorpusFingerprint:
    """Content identity and coverage of the exact match set a model was fitted on."""

    content_hash: str
    match_count: int
    latest_observation_unix: int
    earliest_observation_unix: int
    seasons: tuple[str, ...]
    season_ids: tuple[int, ...]

    @property
    def latest_observation_utc(self) -> str:
        return _iso(self.latest_observation_unix) if self.match_count else ""

    @property
    def earliest_observation_utc(self) -> str:
        return _iso(self.earliest_observation_unix) if self.match_count else ""

    def provenance_dict(self) -> dict[str, Any]:
        """The publishable provenance block.

        Deliberately small and stable: a reader checking a months-old forecast needs
        to know which observations produced it, how many there were, when they
        stopped, and which competitions they covered.
        """
        return {
            "corpus_content_hash": self.content_hash,
            "corpus_match_count": int(self.match_count),
            "corpus_latest_observation_utc": self.latest_observation_utc,
            "corpus_earliest_observation_utc": self.earliest_observation_utc,
            "corpus_seasons": list(self.seasons),
            "corpus_season_ids": [int(s) for s in self.season_ids],
        }


def fingerprint_matches(matches: Sequence[Mapping[str, Any]]) -> CorpusFingerprint:
    """Content hash and coverage summary for a match set.

    The hash covers the sorted, de-duplicated ``(match_id, kickoff_unix)`` set and
    the season labels present. It is invariant to the order rows were loaded in, to
    which files they came from, and to when those files were written — so a rebuild
    of unchanged seasons is provably a no-op, and any change to the observation set
    is provably visible.

    Args:
        matches: corpus rows in FootyStats schema.

    Returns:
        The fingerprint. An empty input yields a well-defined fingerprint with
        ``match_count == 0`` rather than an error, so callers can hand it to the
        freshness gate and get a clean refusal instead of a traceback.
    """
    identities: set[tuple[str, int]] = set()
    seasons: set[str] = set()
    season_ids: set[int] = set()
    for match in matches:
        identity = _match_identity(match)
        if identity is None:
            continue
        identities.add(identity)
        season = match.get("season")
        if season:
            seasons.add(str(season))
        raw_comp = match.get("competition_id")
        try:
            season_ids.add(int(raw_comp))
        except (TypeError, ValueError):
            pass

    ordered = sorted(identities, key=lambda item: (item[1], item[0]))
    content_hash = _sha256(
        _canonical_json(
            {
                "contract": CORPUS_SNAPSHOT_CONTRACT,
                "observations": [[mid, ko] for mid, ko in ordered],
                "seasons": sorted(seasons),
                "season_ids": sorted(season_ids),
            }
        )
    )
    kickoffs = [ko for _, ko in ordered]
    return CorpusFingerprint(
        content_hash=content_hash,
        match_count=len(ordered),
        latest_observation_unix=max(kickoffs) if kickoffs else 0,
        earliest_observation_unix=min(kickoffs) if kickoffs else 0,
        seasons=tuple(sorted(seasons)),
        season_ids=tuple(sorted(season_ids)),
    )


def assert_prior_only_snapshot(
    matches: Sequence[Mapping[str, Any]],
    *,
    cutoff_unix: float,
    completion_seconds: int = MATCH_COMPLETION_SECONDS,
) -> None:
    """Refuse a snapshot containing any match not certainly finished by ``cutoff_unix``.

    This is the structural half of the leakage constraint. It is checked over the
    whole snapshot once, so an in-play or future match cannot reach *any* fixture's
    features — as opposed to being caught per fixture, where one missed call is a
    silent leak.

    Raises:
        CorpusIntegrityError: naming the offending matches. The message lists them
            because "leakage detected" without the rows is not actionable at 04:00.
    """
    offenders: list[str] = []
    for match in matches:
        try:
            kickoff = float(match["date_unix"])
        except (KeyError, TypeError, ValueError):
            continue
        finished_at = kickoff + completion_seconds
        if finished_at >= float(cutoff_unix):
            offenders.append(
                f"{match.get('id')} {match.get('home_name')} vs "
                f"{match.get('away_name')} kickoff={_iso(kickoff)} "
                f"finishes={_iso(finished_at)}"
            )
        if len(offenders) >= 10:
            break
    if offenders:
        raise CorpusIntegrityError(
            f"corpus snapshot with cutoff {_iso(cutoff_unix)} contains "
            f"{len(offenders)}+ match(es) that had not certainly finished by the "
            "cutoff; these cannot be feature inputs: " + "; ".join(offenders)
        )


def build_snapshot(
    matches: Iterable[Mapping[str, Any]],
    *,
    cutoff_unix: float,
    completion_seconds: int = MATCH_COMPLETION_SECONDS,
) -> tuple[tuple[Mapping[str, Any], ...], CorpusFingerprint]:
    """Freeze the corpus at ``cutoff_unix`` and fingerprint what survived.

    Admits a match only when it had certainly finished before the cutoff. The
    returned tuple is immutable so a later phase of the run cannot append to the
    training set after the fingerprint was taken — the fingerprint would then
    describe something other than what was fitted.

    Args:
        matches: corpus rows in FootyStats schema, already filtered to completed.
        cutoff_unix: the snapshot boundary, normally the start of the run.
        completion_seconds: how long after kick-off a match counts as finished.

    Returns:
        ``(snapshot, fingerprint)``.

    Raises:
        CorpusIntegrityError: if the snapshot it just built violates the prior-only
            guarantee. Self-checking rather than trusting its own filter, because
            the filter is the thing most likely to be edited wrongly later.
    """
    boundary = float(cutoff_unix)
    snapshot: list[Mapping[str, Any]] = []
    for match in matches:
        try:
            kickoff = float(match["date_unix"])
        except (KeyError, TypeError, ValueError):
            continue
        if kickoff + completion_seconds < boundary:
            snapshot.append(match)
    snapshot.sort(key=lambda m: float(m["date_unix"]))
    frozen = tuple(snapshot)
    assert_prior_only_snapshot(
        frozen, cutoff_unix=boundary, completion_seconds=completion_seconds
    )
    return frozen, fingerprint_matches(frozen)


def assert_fixture_absent_from_history(
    histories: Mapping[str, Sequence[tuple[float, Mapping[str, Any], str]]],
    *,
    home_team: str,
    away_team: str,
    kickoff_unix: float,
    completion_seconds: int = MATCH_COMPLETION_SECONDS,
) -> None:
    """Refuse to forecast a fixture whose own result is already in the histories.

    The rolling feature builder takes matches strictly before the fixture kick-off,
    which is correct arithmetic but is only a convention about the inequality. This
    makes the guarantee explicit at the point of use: if the corpus holds a match
    between these two teams at, or close to, this kick-off, the "forecast" would be
    computed with knowledge of the result and must not be produced.

    The window is ``+/- completion_seconds`` around the kick-off rather than an exact
    timestamp match, because providers revise kick-off times by minutes and an exact
    comparison would be defeated by a 15-minute correction.

    Raises:
        SameMatchLeakageError: if the fixture, or a same-pairing match within the
            tolerance window, is present.
    """
    window = float(completion_seconds)
    target = float(kickoff_unix)
    pair = {str(home_team), str(away_team)}
    for team in (str(home_team), str(away_team)):
        for observed_unix, match, _role in histories.get(team, ()):
            if abs(float(observed_unix) - target) > window:
                continue
            observed_pair = {
                str(match.get("home_name") or ""),
                str(match.get("away_name") or ""),
            }
            if observed_pair == pair:
                raise SameMatchLeakageError(
                    f"refusing to forecast {home_team} vs {away_team} at "
                    f"{_iso(target)}: the corpus already contains this fixture "
                    f"(match id {match.get('id')}, kickoff "
                    f"{_iso(observed_unix)}). A forecast cannot use its own result "
                    "as a feature input."
                )


def newest_observation_per_team(
    histories: Mapping[str, Sequence[tuple[float, Mapping[str, Any], str]]],
    teams: Iterable[str],
) -> dict[str, Optional[dict[str, Any]]]:
    """The most recent corpus match for each named team, for provenance reporting.

    Exists so an operator can answer "what does the engine think this team's recent
    form is" without re-deriving it from the corpus by hand. That question had no
    cheap answer while the corpus was stale, which is part of why the staleness
    survived so long.
    """
    out: dict[str, Optional[dict[str, Any]]] = {}
    for team in teams:
        rows = histories.get(str(team)) or ()
        if not rows:
            out[str(team)] = None
            continue
        observed_unix, match, role = max(rows, key=lambda item: float(item[0]))
        out[str(team)] = {
            "match_id": match.get("id"),
            "kickoff_unix": int(float(observed_unix)),
            "kickoff_utc": _iso(observed_unix),
            "home_name": match.get("home_name"),
            "away_name": match.get("away_name"),
            "season": match.get("season"),
            "competition_id": match.get("competition_id"),
            "role": role,
        }
    return out


def observations_per_season(
    matches: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Per-season coverage of a match set: count and newest observation.

    Used by the refresh report and the health report so a partial ingestion (current
    season registered but only half fetched) is visible as a season with an old
    newest-observation, rather than hiding inside a healthy-looking total.
    """
    grouped: dict[str, list[float]] = defaultdict(list)
    labels: dict[str, str] = {}
    for match in matches:
        try:
            kickoff = float(match["date_unix"])
        except (KeyError, TypeError, ValueError):
            continue
        key = str(match.get("competition_id") or "unknown")
        grouped[key].append(kickoff)
        if match.get("season"):
            labels[key] = str(match["season"])
    return {
        season_id: {
            "season": labels.get(season_id),
            "match_count": len(kickoffs),
            "latest_observation_unix": int(max(kickoffs)),
            "latest_observation_utc": _iso(max(kickoffs)),
        }
        for season_id, kickoffs in sorted(grouped.items())
    }
