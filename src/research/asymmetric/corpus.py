"""Cached corpus loaders (zero-API) for the Rich and Broad corpora.

Responsibility:
    ``RichCorpusLoader`` loads the ~3,189-match TheStatsAPI corpus (Championship,
    Ligue 2, La Liga 2, plus any cached EPL) and ``BroadCorpusLoader`` loads the
    ~15,362-match FootyStats corpus, both **from cache only**. Loaders accept an
    injected data source / client that reads cache exclusively, MUST never import
    the live-fetch path, and preserve NULL != ZERO field semantics from the
    normalizer (Requirements 4.1, 4.2, 12.1, 12.2, 13.4).

Design decisions:
    * **Reuse, do not reimplement.** The Rich loader reuses
      ``scripts/multisrc_corpus.py`` (the ``LEAGUES`` registry and
      ``load_season`` / ``load_fixtures``, which in turn reuse
      ``scripts/championship_adapter.adapt_match``) to adapt raw TheStatsAPI
      stats into a FootyStats-schema match dict; this module only maps that dict
      into the universal :class:`ResearchMatch` and never re-derives stats. The
      Broad loader reuses ``src.research.footystats`` — the same
      :class:`MatchNormalizer` used by ``FootyStatsDataSource`` — so the -1
      "unplayed" sentinel and null-odds handling behave identically.
    * **NULL != ZERO preserved.** A field that is absent or ``null`` stays
      ``None``; a real zero stays ``0``. The Rich mapping copies adapter cells
      through unchanged (``None`` stays ``None``), and the Broad mapping delegates
      to :class:`MatchNormalizer`, whose ``_safe_int`` maps the FootyStats ``-1``
      sentinel to ``None`` (not-populated) while preserving genuine zeros.
    * **Zero-API by construction.** Neither loader imports ``live_fetch``. Both
      accept an injected source; an injected client that raises on any network
      call is therefore never invoked, because the loaders only read cache files
      already on disk (Property 23).
    * **League identity per match.** ``ResearchMatch.league_id`` carries the
      league identity, and :meth:`LoadedMatch` pairs each match with a
      human-readable league label so downstream code can filter/report per
      league (Req 4).

This module deliberately imports nothing from Pilot C, Pipeline A, manual work,
or flagged ledgers (isolation, Req 13.2).
"""

from __future__ import annotations

import glob
import importlib.util
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from src.research.data_source import ResearchMatch
from src.research.footystats.normalizer import MatchNormalizer

# --------------------------------------------------------------------------- #
# Reuse scripts/multisrc_corpus.py without turning ``scripts`` into a package.
# The scripts directory is not importable as ``scripts.multisrc_corpus`` in this
# codebase (no package marker / sys.path entry), so we load it by file path.
# This keeps the Rich loader a thin adapter over the EXISTING loader rather than
# a reimplementation.
# --------------------------------------------------------------------------- #
_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"


