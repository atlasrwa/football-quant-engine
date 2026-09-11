"""End-to-end coverage report: what the engine reached this tick, and what it did not.

WHAT THIS ANSWERS
=================
One machine-readable artifact per tick covering the whole path — provider
discovery, identity mapping, fixtures in horizon, forecasts, prospective shadows,
frontier exclusions, genuine closes, evaluations, and Telegram delivery — so that
"the engine produced nothing" is never ambiguous.

ZERO MUST NOT CONCEAL UNKNOWN
=============================
Every count is explicit, including zeros, and every zero is accompanied by an
exclusion reason breakdown. A stage that could not be evaluated reports ``None``
(UNKNOWN), never ``0``. The two are different claims: ``0`` means "we looked and
there were none", ``None`` means "we could not look". Conflating them is how a
silently broken stage reads as a quiet week — the failure mode this whole report
exists to remove.

THE SIX EXCLUSION CLASSES ARE KEPT DISTINCT
===========================================
Per requirement, these must never collapse into one "excluded" bucket, because
each has a different remedy:

* ``provider_unsupported``      — a provider genuinely lacks the competition.
* ``identity_unresolved``       — both may have it; we refuse to guess which.
* ``market_unavailable``        — competition fine, this market is not priced.
* ``model_prerequisites``       — no training data / thin history for this fixture.
* ``pre_frontier``              — candidate froze before the live frontier.
* ``no_fixture_due``            — nothing has reached its horizon yet.

NOT A PROMOTION METRIC
======================
Nothing here is evidence of skill, validation, or signal eligibility. Counting
shadows does not validate a league. The report deliberately carries no accuracy,
EV, ROI, edge or hit-rate figure.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.research.prospective.coverage_matrix import CHAMPION_MARKETS, MarketEligibility
from src.research.scope.dual_provider import (
    IDENTITY_UNSAFE_REASONS,
    PROVIDER_UNSUPPORTED_REASONS,
)
from src.research.scope.market_scope import ResearchScope

#: Contract string for the emitted report.
COVERAGE_REPORT_CONTRACT = "engine-coverage-report/v1"

#: The six mutually exclusive exclusion classes. Named so a consumer can rely on
#: the keys existing rather than discovering them empirically.
EXCLUSION_CLASSES: tuple[str, ...] = (
    "provider_unsupported",
    "identity_unresolved",
    "market_unavailable",
    "model_prerequisites",
    "pre_frontier",
    "no_fixture_due",
)

#: Sentinel meaning "this stage could not be evaluated". Distinct from zero.
UNKNOWN: None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> Optional[list[dict[str, Any]]]:
    """Read a JSONL ledger, or ``None`` if it cannot be read.

    ``None`` (UNKNOWN) rather than ``[]`` when the file is absent or unreadable:
    an absent shadow ledger means "no shadow has ever been frozen", which is a
    different statement from "the ledger says zero", and a monitor must be able to
    tell them apart.
    """
    p = Path(path)
    if not p.exists():
        return None
    out: list[dict[str, Any]] = []
    try:
        with open(p, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except OSError:
        return None
    return out


def _count_gz_jsonl(path: Path) -> Optional[int]:
    """Count records in a gzipped JSONL store, or ``None`` if unreadable.

    Tolerates a truncated final member (a live writer): partial reads return what
    was readable rather than ``None``, because a growing file is not a fault.
    """
    p = Path(path)
    if not p.exists():
        return None
    n = 0
    try:
        with gzip.open(p, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    n += 1
    except EOFError:
        return n
    except OSError:
        return None
    return n


@dataclass
class CoverageReport:
    """One tick's coverage across every stage, with explicit exclusion reasons."""

    generated_at_utc: str = field(default_factory=_now_iso)

    # ── stage 1-2: provider discovery + identity ────────────────────────────
    registry_leagues_total: int = 0
    dual_provider_leagues_discovered: int = 0
    leagues_safely_mapped: int = 0
    leagues_provider_unsupported: int = 0
    leagues_identity_unresolved: int = 0
    league_exclusion_reasons: dict[str, int] = field(default_factory=dict)
    excluded_league_detail: list[dict[str, Any]] = field(default_factory=list)

    # ── stage 3-4: fixtures + market scope ──────────────────────────────────
    competitions_with_processable_market: int = 0
    competitions_with_fixtures_in_horizon: Optional[int] = UNKNOWN
    fixtures_in_horizon: Optional[int] = UNKNOWN
    competitions_processed: Optional[int] = UNKNOWN
    fixtures_processed: Optional[int] = UNKNOWN
    league_market_matrix: dict[str, dict[str, str]] = field(default_factory=dict)
    market_status_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    # ── stage 5-9: provider observations + forecasts ────────────────────────
    provider_observations: Optional[int] = UNKNOWN
    forecasts_produced: Optional[int] = UNKNOWN
    forecast_not_published: Optional[int] = UNKNOWN
    model_prerequisite_exclusions: dict[str, int] = field(default_factory=dict)
    market_stage_abstentions: Optional[int] = UNKNOWN

    # ── stage 10-12: prospective shadows ────────────────────────────────────
    prospective_shadow_candidates: Optional[int] = UNKNOWN
    prospective_shadows_frozen: Optional[int] = UNKNOWN
    reconstructed_shadows: Optional[int] = UNKNOWN
    frontier_exclusions: Optional[int] = UNKNOWN
    frontier_established_at: Optional[float] = UNKNOWN
    shadow_competitions: list[str] = field(default_factory=list)

    # ── stage 13-16: closes + evaluation ────────────────────────────────────
    genuine_closes_obtained: Optional[int] = UNKNOWN
    shadow_evaluations_completed: Optional[int] = UNKNOWN

    # ── stage 18: research telemetry ────────────────────────────────────────
    telegram_publication_enabled: Optional[bool] = UNKNOWN
    telegram_credentials_present: Optional[bool] = UNKNOWN
    telegram_shadows_queued: Optional[int] = UNKNOWN
    telegram_shadows_sent: Optional[int] = UNKNOWN
    telegram_updates_sent: Optional[int] = UNKNOWN

    notes: list[str] = field(default_factory=list)

    def exclusion_summary(self) -> dict[str, Any]:
        """The six exclusion classes, each always present.

        A class that could not be evaluated reports ``None``, so a missing stage is
        visible instead of reading as a clean zero.
        """
        return {
            "provider_unsupported": self.leagues_provider_unsupported,
            "identity_unresolved": self.leagues_identity_unresolved,
            "market_unavailable": self._market_unavailable_cells(),
            "model_prerequisites": (
                sum(self.model_prerequisite_exclusions.values())
                if self.model_prerequisite_exclusions
                else (0 if self.forecasts_produced is not None else UNKNOWN)
            ),
            "pre_frontier": self.frontier_exclusions,
            "no_fixture_due": self._no_fixture_due(),
        }

    def _no_fixture_due(self) -> Optional[int]:
        """In-scope competitions that currently have no fixture in the horizon.

        A count, not a flag: "38 of 46 eligible competitions have nothing due right
        now" is actionable, whereas a bare zero cannot be told apart from a
        discovery outage. Returns ``None`` when the horizon was never evaluated,
        because in that case we genuinely do not know.
        """
        if self.competitions_with_fixtures_in_horizon is None:
            return UNKNOWN
        return max(
            0,
            self.competitions_with_processable_market
            - self.competitions_with_fixtures_in_horizon,
        )

    def _market_unavailable_cells(self) -> Optional[int]:
        """Count of ``competition x market`` cells that are not processable."""
        if not self.market_status_counts:
            return UNKNOWN
        total = 0
        for statuses in self.market_status_counts.values():
            total += statuses.get(MarketEligibility.UNSUPPORTED.value, 0)
            total += statuses.get(MarketEligibility.UNKNOWN.value, 0)
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_contract": COVERAGE_REPORT_CONTRACT,
            "generated_at_utc": self.generated_at_utc,
            "scope_rule": "dual_provider_intersection",
            "pilot_c_is_behavioral_input": False,
            "unknown_is_null_not_zero": True,
            "league_universe": {
                "registry_leagues_total": self.registry_leagues_total,
                "dual_provider_leagues_discovered": self.dual_provider_leagues_discovered,
                "leagues_safely_mapped": self.leagues_safely_mapped,
                "leagues_provider_unsupported": self.leagues_provider_unsupported,
                "leagues_identity_unresolved": self.leagues_identity_unresolved,
                "exclusion_reasons": dict(sorted(self.league_exclusion_reasons.items())),
                "excluded_detail": list(self.excluded_league_detail),
            },
            "fixtures": {
                "competitions_with_processable_market": self.competitions_with_processable_market,
                "competitions_with_fixtures_in_horizon": self.competitions_with_fixtures_in_horizon,
                "fixtures_in_horizon": self.fixtures_in_horizon,
                "competitions_processed": self.competitions_processed,
                "fixtures_processed": self.fixtures_processed,
            },
            "markets": {
                "champion_markets": list(CHAMPION_MARKETS),
                "status_counts": self.market_status_counts,
                "league_market_matrix": self.league_market_matrix,
            },
            "forecasts": {
                "provider_observations": self.provider_observations,
                "produced": self.forecasts_produced,
                "not_published": self.forecast_not_published,
                "model_prerequisite_exclusions": dict(
                    sorted(self.model_prerequisite_exclusions.items())
                ),
                "market_stage_abstentions": self.market_stage_abstentions,
            },
            "prospective": {
                "shadow_candidates": self.prospective_shadow_candidates,
                "shadows_frozen": self.prospective_shadows_frozen,
                "reconstructed_shadows": self.reconstructed_shadows,
                "frontier_exclusions": self.frontier_exclusions,
                "frontier_established_at": self.frontier_established_at,
                "competitions_represented": list(self.shadow_competitions),
            },
            "evaluation": {
                "genuine_closes_obtained": self.genuine_closes_obtained,
                "shadow_evaluations_completed": self.shadow_evaluations_completed,
            },
            "research_telegram": {
                "publication_enabled": self.telegram_publication_enabled,
                "dedicated_credentials_present": self.telegram_credentials_present,
                "shadows_queued": self.telegram_shadows_queued,
                "shadows_sent": self.telegram_shadows_sent,
                "updates_sent": self.telegram_updates_sent,
                "credential_fallback_permitted": False,
            },
            "exclusions": self.exclusion_summary(),
            "validation_boundary": {
                "research_coverage_implies_validated_signal": False,
                "note": (
                    "FULL RESEARCH COVERAGE != VALIDATED SIGNAL COVERAGE. Nothing in "
                    "this report is evidence of skill, calibration, or signal "
                    "eligibility."
                ),
            },
            "notes": list(self.notes),
        }


