"""The dual-provider intersection rule — the engine's league universe.

THE RULE
========
A competition may enter the engine universe when **all four** hold:

1. FootyStats supports it (it is a row in the provider registry, which is built
   from the FootyStats chosen-league list).
2. TheStatsAPI supports the corresponding competition (a counterpart exists in
   the cached TheStatsAPI inventory).
3. Provider identity maps deterministically: exactly one FootyStats season id
   linked to exactly one TheStatsAPI competition id, confirmed through the
   canonical identity registry rather than by display name.
4. The mapping is not ambiguous, split, or unresolved.

Everything else is **excluded with a named reason**. There is no "probably the
same competition" path: a mapping that cannot prove it identifies one competition
on each side is refused, because a wrong join silently mixes two leagues' fixtures
into one evidence pool and nothing downstream can detect it.

WHY THIS EXISTS (Pilot C deprecation)
=====================================
Pilot C was a pre-registered four-league experiment
(``comp_3039``/``comp_8321``/``comp_9777``/``comp_0976``). Its competition list
was copied into ``config/forecast_broadcast_scope.json``, and because a forecast
commitment is the prerequisite for every downstream research artifact — capture
join, shadow residual, evaluation, research telemetry — that four-league list
became the engine's entire reach. Prospective *capture* meanwhile already spanned
46 competitions, so the engine was observing markets it could never produce a
research observation for.

This module replaces that list as the *source of eligibility*. Pilot C membership
is not an input to any function here. It is not read, not consulted, and not
special-cased.

LEGACY ``model_status`` IS NON-BEHAVIORAL
=========================================
The registry carries a ``model_status`` field with historical values including
``PILOT_C_EXISTING_SCOPE``. It is **deprecated metadata**: retained so persisted
registry snapshots stay readable and reproducible, but it must never influence the
processing universe. :func:`evaluate_league` deliberately never reads it, and
:func:`assert_model_status_non_behavioral` exists so a test can pin that property
rather than trusting a comment.

Crucially, a two-season model corpus is **not** an eligibility input either.
Corpus depth decides which *stages* can run (a model cannot be fitted without
training data); it does not decide whether the competition belongs to the engine.
A league present in both providers keeps accumulating provider and prospective
observations even while it has no fittable model — which is precisely how it
eventually acquires one.

FAIL-CLOSED, INCLUDING SPLIT SEASONS
====================================
Apertura/Clausura representations (``SPLIT_OR_PARTIAL``) are **not** activated
just to raise the league count. One FootyStats league mapping onto two
TheStatsAPI competitions, or onto only one half of a split season, cannot be
represented deterministically without risking fixtures from the wrong
competition/season being pooled together. Those leagues stay excluded and the
report says exactly why, so the exclusion is a visible decision rather than a
gap.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional

from src.research.identity.registry_loader import DEFAULT_REGISTRY_PATH
from src.research.prospective.crosswalk import (
    CrosswalkEntry,
    IdentityStatus,
    build_crosswalk,
)

#: Contract string for the machine-readable universe report.
DUAL_PROVIDER_UNIVERSE_CONTRACT = "dual-provider-league-universe/v1"

#: The legacy Pilot-C ``model_status`` value. Retained in persisted registry
#: metadata for backward compatibility and reproducibility of historical
#: snapshots; it MUST NOT influence eligibility. Kept as a named constant so the
#: deprecation is greppable and testable rather than a comment somebody deletes.
DEPRECATED_PILOT_C_MODEL_STATUS = "PILOT_C_EXISTING_SCOPE"

#: Every historical ``model_status`` value. All of them are descriptive only.
#: None of them is read by this module, and none may gate the engine universe.
#: ``BLOCKED_NO_TWO_SEASON_CORPUS`` in particular is *not* an exclusion: corpus
#: depth is a model-readiness fact, not a provider-eligibility fact.
LEGACY_NON_BEHAVIORAL_MODEL_STATUSES: frozenset[str] = frozenset(
    {
        DEPRECATED_PILOT_C_MODEL_STATUS,
        "RESEARCH_ONLY_NOT_VALIDATED",
        "BLOCKED_NO_TWO_SEASON_CORPUS",
        "BLOCKED_PROVIDER_MAPPING",
    }
)


class ScopeDecision(str, Enum):
    """Whether a competition belongs to the engine universe."""

    #: Both providers support it and identity resolves deterministically.
    ELIGIBLE = "ELIGIBLE"
    #: Fails at least one condition of the intersection rule.
    EXCLUDED = "EXCLUDED"


class ScopeExclusionReason(str, Enum):
    """Why a competition is not in the engine universe.

    These are deliberately distinct rather than collapsed into one "unsupported"
    bucket. "The provider does not have this competition" and "we cannot prove
    which competition this is" call for completely different remedies, and a
    report that cannot tell them apart cannot be acted on.
    """

    NONE = "NONE"
    #: No FootyStats identity (absent from, or unidentifiable in, the registry).
    FOOTYSTATS_UNSUPPORTED = "FOOTYSTATS_UNSUPPORTED"
    #: FootyStats has it; TheStatsAPI has no counterpart competition at all.
    THESTATSAPI_UNSUPPORTED = "THESTATSAPI_UNSUPPORTED"
    #: Registry explicitly marks the provider mapping blocked.
    PROVIDER_MAPPING_BLOCKED = "PROVIDER_MAPPING_BLOCKED"
    #: A counterpart exists but identity cannot be pinned to exactly one
    #: competition on each side (multiple candidates, or link disagreement).
    IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
    #: No usable mapping status at all; identity is simply unknown.
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
    #: Split/partial season representation (e.g. Apertura/Clausura) that cannot
    #: be represented deterministically without mixing competitions or seasons.
    SPLIT_OR_PARTIAL_NOT_DETERMINISTIC = "SPLIT_OR_PARTIAL_NOT_DETERMINISTIC"


#: Exclusion reasons that mean "the provider genuinely lacks the competition",
#: as distinct from "we cannot safely identify it". Used by the coverage report
#: so ``provider unsupported`` never gets conflated with ``identity unresolved``.
PROVIDER_UNSUPPORTED_REASONS: frozenset[ScopeExclusionReason] = frozenset(
    {
        ScopeExclusionReason.FOOTYSTATS_UNSUPPORTED,
        ScopeExclusionReason.THESTATSAPI_UNSUPPORTED,
        ScopeExclusionReason.PROVIDER_MAPPING_BLOCKED,
    }
)

#: Exclusion reasons that mean "both providers may well have it, but we refuse to
#: guess which competition it is".
IDENTITY_UNSAFE_REASONS: frozenset[ScopeExclusionReason] = frozenset(
    {
        ScopeExclusionReason.IDENTITY_AMBIGUOUS,
        ScopeExclusionReason.IDENTITY_UNRESOLVED,
        ScopeExclusionReason.SPLIT_OR_PARTIAL_NOT_DETERMINISTIC,
    }
)


@dataclass(frozen=True, slots=True)
class DualProviderLeague:
    """One league's dual-provider eligibility decision, with its evidence."""

    canonical_name: str
    country: Optional[str]
    footystats_id: Optional[str]
    footystats_name: str
    thestatsapi_competition_id: Optional[str]
    thestatsapi_name: Optional[str]
    decision: ScopeDecision
    exclusion_reason: ScopeExclusionReason
    detail: str
    identity_status: str
    registry_mapping_status: str
    verification_method: str
    #: Every TheStatsAPI competition id the registry associates with this league.
    #: For an eligible league this is exactly one id and equals
    #: ``thestatsapi_competition_id``. For an ambiguous/split league it is kept as
    #: diagnostic evidence and is deliberately NOT joined.
    candidate_competition_ids: tuple[str, ...]
    #: Provider capability flags, carried through unchanged. ``None`` is UNKNOWN
    #: and is never coerced to ``False``.
    odds_available: Optional[bool]
    xg_available: Optional[bool]
    #: Completed corpus seasons. Reported for model-readiness triage ONLY; it is
    #: not an input to :attr:`decision`.
    corpus_complete_seasons: Optional[int]
    #: The legacy, non-behavioral registry label. Reported so its irrelevance is
    #: auditable; never read as a gate.
    legacy_model_status: Optional[str] = None

    @property
    def is_eligible(self) -> bool:
        return self.decision is ScopeDecision.ELIGIBLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "country": self.country,
            "footystats_id": self.footystats_id,
            "footystats_name": self.footystats_name,
            "thestatsapi_competition_id": self.thestatsapi_competition_id,
            "thestatsapi_name": self.thestatsapi_name,
            "decision": self.decision.value,
            "exclusion_reason": self.exclusion_reason.value,
            "detail": self.detail,
            "identity_status": self.identity_status,
            "registry_mapping_status": self.registry_mapping_status,
            "verification_method": self.verification_method,
            "candidate_competition_ids": list(self.candidate_competition_ids),
            "odds_available": self.odds_available,
            "xg_available": self.xg_available,
            "corpus_complete_seasons": self.corpus_complete_seasons,
            "legacy_model_status": self.legacy_model_status,
            "legacy_model_status_is_behavioral": False,
        }