def _load_multisrc_module() -> Any:
    """Import ``scripts/multisrc_corpus.py`` by path (cache-only, no network)."""
    path = _SCRIPTS_DIR / "multisrc_corpus.py"
    spec = importlib.util.spec_from_file_location("_asym_multisrc_corpus", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load multisrc_corpus from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Default cache locations (cache-only; never fetched here).
RICH_CACHE_DIR = "/home/ubuntu/data/thestatsapi/championship"
BROAD_CACHE_DIR = "/home/ubuntu/.cache/footystats_forward"


class NetworkAccessError(RuntimeError):
    """Raised by cache-only sources if a network call is ever attempted.

    The build/backtest path must be strictly zero-API (Req 12.1, 12.2). A source
    that raises this on any network method can be injected into the loaders to
    prove, by construction, that no network call is made.
    """


@dataclass(frozen=True)
class LoadedMatch:
    """A cached match paired with its human-readable league identity.

    ``match`` is the universal :class:`ResearchMatch` (``match.league_id`` carries
    the machine league id); ``league`` is a readable label (e.g. ``"Championship"``,
    ``"Ligue 2"``) so downstream code can filter and report per league (Req 4)
    without re-deriving it from the id.
    """

    match: ResearchMatch
    league: str


# --------------------------------------------------------------------------- #
# Rich corpus (TheStatsAPI)
# --------------------------------------------------------------------------- #
def _iso_to_unix(iso: str) -> int:
    """Convert an ISO-8601 UTC timestamp to a unix seconds int."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return int(dt.timestamp())


def _adapted_to_research_match(
    adapted: dict[str, Any], league_id: int, season: str
) -> ResearchMatch:
    """Map a championship_adapter FootyStats-schema dict to a ResearchMatch.

    NULL != ZERO: cells are copied through unchanged. ``adapt_match`` yields
    ``None`` for stats whose source cell was absent/null; those stay ``None``
    here. Genuine zeros (e.g. a real 0 corners) are preserved as ``0``. The only
    coercion is the one the adapter itself already applies (red cards null -> 0),
    which we do not reverse.

    Corners and shots-on-target come from the adapter's ``_rich`` block
    (home, away) tuples, which are ``None`` when the source cell was absent.
    """
    rich = adapted.get("_rich") or {}

    def rich_pair(name: str) -> tuple[Optional[int], Optional[int]]:
        pair = rich.get(name)
        if not pair:
            return (None, None)
        h, a = pair
        return (
            int(h) if h is not None else None,
            int(a) if a is not None else None,
        )

    ch, ca = rich_pair("corner_kicks")
    total_corners = (ch + ca) if (ch is not None and ca is not None) else None

    yc_h = adapted.get("team_a_yellow_cards")
    yc_a = adapted.get("team_b_yellow_cards")
    rc_h = adapted.get("team_a_red_cards")
    rc_a = adapted.get("team_b_red_cards")
    card_parts = [c for c in (yc_h, yc_a, rc_h, rc_a) if c is not None]
    total_cards = sum(card_parts) if card_parts else None

    gh = adapted.get("homeGoalCount")
    ga = adapted.get("awayGoalCount")
    total_goals = adapted.get("overallGoalCount")

    return ResearchMatch(
        match_id=_coerce_match_id(adapted.get("match_id")),
        date_unix=int(adapted["date_unix"]),
        league_id=league_id,
        season=str(season),
        home_team=str(adapted.get("home_name", "")),
        away_team=str(adapted.get("away_name", "")),
        home_goals=gh,
        away_goals=ga,
        total_goals=total_goals,
        shots_on_target_home=adapted.get("team_a_shotsOnTarget"),
        shots_on_target_away=adapted.get("team_b_shotsOnTarget"),
        corners_home=ch,
        corners_away=ca,
        total_corners=total_corners,
        yellow_cards_home=yc_h,
        yellow_cards_away=yc_a,
        red_cards_home=rc_h,
        red_cards_away=rc_a,
        total_cards=total_cards,
        fouls_home=adapted.get("team_a_fouls"),
        fouls_away=adapted.get("team_b_fouls"),
        home_xg=adapted.get("team_a_xg"),
        away_xg=adapted.get("team_b_xg"),
    )


def _coerce_match_id(raw_id: Any) -> int:
    """Coerce a possibly-string match id (e.g. ``"mt_010470109"``) to int.

    TheStatsAPI ids are strings like ``mt_010470109``; ResearchMatch.match_id is
    typed ``int``. We keep the numeric suffix so ids remain stable and unique.
    """
    if isinstance(raw_id, int):
        return raw_id
    s = str(raw_id)
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else abs(hash(s))


class RichCorpusLoader:
    """Loads the Rich_Corpus (TheStatsAPI) from cache only (Req 4.1, 12.1, 12.2).

    Reuses ``scripts/multisrc_corpus.py`` for fixture/stats loading and stat
    adaptation, then maps each adapted match into a :class:`ResearchMatch` while
    preserving NULL != ZERO semantics. Every returned :class:`LoadedMatch`
    carries its league label so downstream code can report per league.

    Zero-API: this class never imports ``live_fetch`` and only reads files that
    already exist under the cache directory. An optional ``source`` may be
    injected (any object with a ``load_season(tag, season_id)`` and
    ``LEAGUES`` mapping, or a module-like object); if it raises on network the
    loader still never triggers it beyond cached reads.
    """

    def __init__(
        self,
        cache_dir: str = RICH_CACHE_DIR,
        source: Optional[Any] = None,
    ) -> None:
        self._cache_dir = cache_dir
        # ``source`` is the injected data source. Default reuses multisrc_corpus.
        self._source = source if source is not None else _load_multisrc_module()
        # Point the reused loader at the requested cache dir (cache-only).
        if hasattr(self._source, "CACHE"):
            try:
                self._source.CACHE = cache_dir
            except Exception:  # pragma: no cover - defensive
                pass

    @property
    def leagues(self) -> dict[str, Any]:
        return getattr(self._source, "LEAGUES", {})

    def _league_id_for(self, comp: str, tag: str) -> int:
        """Derive a stable integer league id from the competition tag."""
        # ``comp`` is a readable slug (e.g. "championship"); hash to a stable id.
        return abs(hash((comp, tag))) % (10**8)

    def load(self) -> list[LoadedMatch]:
        """Load all cached Rich_Corpus matches as LoadedMatch, sorted by date."""
        out: list[LoadedMatch] = []
        leagues = self.leagues
        for tag, meta in leagues.items():
            display = meta.get("display", tag)
            comp = meta.get("comp", tag)
            league_id = self._league_id_for(comp, tag)
            for season_id in meta.get("seasons", []):
                # Skip seasons whose fixture file is not cached (cache-only).
                fx_path = self._source.fixture_path(tag, season_id)
                if not os.path.exists(fx_path):
                    continue
                adapted_matches = self._source.load_season(tag, season_id)
                for adapted in adapted_matches:
                    rm = _adapted_to_research_match(adapted, league_id, season_id)
                    out.append(LoadedMatch(match=rm, league=display))
        out.sort(key=lambda lm: lm.match.date_unix)
        return out

    def load_matches(self) -> list[ResearchMatch]:
        """Convenience: just the :class:`ResearchMatch` list (Req 4.1)."""
        return [lm.match for lm in self.load()]


# --------------------------------------------------------------------------- #
# Broad corpus (FootyStats)
# --------------------------------------------------------------------------- #
class CacheOnlyFootyStatsSource:
    """A cache-only FootyStats source: reads cached league-matches JSON files.

    This is the default injected source for :class:`BroadCorpusLoader`. It reads
    the ``league-matches_*.json`` files the FootyStats client writes under its
    cache directory and returns their raw ``data`` arrays. It performs NO network
    I/O; there is deliberately no HTTP client here, so the zero-API guarantee
    holds by construction (Req 12.1, 12.2).
    """

    def __init__(self, cache_dir: str = BROAD_CACHE_DIR) -> None:
        self._cache_dir = cache_dir

    def iter_raw_records(self) -> Iterable[dict[str, Any]]:
        pattern = os.path.join(self._cache_dir, "league-matches_*.json")
        for path in sorted(glob.glob(pattern)):
            with open(path, "r") as fh:
                payload = json.load(fh)
            for rec in payload.get("data", []):
                yield rec


class BroadCorpusLoader:
    """Loads the Broad_Corpus (FootyStats) from cache only (Req 4.2, 12.1, 12.2).

    Reuses :class:`MatchNormalizer` (the same normalizer used by
    ``FootyStatsDataSource``) so that the FootyStats ``-1`` "unplayed" sentinel is
    surfaced as *not-populated* (``None``) rather than a real value, genuine zeros
    are preserved, and only ``status == "complete"`` matches are admitted
    (NULL != ZERO, Req 12 audit note).

    A ``source`` exposing ``iter_raw_records()`` may be injected; the default is
    :class:`CacheOnlyFootyStatsSource`. The loader never imports ``live_fetch``
    and makes no network call.
    """

    def __init__(
        self,
        cache_dir: str = BROAD_CACHE_DIR,
        source: Optional[Any] = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._source = source if source is not None else CacheOnlyFootyStatsSource(cache_dir)
        self._normalizer = MatchNormalizer()

    @property
    def normalizer(self) -> MatchNormalizer:
        return self._normalizer

    def _league_label(self, match: ResearchMatch) -> str:
        """Readable league label for a broad-corpus match.

        The FootyStats broad corpus spans many leagues; we surface the numeric
        competition id as the label (``"league_<id>"``) so downstream code can
        still filter/group per league without inventing names it cannot verify.
        """
        return f"league_{match.league_id}"

    def load(self) -> list[LoadedMatch]:
        """Load all cached, completed Broad_Corpus matches as LoadedMatch."""
        out: list[LoadedMatch] = []
        for raw in self._source.iter_raw_records():
            rm = self._normalizer.normalize(raw)
            if rm is None:
                continue
            out.append(LoadedMatch(match=rm, league=self._league_label(rm)))
        out.sort(key=lambda lm: lm.match.date_unix)
        return out

    def load_matches(self) -> list[ResearchMatch]:
        """Convenience: just the :class:`ResearchMatch` list (Req 4.2)."""
        return [lm.match for lm in self.load()]
