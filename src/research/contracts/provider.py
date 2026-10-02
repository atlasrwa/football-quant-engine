"""Provider-scoped semantic contracts for QFE V2.

This module is deliberately declarative. A field is not eligible merely because
it exists in a payload or in ResearchMatch; it must have an explicit
provider-scoped contract.

Coverage is measured from the corpus at runtime. No static coverage percentage
is treated as truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from src.research.data_source import ResearchMatch


THESTATSAPI_CONTRACT_SOURCE_URL = "https://api.thestatsapi.com/llms.txt"
THESTATSAPI_CONTRACT_SOURCE_SHA256 = (
    "bbe70fdedb92b75de8c92426ac4b14199aa640f6f524d8aa80e92b926e02b9c1"
)
THESTATSAPI_CONTRACT_VERIFIED_ON = "2026-10-01"


class SemanticStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NEEDS_AUDIT = "NEEDS_AUDIT"


class AvailabilitySemantics(str, Enum):
    FINAL_FIXTURE = "FINAL_FIXTURE"
    POST_MATCH_FINALIZED = "POST_MATCH_FINALIZED"
    PROSPECTIVE_TIMESTAMPED_ONLY = "PROSPECTIVE_TIMESTAMPED_ONLY"


class FieldRole(str, Enum):
    IDENTITY = "IDENTITY"
    OUTCOME = "OUTCOME"
    HISTORICAL_EVIDENCE = "HISTORICAL_EVIDENCE"


@dataclass(frozen=True, slots=True)
class EvidenceFieldContract:
    canonical_field: str
    provider_path: str
    definition: str
    unit: str
    period: str
    side_semantics: str
    missing_semantics: str
    availability: AvailabilitySemantics
    role: FieldRole
    semantic_status: SemanticStatus = SemanticStatus.VERIFIED
    historical_model_eligible: bool = False
    target_source_eligible: bool = False
    notes: str = ""


@dataclass(frozen=True, slots=True)
class FieldCoverage:
    canonical_field: str
    available: int
    missing: int
    coverage: float
    semantic_status: SemanticStatus
    historical_model_eligible: bool
    target_source_eligible: bool


@dataclass(frozen=True, slots=True)
class CapabilityAudit:
    provider: str
    registry_version: str
    contract_source_url: str
    contract_source_sha256: str
    contract_verified_on: str
    n_matches: int
    fields: tuple[FieldCoverage, ...]

    def by_field(self) -> dict[str, FieldCoverage]:
        return {row.canonical_field: row for row in self.fields}

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "registry_version": self.registry_version,
            "contract_source_url": self.contract_source_url,
            "contract_source_sha256": self.contract_source_sha256,
            "contract_verified_on": self.contract_verified_on,
            "n_matches": self.n_matches,
            "fields": [
                {
                    "canonical_field": row.canonical_field,
                    "available": row.available,
                    "missing": row.missing,
                    "coverage": row.coverage,
                    "semantic_status": row.semantic_status.value,
                    "historical_model_eligible": row.historical_model_eligible,
                    "target_source_eligible": row.target_source_eligible,
                }
                for row in self.fields
            ],
        }


@dataclass(frozen=True, slots=True)
class ProviderCapabilityRegistry:
    provider: str
    version: str
    contract_source_url: str
    contract_source_sha256: str
    contract_verified_on: str
    fields: tuple[EvidenceFieldContract, ...]

    def __post_init__(self) -> None:
        names = [field.canonical_field for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate canonical_field in provider registry")

    def contract(self, canonical_field: str) -> EvidenceFieldContract:
        for field in self.fields:
            if field.canonical_field == canonical_field:
                return field
        raise KeyError(canonical_field)

    def eligible_historical_fields(self) -> tuple[str, ...]:
        return tuple(
            field.canonical_field
            for field in self.fields
            if field.historical_model_eligible
            and field.semantic_status == SemanticStatus.VERIFIED
        )

    def audit(self, matches: Iterable[ResearchMatch]) -> CapabilityAudit:
        rows = tuple(matches)
        n = len(rows)
        coverage: list[FieldCoverage] = []
        for contract in self.fields:
            available = sum(
                1
                for match in rows
                if getattr(match, contract.canonical_field, None) is not None
            )
            missing = n - available
            coverage.append(
                FieldCoverage(
                    canonical_field=contract.canonical_field,
                    available=available,
                    missing=missing,
                    coverage=(available / n) if n else 0.0,
                    semantic_status=contract.semantic_status,
                    historical_model_eligible=contract.historical_model_eligible,
                    target_source_eligible=contract.target_source_eligible,
                )
            )
        return CapabilityAudit(
            provider=self.provider,
            registry_version=self.version,
            contract_source_url=self.contract_source_url,
            contract_source_sha256=self.contract_source_sha256,
            contract_verified_on=self.contract_verified_on,
            n_matches=n,
            fields=tuple(coverage),
        )


THESTATSAPI_CAPABILITIES_V1 = ProviderCapabilityRegistry(
    provider="THESTATSAPI",
    version="thestatsapi-capabilities-v1",
    contract_source_url=THESTATSAPI_CONTRACT_SOURCE_URL,
    contract_source_sha256=THESTATSAPI_CONTRACT_SOURCE_SHA256,
    contract_verified_on=THESTATSAPI_CONTRACT_VERIFIED_ON,
    fields=(
        EvidenceFieldContract(
            "home_goals",
            "match.score.home",
            "Provider final home score. Regulation target use requires no ET/shootout metadata.",
            "count",
            "match",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.FINAL_FIXTURE,
            FieldRole.OUTCOME,
            historical_model_eligible=True,
            target_source_eligible=True,
        ),
        EvidenceFieldContract(
            "away_goals",
            "match.score.away",
            "Provider final away score. Regulation target use requires no ET/shootout metadata.",
            "count",
            "match",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.FINAL_FIXTURE,
            FieldRole.OUTCOME,
            historical_model_eligible=True,
            target_source_eligible=True,
        ),
        EvidenceFieldContract(
            "corners_home",
            "stats.overview.corner_kicks.all.home",
            "Home corner kicks in provider all-period match statistics.",
            "count",
            "all",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
            target_source_eligible=True,
        ),
        EvidenceFieldContract(
            "corners_away",
            "stats.overview.corner_kicks.all.away",
            "Away corner kicks in provider all-period match statistics.",
            "count",
            "all",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
            target_source_eligible=True,
        ),
        EvidenceFieldContract(
            "shots_home",
            "stats.overview.total_shots.all.home",
            "Home total shots.",
            "count",
            "all",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "shots_away",
            "stats.overview.total_shots.all.away",
            "Away total shots.",
            "count",
            "all",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "shots_on_target_home",
            "stats.overview.shots_on_target.all.home",
            "Home shots on target.",
            "count",
            "all",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "shots_on_target_away",
            "stats.overview.shots_on_target.all.away",
            "Away shots on target.",
            "count",
            "all",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "fouls_home",
            "stats.overview.fouls.all.home",
            "Home fouls.",
            "count",
            "all",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "fouls_away",
            "stats.overview.fouls.all.away",
            "Away fouls.",
            "count",
            "all",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "yellow_cards_home",
            "stats.overview.yellow_cards.all.home",
            "Home yellow-card count as reported by provider.",
            "count",
            "all",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
            notes="Not automatically equivalent to sportsbook bookings settlement.",
        ),
        EvidenceFieldContract(
            "yellow_cards_away",
            "stats.overview.yellow_cards.all.away",
            "Away yellow-card count as reported by provider.",
            "count",
            "all",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
            notes="Not automatically equivalent to sportsbook bookings settlement.",
        ),
        EvidenceFieldContract(
            "red_cards_home",
            "stats.overview.red_cards.all.home",
            "Home red-card count as reported by provider.",
            "count",
            "all",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
            notes="Card weighting and second-yellow semantics require explicit settlement reconciliation.",
        ),
        EvidenceFieldContract(
            "red_cards_away",
            "stats.overview.red_cards.all.away",
            "Away red-card count as reported by provider.",
            "count",
            "all",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
            notes="Card weighting and second-yellow semantics require explicit settlement reconciliation.",
        ),
        EvidenceFieldContract(
            "possession_home",
            "stats.overview.ball_possession.all.home",
            "Home possession percentage.",
            "percent",
            "all",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "possession_away",
            "stats.overview.ball_possession.all.away",
            "Away possession percentage.",
            "percent",
            "all",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "home_xg",
            "stats.overview.expected_goals.all.home",
            "Home expected goals where provider supplies it.",
            "xg",
            "all",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "away_xg",
            "stats.overview.expected_goals.all.away",
            "Away expected goals where provider supplies it.",
            "xg",
            "all",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            historical_model_eligible=True,
        ),
        EvidenceFieldContract(
            "npxg_home",
            "stats.np_expected_goals.all.home",
            "Provider non-penalty expected-goals field retained by the normalizer.",
            "xg",
            "all",
            "home",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            semantic_status=SemanticStatus.NEEDS_AUDIT,
        ),
        EvidenceFieldContract(
            "npxg_away",
            "stats.np_expected_goals.all.away",
            "Provider non-penalty expected-goals field retained by the normalizer.",
            "xg",
            "all",
            "away",
            "null=missing; zero valid",
            AvailabilitySemantics.POST_MATCH_FINALIZED,
            FieldRole.HISTORICAL_EVIDENCE,
            semantic_status=SemanticStatus.NEEDS_AUDIT,
        ),
    ),
)