def build_coverage_report(
    *,
    scope: Optional[ResearchScope] = None,
    shadow_root: Path = Path("data/prospective"),
    research_record_root: Path = Path("data/research_forecast"),
    broadcast_root: Path = Path("data/forecast_broadcast"),
    research_run: Optional[dict[str, Any]] = None,
) -> CoverageReport:
    """Assemble the coverage report from persisted state only.

    Performs no provider request and runs no model: every figure comes from an
    artifact already on disk, so generating the report can never change what it
    reports on.

    Args:
        scope: the research scope. Built from the registry when omitted.
        shadow_root: prospective capture + shadow ledger root.
        research_record_root: research forecast commitment ledger root.
        broadcast_root: consumer commitment ledger root.
        research_run: the last research forecast run summary, when available.

    Returns:
        The :class:`CoverageReport`. Stages with no readable artifact are left as
        ``None`` (UNKNOWN) rather than zero.
    """
    from src.research.scope.market_scope import build_research_scope

    rs = scope or build_research_scope()
    report = CoverageReport()

    # ── provider + identity ─────────────────────────────────────────────────
    report.registry_leagues_total = len(rs.universe.leagues)
    report.dual_provider_leagues_discovered = len(rs.universe.leagues)
    report.leagues_safely_mapped = len(rs.universe.eligible)
    report.leagues_provider_unsupported = sum(
        1 for lg in rs.universe.excluded if lg.exclusion_reason in PROVIDER_UNSUPPORTED_REASONS
    )
    report.leagues_identity_unresolved = sum(
        1 for lg in rs.universe.excluded if lg.exclusion_reason in IDENTITY_UNSAFE_REASONS
    )
    report.league_exclusion_reasons = rs.universe.exclusion_summary()
    report.excluded_league_detail = [
        {
            "canonical_name": lg.canonical_name,
            "exclusion_reason": lg.exclusion_reason.value,
            "detail": lg.detail,
            "candidate_competition_ids": list(lg.candidate_competition_ids),
        }
        for lg in rs.universe.excluded
    ]

    # ── market scope ────────────────────────────────────────────────────────
    report.competitions_with_processable_market = len(rs.processable_competition_ids)
    report.market_status_counts = rs.market_status_counts()
    report.league_market_matrix = rs.market_matrix()

    # ── provider observations ───────────────────────────────────────────────
    report.provider_observations = _count_gz_jsonl(
        Path(shadow_root) / "captures.jsonl.gz"
    )

    # ── forecasts (research ledger is the expanded universe) ────────────────
    research_rows = _read_jsonl(Path(research_record_root) / "broadcasts.jsonl")
    consumer_rows = _read_jsonl(Path(broadcast_root) / "broadcasts.jsonl")
    if research_rows is None and consumer_rows is None:
        report.forecasts_produced = UNKNOWN
        report.forecast_not_published = UNKNOWN
    else:
        rows = (research_rows or []) + (consumer_rows or [])
        report.forecasts_produced = sum(
            1 for r in rows if r.get("record_type") == "FORECAST_COMMITTED"
        )
        report.forecast_not_published = sum(
            1 for r in rows if r.get("record_type") == "NOT_PUBLISHED"
        )
        report.fixtures_processed = len(
            {str(r.get("fixture_id")) for r in rows if r.get("fixture_id")}
        )
        report.competitions_processed = len(
            {str(r.get("comp_id")) for r in rows if r.get("comp_id")}
        )

    if research_run:
        fixtures = research_run.get("fixtures") or {}
        leagues = research_run.get("league_universe") or {}
        commitments = research_run.get("commitments") or {}
        report.fixtures_in_horizon = fixtures.get("due")
        report.competitions_with_fixtures_in_horizon = leagues.get(
            "competitions_with_fixtures_in_horizon"
        )
        report.model_prerequisite_exclusions = dict(
            commitments.get("model_stage_exclusions") or {}
        )
        report.market_stage_abstentions = commitments.get("abstained_cells")

    # ── prospective shadows ─────────────────────────────────────────────────
    shadow_rows = _read_jsonl(Path(shadow_root) / "shadow_residuals.jsonl")
    if shadow_rows is None:
        report.prospective_shadows_frozen = UNKNOWN
        report.reconstructed_shadows = UNKNOWN
        report.notes.append(
            "shadow residual ledger absent: no shadow has been frozen yet. This is "
            "UNKNOWN, not zero."
        )
    else:
        report.prospective_shadows_frozen = sum(
            1 for r in shadow_rows if r.get("provenance_kind") == "PROSPECTIVE_SHADOW"
        )
        report.reconstructed_shadows = sum(
            1 for r in shadow_rows if r.get("provenance_kind") == "RECONSTRUCTED_SHADOW"
        )
        report.shadow_competitions = sorted(
            {str(r.get("competition")) for r in shadow_rows if r.get("competition")}
        )

    eval_rows = _read_jsonl(Path(shadow_root) / "shadow_evaluations.jsonl")
    report.shadow_evaluations_completed = (
        len(eval_rows) if eval_rows is not None else UNKNOWN
    )

    # Frontier + candidate/exclusion counts come from the shadow processor's own
    # ops log, which is the only place that knows how many candidates the join
    # produced before the frontier gate removed some.
    shadow_ops = _read_jsonl(Path(shadow_root) / "shadow_ops.jsonl")
    if shadow_ops:
        last = shadow_ops[-1]
        note = str(last.get("note") or "")
        report.frontier_exclusions = _parse_note_int(note, "pre_frontier_excluded")
        report.prospective_shadow_candidates = _parse_note_int(note, "new_candidates")
        report.frontier_established_at = _parse_note_float(note, "frontier")

    frontier_path = Path(shadow_root) / "shadow_frontier.json"
    if report.frontier_established_at is None and frontier_path.exists():
        try:
            data = json.loads(frontier_path.read_text(encoding="utf-8"))
            raw = data.get("established_at")
            report.frontier_established_at = float(raw) if raw is not None else UNKNOWN
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            report.frontier_established_at = UNKNOWN

    # ── genuine closes ──────────────────────────────────────────────────────
    # Uses the canonical predicate, which already fails closed to UNKNOWN (None,
    # never 0) when the capture store is missing, unreadable, or truncated.
    try:
        from src.research.prospective.genuine_close_metrics import (
            genuine_close_counts_from_root,
        )

        counts = genuine_close_counts_from_root(capture_root=Path(shadow_root))
        report.genuine_closes_obtained = counts.genuine_closing_keys
    except Exception:  # noqa: BLE001 - metrics are observability, never load-bearing
        report.genuine_closes_obtained = UNKNOWN

    # ── research telegram ───────────────────────────────────────────────────
    try:
        from src.research.prospective.shadow_feed import (
            research_telegram_transport,
            shadow_feed_publication_enabled,
        )

        report.telegram_publication_enabled = shadow_feed_publication_enabled()
        report.telegram_credentials_present = research_telegram_transport() is not None
    except Exception:  # noqa: BLE001
        report.telegram_publication_enabled = UNKNOWN
        report.telegram_credentials_present = UNKNOWN

    feed_ops = _read_jsonl(Path(shadow_root) / "shadow_feed_ops.jsonl")
    if feed_ops:
        note = str(feed_ops[-1].get("note") or "")
        report.telegram_shadows_queued = _parse_note_int(note, "queued")
        report.telegram_shadows_sent = _parse_note_int(note, "published")
        report.telegram_updates_sent = _parse_note_int(note, "evals_published")

    return report


def _parse_note_int(note: str, key: str) -> Optional[int]:
    """Pull ``key=<int>`` out of an ops-log note, or ``None`` if absent."""
    for token in note.split():
        if token.startswith(f"{key}="):
            raw = token.split("=", 1)[1]
            try:
                return int(raw)
            except ValueError:
                return UNKNOWN
    return UNKNOWN


def _parse_note_float(note: str, key: str) -> Optional[float]:
    for token in note.split():
        if token.startswith(f"{key}="):
            raw = token.split("=", 1)[1]
            try:
                return float(raw)
            except ValueError:
                return UNKNOWN
    return UNKNOWN


def emit_coverage_report(
    report: CoverageReport,
    *,
    path: Path = Path("research/evaluation/engine_coverage_report.json"),
) -> Path:
    """Write the report, overwriting the previous one.

    Overwrite rather than append: this artifact answers "what did the engine reach
    right now". The durable history lives in the append-only ledgers it reads.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return p
