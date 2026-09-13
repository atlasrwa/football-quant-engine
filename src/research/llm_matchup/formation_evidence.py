"""formation_evidence (formation_policy_v1) — formation-conditioned behavioral evidence.

Deterministic, PIT-safe computation of:
  * formation-conditioned behavior for a team (TEAM + VENUE + RESOLVED_FORMATION -> behavior)
  * formation delta vs the team's own baseline
  * hierarchical formation x opponent-formation matchup evidence with empirical-Bayes
    shrinkage across the mandated tier ladder.

CRITICAL BOUNDARIES (brief §3, §29, §34):
  * Only prior matches (kickoff < target cutoff), same competition-season for team state.
  * The RESOLVED formation of a HISTORICAL source match is used as a conditioning key.
  * The TARGET fixture's own resolved formation is NEVER read here. Callers pass a
    FormationInput (prematch) for the target; this module conditions history only.
  * A family is a conditioning key, never a behavioral assumption. All behavior numbers
    come from measured history; Sonnet interprets, this module computes.

Tier ladder for a formation matchup A_form vs B_form (most specific -> most general):
  1. EXACT x EXACT          A exact formation vs B exact formation
  2. FAMILY x EXACT         A family        vs B exact formation
  3. EXACT x FAMILY         A exact formation vs B family
  4. FAMILY x FAMILY        A family        vs B family
  5. VENUE_OVERALL          A at venue, any opponent
  6. TEAM_BASELINE          A overall
  7. COMPETITION_PRIOR      league environment
Each tier carries n, effective_n, shrinkage_weight, reliability. Estimates shrink from
specific toward the next-more-general tier so a tiny exact cohort cannot masquerade as
strong evidence.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

from src.research.llm_matchup import cohorts as CH
from src.research.llm_matchup import formation as FM
from src.research.matchup.corpus import MatchRecord, season_of

# Behavioral metrics we condition on formation (corners-relevant + general football state).
FORMATION_METRICS: list[tuple[str, str]] = [
    ("crosses", "for"), ("crosses", "against"),
    ("total_shots", "for"), ("total_shots", "against"),
    ("shots_on_target", "for"), ("shots_on_target", "against"),
    ("shots_inside_box", "for"), ("shots_inside_box", "against"),
    ("touches_in_box", "for"), ("touches_in_box", "against"),
    ("corners", "for"), ("corners", "against"),
    ("blocked_shots", "for"),
    ("clearances", "for"),
    ("possession", "for"),
    ("tackles", "for"),
    ("fouls", "for"),
    ("yellow_cards", "for"),
]

MIN_FORMATION_N = 3          # below this an exact-formation cohort is treated as very weak
SHRINK_K = CH.SHRINK_K        # reuse the same empirical-Bayes strength as Phase A


def _reliability(n: int, effective_n: float) -> str:
    if effective_n >= 12 and n >= 10:
        return "HIGH"
    if effective_n >= 5 and n >= MIN_FORMATION_N:
        return "MEDIUM"
    return "LOW"


@dataclass
class TierEstimate:
    tier: str
    value: Optional[float]
    n: int
    effective_n: float
    shrinkage_weight: float          # weight placed on this tier's own (child) mean
    reliability: str
    parent_tier: Optional[str]


@dataclass
class FormationConditionedMetric:
    metric: str                      # e.g. "crosses_for"
    formation: Optional[str]
    family: str
    venue: str
    formation_value: Optional[float]     # conditioned (shrunk) estimate
    team_baseline: Optional[float]       # team overall at venue
    formation_delta: Optional[float]     # formation_value - team_baseline
    competition_value: Optional[float]   # league env total (context)
    sample_n: int
    effective_n: float
    reliability: str
    preferred_tier: str


# ---------------------------------------------------------------------------
# formation-conditioned team behavior
# ---------------------------------------------------------------------------
class FormationHistoryIndex:
    """Wraps the Phase-A HistoryIndex and attaches resolved formation per record.

    Formation is loaded lazily per fixture from the lineup cache. Records without a
    resolved formation contribute to venue/team baselines but not to a specific
    exact/family cohort (fail-closed: no fabrication of a formation).
    """

    def __init__(self, recs: list[MatchRecord]):
        self.base = CH.HistoryIndex(recs)
        self.recs = self.base.recs
        self._form_cache: dict[str, Optional[dict]] = {}

    def team_formation(self, rec: MatchRecord, team: str) -> tuple[Optional[str], str]:
        """Resolved (formation, family) that `team` actually used in `rec`. PIT: rec is a
        historical source match only; callers must never pass the target fixture."""
        fid = rec.fixture_id
        if fid not in self._form_cache:
            self._form_cache[fid] = FM.load_resolved_formation(fid)
        rf = self._form_cache[fid]
        if rf is None:
            return None, FM.UNKNOWN_FORMATION
        is_home = (rec.home == team or rec.home_id == team)
        side = "home" if is_home else "away"
        r = rf.get(side)
        if r is None:
            return None, FM.UNKNOWN_FORMATION
        return r.formation, r.family

    def prior_form_records(self, team, before_unix, season, venue=None):
        """Prior records for team, each annotated with (formation, family) it played."""
        out = []
        for r in self.base.prior_records(team, before_unix, season, venue):
            form, fam = self.team_formation(r, team)
            out.append((r, form, fam))
        return out

    def conditioned_values(self, team, metric, side, before_unix, season, venue,
                           formation=None, family=None, opp_formation=None, opp_family=None):
        """Values of `metric` for `team` across prior matches filtered by the given
        formation / family / opponent-formation / opponent-family conditions.

        Any condition left None is not filtered on. Opponent-formation filtering reads the
        opponent's resolved formation in that historical match (a legitimate historical
        conditioning key)."""
        vals = []
        for r in self.base.prior_records(team, before_unix, season, venue):
            f_team, fam_team = self.team_formation(r, team)
            if formation is not None and f_team != formation:
                continue
            if family is not None and fam_team != family:
                continue
            if opp_formation is not None or opp_family is not None:
                opp = r.away if (r.home == team or r.home_id == team) else r.home
                of, ofam = self.team_formation(r, opp)
                if opp_formation is not None and of != opp_formation:
                    continue
                if opp_family is not None and ofam != opp_family:
                    continue
            v = CH.team_metric(r, team, metric, side, "all")
            if v is not None:
                vals.append(v)
        return vals


def _mean(vals):
    return (sum(vals) / len(vals)) if vals else None


def formation_conditioned_metric(idx: FormationHistoryIndex, team: str, venue: str,
                                  metric: str, side: str, before_unix: int, season: str,
                                  formation: Optional[str], family: str,
                                  competition_value: Optional[float]) -> FormationConditionedMetric:
    """Compute a single formation-conditioned metric with shrinkage toward team baseline."""
    baseline_vals = idx.conditioned_values(team, metric, side, before_unix, season, venue)
    team_baseline = _mean(baseline_vals) if len(baseline_vals) >= CH.MIN_HISTORY else None

    # exact-formation cohort at venue, shrunk toward team baseline (parent)
    form_vals = idx.conditioned_values(team, metric, side, before_unix, season, venue,
                                       formation=formation) if formation else []
    n = len(form_vals)
    if n == 0:
        est = team_baseline
        eff_n = float(len(baseline_vals)) if team_baseline is not None else 0.0
        w = 0.0
        pref = "TEAM_BASELINE" if team_baseline is not None else "NONE"
    else:
        est = CH.shrink(form_vals, team_baseline)
        w = n / (n + SHRINK_K)
        eff_n = n + (0.0 if team_baseline is None else SHRINK_K)
        pref = "EXACT_FORMATION"
    delta = (est - team_baseline) if (est is not None and team_baseline is not None) else None
    return FormationConditionedMetric(
        metric=f"{metric}_{side}", formation=formation, family=family, venue=venue,
        formation_value=(round(est, 4) if est is not None else None),
        team_baseline=(round(team_baseline, 4) if team_baseline is not None else None),
        formation_delta=(round(delta, 4) if delta is not None else None),
        competition_value=(round(competition_value, 4) if competition_value is not None else None),
        sample_n=n, effective_n=round(eff_n, 2), reliability=_reliability(n, eff_n),
        preferred_tier=pref,
    )


# ---------------------------------------------------------------------------
# hierarchical formation x opponent-formation matchup
# ---------------------------------------------------------------------------
@dataclass
class FormationMatchup:
    metric: str
    team: str
    venue: str
    team_formation: Optional[str]
    team_family: str
    opp_formation: Optional[str]
    opp_family: str
    tiers: list                       # list[TierEstimate as dict]
    resolved_value: Optional[float]   # value after descending the ladder
    preferred_tier: str
    reliability: str


def _tier(idx, team, metric, side, before_unix, season, venue,
          formation, family, opp_formation, opp_family, tier_name, parent_tier):
    vals = idx.conditioned_values(team, metric, side, before_unix, season, venue,
                                  formation=formation, family=family,
                                  opp_formation=opp_formation, opp_family=opp_family)
    n = len(vals)
    return vals, TierEstimate(
        tier=tier_name, value=(round(_mean(vals), 4) if vals else None), n=n,
        effective_n=float(n), shrinkage_weight=(n / (n + SHRINK_K) if n else 0.0),
        reliability=_reliability(n, float(n)), parent_tier=parent_tier,
    )


def formation_matchup(idx: FormationHistoryIndex, team: str, venue: str,
                      metric: str, side: str, before_unix: int, season: str,
                      team_formation: Optional[str], team_family: str,
                      opp_formation: Optional[str], opp_family: str,
                      competition_value: Optional[float] = None) -> FormationMatchup:
    """Build the full hierarchical tier ladder for one team-metric under a formation x
    opponent-formation condition, then resolve to a single shrunk value.

    The resolution walks specific -> general, shrinking each usable child toward the next
    tier's mean. A tier is 'usable' only if it has >= MIN_FORMATION_N samples; otherwise it
    is recorded (for transparency) but skipped for the point estimate. This guarantees a
    tiny exact-vs-exact cohort cannot dominate.
    """
    tiers_vals = []
    tier_objs: list[TierEstimate] = []

    def add(name, formation, family, opp_formation_, opp_family_, parent):
        vals, te = _tier(idx, team, metric, side, before_unix, season, venue,
                         formation, family, opp_formation_, opp_family_, name, parent)
        tiers_vals.append((name, vals))
        tier_objs.append(te)
        return vals

    # 1 exact x exact
    add("EXACT_x_EXACT", team_formation, None, opp_formation, None, "FAMILY_x_EXACT")
    # 2 family x exact
    add("FAMILY_x_EXACT", None, team_family, opp_formation, None, "EXACT_x_FAMILY")
    # 3 exact x family
    add("EXACT_x_FAMILY", team_formation, None, None, opp_family, "FAMILY_x_FAMILY")
    # 4 family x family
    add("FAMILY_x_FAMILY", None, team_family, None, opp_family, "VENUE_OVERALL")
    # 5 venue overall (team at venue, any opponent)
    add("VENUE_OVERALL", None, None, None, None, "TEAM_BASELINE")
    # 6 team baseline (all venues)
    base_vals = idx.conditioned_values(team, metric, side, before_unix, season, None)
    tiers_vals.append(("TEAM_BASELINE", base_vals))
    tier_objs.append(TierEstimate(
        tier="TEAM_BASELINE", value=(round(_mean(base_vals), 4) if base_vals else None),
        n=len(base_vals), effective_n=float(len(base_vals)),
        shrinkage_weight=(len(base_vals) / (len(base_vals) + SHRINK_K) if base_vals else 0.0),
        reliability=_reliability(len(base_vals), float(len(base_vals))),
        parent_tier="COMPETITION_PRIOR"))
    # 7 competition prior (context only)
    tier_objs.append(TierEstimate(
        tier="COMPETITION_PRIOR", value=(round(competition_value, 4) if competition_value is not None else None),
        n=0, effective_n=0.0, shrinkage_weight=0.0,
        reliability=("MEDIUM" if competition_value is not None else "LOW"),
        parent_tier=None))

    # resolve: build a parent chain of usable tier means, then shrink from most-specific
    usable = [(name, vals) for name, vals in tiers_vals if len(vals) >= MIN_FORMATION_N]
    # parent mean = most general usable tier (or competition prior)
    parent_mean = None
    parent_name = "COMPETITION_PRIOR"
    if competition_value is not None:
        parent_mean = competition_value
    for name, vals in reversed(usable):
        m = _mean(vals)
        if m is None:
            continue
        if parent_mean is None:
            parent_mean = m
            parent_name = name
        else:
            # shrink this tier toward the running parent
            parent_mean = CH.shrink(vals, parent_mean)
            parent_name = name
    resolved = parent_mean
    # preferred tier = most specific usable tier
    preferred = usable[0][0] if usable else ("TEAM_BASELINE" if len(base_vals) >= CH.MIN_HISTORY
                                             else "COMPETITION_PRIOR")
    pref_n = next((len(v) for nm, v in tiers_vals if nm == preferred), 0)
    return FormationMatchup(
        metric=f"{metric}_{side}", team=team, venue=venue,
        team_formation=team_formation, team_family=team_family,
        opp_formation=opp_formation, opp_family=opp_family,
        tiers=[asdict(t) for t in tier_objs],
        resolved_value=(round(resolved, 4) if resolved is not None else None),
        preferred_tier=preferred, reliability=_reliability(pref_n, float(pref_n)),
    )