def _split_detail(entry: CrosswalkEntry, ids: tuple[str, ...]) -> str:
    """Explain a split/partial refusal in terms of what would go wrong."""
    if len(ids) > 1:
        return (
            f"registry maps this single FootyStats league onto {len(ids)} separate "
            f"TheStatsAPI competitions ({', '.join(ids)}); activating it would pool "
            "fixtures from distinct competitions/seasons into one evidence set, so "
            "it stays excluded until the split is modelled explicitly"
        )
    return (
        "registry marks the provider representation split/partial: the TheStatsAPI "
        "counterpart covers only part of the FootyStats season, so a fixture from "
        "the unmapped part would either be dropped silently or attributed to the "
        "wrong competition. Excluded until the split is modelled explicitly"
    )


def evaluate_league(
    entry: CrosswalkEntry,
    *,
    corpus_complete_seasons: Optional[int] = None,
    legacy_model_status: Optional[str] = None,
) -> DualProviderLeague:
    """Apply the dual-provider intersection rule to one crosswalk entry.

    Identity truth is **not** re-derived here. :func:`build_crosswalk` already
    resolves each registry league through the canonical identity registry, which
    links only ``MATCHED`` entries carrying exactly one TheStatsAPI competition
    id and confirms the link rather than trusting the registry's word. This
    function turns that identity verdict into an explicit engine-scope decision
    with an actionable reason.

    Args:
        entry: the crosswalk row for one FootyStats league.
        corpus_complete_seasons: completed corpus seasons, for reporting only.
        legacy_model_status: the deprecated registry label, for reporting only.

    Returns:
        The :class:`DualProviderLeague` decision. Never raises: an unrecognised
        state becomes ``IDENTITY_UNRESOLVED`` rather than an optimistic default.
    """
    ids = tuple(
        str(i) for i in (entry.evidence or {}).get("thestatsapi_competition_ids", []) or []
    )
    mapping_status = str((entry.evidence or {}).get("mapping_status", "") or "")

    common = {
        "canonical_name": entry.canonical_name,
        "country": entry.country,
        "footystats_id": entry.footystats_id,
        "footystats_name": entry.footystats_name,
        "thestatsapi_name": entry.thestatsapi_name,
        "identity_status": entry.identity_status.value,
        "registry_mapping_status": mapping_status,
        "verification_method": entry.verification_method,
        "candidate_competition_ids": ids,
        "odds_available": entry.odds_available,
        "xg_available": entry.xg_available,
        "corpus_complete_seasons": corpus_complete_seasons,
        "legacy_model_status": legacy_model_status,
    }

    def excluded(reason: ScopeExclusionReason, detail: str) -> DualProviderLeague:
        return DualProviderLeague(
            thestatsapi_competition_id=None,
            decision=ScopeDecision.EXCLUDED,
            exclusion_reason=reason,
            detail=detail,
            **common,
        )

    # Condition 1: FootyStats side must be identifiable. Without a FootyStats
    # season id there is nothing to link from, so no deterministic mapping is
    # possible regardless of what TheStatsAPI has.
    if not entry.footystats_id or not entry.footystats_name:
        return excluded(
            ScopeExclusionReason.FOOTYSTATS_UNSUPPORTED,
            "no usable FootyStats identity (missing league name or current season id)",
        )

    # Condition 2: TheStatsAPI must actually have a counterpart competition.
    if entry.identity_status == IdentityStatus.API_UNSUPPORTED:
        if ids:
            return excluded(
                ScopeExclusionReason.PROVIDER_MAPPING_BLOCKED,
                "registry marks the provider mapping BLOCKED; the reviewed "
                "counterpart is not resolvable in the TheStatsAPI inventory",
            )
        return excluded(
            ScopeExclusionReason.THESTATSAPI_UNSUPPORTED,
            "TheStatsAPI has no counterpart competition for this FootyStats league",
        )
    if not ids:
        return excluded(
            ScopeExclusionReason.THESTATSAPI_UNSUPPORTED,
            "no TheStatsAPI competition id is associated with this FootyStats league",
        )

    # Conditions 3 and 4: identity must resolve deterministically to exactly one
    # competition per provider. Split/partial is reported separately from generic
    # ambiguity because the remedy differs (model the split, vs. fix the link).
    if mapping_status == "SPLIT_OR_PARTIAL" or (
        entry.identity_status == IdentityStatus.AMBIGUOUS and len(ids) > 1
    ):
        return excluded(
            ScopeExclusionReason.SPLIT_OR_PARTIAL_NOT_DETERMINISTIC,
            _split_detail(entry, ids),
        )
    if entry.identity_status in (IdentityStatus.AMBIGUOUS, IdentityStatus.PROBABLE):
        return excluded(
            ScopeExclusionReason.IDENTITY_AMBIGUOUS,
            f"identity is {entry.identity_status.value} "
            f"({entry.verification_method}); refusing to guess which competition "
            "this is",
        )
    if entry.identity_status != IdentityStatus.VERIFIED:
        return excluded(
            ScopeExclusionReason.IDENTITY_UNRESOLVED,
            f"identity is {entry.identity_status.value}; no deterministic provider "
            "mapping is available",
        )

    # VERIFIED implies the canonical registry linked exactly one comp id. Assert
    # it rather than assume it: this is the one invariant whose violation would
    # silently attach a competition id to the wrong league.
    cid = entry.thestatsapi_competition_id
    if not cid:
        return excluded(
            ScopeExclusionReason.IDENTITY_UNRESOLVED,
            "identity reported VERIFIED but no TheStatsAPI competition id was "
            "linked; failing closed rather than activating without a stable id",
        )
    if len(ids) != 1 or ids[0] != cid:
        return excluded(
            ScopeExclusionReason.IDENTITY_AMBIGUOUS,
            f"linked competition id {cid} is not the unique registry candidate "
            f"({', '.join(ids) or 'none'}); failing closed",
        )

    return DualProviderLeague(
        thestatsapi_competition_id=cid,
        decision=ScopeDecision.ELIGIBLE,
        exclusion_reason=ScopeExclusionReason.NONE,
        detail=(
            "FootyStats and TheStatsAPI both support this competition and identity "
            f"resolves deterministically to {cid} via {entry.verification_method}"
        ),
        **common,
    )


