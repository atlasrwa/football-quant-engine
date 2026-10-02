"""Point-in-time historical dataset construction for QFE V2.

The builder uses a streaming, as-of architecture:

1. Sort fixtures deterministically by kickoff and stable provider id.
2. For target fixture F, compute its registered prediction cutoff.
3. Admit only earlier matches whose reconstructed availability time is at or
   before that cutoff.
4. Snapshot history-derived features.
5. Attach F's realized target labels in a physically separate target section.
6. Only after the row is created may F become eligible evidence for later rows.

That ordering makes same-row target leakage structurally difficult.

Historical post-match stats do not carry original publication timestamps. QFE
therefore labels their availability as RECONSTRUCTED and applies an explicit,
manifested post-kickoff embargo. It never pretends those timestamps were
actually observed historically.
"""

from __future__ import annotations

import hashlib
import heapq
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from src.research.contracts.provider import (
    ProviderCapabilityRegistry,
    THESTATSAPI_CAPABILITIES_V1,
)
from src.research.contracts.target import (
    TARGET_REGISTRY_V1,
    TargetObservation,
    TargetRegistry,
)
from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import (
    PITDatasetManifest,
    canonical_json,
    canonical_rows_jsonl,
    rows_digest,
    sha256_bytes,
    sha256_json,
)


class DatasetIntegrityError(ValueError):
    """Raised when the historical corpus cannot satisfy the PIT contract."""


@dataclass(frozen=True, slots=True)
class HistoryMetric:
    name: str
    home_field: str
    away_field: str


DEFAULT_HISTORY_METRICS: tuple[HistoryMetric, ...] = (
    HistoryMetric("goals", "home_goals", "away_goals"),
    HistoryMetric("corners", "corners_home", "corners_away"),
    HistoryMetric("shots", "shots_home", "shots_away"),
    HistoryMetric(
        "shots_on_target",
        "shots_on_target_home",
        "shots_on_target_away",
    ),
    HistoryMetric("fouls", "fouls_home", "fouls_away"),
    HistoryMetric("yellow_cards", "yellow_cards_home", "yellow_cards_away"),
    HistoryMetric("possession", "possession_home", "possession_away"),
    HistoryMetric("xg", "home_xg", "away_xg"),
)


@dataclass(frozen=True, slots=True)
class PITDatasetSpec:
    decision_horizon_seconds: int
    reconstructed_post_match_embargo_seconds: int = 6 * 3600
    exclude_extra_time_history: bool = True
    schema_version: str = "qfe-pit-dataset-v1"
    availability_policy: str = "RECONSTRUCTED_KICKOFF_PLUS_EMBARGO"

    def __post_init__(self) -> None:
        if self.decision_horizon_seconds <= 0:
            raise ValueError("decision_horizon_seconds must be positive")
        if self.reconstructed_post_match_embargo_seconds < 0:
            raise ValueError(
                "reconstructed_post_match_embargo_seconds must be non-negative"
            )
        if not self.availability_policy.startswith("RECONSTRUCTED_"):
            raise ValueError(
                "Historical stats without true observation timestamps must be "
                "labelled RECONSTRUCTED"
            )


@dataclass(frozen=True, slots=True)
class HistoryLineage:
    eligible_history_matches: int
    source_chain_digest: str
    max_source_kickoff_ts: Optional[float]
    max_source_available_at: Optional[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible_history_matches": self.eligible_history_matches,
            "source_chain_digest": self.source_chain_digest,
            "max_source_kickoff_ts": self.max_source_kickoff_ts,
            "max_source_available_at": self.max_source_available_at,
        }


