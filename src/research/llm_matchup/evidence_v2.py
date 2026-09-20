"""fixture_evidence_packet_v2 — Phase B packet with formation-resolution evidence.

Extends the Phase-A EvidencePacketBuilder WITHOUT mutating it. Adds:
  * formation-conditioned team behavior (fc_* evidence items) for each side, keyed on the
    team's PROJECTED / provided pre-match formation applied to HISTORICAL cohorts;
  * formation x opponent-formation hierarchical matchup evidence (fmx_* items);
  * a formation_context block declaring resolution_status + prematch_status (two-concept
    model) so the validator can enforce honesty.

LEAKAGE BOUNDARY (brief §3):
  * The target fixture's OWN resolved formation is never read.
  * Historical cohorts are conditioned on the resolved formation those source matches
    actually used (a legitimate historical conditioning key).
  * The formation attached to the TARGET is a FormationInput (ANNOUNCED / PROJECTED /
    UNKNOWN). In Phase B, when no pre-match formation exists we pass UNKNOWN and the
    formation-conditioned cohorts fall back to family/venue/team tiers.

ABLATION / SHUFFLE controls (brief §20, §21):
  * include_formation=False produces the SAME behavioral evidence with all fc_/fmx_ items
    and formation_context removed (the ablation packet).
  * formation_override lets the harness inject a (a_formation, b_formation) pair to run the
    label-shuffle control: behavioral evidence is unchanged, only the nominal label the
    cohorts key on changes.
"""
from __future__ import annotations
from dataclasses import asdict
from typing import Optional

from src.research.matchup.corpus import MatchRecord
from src.research.llm_matchup.evidence import (
    EvidencePacketBuilder, EvidenceItem, _mk_id, _league_env, packet_hash,
)
from src.research.llm_matchup import cohorts as CH
from src.research.llm_matchup import formation as FM
from src.research.llm_matchup import formation_evidence as FE
from src.research.llm_matchup.versions import PACKET_SCHEMA_VERSION, FORMATION_POLICY_VERSION


# metrics surfaced as formation-conditioned team behavior (corners-first + general)
_FC_METRICS = [
    ("crosses", "for"), ("corners", "for"), ("corners", "against"),
    ("touches_in_box", "for"), ("total_shots", "for"), ("possession", "for"),
    ("crosses", "against"), ("clearances", "for"), ("blocked_shots", "for"),
]
# metrics surfaced as formation x opponent-formation matchup evidence
_FMX_METRICS = [
    ("crosses", "for"), ("crosses", "against"), ("corners", "for"), ("corners", "against"),
    ("touches_in_box", "for"), ("clearances", "for"), ("blocked_shots", "for"),
    ("shots_inside_box", "against"),
]