@dataclass(frozen=True, slots=True)
class DualProviderUniverse:
    """The full decision set: every registry league, eligible or not.

    One row per registry league, always. A league that is excluded is *present
    and labelled*, never absent — an omitted league is indistinguishable from a
    league nobody has looked at, which is the ambiguity this whole refactor
    exists to remove.
    """

    leagues: tuple[DualProviderLeague, ...]
    registry_path: str

    @property
    def eligible(self) -> tuple[DualProviderLeague, ...]:
        return tuple(lg for lg in self.leagues if lg.is_eligible)

    @property
    def excluded(self) -> tuple[DualProviderLeague, ...]:
        return tuple(lg for lg in self.leagues if not lg.is_eligible)

    @property
    def eligible_competition_ids(self) -> tuple[str, ...]:
        """Eligible TheStatsAPI competition ids, sorted for determinism."""
        return tuple(
            sorted(
                lg.thestatsapi_competition_id
                for lg in self.eligible
                if lg.thestatsapi_competition_id
            )
        )

    def is_eligible(self, competition_id: Optional[str]) -> bool:
        """Membership by TheStatsAPI competition id. Never by name, never by model."""
        if not competition_id:
            return False
        return competition_id in frozenset(self.eligible_competition_ids)

    def label_for(self, competition_id: Optional[str]) -> Optional[str]:
        for lg in self.eligible:
            if lg.thestatsapi_competition_id == competition_id:
                return lg.canonical_name
        return None

    def league_for(self, competition_id: Optional[str]) -> Optional[DualProviderLeague]:
        if not competition_id:
            return None
        for lg in self.leagues:
            if lg.thestatsapi_competition_id == competition_id:
                return lg
        return None

    def exclusion_summary(self) -> dict[str, int]:
        """Count of excluded leagues by reason (sorted, deterministic)."""
        from collections import Counter

        counts = Counter(lg.exclusion_reason.value for lg in self.excluded)
        return dict(sorted(counts.items()))

    def summary(self) -> dict[str, Any]:
        return {
            "contract": DUAL_PROVIDER_UNIVERSE_CONTRACT,
            "registry_path": self.registry_path,
            "registry_leagues_total": len(self.leagues),
            "dual_provider_eligible": len(self.eligible),
            "excluded": len(self.excluded),
            "exclusion_reasons": self.exclusion_summary(),
            "eligible_competition_ids": list(self.eligible_competition_ids),
            "pilot_c_is_behavioral_input": False,
            "legacy_model_status_is_behavioral": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "leagues": [lg.to_dict() for lg in self.leagues],
        }


