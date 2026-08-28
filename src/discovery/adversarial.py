"""Adversarial review framework for metric discovery.

Every metric surviving FDR goes through adversarial interrogation BEFORE
held-out validation. The review's role is explicitly critical — it is
trying to kill the metric, not celebrate it.

Authority: PROPOSE and CRITIQUE only. Cannot promote, alter thresholds,
modify results, or bypass any gate.

For each surviving metric, the review must answer:
1. MECHANISM — what football phenomenon makes this predictive?
2. NUMEROLOGY — is this explicable or arbitrary arithmetic?
3. REDUNDANCY — is this materially different from existing metrics?
4. LEAKAGE — could any input encode post-match information?
5. FAILURE CONDITIONS — when would this stop working?
6. CONFOUNDING — is this proxying for a simpler variable?
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from src.discovery.generator import CandidateMetric
from src.discovery.screener import ScreeningResult

logger = logging.getLogger(__name__)


@dataclass
class AdversarialReview:
    """Complete adversarial review of a candidate metric."""
    metric_id: str
    metric_name: str
    formula: str

    # The six questions
    mechanism: str          # What football phenomenon makes this predictive?
    mechanism_plausible: bool
    numerology_flag: bool   # True = suspicious arbitrary combination
    numerology_note: str
    redundancy_flag: bool   # True = near-duplicate of existing metric
    redundancy_note: str
    leakage_flag: bool      # True = potential post-match data contamination
    leakage_note: str
    failure_conditions: str # Under what circumstances would this stop working?
    confounding_flag: bool  # True = likely proxying for simpler variable
    confounding_note: str

    # Overall verdict
    recommendation: str     # "PROCEED" / "FLAG_FOR_HUMAN" / "REJECT"
    concerns: list[str]     # Unresolved concerns
    confidence: str         # "HIGH" / "MEDIUM" / "LOW"

    def to_dict(self) -> dict:
        return {
            "metric_id": self.metric_id,
            "metric_name": self.metric_name,
            "formula": self.formula,
            "mechanism": self.mechanism,
            "mechanism_plausible": self.mechanism_plausible,
            "numerology_flag": self.numerology_flag,
            "numerology_note": self.numerology_note,
            "redundancy_flag": self.redundancy_flag,
            "redundancy_note": self.redundancy_note,
            "leakage_flag": self.leakage_flag,
            "leakage_note": self.leakage_note,
            "failure_conditions": self.failure_conditions,
            "confounding_flag": self.confounding_flag,
            "confounding_note": self.confounding_note,
            "recommendation": self.recommendation,
            "concerns": self.concerns,
            "confidence": self.confidence,
        }


# ═══════════════════════════════════════════════════════════════
# KNOWN MECHANISMS (from football domain knowledge)
# ═══════════════════════════════════════════════════════════════

KNOWN_MECHANISMS: dict[str, str] = {
    "corners_per_shot": (
        "Teams that take more shots relative to their accuracy tend to hit "
        "blocked shots and wide shots that deflect out for corners. The ratio "
        "of corners per shot captures offensive intent that doesn't convert."
    ),
    "dangerous_attacks_to_corners": (
        "Dangerous attacks near the box frequently end in blocks, deflections, "
        "or saves that produce corners. This ratio measures conversion of "
        "attacking pressure into set-piece opportunities."
    ),
    "fouls_to_cards": (
        "Teams that commit more fouls relative to their card count have a "
        "referee who is tolerant. The inverse (cards per foul) indicates "
        "referee strictness — a match-level confound for card prediction."
    ),
    "possession_to_shots": (
        "Teams that dominate possession but take few shots are 'sterile dominators' — "
        "their possession doesn't translate to attacking threat. Inversely, low "
        "possession with high shots indicates counter-attacking efficiency."
    ),
    "xg_vs_shots_on_target": (
        "The ratio of xG to shots on target measures shot quality independent "
        "of quantity — are they taking high-value chances? Divergence from 1.0 "
        "indicates the quality-vs-quantity tradeoff."
    ),
}

# Fields confirmed POST-MATCH only (cannot be used directly pre-kickoff)
POST_MATCH_ONLY_FIELDS = {
    "team_a_corners", "team_b_corners",
    "team_a_yellow_cards", "team_b_yellow_cards", "team_a_red_cards", "team_b_red_cards",
    "team_a_shots", "team_b_shots",
    "team_a_shotsOnTarget", "team_b_shotsOnTarget",
    "team_a_possession", "team_b_possession",
    "homeGoalCount", "awayGoalCount", "overallGoalCount",
    "team_a_xg", "team_b_xg",
    "team_a_fouls", "team_b_fouls",
    "team_a_offsides", "team_b_offsides",
    "team_a_dangerous_attacks", "team_b_dangerous_attacks",
    "team_a_attacks", "team_b_attacks",
    "team_a_freekicks", "team_b_freekicks",
    "team_a_throwins", "team_b_throwins",
    "team_a_goalkicks", "team_b_goalkicks",
    "team_a_fh_corners", "team_b_fh_corners",
    "team_a_2h_corners", "team_b_2h_corners",
    "team_a_fh_cards", "team_b_fh_cards",
    "team_a_2h_cards", "team_b_2h_cards",
    "team_a_shotsOffTarget", "team_b_shotsOffTarget",
    "team_a_penalties_won", "team_b_penalties_won",
}


class AdversarialReviewer:
    """Performs adversarial review on FDR-surviving metrics.

    Uses rule-based domain knowledge for v1. Can be extended to use
    Bedrock LLM for deeper interrogation (see review template below).

    Authority: PROPOSE and CRITIQUE only.
    """

    def __init__(self, existing_metrics: list[str] | None = None) -> None:
        """Initialize with list of existing validated metric names for redundancy check."""
        self._existing = set(existing_metrics or [])

    def review(
        self,
        metric: CandidateMetric,
        screening: ScreeningResult,
    ) -> AdversarialReview:
        """Perform adversarial review on a metric.

        Returns the review record. Does NOT make promotion decisions —
        that's for the pipeline orchestrator.
        """
        concerns = []

        # 1. MECHANISM
        mechanism, mechanism_plausible = self._assess_mechanism(metric)
        if not mechanism_plausible:
            concerns.append("No plausible football mechanism identified")

        # 2. NUMEROLOGY
        numerology_flag, numerology_note = self._check_numerology(metric)
        if numerology_flag:
            concerns.append(f"Numerology concern: {numerology_note}")

        # 3. REDUNDANCY
        redundancy_flag, redundancy_note = self._check_redundancy(metric)
        if redundancy_flag:
            concerns.append(f"Redundancy: {redundancy_note}")

        # 4. LEAKAGE
        leakage_flag, leakage_note = self._check_leakage(metric)
        if leakage_flag:
            concerns.append(f"LEAKAGE RISK: {leakage_note}")

        # 5. FAILURE CONDITIONS
        failure_conditions = self._assess_failure_conditions(metric)

        # 6. CONFOUNDING
        confounding_flag, confounding_note = self._check_confounding(metric)
        if confounding_flag:
            concerns.append(f"Confounding: {confounding_note}")

        # Overall recommendation
        if leakage_flag:
            recommendation = "REJECT"
            confidence = "HIGH"
        elif not mechanism_plausible and numerology_flag:
            recommendation = "FLAG_FOR_HUMAN"
            confidence = "LOW"
        elif len(concerns) > 2:
            recommendation = "FLAG_FOR_HUMAN"
            confidence = "MEDIUM"
        else:
            recommendation = "PROCEED"
            confidence = "HIGH" if mechanism_plausible else "MEDIUM"

        return AdversarialReview(
            metric_id=metric.metric_id,
            metric_name=metric.name,
            formula=f"{metric.formula_type}({', '.join(metric.fields)}, window={metric.params.get('window', '?')})",
            mechanism=mechanism,
            mechanism_plausible=mechanism_plausible,
            numerology_flag=numerology_flag,
            numerology_note=numerology_note,
            redundancy_flag=redundancy_flag,
            redundancy_note=redundancy_note,
            leakage_flag=leakage_flag,
            leakage_note=leakage_note,
            failure_conditions=failure_conditions,
            confounding_flag=confounding_flag,
            confounding_note=confounding_note,
            recommendation=recommendation,
            concerns=concerns,
            confidence=confidence,
        )

    def _assess_mechanism(self, metric: CandidateMetric) -> tuple[str, bool]:
        """Identify a football mechanism for this metric."""
        fields = metric.fields
        formula = metric.formula_type

        # Check known mechanisms
        for key, explanation in KNOWN_MECHANISMS.items():
            field_str = "_".join(fields)
            if any(k in field_str for k in key.split("_")):
                return explanation, True

        # Heuristic mechanism generation
        if "corners" in str(fields) and ("shot" in str(fields) or "attack" in str(fields)):
            return (
                "Corners are generated from attacking actions (blocked shots, deflections near "
                "the box). Linking corner-production to attacking metrics captures this conversion."
            ), True

        if "fouls" in str(fields) and "card" in str(fields):
            return (
                "The foul-to-card ratio captures referee card threshold. Referees who show "
                "cards early create a different match dynamic than lenient ones."
            ), True

        if "possession" in str(fields) and "shot" in str(fields):
            return (
                "Possession without shots indicates sterile dominance; shots without "
                "possession indicates counter-attacking style. Both patterns predict "
                "different set-piece dynamics."
            ), True

        if "xg" in str(fields):
            return (
                "xG captures shot quality independent of shot quantity, measuring whether "
                "a team creates high-value chances that stress defenses."
            ), True

        if "dangerous_attacks" in str(fields):
            return (
                "Dangerous attacks represent entries into the final third that create genuine "
                "scoring or corner opportunities."
            ), True

        return "No clear mechanism identified — may be arbitrary arithmetic.", False

    def _check_numerology(self, metric: CandidateMetric) -> tuple[bool, str]:
        """Check if metric is arbitrary arithmetic rather than meaningful."""
        if metric.formula_type == "rolling_product":
            # Products of unrelated fields are suspicious
            fields = metric.fields
            if not self._fields_conceptually_related(fields):
                return True, "Product of conceptually unrelated fields"
        return False, ""

    def _check_redundancy(self, metric: CandidateMetric) -> tuple[bool, str]:
        """Check if metric is near-duplicate of existing validated metric."""
        name = metric.name
        for existing in self._existing:
            if name == existing:
                return True, f"Identical to existing metric: {existing}"
            # Simple similarity check
            name_parts = set(name.lower().split("_"))
            existing_parts = set(existing.lower().split("_"))
            overlap = len(name_parts & existing_parts) / max(len(name_parts | existing_parts), 1)
            if overlap > 0.8:
                return True, f"Very similar to existing: {existing} (overlap={overlap:.0%})"
        return False, ""

    def _check_leakage(self, metric: CandidateMetric) -> tuple[bool, str]:
        """Check for potential data leakage."""
        # Rolling metrics are safe — they use only PRIOR match data
        if metric.formula_type.startswith("rolling"):
            # But verify the source fields are legitimate historical stats
            for f in metric.fields:
                if f in POST_MATCH_ONLY_FIELDS:
                    # This is OK — rolling aggregation of post-match data IS safe
                    # because it only uses data from completed prior matches
                    pass
            return False, ""

        # Direct raw access to current-match fields would be leakage
        for f in metric.fields:
            if f in POST_MATCH_ONLY_FIELDS and "rolling" not in metric.formula_type:
                return True, f"Field '{f}' is post-match only and not accessed via rolling aggregate"

        return False, ""

    def _assess_failure_conditions(self, metric: CandidateMetric) -> str:
        """Identify conditions under which this metric might stop working."""
        conditions = []

        if "corners" in str(metric.fields):
            conditions.append("Rule changes to corner-kick procedures")
            conditions.append("Tactical trend away from crossing (e.g., all teams play through the middle)")

        if "card" in str(metric.fields) or "foul" in str(metric.fields):
            conditions.append("Referee assignment policy changes")
            conditions.append("VAR threshold changes affecting card decisions")

        if "possession" in str(metric.fields):
            conditions.append("Major tactical shift in league (e.g., all teams adopt pressing)")

        if "xg" in str(metric.fields):
            conditions.append("xG model methodology changes by the data provider")

        if not conditions:
            conditions.append("General: league composition changes, team-quality shifts between seasons")

        return "; ".join(conditions)

    def _check_confounding(self, metric: CandidateMetric) -> tuple[bool, str]:
        """Check if metric is proxying for a simpler variable."""
        # A ratio of team_a_X / team_b_X might just proxy for team quality
        fields = metric.fields
        if len(fields) == 2:
            if fields[0].startswith("team_a_") and fields[1].startswith("team_b_"):
                # home_X / away_X often just captures relative team strength
                return True, "Ratio of home/away stats may primarily proxy for relative team quality rather than a specific tactical phenomenon"

        # possession-normalized variants might just measure possession itself
        if "possession" in str(fields) and metric.formula_type == "rolling_per_norm":
            return True, "Per-possession normalization may be capturing possession dominance rather than independent signal"

        return False, ""

    def _fields_conceptually_related(self, fields: tuple[str, ...]) -> bool:
        """Check if fields are conceptually related (same domain)."""
        domains = {
            "corner": {"team_a_corners", "team_b_corners", "team_a_fh_corners", "team_b_fh_corners"},
            "shot": {"team_a_shots", "team_b_shots", "team_a_shotsOnTarget", "team_b_shotsOnTarget"},
            "attack": {"team_a_attacks", "team_b_attacks", "team_a_dangerous_attacks", "team_b_dangerous_attacks"},
            "discipline": {"team_a_fouls", "team_b_fouls", "team_a_yellow_cards", "team_b_yellow_cards"},
            "possession": {"team_a_possession", "team_b_possession"},
            "xg": {"team_a_xg", "team_b_xg"},
        }

        field_domains = set()
        for f in fields:
            for domain_name, domain_fields in domains.items():
                if f in domain_fields:
                    field_domains.add(domain_name)

        # Related if they share a domain or bridge two adjacent domains
        return len(field_domains) <= 2


# ═══════════════════════════════════════════════════════════════
# BEDROCK REVIEW TEMPLATE (for LLM-assisted deep review)
# ═══════════════════════════════════════════════════════════════

BEDROCK_REVIEW_PROMPT_TEMPLATE = """You are reviewing a candidate predictive metric for a football quantitative model. Your role is ADVERSARIAL — you are trying to DISPROVE this metric's validity, not support it.

