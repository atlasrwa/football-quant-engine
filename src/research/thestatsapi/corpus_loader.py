"""Cache-backed loader for TheStatsAPI payloads.

Loads fixtures / stats / odds payloads from a directory of cached JSON files
(the shape under ``data/thestatsapi/championship/``) WITHOUT any network
access. This is the point-in-time-safe path used by research and tests: it
reads only files that already exist on disk and never fabricates data.

The loader is intentionally tolerant of the real cache's heterogeneous
filenames. Callers pass explicit file paths (or globs) so the loader never has
to guess which season a directory represents.

It returns raw dicts only; normalization is the normalizer's job.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


class TheStatsAPICorpusLoader:
    """Loads fixtures, per-match stats, and odds from cached files.

    Usage:
        loader = TheStatsAPICorpusLoader(base_dir="data/thestatsapi/championship")
        fixtures = loader.load_fixtures(["_all_fixtures_epl_sn_3057848.json"])
        stats = loader.load_stats_map(stats_glob="epl_stats_mt_*.json")
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)

    @property
    def base_dir(self) -> Path:
        return self._base

    def load_fixtures(self, filenames: Iterable[str]) -> list[dict[str, Any]]:
        """Load and flatten fixtures from one or more fixtures files.

        Each file is expected to have a top-level ``fixtures`` list. Files
        without it are skipped with a warning.
        """
        out: list[dict[str, Any]] = []
        for name in filenames:
            path = self._base / name
            data = _read_json(path)
            if not data:
                continue
            fixtures = data.get("fixtures")
            if not isinstance(fixtures, list):
                logger.warning("File %s has no 'fixtures' list", path)
                continue
            out.extend(fx for fx in fixtures if isinstance(fx, dict))
        return out

    def load_fixtures_glob(self, pattern: str) -> list[dict[str, Any]]:
        """Load fixtures from all files matching a glob under base_dir."""
        names = sorted(p.name for p in self._base.glob(pattern))
        return self.load_fixtures(names)

    def load_stats_map(
        self,
        *,
        stats_glob: Optional[str] = None,
        filenames: Optional[Iterable[str]] = None,
    ) -> dict[str, dict[str, Any]]:
        """Load per-match stats keyed by the provider match ref ("mt_...").

        Args:
            stats_glob: Glob (relative to base_dir) selecting stats files.
            filenames: Explicit stats filenames (alternative to glob).

        Returns:
            Mapping match_ref -> parsed stats payload.
        """
        paths: list[Path] = []
        if stats_glob:
            paths.extend(sorted(self._base.glob(stats_glob)))
        if filenames:
            paths.extend(self._base / n for n in filenames)

        result: dict[str, dict[str, Any]] = {}
        for path in paths:
            data = _read_json(path)
            if not data:
                continue
            match_ref = (data.get("data") or {}).get("match_id")
            if isinstance(match_ref, str) and match_ref:
                result[match_ref] = data
        return result

    def load_odds(self, filename: str) -> Optional[dict[str, Any]]:
        """Load a single odds payload file (e.g. cma_odds_mt_*.json)."""
        return _read_json(self._base / filename)

    def load_odds_glob(self, pattern: str) -> list[dict[str, Any]]:
        """Load all odds payloads matching a glob under base_dir."""
        out: list[dict[str, Any]] = []
        for path in sorted(self._base.glob(pattern)):
            data = _read_json(path)
            if data:
                out.append(data)
        return out