class EvidencePacketBuilderV2:
    """Phase-B builder. Wraps the Phase-A builder and adds formation dimensions.

    `prematch_formations` maps side ("home"/"away") -> FormationInput for the TARGET. If
    None, both sides default to FormationInput.unknown() (no pre-match formation), which is
    the honest Phase-B state given the absence of announcement timestamps.
    """

    def __init__(self, recs: list[MatchRecord], enrich_halves: bool = True):
        self._base = EvidencePacketBuilder(recs, enrich_halves=enrich_halves)
        self.recs = self._base.recs
        self._fidx = FE.FormationHistoryIndex(self.recs)

    # -- resolution status for context (historical coverage of the two teams' history) --
    def _resolution_status(self, team, before_unix, season) -> str:
        recs = self._fidx.base.prior_records(team, before_unix, season)
        if not recs:
            return "RESOLVED_UNAVAILABLE"
        n_res = 0
        for r in recs:
            f, _ = self._fidx.team_formation(r, team)
            if f is not None:
                n_res += 1
        if n_res == 0:
            return "RESOLVED_UNAVAILABLE"
        frac = n_res / len(recs)
        return "RESOLVED_AVAILABLE" if frac >= 0.5 else "RESOLVED_PARTIAL"

    def _fc_items(self, team, venue, before_unix, season, finput: FM.FormationInput,
                  comp_env: dict, prefix: str) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        formation = finput.formation
        family = finput.formation_family
        for metric, side in _FC_METRICS:
            cev = comp_env.get(metric)
            fcm = FE.formation_conditioned_metric(
                self._fidx, team, venue, metric, side, before_unix, season,
                formation, family, cev)
            if fcm.formation_value is None:
                continue
            scope = {"team": team, "venue": venue, "side": side,
                     "prematch_formation": formation, "formation_family": family,
                     "prematch_source": finput.source_type}
            items.append(EvidenceItem(
                id=_mk_id(prefix, f"fc_{metric}_{side}", scope, fcm.sample_n),
                metric=f"fc_{metric}_{side}", value=fcm.formation_value,
                sample_n=fcm.sample_n, scope=scope, reliability=fcm.reliability,
                shrinkage_level=("SHRUNK" if fcm.preferred_tier != "EXACT_FORMATION" else "DIRECT"),
                evidence_level=fcm.preferred_tier, source_provider="derived_formation",
                source_field=f"formation-conditioned {metric} ({fcm.preferred_tier})",
                cutoff_unix=before_unix, temporal_status="PIT_SAFE",
            ))
            # formation delta as a separate, explicitly-labelled evidence item
            if fcm.formation_delta is not None:
                sc = dict(scope); sc["kind"] = "delta_vs_baseline"
                items.append(EvidenceItem(
                    id=_mk_id(prefix, f"formation_delta_{metric}_{side}", sc, fcm.sample_n),
                    metric=f"formation_delta_{metric}_{side}", value=fcm.formation_delta,
                    sample_n=fcm.sample_n, scope=sc, reliability=fcm.reliability,
                    shrinkage_level="DERIVED", evidence_level=fcm.preferred_tier,
                    source_provider="derived_formation",
                    source_field=f"{metric} formation minus team baseline",
                    cutoff_unix=before_unix, temporal_status="PIT_SAFE",
                ))
        return items

    def _fmx_items(self, team, venue, before_unix, season,
                   team_finput: FM.FormationInput, opp_finput: FM.FormationInput,
                   comp_env: dict, prefix: str) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for metric, side in _FMX_METRICS:
            fm = FE.formation_matchup(
                self._fidx, team, venue, metric, side, before_unix, season,
                team_finput.formation, team_finput.formation_family,
                opp_finput.formation, opp_finput.formation_family,
                comp_env.get(metric))
            if fm.resolved_value is None:
                continue
            scope = {"team": team, "venue": venue, "side": side,
                     "team_formation": team_finput.formation,
                     "team_family": team_finput.formation_family,
                     "opp_formation": opp_finput.formation,
                     "opp_family": opp_finput.formation_family,
                     "preferred_tier": fm.preferred_tier}
            # compact tier summary keeps the packet small (full tier objects would balloon
            # input tokens); each entry is {tier, n, value}.
            tier_summary = [{"tier": t["tier"], "n": t["n"], "value": t["value"]}
                            for t in fm.tiers if t["n"] > 0 or t["value"] is not None]
            items.append(EvidenceItem(
                id=_mk_id(prefix, f"fmx_{metric}_{side}", scope, 0),
                metric=f"fmx_{metric}_{side}", value=fm.resolved_value,
                sample_n=next((t["n"] for t in fm.tiers if t["tier"] == fm.preferred_tier), 0),
                scope={**scope, "tier_summary": tier_summary}, reliability=fm.reliability,
                shrinkage_level="HIERARCHICAL", evidence_level=fm.preferred_tier,
                source_provider="derived_formation",
                source_field=f"formation x opp-formation {metric} (tier {fm.preferred_tier})",
                cutoff_unix=before_unix, temporal_status="PIT_SAFE",
            ))
        return items

    def build(self, target: MatchRecord,
              prematch_formations: Optional[dict[str, FM.FormationInput]] = None,
              include_formation: bool = True,
              formation_override: Optional[dict[str, str]] = None) -> dict:
        # start from the Phase-A packet (behavioral evidence, unchanged)
        packet = self._base.build(target)
        packet["packet_schema_version"] = PACKET_SCHEMA_VERSION

        A, B = target.home, target.away
        before = target.kickoff_unix
        # TARGET fixture's own season-instance (A3): one key filters BOTH sides, so
        # neither team can drift into a different season, and a team with no prior
        # matches in it abstains instead of falling back to the previous season.
        seasonA = seasonB = CH.HistoryIndex.target_season(target)

        # pre-match formation inputs for the TARGET (never the target's resolved formation)
        pf = prematch_formations or {}
        a_fin = pf.get("home") or FM.FormationInput.unknown()
        b_fin = pf.get("away") or FM.FormationInput.unknown()
        if formation_override:  # label-shuffle control: swap nominal labels only
            if "home" in formation_override:
                a_fin = FM.FormationInput.projected(formation_override["home"], "shuffle_control")
            if "away" in formation_override:
                b_fin = FM.FormationInput.projected(formation_override["away"], "shuffle_control")
        FM.assert_not_target_resolved(a_fin)
        FM.assert_not_target_resolved(b_fin)

        # competition environment means (context) for the fc/fmx metrics
        comp_env = {}
        for metric in set(m for m, _ in _FC_METRICS + _FMX_METRICS):
            comp_env[metric] = _league_env(self.recs, target, metric)

        formation_context = {
            "policy_version": FORMATION_POLICY_VERSION,
            "resolution_status": self._resolution_status(A, before, seasonA)
                if self._resolution_status(A, before, seasonA) == self._resolution_status(B, before, seasonB)
                else "RESOLVED_PARTIAL",
            "prematch_status": ("PREMATCH_UNKNOWN" if a_fin.source_type == "UNKNOWN"
                                else a_fin.source_type),
            "team_a_prematch_formation": a_fin.to_dict(),
            "team_b_prematch_formation": b_fin.to_dict(),
            "formation_family_version": FM.FORMATION_FAMILY_VERSION,
            "leakage_note": "target resolved formation NOT used; historical cohorts keyed on "
                            "resolved source-match formation; target uses pre-match FormationInput only",
        }
        # Reconcile the legacy Phase-A flag with the two-concept model: the legacy
        # formation_status describes PRE-MATCH availability, so it is KNOWN_PIT_SAFE only
        # when an ANNOUNCED pre-match formation exists, otherwise FORMATION_UNKNOWN.
        packet["unsupported_context"]["formation_status"] = (
            "KNOWN_PIT_SAFE" if a_fin.source_type == "ANNOUNCED" else "FORMATION_UNKNOWN")

        if include_formation:
            fc_items = (self._fc_items(A, "home", before, seasonA, a_fin, comp_env, "A_FC")
                        + self._fmx_items(A, "home", before, seasonA, a_fin, b_fin, comp_env, "A_FMX"))
            fc_items_b = (self._fc_items(B, "away", before, seasonB, b_fin, comp_env, "B_FC")
                          + self._fmx_items(B, "away", before, seasonB, b_fin, a_fin, comp_env, "B_FMX"))
            new_items = fc_items + fc_items_b
            packet["evidence"] = packet["evidence"] + [asdict(i) for i in new_items]
            packet["team_a"]["formation_evidence_ids"] = [i.id for i in fc_items]
            packet["team_b"]["formation_evidence_ids"] = [i.id for i in fc_items_b]
            packet["formation_context"] = formation_context
            packet["ablation"] = {"include_formation": True}
        else:
            # ablation: behavioral evidence only, no formation dimensions
            packet["formation_context"] = {
                "policy_version": FORMATION_POLICY_VERSION,
                "resolution_status": "RESOLVED_UNAVAILABLE",
                "prematch_status": "PREMATCH_UNKNOWN",
                "leakage_note": "ablation packet: formation dimensions removed",
            }
            packet["ablation"] = {"include_formation": False}

        # refresh data-quality counts and hash (packet changed)
        allev = packet["evidence"]
        packet["data_quality"] = {
            "n_evidence": len(allev),
            "n_pit_safe": sum(1 for i in allev if i["temporal_status"] == "PIT_SAFE"),
            "n_unavailable": sum(1 for i in allev if i["temporal_status"] == "UNAVAILABLE"),
            "n_formation_evidence": sum(1 for i in allev
                                        if i["metric"].startswith(("fc_", "fmx_", "formation_delta_"))),
        }
        packet.pop("packet_hash", None)
        packet["packet_hash"] = packet_hash(packet)
        return packet