@dataclass(frozen=True, slots=True)
class PITFeatureRow:
    fixture_key: str
    source_provider: str
    source_match_ref: str
    competition_ref: str
    season_ref: str
    home_team_ref: str
    away_team_ref: str
    home_team_name: str
    away_team_name: str
    kickoff_ts: float
    cutoff_ts: float
    decision_horizon_seconds: int
    features: dict[str, float | int | None]
    targets: dict[str, Optional[int]]
    target_status: dict[str, str]
    target_reasons: dict[str, str]
    lineage: HistoryLineage

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_key": self.fixture_key,
            "source_provider": self.source_provider,
            "source_match_ref": self.source_match_ref,
            "competition_ref": self.competition_ref,
            "season_ref": self.season_ref,
            "home_team_ref": self.home_team_ref,
            "away_team_ref": self.away_team_ref,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "kickoff_ts": self.kickoff_ts,
            "cutoff_ts": self.cutoff_ts,
            "decision_horizon_seconds": self.decision_horizon_seconds,
            "features": dict(sorted(self.features.items())),
            "targets": dict(sorted(self.targets.items())),
            "target_status": dict(sorted(self.target_status.items())),
            "target_reasons": dict(sorted(self.target_reasons.items())),
            "lineage": self.lineage.to_dict(),
        }

    @property
    def content_hash(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class PITDatasetArtifact:
    manifest: PITDatasetManifest
    rows: tuple[PITFeatureRow, ...]

    def row_dicts(self) -> tuple[dict[str, Any], ...]:
        return tuple(row.to_dict() for row in self.rows)


@dataclass(slots=True)
class _RunningStat:
    total: float = 0.0
    count: int = 0

    def add(self, value: Optional[float | int]) -> None:
        if value is None:
            return
        self.total += float(value)
        self.count += 1

    @property
    def mean(self) -> Optional[float]:
        if self.count == 0:
            return None
        return self.total / self.count


@dataclass(slots=True)
class _MetricPair:
    for_stat: _RunningStat = field(default_factory=_RunningStat)
    against_stat: _RunningStat = field(default_factory=_RunningStat)


@dataclass(slots=True)
class _TeamHistoryState:
    metrics: tuple[HistoryMetric, ...]
    match_count: int = 0
    latest_event_ts: Optional[float] = None
    values: dict[str, _MetricPair] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.values:
            self.values = {
                metric.name: _MetricPair()
                for metric in self.metrics
            }

    def add(
        self,
        *,
        match: ResearchMatch,
        team_is_home: bool,
    ) -> None:
        self.match_count += 1
        event_ts = float(match.date_unix)
        if self.latest_event_ts is None or event_ts > self.latest_event_ts:
            self.latest_event_ts = event_ts

        for metric in self.metrics:
            home_value = getattr(match, metric.home_field)
            away_value = getattr(match, metric.away_field)
            if team_is_home:
                value_for, value_against = home_value, away_value
            else:
                value_for, value_against = away_value, home_value
            pair = self.values[metric.name]
            pair.for_stat.add(value_for)
            pair.against_stat.add(value_against)

    def snapshot(
        self,
        *,
        prefix: str,
        target_kickoff_ts: float,
    ) -> dict[str, float | int | None]:
        out: dict[str, float | int | None] = {
            f"{prefix}_history_matches": self.match_count,
            f"{prefix}_days_since_last_match": (
                (target_kickoff_ts - self.latest_event_ts) / 86400.0
                if self.latest_event_ts is not None
                else None
            ),
        }
        for metric in self.metrics:
            pair = self.values[metric.name]
            out[f"{prefix}_{metric.name}_for_mean"] = pair.for_stat.mean
            out[f"{prefix}_{metric.name}_against_mean"] = pair.against_stat.mean
            out[f"{prefix}_{metric.name}_for_n"] = pair.for_stat.count
            out[f"{prefix}_{metric.name}_against_n"] = pair.against_stat.count
        return out


@dataclass(slots=True)
class _CompetitionMetric:
    home: _RunningStat = field(default_factory=_RunningStat)
    away: _RunningStat = field(default_factory=_RunningStat)
    total: _RunningStat = field(default_factory=_RunningStat)


@dataclass(slots=True)
class _CompetitionState:
    metrics: tuple[HistoryMetric, ...]
    match_count: int = 0
    values: dict[str, _CompetitionMetric] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.values:
            self.values = {
                metric.name: _CompetitionMetric()
                for metric in self.metrics
            }

    def add(self, match: ResearchMatch) -> None:
        self.match_count += 1
        for metric in self.metrics:
            home_value = getattr(match, metric.home_field)
            away_value = getattr(match, metric.away_field)
            stat = self.values[metric.name]
            stat.home.add(home_value)
            stat.away.add(away_value)
            if home_value is not None and away_value is not None:
                stat.total.add(float(home_value) + float(away_value))

    def snapshot(self) -> dict[str, float | int | None]:
        out: dict[str, float | int | None] = {
            "competition_history_matches": self.match_count,
        }
        for metric in self.metrics:
            stat = self.values[metric.name]
            out[f"competition_{metric.name}_home_mean"] = stat.home.mean
            out[f"competition_{metric.name}_away_mean"] = stat.away.mean
            out[f"competition_{metric.name}_total_mean"] = stat.total.mean
            out[f"competition_{metric.name}_total_n"] = stat.total.count
        return out


_EMPTY_CHAIN = hashlib.sha256(b"qfe-pit-lineage-v1").digest()


class PITDatasetBuilder:
    """Build deterministic point-in-time feature rows from normalized matches."""

    def __init__(
        self,
        *,
        spec: PITDatasetSpec,
        provider_registry: ProviderCapabilityRegistry = THESTATSAPI_CAPABILITIES_V1,
        target_registry: TargetRegistry = TARGET_REGISTRY_V1,
        history_metrics: tuple[HistoryMetric, ...] = DEFAULT_HISTORY_METRICS,
    ) -> None:
        self.spec = spec
        self.provider_registry = provider_registry
        self.target_registry = target_registry
        self.history_metrics = history_metrics
        self._validate_metric_contracts()

    def _validate_metric_contracts(self) -> None:
        eligible = set(self.provider_registry.eligible_historical_fields())
        # Goals are outcomes but are also legitimate lagged evidence for later
        # fixtures; the registry explicitly marks them historical-eligible.
        for metric in self.history_metrics:
            for field_name in (metric.home_field, metric.away_field):
                if field_name not in eligible:
                    raise DatasetIntegrityError(
                        f"History metric {metric.name!r} uses field {field_name!r} "
                        "without a VERIFIED historical provider contract"
                    )

    def build(self, matches: Iterable[ResearchMatch]) -> PITDatasetArtifact:
        ordered = self._validate_and_sort(tuple(matches))

        team_global: dict[str, _TeamHistoryState] = {}
        team_comp: dict[tuple[str, str], _TeamHistoryState] = {}
        team_venue: dict[tuple[str, str], _TeamHistoryState] = {}
        competition: dict[str, _CompetitionState] = {}

        pending: list[tuple[float, str, ResearchMatch]] = []
        rows: list[PITFeatureRow] = []

        chain = _EMPTY_CHAIN
        eligible_history_matches = 0
        max_source_kickoff: Optional[float] = None
        max_source_available: Optional[float] = None
        excluded_extra_time = 0

        for match in ordered:
            fixture_key = self._fixture_key(match)
            cutoff = float(match.date_unix - self.spec.decision_horizon_seconds)

            while pending and pending[0][0] <= cutoff:
                available_at, source_key, source_match = heapq.heappop(pending)
                self._ingest_history(
                    source_match,
                    team_global=team_global,
                    team_comp=team_comp,
                    team_venue=team_venue,
                    competition=competition,
                )
                chain = self._extend_chain(
                    chain,
                    source_match,
                    available_at=available_at,
                )
                eligible_history_matches += 1
                max_source_kickoff = max(
                    max_source_kickoff or float("-inf"),
                    float(source_match.date_unix),
                )
                max_source_available = max(
                    max_source_available or float("-inf"),
                    float(available_at),
                )

            features = self._snapshot_features(
                match,
                team_global=team_global,
                team_comp=team_comp,
                team_venue=team_venue,
                competition=competition,
            )
            observations = self.target_registry.observations(match)
            lineage = HistoryLineage(
                eligible_history_matches=eligible_history_matches,
                source_chain_digest=chain.hex(),
                max_source_kickoff_ts=max_source_kickoff,
                max_source_available_at=max_source_available,
            )

            self._assert_row_pit(
                match=match,
                cutoff=cutoff,
                lineage=lineage,
                features=features,
            )

            rows.append(
                self._row_from(
                    match=match,
                    fixture_key=fixture_key,
                    cutoff=cutoff,
                    features=features,
                    observations=observations,
                    lineage=lineage,
                )
            )

            if (
                self.spec.exclude_extra_time_history
                and match.has_extra_time_or_shootout_metadata
            ):
                excluded_extra_time += 1
                continue

            available_at = float(
                match.date_unix
                + self.spec.reconstructed_post_match_embargo_seconds
            )
            heapq.heappush(pending, (available_at, fixture_key, match))

        manifest = self._manifest(
            ordered=ordered,
            rows=rows,
            excluded_extra_time=excluded_extra_time,
            pending_at_last_cutoff=len(pending),
        )
        return PITDatasetArtifact(manifest=manifest, rows=tuple(rows))

    def _validate_and_sort(
        self,
        matches: tuple[ResearchMatch, ...],
    ) -> tuple[ResearchMatch, ...]:
        seen: set[str] = set()
        for match in matches:
            fixture_key = self._fixture_key(match)
            if fixture_key in seen:
                raise DatasetIntegrityError(f"Duplicate fixture {fixture_key}")
            seen.add(fixture_key)
            if match.date_unix <= 0:
                raise DatasetIntegrityError(
                    f"Non-positive kickoff for {fixture_key}"
                )
            if match.home_team_ref == match.away_team_ref:
                raise DatasetIntegrityError(
                    f"Home and away identity collide for {fixture_key}"
                )
            if match.source_provider.upper() != self.provider_registry.provider.upper():
                raise DatasetIntegrityError(
                    f"Provider mismatch for {fixture_key}: "
                    f"{match.source_provider!r} != {self.provider_registry.provider!r}"
                )

        return tuple(
            sorted(
                matches,
                key=lambda match: (
                    match.date_unix,
                    self._fixture_key(match),
                ),
            )
        )

    @staticmethod
    def _fixture_key(match: ResearchMatch) -> str:
        required = {
            "source_provider": match.source_provider,
            "source_match_ref": match.source_match_ref,
            "competition_ref": match.competition_ref,
            "season_ref": match.season_ref,
            "home_team_ref": match.home_team_ref,
            "away_team_ref": match.away_team_ref,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise DatasetIntegrityError(
                f"Missing stable identity fields: {', '.join(missing)}"
            )
        assert match.stable_fixture_key is not None
        return match.stable_fixture_key

    def _state(
        self,
        mapping: dict[Any, _TeamHistoryState],
        key: Any,
    ) -> _TeamHistoryState:
        state = mapping.get(key)
        if state is None:
            state = _TeamHistoryState(metrics=self.history_metrics)
            mapping[key] = state
        return state

    def _competition_state(
        self,
        mapping: dict[str, _CompetitionState],
        key: str,
    ) -> _CompetitionState:
        state = mapping.get(key)
        if state is None:
            state = _CompetitionState(metrics=self.history_metrics)
            mapping[key] = state
        return state

    def _ingest_history(
        self,
        match: ResearchMatch,
        *,
        team_global: dict[str, _TeamHistoryState],
        team_comp: dict[tuple[str, str], _TeamHistoryState],
        team_venue: dict[tuple[str, str], _TeamHistoryState],
        competition: dict[str, _CompetitionState],
    ) -> None:
        assert match.home_team_ref
        assert match.away_team_ref
        assert match.competition_ref

        self._state(team_global, match.home_team_ref).add(
            match=match,
            team_is_home=True,
        )
        self._state(team_global, match.away_team_ref).add(
            match=match,
            team_is_home=False,
        )
        self._state(
            team_comp,
            (match.home_team_ref, match.competition_ref),
        ).add(match=match, team_is_home=True)
        self._state(
            team_comp,
            (match.away_team_ref, match.competition_ref),
        ).add(match=match, team_is_home=False)
        self._state(team_venue, (match.home_team_ref, "HOME")).add(
            match=match,
            team_is_home=True,
        )
        self._state(team_venue, (match.away_team_ref, "AWAY")).add(
            match=match,
            team_is_home=False,
        )
        self._competition_state(competition, match.competition_ref).add(match)

    def _snapshot_features(
        self,
        match: ResearchMatch,
        *,
        team_global: dict[str, _TeamHistoryState],
        team_comp: dict[tuple[str, str], _TeamHistoryState],
        team_venue: dict[tuple[str, str], _TeamHistoryState],
        competition: dict[str, _CompetitionState],
    ) -> dict[str, float | int | None]:
        assert match.home_team_ref
        assert match.away_team_ref
        assert match.competition_ref

        features: dict[str, float | int | None] = {}
        target_kickoff = float(match.date_unix)

        for prefix, team_ref, venue in (
            ("home", match.home_team_ref, "HOME"),
            ("away", match.away_team_ref, "AWAY"),
        ):
            global_state = team_global.get(team_ref) or _TeamHistoryState(
                metrics=self.history_metrics
            )
            comp_state = team_comp.get(
                (team_ref, match.competition_ref)
            ) or _TeamHistoryState(metrics=self.history_metrics)
            venue_state = team_venue.get(
                (team_ref, venue)
            ) or _TeamHistoryState(metrics=self.history_metrics)

            features.update(
                global_state.snapshot(
                    prefix=prefix,
                    target_kickoff_ts=target_kickoff,
                )
            )
            features.update(
                self._namespace_team_snapshot(
                    comp_state.snapshot(
                        prefix=prefix,
                        target_kickoff_ts=target_kickoff,
                    ),
                    prefix=prefix,
                    namespace="comp",
                )
            )
            features.update(
                self._namespace_team_snapshot(
                    venue_state.snapshot(
                        prefix=prefix,
                        target_kickoff_ts=target_kickoff,
                    ),
                    prefix=prefix,
                    namespace="venue",
                )
            )

        comp_state = competition.get(match.competition_ref) or _CompetitionState(
            metrics=self.history_metrics
        )
        features.update(comp_state.snapshot())
        return dict(sorted(features.items()))

    @staticmethod
    def _namespace_team_snapshot(
        snapshot: dict[str, float | int | None],
        *,
        prefix: str,
        namespace: str,
    ) -> dict[str, float | int | None]:
        lead = f"{prefix}_"
        return {
            f"{prefix}_{namespace}_{key[len(lead):]}": value
            for key, value in snapshot.items()
        }

    @staticmethod
    def _extend_chain(
        current: bytes,
        match: ResearchMatch,
        *,
        available_at: float,
    ) -> bytes:
        payload = {
            "fixture_key": match.stable_fixture_key,
            "kickoff_ts": match.date_unix,
            "available_at": available_at,
            "competition_ref": match.competition_ref,
            "home_team_ref": match.home_team_ref,
            "away_team_ref": match.away_team_ref,
        }
        return hashlib.sha256(
            current + b"\n" + canonical_json(payload).encode("utf-8")
        ).digest()

    @staticmethod
    def _assert_row_pit(
        *,
        match: ResearchMatch,
        cutoff: float,
        lineage: HistoryLineage,
        features: dict[str, float | int | None],
    ) -> None:
        if cutoff >= match.date_unix:
            raise DatasetIntegrityError("Forecast cutoff must be before kickoff")
        if (
            lineage.max_source_available_at is not None
            and lineage.max_source_available_at > cutoff
        ):
            raise DatasetIntegrityError(
                "Feature lineage contains evidence available after cutoff"
            )
        if any(
            token in name.lower()
            for name in features
            for token in ("odds", "price", "market_prob", "p_market")
        ):
            raise DatasetIntegrityError(
                "Independent PIT feature table contains market-derived fields"
            )

    def _row_from(
        self,
        *,
        match: ResearchMatch,
        fixture_key: str,
        cutoff: float,
        features: dict[str, float | int | None],
        observations: dict[str, TargetObservation],
        lineage: HistoryLineage,
    ) -> PITFeatureRow:
        assert match.source_match_ref
        assert match.competition_ref
        assert match.season_ref
        assert match.home_team_ref
        assert match.away_team_ref

        targets = {
            target_id: obs.count if obs.available else None
            for target_id, obs in observations.items()
        }
        statuses = {
            target_id: obs.status.value
            for target_id, obs in observations.items()
        }
        reasons = {
            target_id: obs.reason
            for target_id, obs in observations.items()
            if obs.reason
        }

        return PITFeatureRow(
            fixture_key=fixture_key,
            source_provider=match.source_provider,
            source_match_ref=match.source_match_ref,
            competition_ref=match.competition_ref,
            season_ref=match.season_ref,
            home_team_ref=match.home_team_ref,
            away_team_ref=match.away_team_ref,
            home_team_name=match.home_team,
            away_team_name=match.away_team,
            kickoff_ts=float(match.date_unix),
            cutoff_ts=cutoff,
            decision_horizon_seconds=self.spec.decision_horizon_seconds,
            features=features,
            targets=targets,
            target_status=statuses,
            target_reasons=reasons,
            lineage=lineage,
        )

    def _manifest(
        self,
        *,
        ordered: tuple[ResearchMatch, ...],
        rows: list[PITFeatureRow],
        excluded_extra_time: int,
        pending_at_last_cutoff: int,
    ) -> PITDatasetManifest:
        row_dicts = [row.to_dict() for row in rows]
        feature_names = sorted(
            {name for row in rows for name in row.features}
        )
        status_counts: dict[str, dict[str, int]] = {}
        for row in rows:
            for target_id, status in row.target_status.items():
                target_counts = status_counts.setdefault(target_id, {})
                target_counts[status] = target_counts.get(status, 0) + 1

        source_payload = [
            match.to_dict()
            for match in sorted(
                ordered,
                key=lambda item: self._fixture_key(item),
            )
        ]

        cutoffs = [row.cutoff_ts for row in rows]
        return PITDatasetManifest(
            schema_version=self.spec.schema_version,
            provider=self.provider_registry.provider,
            provider_registry_version=self.provider_registry.version,
            provider_contract_source_url=self.provider_registry.contract_source_url,
            provider_contract_source_sha256=self.provider_registry.contract_source_sha256,
            provider_contract_verified_on=self.provider_registry.contract_verified_on,
            target_registry_version=self.target_registry.version,
            decision_horizon_seconds=self.spec.decision_horizon_seconds,
            historical_availability_policy=self.spec.availability_policy,
            reconstructed_post_match_embargo_seconds=(
                self.spec.reconstructed_post_match_embargo_seconds
            ),
            exclude_extra_time_history=self.spec.exclude_extra_time_history,
            n_input_matches=len(ordered),
            n_rows=len(rows),
            n_feature_fields=len(feature_names),
            first_cutoff_ts=min(cutoffs) if cutoffs else None,
            last_cutoff_ts=max(cutoffs) if cutoffs else None,
            source_data_hash=sha256_json(source_payload),
            rows_hash=rows_digest(row_dicts),
            rows_file_sha256=sha256_bytes(canonical_rows_jsonl(row_dicts)),
            feature_schema_hash=sha256_json(feature_names),
            target_status_counts=status_counts,
            excluded_history_counts={
                "extra_time_or_shootout": excluded_extra_time,
                "pending_at_last_cutoff": pending_at_last_cutoff,
            },
        )