def _registry_side_channels(
    path: Path,
) -> tuple[dict[str, Optional[int]], dict[str, Optional[str]]]:
    """Read per-league corpus depth and the legacy model_status, for REPORTING.

    Both are keyed by FootyStats league name. Neither is used as a gate — they
    are read here so the universe report can *show* that an excluded league was
    not excluded for having a thin corpus, and that an eligible league was not
    eligible for carrying a Pilot-C label.
    """
    seasons: dict[str, Optional[int]] = {}
    legacy: dict[str, Optional[str]] = {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return seasons, legacy
    for entry in data.get("leagues", []) or []:
        if not isinstance(entry, dict):
            continue
        name = str((entry.get("footystats") or {}).get("name") or "")
        if not name:
            continue
        corpus = entry.get("corpus") or {}
        raw = corpus.get("complete_seasons")
        seasons[name] = int(raw) if isinstance(raw, (int, float)) else None
        status = entry.get("model_status")
        legacy[name] = str(status) if status is not None else None
    return seasons, legacy


def build_dual_provider_universe(
    path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    entries: Optional[Iterable[CrosswalkEntry]] = None,
) -> DualProviderUniverse:
    """Build the engine's league universe from the provider registry.

    Pure function of the registry file contents (or of injected crosswalk
    entries), so it is deterministic and testable with no network access.

    Args:
        path: the provider league registry.
        entries: pre-built crosswalk entries, for tests that construct identity
            states directly instead of writing a registry fixture.

    Returns:
        The :class:`DualProviderUniverse`, containing one row per league.
    """
    p = Path(path)
    rows = list(entries) if entries is not None else build_crosswalk(p)
    seasons, legacy = _registry_side_channels(p)
    leagues = tuple(
        evaluate_league(
            entry,
            corpus_complete_seasons=seasons.get(entry.canonical_name),
            legacy_model_status=legacy.get(entry.canonical_name),
        )
        for entry in rows
    )
    return DualProviderUniverse(leagues=leagues, registry_path=str(p))


def corpus_covered_competition_ids(
    universe: DualProviderUniverse, *, min_complete_seasons: int = 2
) -> frozenset[str]:
    """Eligible competitions the training corpus actually covers.

    This is **not** an eligibility filter. It exists for one narrow purpose: the
    corpus-freshness gate judges the corpus against "what the fixture calendar
    says has already been played", and that comparison is only meaningful over
    competitions the corpus was ever supposed to contain. Including a league the
    corpus has never covered would make a finished fixture there read as evidence
    of an ingestion failure, and would block every forecast in every league —
    turning coverage expansion into an outage.

    See :func:`src.research.prediction_engine.broadcast.corpus_freshness.in_scope_kickoffs`
    for the consumer of this set.
    """
    return frozenset(
        lg.thestatsapi_competition_id
        for lg in universe.eligible
        if lg.thestatsapi_competition_id
        and (lg.corpus_complete_seasons or 0) >= min_complete_seasons
    )


def assert_model_status_non_behavioral() -> None:
    """Pin the invariant that legacy ``model_status`` never gates eligibility.

    :func:`evaluate_league` takes ``legacy_model_status`` for reporting only. This
    helper re-runs the rule across every legacy value — including
    ``PILOT_C_EXISTING_SCOPE`` and ``None`` — on an otherwise identical entry and
    requires an identical decision.

    Raises:
        AssertionError: if any legacy label changes the outcome.
    """
    probe = CrosswalkEntry(
        canonical_competition_id="canon_probe",
        canonical_name="Probe League",
        country="Nowhere",
        footystats_id="999999",
        footystats_name="Probe League",
        thestatsapi_competition_id="comp_probe",
        thestatsapi_name="Probe",
        identity_status=IdentityStatus.VERIFIED,
        verification_method="level_a_registry_matched_single_id",
        odds_available=True,
        xg_available=True,
        has_team_stats=True,
        has_player_stats=True,
        evidence={
            "mapping_status": "MATCHED",
            "thestatsapi_competition_ids": ["comp_probe"],
        },
    )
    baseline = evaluate_league(probe, legacy_model_status=None)
    for status in sorted(LEGACY_NON_BEHAVIORAL_MODEL_STATUSES) + [None, "ANY_FUTURE_LABEL"]:
        got = evaluate_league(probe, legacy_model_status=status)
        if (got.decision, got.exclusion_reason) != (
            baseline.decision,
            baseline.exclusion_reason,
        ):
            raise AssertionError(
                f"legacy model_status {status!r} changed the scope decision from "
                f"{baseline.decision.value} to {got.decision.value}; legacy Pilot-C "
                "era metadata must be non-behavioral"
            )