## Metric Under Review
- Name: {metric_name}
- Formula: {formula}
- Fields used: {fields}
- Discovery-set performance: {performance_summary}

## Your Task (answer each honestly)

1. MECHANISM: What specific football phenomenon would make this metric predictive? State it concretely. "The data shows a correlation" is NOT a mechanism.

2. NUMEROLOGY CHECK: Is this formula explicable from football domain knowledge, or is it arbitrary arithmetic that happens to fit the data? A ratio of "throwins × goalkicks" would be suspicious. A ratio of "dangerous attacks / corners" has a clear interpretation.

3. REDUNDANCY: Is this materially different from simpler metrics? Could you get the same information from just looking at one of the input fields alone?

4. LEAKAGE AUDIT: The metric uses rolling averages from PRIOR completed matches only. But could any of the input fields ({fields}) contain information that is actually forward-looking or post-match for the PREDICTED match?

5. FAILURE CONDITIONS: Under what specific circumstances would this metric stop working? (Rule changes, tactical trends, league-specific factors, data-source changes)

6. CONFOUNDING: Is this metric measuring something real and specific, or is it primarily a proxy for team quality (good teams do everything better)?

## Format your answer as:
MECHANISM: [your answer]
MECHANISM_PLAUSIBLE: [YES/NO]
NUMEROLOGY: [CLEAN/SUSPICIOUS] — [reason]
REDUNDANCY: [UNIQUE/REDUNDANT] — [reason]
LEAKAGE: [CLEAN/RISK] — [reason]
FAILURE_CONDITIONS: [list]
CONFOUNDING: [INDEPENDENT/PROXY] — [reason]
RECOMMENDATION: [PROCEED/FLAG_FOR_HUMAN/REJECT]
CONCERNS: [numbered list of unresolved issues]
"""
