"""Research forecast commitments across the full dual-provider league universe.

WHAT THIS IS FOR
================
A prospective shadow residual is a join of two things: a *committed forecast* and
our *own pre-kickoff market snapshot*. Capture already spans every competition in
the dual-provider intersection, but forecast commitments existed only for the four
Pilot-C leagues declared in ``config/forecast_broadcast_scope.json``. The engine
was therefore observing markets in 46 competitions while being structurally
incapable of producing a research observation for 42 of them.

This module produces forecast commitments for the *whole* eligible universe, into
a **separate append-only ledger** (``data/research_forecast/``), so that:

* every safely-mapped competition can generate genuine prospective shadows, and
* consumer publication scope is left exactly as it was.

WHAT IT DELIBERATELY DOES NOT DO
================================
It does not deliver anything. There is no transport parameter, no queue, and no
renderer reachable from here — a research commitment is written and that is the
end of the path. Consumer/validated publication continues to be governed solely
by ``config/forecast_broadcast_scope.json`` plus
:func:`src.research._data_accumulation_mode.can_publish_validated_signals`, and
neither is read, imported, or influenced by this module.

**Expanded research coverage is not expanded signal coverage.** A competition
appearing here has not been validated, promoted, or declared to have skill. It has
been declared *observable*.

WHY A SEPARATE LEDGER
=====================
``BroadcastLedger`` enforces exactly-once per fixture through
:meth:`~src.research.prediction_engine.broadcast.record.BroadcastLedger.fired_fixture_ids`.
Writing research commitments into the consumer ledger would make a research
commitment suppress the later consumer commitment for the same fixture (or vice
versa), silently changing what the consumer channel publishes. A separate root
keeps both exactly-once domains intact and keeps the consumer coverage report
answering the question it was built to answer.

THE MODEL IS UNTOUCHED
======================
This module contains no model, no coefficient, no line selection and no
calibration. It reuses the champion forecast engine exactly as the consumer path
does — same corpus snapshot, same frozen hyperparameters, same fitted cells, same
``predict_one``. The declared market cells are copied verbatim from the consumer
scope declaration, so a research forecast for a market is numerically the same
computation as a consumer forecast for that market. Only the set of *competitions*
is wider.

FAIL CLOSED AT THE STAGE, NOT AT THE LEAGUE
===========================================
Per requirement, a missing prerequisite must not delete a league:

* competition not in the dual-provider intersection -> excluded (provider stage);
* market not priced by the provider -> that *market* abstains, other markets
  proceed (market stage);
* team history absent or below the minimum-history floor -> that *fixture*
  abstains with a named reason, other fixtures proceed (model stage);
* corpus stale -> the *model* stage is refused for the run, and every due fixture
  is recorded ``NOT_PUBLISHED`` with the gate's reasoning.

No stage ever manufactures a probability to avoid a gap.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from src.research.prediction_engine.broadcast.scope_config import (
    DELAY_NEVER_CANCEL,
    FIXED_DECLARED_LINE,
    SCOPE_CONFIG_CONTRACT,
    MarketSpec,
    ScopeConfig,
    parse_scope_config,
)
from src.research.scope.market_scope import (
    MODEL_MARKET_TO_ODDS_MARKET,
    MarketExclusionReason,
    ResearchScope,
)

_HOME = Path("/home/ubuntu")

#: Research commitments live in their own append-only root, never mixed with the
#: consumer broadcast ledger.
DEFAULT_RESEARCH_RECORD_ROOT = _HOME / "data" / "research_forecast"

#: Append-only provenance log of every research scope version that has been in
#: force. Unlike the consumer scope change log this is a *record*, not a gate:
#: research scope is derived from provider state and legitimately changes when the
#: registry or coverage matrix changes, so requiring an operator to pre-approve
#: each hash would freeze coverage at whatever the registry said last. The log
#: preserves reproducibility (which competitions and cells were in force when)
#: without converting dynamic coverage into a manual bottleneck.
RESEARCH_SCOPE_VERSION_LOG = "scope_versions.jsonl"

#: Contract string for rows in the scope-version log.
RESEARCH_SCOPE_VERSION_CONTRACT = "research-forecast-scope-version/v1"

#: How far before kickoff a research forecast is committed.
#:
#: Wider than the consumer T-8h horizon on purpose. Capture vintages are EARLY
#: (~T-24h), MID (~T-6h), LATE (~T-60m) and FINAL (~T-15m), and a shadow candidate
#: requires a market snapshot observed at or after the forecast was generated.
#: Committing at T-30h therefore makes all four vintages joinable, which maximises
#: legitimate prospective evidence per fixture. It does not weaken anything: the
#: point-in-time features still read only history strictly before kickoff, and the
#: prospective frontier and ``information_cutoff < kickoff_ts`` rules are enforced
#: unchanged downstream.
DEFAULT_RESEARCH_HORIZON_HOURS = int(
    os.environ.get("RESEARCH_FORECAST_HORIZON_HOURS", "30")
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Declared research scope
# ─────────────────────────────────────────────────────────────────────────────
def build_research_scope_declaration(
    *,
    competitions: Sequence[tuple[str, str]],
    market_specs: Sequence[MarketSpec],
    horizon_hours: int = DEFAULT_RESEARCH_HORIZON_HOURS,
    quiet_hours: Optional[tuple[int, int]] = None,
) -> dict[str, Any]:
    """Assemble a research scope declaration in the standard scope-config shape.

    Reusing the existing declaration shape means research scope inherits every
    validation the consumer scope gets: a duplicated competition, a duplicated
    market cell, a market missing a side label, or an unsupported line-selection
    rule is refused rather than silently degraded.

    Args:
        competitions: ``(comp_id, label)`` pairs, deterministically ordered.
        market_specs: the champion market cells, copied verbatim from the consumer
            declaration so no new line is ever chosen here.
        horizon_hours: how far before kickoff a research forecast is committed.
        quiet_hours: kept for shape compatibility only. Research commitments are
            never delivered, so quiet hours cannot suppress anything; the default
            declares a zero-length window.

    Returns:
        The raw declaration dict, ready for :func:`parse_scope_config`.
    """
    if not competitions:
        raise ValueError(
            "research scope declaration requires at least one competition; an empty "
            "universe must be reported as an empty run, not declared as scope"
        )
    if not market_specs:
        raise ValueError("research scope declaration requires at least one market cell")

    start_hour, end_hour = quiet_hours if quiet_hours is not None else (0, 0)
    seen: set[str] = set()
    leagues: list[dict[str, str]] = []
    for comp_id, label in competitions:
        cid = str(comp_id)
        if cid in seen:
            continue
        seen.add(cid)
        leagues.append({"comp_id": cid, "label": str(label or cid)})
    leagues.sort(key=lambda entry: entry["comp_id"])

    return {
        "config_contract": SCOPE_CONFIG_CONTRACT,
        "horizon_hours_before_kickoff": int(horizon_hours),
        "leagues": leagues,
        "markets": [
            {
                "market": spec.market,
                "line": spec.line,
                "over_label": spec.over_label,
                "under_label": spec.under_label,
            }
            for spec in market_specs
        ],
        "line_selection_rule": {
            "rule": FIXED_DECLARED_LINE,
            "description": (
                "Lines are the literal declared values, copied verbatim from the "
                "consumer scope declaration. Research coverage widens the set of "
                "competitions, never the set of lines, so no line is ever selected "
                "per fixture or derived from a posted price."
            ),
        },
        "confidence_label_rule": None,
        "quiet_hours_utc": {
            "start_hour": int(start_hour),
            "end_hour": int(end_hour),
            "policy": DELAY_NEVER_CANCEL,
        },
        "notes": [
            "RESEARCH SCOPE. Derived from the dual-provider FootyStats x "
            "TheStatsAPI intersection; not a consumer publication scope.",
            "Commitments written under this scope are never delivered to any "
            "channel. They exist so prospective shadow residuals can be built "
            "for every safely-mapped competition.",
            "Pilot C membership is not an input to this scope.",
            "Presence here implies observability, not validation. Validated "
            "signal publication remains governed solely by "
            "can_publish_validated_signals().",
        ],
    }


def build_research_scope_config(
    *,
    scope: ResearchScope,
    market_specs: Sequence[MarketSpec],
    horizon_hours: int = DEFAULT_RESEARCH_HORIZON_HOURS,
    competition_ids: Optional[Iterable[str]] = None,
) -> ScopeConfig:
    """Build the validated research :class:`ScopeConfig` from the research scope.

    Args:
        scope: the dual-provider research scope.
        market_specs: champion market cells, copied from the consumer declaration.
        horizon_hours: research commitment horizon.
        competition_ids: restrict to these competitions (tests and partial runs).
            Ids not forecastable in ``scope`` are dropped.

    Returns:
        The validated research scope config, carrying its own
        ``scope_version_hash``. This never passes through
        :func:`~src.research.prediction_engine.broadcast.scope_config.load_scope_config`,
        so the consumer scope-change gate is neither used nor weakened.
    """
    wanted = set(competition_ids) if competition_ids is not None else None
    competitions = [
        (comp.competition_id, comp.canonical_name)
        for comp in scope.competitions
        if comp.has_forecastable_market
        and (wanted is None or comp.competition_id in wanted)
    ]
    declaration = build_research_scope_declaration(
        competitions=competitions,
        market_specs=market_specs,
        horizon_hours=horizon_hours,
    )
    return parse_scope_config(
        declaration, source_path="<derived:dual-provider-research-scope>"
    )


def record_research_scope_version(
    config: ScopeConfig,
    *,
    scope: ResearchScope,
    root: Path = DEFAULT_RESEARCH_RECORD_ROOT,
    now_iso: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Append this research scope version to the provenance log, once.

    Idempotent: a version already recorded is not written again, so a scheduler
    tick under unchanged scope adds nothing. Returns the row written, or ``None``
    when the version was already present.
    """
    path = Path(root) / RESEARCH_SCOPE_VERSION_LOG
    if path.exists():
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("scope_version_hash") == config.scope_version_hash:
                        return None
        except OSError:
            pass

    record = {
        "record_contract": RESEARCH_SCOPE_VERSION_CONTRACT,
        "scope_version_hash": config.scope_version_hash,
        "recorded_at_utc": now_iso or _now_iso(),
        "derivation": {
            "rule": "dual_provider_intersection",
            "registry_path": scope.universe.registry_path,
            "coverage_matrix_path": scope.coverage_matrix_path,
        },
        "scope": config.provenance(),
        "competition_count": len(config.leagues),
        "excluded_league_reasons": scope.universe.exclusion_summary(),
        "pilot_c_is_behavioral_input": False,
    }
    _append_jsonl(path, record)
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Market-stage abstention
# ─────────────────────────────────────────────────────────────────────────────
def market_abstentions(
    *,
    scope: ResearchScope,
    competition_id: Optional[str],
    market_specs: Sequence[MarketSpec],
) -> dict[tuple[str, Optional[float]], str]:
    """Cells this competition must abstain on, with a reason per cell.

    This is where market isolation happens. A competition whose provider does not
    price cards still processes goals and corners; only the cards cell abstains,
    and it abstains with a stated reason rather than by disappearing.

    Returns:
        ``{(market, line): reason}`` for every declared cell that must not be
        priced for this competition. Cells absent from the result are processable.
    """
    allowed = set(scope.model_markets_for(competition_id))
    comp = scope.scope_for(competition_id)
    out: dict[tuple[str, Optional[float]], str] = {}
    for spec in market_specs:
        if spec.market in allowed:
            continue
        odds_market = MODEL_MARKET_TO_ODDS_MARKET.get(spec.market)
        if odds_market is None:
            out[spec.cell] = (
                f"market {spec.market!r} has no captured odds counterpart, so it "
                "could never be joined to a market observation; not priced for "
                "research"
            )
            continue
        if comp is None:
            out[spec.cell] = (
                "competition is not in the dual-provider research scope; no market "
                "evidence available"
            )
            continue
        status = comp.market_eligibility.get(odds_market, "UNKNOWN")
        reason_code = comp.market_exclusions.get(
            odds_market, MarketExclusionReason.PROVIDER_MARKET_UNKNOWN.value
        )
        out[spec.cell] = (
            f"provider market eligibility for {odds_market!r} is {status} "
            f"({reason_code}); this market abstains while the rest of the "
            "competition continues"
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Due selection
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ResearchDueFixture:
    """One fixture due for a research forecast commitment."""

    fixture_id: str
    competition_id: Optional[str]
    kickoff_unix: float
    home_team: str
    away_team: str
    info: dict[str, Any]


def research_due_fixtures(
    universe: dict[str, dict[str, Any]],
    *,
    config: ScopeConfig,
    now_unix: float,
    already_fired: frozenset[str],
) -> tuple[list[ResearchDueFixture], dict[str, int]]:
    """Every in-research-scope fixture whose horizon has arrived and not fired.

    Mirrors the consumer selection rule (fire once, never drop a late fixture,
    order by kickoff) so the two paths cannot diverge in commitment semantics.

    Returns:
        ``(due, exclusion_counts)``. The counts distinguish *why* a fixture in the
        universe is not due — out of research scope, already fired, no usable
        kickoff, or simply not yet at its horizon — so a zero-due tick is never
        ambiguous.
    """
    due: list[ResearchDueFixture] = []
    counts = {
        "not_in_research_scope": 0,
        "already_committed": 0,
        "unusable_kickoff": 0,
        "before_horizon": 0,
        "past_kickoff": 0,
    }
    horizon_seconds = config.horizon_seconds
    for fixture_id, info in universe.items():
        comp = info.get("comp")
        if not config.is_in_scope(comp):
            counts["not_in_research_scope"] += 1
            continue
        if str(fixture_id) in already_fired:
            counts["already_committed"] += 1
            continue
        try:
            kickoff = float(info["ts"])
        except (KeyError, TypeError, ValueError):
            counts["unusable_kickoff"] += 1
            continue
        if now_unix < kickoff - horizon_seconds:
            counts["before_horizon"] += 1
            continue
        if now_unix >= kickoff:
            # A forecast committed after kickoff is not a pre-kickoff forecast.
            # Counted separately so a backlog of stale fixtures is visible rather
            # than looking like scope that produced nothing.
            counts["past_kickoff"] += 1
            continue
        due.append(
            ResearchDueFixture(
                fixture_id=str(fixture_id),
                competition_id=str(comp) if comp else None,
                kickoff_unix=kickoff,
                home_team=str(info.get("home") or ""),
                away_team=str(info.get("away") or ""),
                info=info,
            )
        )
    due.sort(key=lambda f: f.kickoff_unix)
    return due, counts


# ─────────────────────────────────────────────────────────────────────────────
# Run result
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ResearchForecastResult:
    """Machine-readable outcome of one research forecast pass.

    Every counter is explicit, including zeros, and exclusions are counted by
    *reason*. A run that commits nothing must be distinguishable as "nothing was
    due" versus "the model had no inputs" versus "the corpus gate refused".
    """

    started_at_utc: str = field(default_factory=_now_iso)
    finished_at_utc: Optional[str] = None
    scope_version_hash: str = ""
    horizon_hours: int = DEFAULT_RESEARCH_HORIZON_HOURS
    dry_run: bool = False
    model_version: Optional[str] = None
    data_cutoff_utc: Optional[str] = None
    freshness_state: Optional[str] = None

    registry_leagues_total: int = 0
    dual_provider_eligible: int = 0
    leagues_excluded: int = 0
    league_exclusion_reasons: dict[str, int] = field(default_factory=dict)
    competitions_in_research_scope: int = 0
    competitions_with_fixtures_in_horizon: int = 0
    competitions_committed: int = 0

    fixtures_in_universe: int = 0
    fixtures_due: int = 0
    fixture_exclusions: dict[str, int] = field(default_factory=dict)

    commitments_written: int = 0
    not_published_written: int = 0
    priced_cells: int = 0
    abstained_cells: int = 0
    market_stage_abstentions: dict[str, int] = field(default_factory=dict)
    model_stage_exclusions: dict[str, int] = field(default_factory=dict)
    committed_by_competition: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_contract": "research-forecast-run/v1",
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "scope_version_hash": self.scope_version_hash,
            "horizon_hours": self.horizon_hours,
            "dry_run": self.dry_run,
            "model_version": self.model_version,
            "data_cutoff_utc": self.data_cutoff_utc,
            "freshness_state": self.freshness_state,
            "league_universe": {
                "registry_leagues_total": self.registry_leagues_total,
                "dual_provider_eligible": self.dual_provider_eligible,
                "leagues_excluded": self.leagues_excluded,
                "league_exclusion_reasons": dict(sorted(self.league_exclusion_reasons.items())),
                "competitions_in_research_scope": self.competitions_in_research_scope,
                "competitions_with_fixtures_in_horizon": self.competitions_with_fixtures_in_horizon,
                "competitions_committed": self.competitions_committed,
            },
            "fixtures": {
                "in_universe": self.fixtures_in_universe,
                "due": self.fixtures_due,
                "exclusions": dict(sorted(self.fixture_exclusions.items())),
            },
            "commitments": {
                "written": self.commitments_written,
                "not_published_written": self.not_published_written,
                "priced_cells": self.priced_cells,
                "abstained_cells": self.abstained_cells,
                "market_stage_abstentions": dict(sorted(self.market_stage_abstentions.items())),
                "model_stage_exclusions": dict(sorted(self.model_stage_exclusions.items())),
                "by_competition": dict(sorted(self.committed_by_competition.items())),
            },
            "publication": {
                "delivered": 0,
                "delivery_attempted": False,
                "note": (
                    "Research commitments are never delivered. This pass has no "
                    "transport and cannot publish to any channel."
                ),
            },
            "errors": list(self.errors),
        }
