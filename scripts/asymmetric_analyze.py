#!/usr/bin/env python3
"""Analysis_CLI — on-demand asymmetric matchup analysis for one fixture.

Usage:
    python scripts/asymmetric_analyze.py --home "Leeds" --away "Norwich" \
        --date 2026-09-05

Flow (design's Analysis_CLI section; Req 9):
    1. Parse & validate args; ``--date`` must be ISO 8601 YYYY-MM-DD (Req 9.1).
    2. Build the recognised-team / scheduled-fixture index from the CACHED corpus
       (zero-API by default). Resolve the two team names and the fixture:
       unrecognised -> reject + identify (Req 9.13); ambiguous -> reject + list
       candidates (Req 9.14); no fixture on date -> report + stop (Req 9.15) —
       all WITHOUT predictions.
    3. Cache-then-live-fetch: when required fixture/team data is absent, fetch via
       the CLI-only CappedLiveFetcher up to the spend cap; a breaching fetch is
       refused and terminates with a capped-fetch error (Req 9.16, 12.3, 12.4).
       (Wired here as an injectable hook; the default run is cache-only.)
    4. Coverage handling: zero cached history -> no profile, identify the team,
       stop (Req 9.8); >=1 but < 5 -> flag reduced-coverage, state count vs
       minimum, continue on the reduced profile (Req 9.7).
    5. Narrative + EV sections, then the MANDATORY CAVEAT on every output
       (Req 9.2-9.12, Property 20).

The build/backtest path is strictly zero-API; this CLI is the only place a live
fetch may occur, and only through the capped fetcher (never imported into
build/backtest).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date as _date
from typing import Any, Optional, Sequence

# ``pythonpath=["."]`` makes ``src.*`` importable when run from the repo root.
from src.research.asymmetric.cli import (
    OddsQuote,
    render_analysis,
    render_cap_exceeded,
    render_rejection,
    render_zero_history,
)
from src.research.asymmetric.corpus import BroadCorpusLoader, RichCorpusLoader
from src.research.asymmetric.derived import DerivedOutcomeCombiner
from src.research.asymmetric.interaction import (
    DIRECTION_A,
    FixtureContext,
    InteractionModel,
    RefereeCardRate,
    build_training_observations,
)
from src.research.asymmetric.live_fetch import CappedLiveFetcher, DEFAULT_SPEND_CAP
from src.research.asymmetric.models import FixturePrediction
from src.research.asymmetric.profiles import TeamProfiler
from src.research.asymmetric.resolution import (
    DateParseError,
    FixtureIndex,
    ResolutionStatus,
    parse_iso_date,
    resolve_fixture,
)
from src.research.data_source import ResearchMatch

MIN_HISTORY = 5


#: The FootyStats broad-corpus cache dir written by the on-demand season ingest
#: (``src.discovery.corpus.ingest_on_demand_season``). Imported lazily so a
#: missing discovery module never breaks the rich-only path.
def _broad_corpus_dir() -> Optional[str]:
    """Return the discovery/broad-corpus cache dir, or None if unavailable."""
    try:
        from src.discovery.corpus import CORPUS_CACHE_DIR  # noqa: PLC0415

        return str(CORPUS_CACHE_DIR)
    except Exception:  # pragma: no cover - discovery module optional
        return "/home/ubuntu/data/discovery/corpus"


# Corpus source tags. ``rich`` = TheStatsAPI (10 full profile dimensions);
# ``broad`` = FootyStats (reduced 3-dimension profile, Req 4.3).
SOURCE_RICH = "rich"
SOURCE_BROAD = "broad"


def _load_corpus() -> list[tuple[ResearchMatch, str, str]]:
    """Load rich + broad cached corpora as (match, league_label, source) triples.

    Zero-API: both loaders read cache only (they never import the live-fetch
    path). The rich corpus (TheStatsAPI) carries the fields for all 10 profile
    dimensions; the broad corpus (FootyStats — including any on-demand-ingested
    season such as Brazil Serie A) carries corners/cards/SoT/fouls. Both are
    merged and profiled together on the FULL dimension set (see ``analyze``), so
    each team draws on whatever fields each of its matches provides. Merging
    means an ingested season immediately becomes analysable here without the
    fixture having to live in TheStatsAPI.

    On a team/fixture that appears in BOTH corpora (77 teams overlap by exact
    name — Championship, EPL, Ligue 1/2, La Liga), both sets of matches are
    retained and combined per team by the profiler's identity keying, so the
    team's rich matches populate the rich-only dimensions and its broad matches
    fill the rest. Each loader failure is isolated so one missing cache never
    suppresses the other (the CLI still emits a clean rejection with the caveat
    downstream if nothing loads).
    """
    out: list[tuple[ResearchMatch, str, str]] = []

    # Rich corpus (unchanged behaviour).
    try:
        for lm in RichCorpusLoader().load():
            out.append((lm.match, lm.league, SOURCE_RICH))
    except Exception:  # pragma: no cover - defensive; cache may be absent
        pass

    # Broad corpus (FootyStats), including on-demand-ingested seasons.
    broad_dir = _broad_corpus_dir()
    if broad_dir:
        try:
            for lm in BroadCorpusLoader(cache_dir=broad_dir).load():
                out.append((lm.match, lm.league, SOURCE_BROAD))
        except Exception:  # pragma: no cover - defensive; cache may be absent
            pass

    return out


def _thestatsapi_transport(key: str) -> Any:
    """Cache-first live transport backed by ``scripts/thestatsapi_client.py``.

    This is the ONLY place the on-demand CLI reaches a live API, and it is only
    constructed when the user passes ``--live``. The underlying client is
    itself cache-first (it returns cached JSON without spending when present)
    and enforces its own hard local request cap, so this transport is doubly
    bounded: by the CappedLiveFetcher's per-invocation spend cap AND by the
    client's process-level ceiling. The build/backtest path never imports this.

    ``key`` is the fixture key ``"<home>|<away>|<date_iso>"`` assembled by
    :func:`analyze`; it is used as the client cache key so repeated on-demand
    runs for the same fixture cost zero budget.
    """
    # Imported lazily so importing this module (and the zero-API build/backtest
    # path that may import it transitively) never pulls in an HTTP client.
    from scripts.thestatsapi_client import get_json  # noqa: PLC0415

    cache_key = "asymmetric_ondemand_" + key.replace("|", "_").replace(" ", "_")
    data, _meta = get_json(
        "/fixtures",
        params={"query": key},
        cache_key=cache_key,
        allow_status=(200, 404),
    )
    return data


def _build_fetcher(spend_cap: float) -> CappedLiveFetcher:
    """Construct the capped, reported live fetcher for on-demand analysis.

    Wires the TheStatsAPI transport behind the CappedLiveFetcher so every live
    request is admitted against ``spend_cap`` and reported. Only called when the
    user opts in via ``--live``.
    """
    return CappedLiveFetcher(
        cap=spend_cap, transport=_thestatsapi_transport
    )


def analyze(
    home: str,
    away: str,
    date_iso: str,
    *,
    corpus: Optional[list[tuple[ResearchMatch, str, str]]] = None,
    odds: Optional[Sequence[OddsQuote]] = None,
    fetcher: Optional[CappedLiveFetcher] = None,
    min_history: int = MIN_HISTORY,
) -> str:
    """Produce the CLI output string for one fixture (always caveat-terminated).

    ``corpus`` may be injected (tests) as ``(match, league_label, source)``
    triples, where ``source`` is ``"rich"`` (TheStatsAPI) or ``"broad"``
    (FootyStats); otherwise the merged cached corpora are loaded. Both sources
    are always profiled TOGETHER on the full dimension set: each team draws on
    whatever fields each of its matches carries, so rich matches populate the
    rich-only dimensions and broad matches fill corners/cards/SoT/fouls-based
    dimensions, with any dimension a team has no fields for recorded as
    not-populated rather than fabricated. ``fetcher`` is the capped live fetcher;
    when a required fetch is refused the output is the capped-fetch error
    (Req 12.4). Every return value already carries the mandatory caveat via the
    ``cli`` render functions.
    """
    # 1. Validate date (Req 9.1).
    try:
        day = parse_iso_date(date_iso)
    except DateParseError as exc:
        return render_rejection("INVALID DATE", str(exc))

    if corpus is None:
        corpus = _load_corpus()
    matches = [m for m, _, _ in corpus]
    league_by_league_id = {m.league_id: lbl for m, lbl, _ in corpus}

    # 2. Resolve teams + fixture (Req 9.13-9.15) — never predict on failure.
    index = FixtureIndex(matches)
    resolution = resolve_fixture(home, away, day, index)
    if not resolution.ok:
        if resolution.status == ResolutionStatus.UNRECOGNISED:
            return render_rejection("UNRECOGNISED TEAM", resolution.message)
        if resolution.status == ResolutionStatus.AMBIGUOUS:
            offending = (
                resolution.home
                if not resolution.home.ok
                else resolution.away
            )
            return render_rejection(
                "AMBIGUOUS TEAM",
                offending.message
                + "\ncandidates: "
                + ", ".join(offending.candidates),
            )
        if resolution.status == ResolutionStatus.NO_FIXTURE:
            return render_rejection("NO MATCHING FIXTURE", resolution.message)
        return render_rejection("RESOLUTION FAILED", resolution.message)

    fixture_match = resolution.fixture
    home_team = resolution.home.canonical
    away_team = resolution.away.canonical
    league_label = league_by_league_id.get(fixture_match.league_id, "unknown")
    # Always profile on the FULL (rich) dimension set over the MERGED rich+broad
    # corpus, so every team draws on both sources at once: a match contributes to
    # each dimension only where it actually carries that dimension's fields, so
    # rich (TheStatsAPI) matches populate the rich-only dimensions while broad
    # (FootyStats) matches fill corners/cards/SoT/fouls-based dimensions — and a
    # broad-only team (e.g. a Brazil Serie A side) simply populates the subset it
    # can, with the rest transparently recorded as not-populated (NULL != ZERO).
    # The single profiler below is shared by training and prediction so the
    # feature rows stay consistent.

    # 3. Cache-then-live-fetch hook (Req 9.16, 12.3, 12.4). The default run is
    #    cache-only; a supplied fetcher whose next fetch would breach the cap
    #    terminates here with the capped-fetch error.
    if fetcher is not None:
        outcome = fetcher.fetch(f"{home_team}|{away_team}|{date_iso}")
        if not outcome.admitted:
            return render_cap_exceeded(fetcher.spend_units, fetcher.cap)

    # 4. Point-in-time profiles as of kickoff, all-leagues history (Req 9.7, 9.8).
    #    reduced=False: always the full rich dimension set over the merged corpus
    #    (see the fixture-source note above); broad-only teams populate the subset
    #    of dimensions their fields support, the rest recorded as not-populated.
    profiler = TeamProfiler(min_history=min_history, reduced=False)
    as_of = fixture_match.date_unix
    home_prof = profiler.profile_for_team_at(home_team, as_of, matches)
    away_prof = profiler.profile_for_team_at(away_team, as_of, matches)

    if home_prof.n_history == 0:
        return render_zero_history(home_team)
    if away_prof.n_history == 0:
        return render_zero_history(away_team)

    # 5. Fit the interaction model on cached history strictly before kickoff
    #    (point-in-time; PRE_MATCH cards conditioning = league rate, Req 16.3).
    train = [m for m in matches if m.date_unix < as_of and m.home_goals is not None]
    model = InteractionModel()
    if train:
        model.fit(build_training_observations(train, profiler))

    # League-level expanding card rate for the fixture (PRE_MATCH substitution,
    # Req 16.3): referee assignment is unavailable pre-match, so the CLI always
    # conditions cards on the league-level expanding rate.
    ref_rate = RefereeCardRate()
    card_rate = ref_rate.rate_for_prediction(
        fixture_match.league_id, as_of, matches
    )
    league_rate = card_rate.rate

    ctx = FixtureContext(
        home_team=home_team,
        away_team=away_team,
        date_unix=as_of,
        home_profiles=home_prof,
        away_profiles=away_prof,
        league_id=fixture_match.league_id,
        card_rate_home=league_rate,
        card_rate_away=league_rate,
        referee_substituted_home=True,
        referee_substituted_away=True,
    )
    directions = model.predict_fixture(ctx)
    combiner = DerivedOutcomeCombiner()
    derived = combiner.combine(directions)
    fixture_pred = FixturePrediction(
        home_team=home_team,
        away_team=away_team,
        date_unix=as_of,
        directions=tuple(directions),
        derived=derived,
        independence_assumption=combiner.independence_assumption,
    )

    return render_analysis(
        home_profiles=home_prof,
        away_profiles=away_prof,
        fixture=fixture_pred,
        league_label=league_label,
        date_iso=date_iso,
        min_history=min_history,
        odds=odds,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="asymmetric_analyze",
        description="On-demand asymmetric matchup analysis for one fixture.",
    )
    p.add_argument("--home", required=True, help="home team name")
    p.add_argument("--away", required=True, help="away team name")
    p.add_argument("--date", required=True, help="fixture date, ISO 8601 YYYY-MM-DD")
    p.add_argument(
        "--live",
        action="store_true",
        help=(
            "allow capped live API fetches when required fixture/team data is "
            "absent from cache (default: cache-only, zero-API)"
        ),
    )
    p.add_argument(
        "--spend-cap",
        type=float,
        default=DEFAULT_SPEND_CAP,
        metavar="UNITS",
        help=(
            "maximum cumulative live-fetch spend for this invocation, in units "
            f"(default: {DEFAULT_SPEND_CAP:g}); only meaningful with --live"
        ),
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.spend_cap < 0.0:
        sys.stderr.write("error: --spend-cap must be >= 0\n")
        return 2
    fetcher = _build_fetcher(args.spend_cap) if args.live else None
    output = analyze(args.home, args.away, args.date, fetcher=fetcher)
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
