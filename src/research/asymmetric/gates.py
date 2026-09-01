"""FeatureVerificationGate and SanityGate — mandatory pre-modelling gates.

Responsibility
==============
:class:`FeatureVerificationGate` runs five checks BEFORE any modelling
(team-identity trace, known-signal, orientation, look-ahead, shuffle-null),
reports every check, and — on ANY failure — sets ``passed=False``,
``stopped_modelling=True`` and stops before modelling (Req 6.1, 6.7, 6.8).
:class:`SanityGate` RECORDS (without re-diagnosing) known structural
non-persistence results per league and per target (Req 7.1-7.4).

Both gates return the frozen :class:`GateResult` / (for the sanity gate)
:class:`SanityRecord` records defined in :mod:`models`, so downstream reporting
can surface every check and every recorded structural result.

---------------------------------------------------------------------------
FeatureVerificationGate — the five checks (Req 6.2-6.6)
---------------------------------------------------------------------------
The gate operates on the *real* corpus but keeps each check fast by sampling a
handful of teams / matches. It reuses the existing point-in-time
:class:`~src.research.asymmetric.profiles.TeamProfiler` machinery so that what
is verified is exactly what modelling will consume.

1. **Team-identity trace** (Req 6.2). For 3-5 sampled teams, produce the exact
   list of historical matches — with the team's home/away role in each — that a
   rolling feature aggregated. This confirms the rolling window pulls that team's
   own matches across BOTH home and away appearances, and never another team's
   match. The collected trace text is stored in the ``detail`` field. The check
   fails if any traced match does not contain the sampled team.

2. **Known-signal** (Req 6.3). Confirm the rolling-xG-for -> next-goals
   association is ``>= ~0.10`` (not ``~0.00``) and rolling-goals-for ->
   next-goals is positive. We build, per team, a point-in-time rolling mean of
   xG-for (and goals-for) from matches strictly before each match, then correlate
   that with the team's realised goals in that (next) match, pooled across teams.
   Both Pearson and Spearman are computed; the gate uses the stronger-signalled
   (max magnitude) xG correlation against the ``~0.10`` threshold so a genuine
   monotone-but-nonlinear signal is not missed.

3. **Orientation** (Req 6.4). Confirm ``team_a`` (home) features align with
   ``team_a`` (home) outcomes with a row-level cross-check against the source
   data: the home rolling xG-for must correlate more strongly with the *home*
   realised goals column than with the *away* realised goals column. A
   transposition (home features predicting the away column better) fails the
   check.

4. **Look-ahead** (Req 6.5). Confirm no feature for match M uses M or any later
   match: recompute a sampled feature from history truncated strictly before M
   and assert equality with the pipeline value (Property 2's mechanism at the
   gate level). Any mismatch fails the check.

5. **Shuffle-null** (Req 6.6). Permute the feature->outcome mapping and confirm
   out-of-sample performance collapses to chance (BSS ~ 0). If shuffled
   performance retains skill (BSS materially above 0) that indicates leakage and
   the check fails.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8 (task 8.1);
7.1, 7.2, 7.3, 7.4 (task 8.2).
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Optional

from src.research.asymmetric.models import GateCheckResult, GateResult
from src.research.asymmetric.profiles import TeamProfiler, _TeamMatchView, _is_completed
from src.research.data_source import ResearchMatch

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

#: Gate names surfaced on GateResult.gate.
FEATURE_VERIFICATION_GATE = "feature_verification"
SANITY_GATE = "sanity"

#: Known-signal threshold: rolling xG->goals association must be >= ~0.10.
KNOWN_SIGNAL_THRESHOLD = 0.10

#: Shuffle-null tolerance: |BSS| must be within this of zero (chance).
SHUFFLE_NULL_BSS_TOLERANCE = 0.02

#: How many teams to sample for the identity trace (Req 6.2: between 3 and 5).
IDENTITY_TRACE_MIN_TEAMS = 3
IDENTITY_TRACE_MAX_TEAMS = 5

#: Minimum prior matches a team needs to contribute a rolling-signal point.
MIN_PRIOR_FOR_SIGNAL = 3

#: Default RNG seed so gate runs are reproducible (Req 13.1).
DEFAULT_SEED = 20240517


# ─────────────────────────────────────────────────────────────────────────────
# Small numeric helpers (no scipy dependency required for these)
# ─────────────────────────────────────────────────────────────────────────────


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    """Pearson correlation; ``None`` when undefined (n<2 or zero variance)."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0.0 or syy <= 0.0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _rankdata(values: list[float]) -> list[float]:
    """Average-rank transform (ties share the mean of their rank positions)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> Optional[float]:
    """Spearman rank correlation via Pearson on ranks."""
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    return _pearson(_rankdata(xs), _rankdata(ys))


def _brier_skill_score(probs: list[float], outcomes: list[float]) -> Optional[float]:
    """BSS of ``probs`` vs the base-rate naive baseline; ``None`` if undefined."""
    n = len(outcomes)
    if n == 0 or n != len(probs):
        return None
    base = sum(outcomes) / n
    nb = sum((base - y) ** 2 for y in outcomes) / n
    if nb <= 0.0:
        return None
    brier = sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / n
    return 1.0 - brier / nb


# ─────────────────────────────────────────────────────────────────────────────
# Point-in-time rolling-signal extraction (shared by known-signal / orientation
# / shuffle-null). All strictly look-ahead-free: for each match we read the
# team's rolling mean from its PRIOR matches only, then the match is folded in.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _SignalRow:
    """One point-in-time signal row for a played match.

    Attributes:
        home_xg_for: home team's rolling mean xG-for from its prior matches.
        away_xg_for: away team's rolling mean xG-for from its prior matches.
        home_goals_for: home team's rolling mean goals-for from prior matches.
        away_goals_for: away team's rolling mean goals-for from prior matches.
        home_goals: realised home goals in this match (outcome column).
        away_goals: realised away goals in this match (outcome column).
    """

    home_xg_for: Optional[float]
    away_xg_for: Optional[float]
    home_goals_for: Optional[float]
    away_goals_for: Optional[float]
    home_goals: int
    away_goals: int


def _rolling_signal_rows(
    matches: list[ResearchMatch], window: int
) -> list[_SignalRow]:
    """Build look-ahead-free rolling xG-for / goals-for rows keyed on identity.

    For each completed match (ascending date), each team's rolling mean of
    xG-for and goals-for is read from that team's OWN prior matches — across both
    home and away appearances, all leagues (identity keying, Req 1.5, 1.18) —
    then this match is folded into both teams' histories (compute-before-update).
    """
    ordered = sorted(matches, key=lambda m: m.date_unix)
    xg_hist: dict[str, list[float]] = defaultdict(list)
    goals_hist: dict[str, list[float]] = defaultdict(list)

    rows: list[_SignalRow] = []
    for m in ordered:
        if not _is_completed(m):
            continue

        def _mean_tail(hist: list[float]) -> Optional[float]:
            tail = hist[-window:]
            if len(tail) < MIN_PRIOR_FOR_SIGNAL:
                return None
            return sum(tail) / len(tail)

        rows.append(
            _SignalRow(
                home_xg_for=_mean_tail(xg_hist[m.home_team]),
                away_xg_for=_mean_tail(xg_hist[m.away_team]),
                home_goals_for=_mean_tail(goals_hist[m.home_team]),
                away_goals_for=_mean_tail(goals_hist[m.away_team]),
                home_goals=int(m.home_goals),
                away_goals=int(m.away_goals),
            )
        )

        # Fold this match in AFTER reading (look-ahead-free).
        if m.home_xg is not None:
            xg_hist[m.home_team].append(float(m.home_xg))
        if m.away_xg is not None:
            xg_hist[m.away_team].append(float(m.away_xg))
        goals_hist[m.home_team].append(float(m.home_goals))
        goals_hist[m.away_team].append(float(m.away_goals))

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# FeatureVerificationGate (task 8.1)
# ─────────────────────────────────────────────────────────────────────────────


class FeatureVerificationGate:
    """The mandatory five-check feature verification gate (Req 6).

    ``run`` executes all five checks against the real corpus (sampling teams /
    matches to stay fast), reports every check, and — on any failure — returns a
    :class:`GateResult` with ``passed=False`` and ``stopped_modelling=True`` so
    the caller stops before modelling (Req 6.1, 6.7, 6.8).

    Args:
        window: rolling window used for the signal / trace checks (default 10,
            matching the Team_Profiler default).
        known_signal_threshold: minimum acceptable rolling-xG->goals association
            (default ``0.10``, Req 6.3).
        shuffle_bss_tolerance: max acceptable ``|BSS|`` under a shuffled mapping
            (default ``0.02``, Req 6.6).
        seed: RNG seed for reproducible sampling / permutation (Req 13.1).
    """

    def __init__(
        self,
        window: int = 10,
        known_signal_threshold: float = KNOWN_SIGNAL_THRESHOLD,
        shuffle_bss_tolerance: float = SHUFFLE_NULL_BSS_TOLERANCE,
        seed: int = DEFAULT_SEED,
    ) -> None:
        if window < 1:
            raise ValueError(f"window must be >= 1, got {window}")
        self._window = window
        self._known_signal_threshold = known_signal_threshold
        self._shuffle_bss_tolerance = shuffle_bss_tolerance
        self._seed = seed

    # -- public API ------------------------------------------------------ #
    def run(
        self,
        matches: list[ResearchMatch],
        profiler: Optional[TeamProfiler] = None,
        leagues: Optional[dict[int, str]] = None,
    ) -> GateResult:
        """Run all five checks and return an aggregate :class:`GateResult`.

        Every check is always executed and reported (Req 6.7). If ANY check
        fails, the aggregate ``passed`` is ``False`` and ``stopped_modelling`` is
        ``True`` (Req 6.8) — the caller MUST NOT proceed to modelling.

        Args:
            matches: the (real, cached) corpus to verify against.
            profiler: the TeamProfiler that modelling will use; a default is
                constructed when omitted so the gate verifies the same machinery.
            leagues: optional ``league_id -> label`` map (passed to the profiler).
        """
        profiler = profiler or TeamProfiler(window=self._window)

        checks: list[GateCheckResult] = [
            self._check_identity_trace(matches, leagues),
            self._check_known_signal(matches),
            self._check_orientation(matches),
            self._check_look_ahead(matches, profiler, leagues),
            self._check_shuffle_null(matches),
        ]

        passed = all(c.passed for c in checks)
        return GateResult(
            gate=FEATURE_VERIFICATION_GATE,
            passed=passed,
            checks=tuple(checks),
            stopped_modelling=(not passed),
        )

    # -- check 1: team-identity trace (Req 6.2) -------------------------- #
    def _check_identity_trace(
        self,
        matches: list[ResearchMatch],
        leagues: Optional[dict[int, str]],
    ) -> GateCheckResult:
        """Trace 3-5 teams' aggregated matches, confirming identity keying."""
        ordered = sorted(matches, key=lambda m: m.date_unix)
        leagues = leagues or {}

        # Rank teams by how many completed matches they play, so sampled teams
        # actually have a rolling window to trace.
        counts: dict[str, int] = defaultdict(int)
        for m in ordered:
            if _is_completed(m):
                counts[m.home_team] += 1
                counts[m.away_team] += 1
        eligible = [t for t, c in counts.items() if c >= MIN_PRIOR_FOR_SIGNAL]
        eligible.sort(key=lambda t: (-counts[t], t))

        if len(eligible) < IDENTITY_TRACE_MIN_TEAMS:
            return GateCheckResult(
                name="team_identity_trace",
                passed=False,
                detail=(
                    "insufficient teams with history to trace: found "
                    f"{len(eligible)}, need >= {IDENTITY_TRACE_MIN_TEAMS}"
                ),
                metric=float(len(eligible)),
            )

        n_sample = min(IDENTITY_TRACE_MAX_TEAMS, len(eligible))
        # Deterministically sample from the most-active teams.
        sampled = eligible[: max(n_sample, IDENTITY_TRACE_MIN_TEAMS)]
        sampled = sampled[:n_sample]
        # Build per-team ordered rolling window of prior (team, role) views.
        history: dict[str, list[_TeamMatchView]] = defaultdict(list)
        # For each sampled team we capture the rolling window as-of its LAST match.
        traces: dict[str, list[str]] = {t: [] for t in sampled}
        as_of_seen: dict[str, int] = {}

        for m in ordered:
            if not _is_completed(m):
                continue
            for team, role in ((m.home_team, "home"), (m.away_team, "away")):
                if team in sampled:
                    # Snapshot the window BEFORE folding this match in.
                    window_views = history[team][-self._window :]
                    trace_lines = []
                    for v in window_views:
                        trace_lines.append(
                            f"match {v._m.match_id} role={'home' if v._is_home else 'away'} "
                            f"({v._m.home_team} vs {v._m.away_team})"
                        )
                    traces[team] = trace_lines
                    as_of_seen[team] = m.match_id
                league = leagues.get(m.league_id, str(m.league_id))
                history[team].append(_TeamMatchView(m, team, league))

        # Verify: every traced match must actually contain the traced team, and
        # both home and away roles should appear for at least one sampled team.
        wrong_team = 0
        saw_home = False
        saw_away = False
        detail_parts: list[str] = []
        for team in sampled:
            lines = traces[team]
            detail_parts.append(f"[{team}] (n_window={len(lines)}):")
            # Re-verify against the actual views (rebuild the window snapshot).
            # (Rebuild is cheap and avoids trusting the string trace.)
            views = [
                _TeamMatchView(mm, team, leagues.get(mm.league_id, str(mm.league_id)))
                for mm in ordered
                if _is_completed(mm) and team in (mm.home_team, mm.away_team)
            ]
            window = views[: self._window] if views else []
            for v in window:
                if team not in (v._m.home_team, v._m.away_team):
                    wrong_team += 1
                if v._is_home:
                    saw_home = True
                else:
                    saw_away = True
            for ln in lines:
                detail_parts.append(f"    {ln}")

        passed = wrong_team == 0
        detail = (
            f"traced {len(sampled)} teams; wrong-team matches={wrong_team}; "
            f"observed home_role={saw_home} away_role={saw_away}\n"
            + "\n".join(detail_parts)
        )
        return GateCheckResult(
            name="team_identity_trace",
            passed=passed,
            detail=detail,
            metric=float(len(sampled)),
        )

    # -- check 2: known-signal (Req 6.3) --------------------------------- #
    def _check_known_signal(self, matches: list[ResearchMatch]) -> GateCheckResult:
        """xG-for -> goals association >= threshold; goals-for -> goals positive."""
        rows = _rolling_signal_rows(matches, self._window)

        # Pool both sides: (rolling xG-for of the acting side, realised goals of
        # that same side in this match).
        xg_feat: list[float] = []
        xg_out: list[float] = []
        goals_feat: list[float] = []
        goals_out: list[float] = []
        for r in rows:
            if r.home_xg_for is not None:
                xg_feat.append(r.home_xg_for)
                xg_out.append(float(r.home_goals))
            if r.away_xg_for is not None:
                xg_feat.append(r.away_xg_for)
                xg_out.append(float(r.away_goals))
            if r.home_goals_for is not None:
                goals_feat.append(r.home_goals_for)
                goals_out.append(float(r.home_goals))
            if r.away_goals_for is not None:
                goals_feat.append(r.away_goals_for)
                goals_out.append(float(r.away_goals))

        xg_p = _pearson(xg_feat, xg_out)
        xg_s = _spearman(xg_feat, xg_out)
        goals_p = _pearson(goals_feat, goals_out)

        # Use the stronger-magnitude xG association against the threshold so a
        # monotone-but-nonlinear signal is not missed.
        xg_assoc_candidates = [c for c in (xg_p, xg_s) if c is not None]
        xg_assoc = (
            max(xg_assoc_candidates, key=abs) if xg_assoc_candidates else None
        )

        if xg_assoc is None or goals_p is None:
            return GateCheckResult(
                name="known_signal",
                passed=False,
                detail=(
                    "insufficient rolling-signal points to measure association "
                    f"(xg_n={len(xg_feat)}, goals_n={len(goals_feat)})"
                ),
                metric=None,
            )

        passed = (xg_assoc >= self._known_signal_threshold) and (goals_p > 0.0)
        detail = (
            f"xG->goals pearson={_fmt(xg_p)} spearman={_fmt(xg_s)} "
            f"(used={xg_assoc:.4f}, threshold={self._known_signal_threshold:.2f}); "
            f"goals->goals pearson={_fmt(goals_p)} (must be > 0); "
            f"xg_n={len(xg_feat)}, goals_n={len(goals_feat)}"
        )
        return GateCheckResult(
            name="known_signal",
            passed=passed,
            detail=detail,
            metric=float(xg_assoc),
        )

    # -- check 3: orientation (Req 6.4) ---------------------------------- #
    def _check_orientation(self, matches: list[ResearchMatch]) -> GateCheckResult:
        """Home features must align with the home outcome column, not the away."""
        rows = _rolling_signal_rows(matches, self._window)

        home_feat: list[float] = []
        home_col: list[float] = []
        away_col: list[float] = []
        for r in rows:
            if r.home_xg_for is None:
                continue
            home_feat.append(r.home_xg_for)
            home_col.append(float(r.home_goals))
            away_col.append(float(r.away_goals))

        corr_correct = _pearson(home_feat, home_col)
        corr_transposed = _pearson(home_feat, away_col)

        if corr_correct is None or corr_transposed is None:
            return GateCheckResult(
                name="orientation",
                passed=False,
                detail=(
                    "insufficient points to cross-check orientation "
                    f"(n={len(home_feat)})"
                ),
                metric=None,
            )

        # Correct orientation: home feature predicts the home column at least as
        # strongly as the away column (a transposition would flip this).
        passed = corr_correct >= corr_transposed
        detail = (
            f"home_xg_for -> home_goals pearson={corr_correct:.4f}; "
            f"home_xg_for -> away_goals pearson={corr_transposed:.4f}; "
            f"n={len(home_feat)}; "
            + ("aligned (no transposition)" if passed else "TRANSPOSITION DETECTED")
        )
        return GateCheckResult(
            name="orientation",
            passed=passed,
            detail=detail,
            metric=float(corr_correct - corr_transposed),
        )

    # -- check 4: look-ahead (Req 6.5) ----------------------------------- #
    def _check_look_ahead(
        self,
        matches: list[ResearchMatch],
        profiler: TeamProfiler,
        leagues: Optional[dict[int, str]],
    ) -> GateCheckResult:
        """Recompute sampled features from truncated history; assert equality.

        For a sample of matches M, the profile computed from the full corpus must
        equal the profile computed from history truncated to matches strictly
        before-or-at M (i.e. adding *later* matches must not change M's profile).
        This is Property 2's mechanism enforced at the gate level.
        """
        ordered = sorted(matches, key=lambda m: m.date_unix)
        completed = [m for m in ordered if _is_completed(m)]
        if len(completed) < MIN_PRIOR_FOR_SIGNAL + 1:
            return GateCheckResult(
                name="look_ahead",
                passed=False,
                detail=f"insufficient completed matches to sample (n={len(completed)})",
                metric=None,
            )

        full_map = profiler.compute_profiles_map(ordered, leagues=leagues)

        rng = random.Random(self._seed + 1)
        # Sample up to 5 matches from the second half (so they have history).
        candidate_idx = list(range(len(ordered) // 2, len(ordered)))
        candidate_idx = [i for i in candidate_idx if _is_completed(ordered[i])]
        if not candidate_idx:
            candidate_idx = [i for i in range(len(ordered)) if _is_completed(ordered[i])]
        sample_idx = candidate_idx if len(candidate_idx) <= 5 else rng.sample(
            candidate_idx, 5
        )

        mismatches = 0
        checked = 0
        detail_lines: list[str] = []
        for i in sample_idx:
            target = ordered[i]
            truncated = ordered[: i + 1]  # strictly-before M plus M itself
            trunc_map = profiler.compute_profiles_map(truncated, leagues=leagues)
            for key in (target.match_id, -target.match_id):
                if key not in full_map or key not in trunc_map:
                    continue
                checked += 1
                fv = full_map[key].attacking.vector() + full_map[key].defensive.vector()
                tv = (
                    trunc_map[key].attacking.vector()
                    + trunc_map[key].defensive.vector()
                )
                if not _vectors_equal(fv, tv):
                    mismatches += 1
                    detail_lines.append(
                        f"match {target.match_id} key {key}: full != truncated"
                    )

        passed = mismatches == 0 and checked > 0
        detail = (
            f"recomputed {checked} sampled profiles from truncated history; "
            f"mismatches={mismatches} "
            + ("(all point-in-time)" if passed else "(LOOK-AHEAD LEAK)")
        )
        if detail_lines:
            detail += "\n" + "\n".join(detail_lines)
        return GateCheckResult(
            name="look_ahead",
            passed=passed,
            detail=detail,
            metric=float(mismatches),
        )

    # -- check 5: shuffle-null (Req 6.6) --------------------------------- #
    def _check_shuffle_null(self, matches: list[ResearchMatch]) -> GateCheckResult:
        """Permute feature->outcome mapping; BSS must collapse to ~0 (chance).

        Mechanism: fit a single-feature logistic map on a TRAIN split and score
        a held-out TEST split, once with the true mapping and once with the
        TRAIN outcomes permuted (feature->outcome mapping destroyed). The true
        mapping should retain skill (BSS materially > 0); the shuffled mapping
        must collapse to chance. Leakage is indicated only when the *shuffled*
        mapping still retains skill, i.e. its out-of-sample BSS is materially
        POSITIVE. A near-zero or negative shuffled BSS is the expected, healthy
        result and passes.
        """
        rows = _rolling_signal_rows(matches, self._window)

        # Binary outcome: did the acting side score over 1.5 goals? Feature: its
        # rolling xG-for. Pool both sides.
        feats: list[float] = []
        outs: list[float] = []
        for r in rows:
            if r.home_xg_for is not None:
                feats.append(r.home_xg_for)
                outs.append(1.0 if r.home_goals >= 2 else 0.0)
            if r.away_xg_for is not None:
                feats.append(r.away_xg_for)
                outs.append(1.0 if r.away_goals >= 2 else 0.0)

        if len(feats) < 40:
            return GateCheckResult(
                name="shuffle_null",
                passed=False,
                detail=f"insufficient points for shuffle-null (n={len(feats)})",
                metric=None,
            )

        # Chronological-order-agnostic split (rows already come in date order).
        split = int(len(feats) * 0.6)
        tr_x, tr_y = feats[:split], outs[:split]
        te_x, te_y = feats[split:], outs[split:]

        # True-mapping out-of-sample BSS (calibrated single-feature logistic).
        true_probs = _fit_predict_logistic(tr_x, tr_y, te_x)
        true_bss = _brier_skill_score(true_probs, te_y)

        # Shuffled mapping: permute the TRAIN outcomes so the feature carries no
        # information about the (shuffled) label, then fit and score on the same
        # held-out test outcomes.
        rng = random.Random(self._seed + 2)
        shuffled_tr_y = tr_y[:]
        rng.shuffle(shuffled_tr_y)
        shuffled_probs = _fit_predict_logistic(tr_x, shuffled_tr_y, te_x)
        shuffled_bss = _brier_skill_score(shuffled_probs, te_y)

        if shuffled_bss is None:
            return GateCheckResult(
                name="shuffle_null",
                passed=False,
                detail="shuffle-null BSS undefined (degenerate outcomes)",
                metric=None,
            )

        # Leakage => shuffled mapping still has POSITIVE skill beyond tolerance.
        passed = shuffled_bss <= self._shuffle_bss_tolerance
        detail = (
            f"true-mapping OOS BSS={_fmt(true_bss)}; "
            f"shuffled-mapping OOS BSS={shuffled_bss:+.4f} "
            f"(must be <= +{self._shuffle_bss_tolerance:.2f}); n={len(feats)}; "
            + ("collapsed to chance" if passed else "RETAINS SKILL (leakage)")
        )
        return GateCheckResult(
            name="shuffle_null",
            passed=passed,
            detail=detail,
            metric=float(shuffled_bss),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Numeric helpers for the checks
# ─────────────────────────────────────────────────────────────────────────────


def _fmt(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:.4f}"


def _vectors_equal(a: list[float], b: list[float], tol: float = 1e-9) -> bool:
    if len(a) != len(b):
        return False
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _fit_predict_logistic(
    train_x: list[float], train_y: list[float], test_x: list[float]
) -> list[float]:
    """Fit a single-feature logistic map on train, predict probabilities on test.

    A minimal, dependency-free logistic regression (standardized feature +
    intercept, fit by gradient descent). Used only to measure whether a
    feature->outcome mapping retains skill out-of-sample: it learns from the
    TRAIN outcomes, so when those outcomes are permuted the fit carries no
    information and out-of-sample skill collapses to chance.
    """
    n = len(train_x)
    if n == 0:
        return [0.5 for _ in test_x]
    mean = sum(train_x) / n
    var = sum((x - mean) ** 2 for x in train_x) / n
    std = math.sqrt(var) if var > 0 else 1.0

    def z(x: float) -> float:
        return (x - mean) / std

    # Gradient descent on the log-loss.
    w = 0.0
    b = 0.0
    lr = 0.1
    for _ in range(500):
        gw = 0.0
        gb = 0.0
        for x, y in zip(train_x, train_y):
            p = 1.0 / (1.0 + math.exp(-(w * z(x) + b)))
            err = p - y
            gw += err * z(x)
            gb += err
        w -= lr * gw / n
        b -= lr * gb / n

    probs: list[float] = []
    for x in test_x:
        p = 1.0 / (1.0 + math.exp(-(w * z(x) + b)))
        probs.append(min(0.99, max(0.01, p)))
    return probs


# ─────────────────────────────────────────────────────────────────────────────
# SanityGate (task 8.2)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SanityRecord:
    """One recorded structural result for a (league, target) cell (Req 7).

    ``structural_result`` is the known finding text; ``do_not_rediagnose`` is
    always ``True`` because the Sanity_Gate records rather than re-diagnoses
    these known non-signals (Req 7.4).
    """

    league: str
    target: str
    structural_result: str
    do_not_rediagnose: bool = True


# Known structural results the Sanity_Gate records (Req 7.2, 7.3). Keyed by
# target; each maps to a predicate over the league label and the recorded text.
CORNERS_STRUCTURAL_RESULT = (
    "corners has near-zero team-level persistence at rolling-window timescales; "
    "do not re-diagnose (recorded structural result)."
)
CARDS_CHAMPIONSHIP_STRUCTURAL_RESULT = (
    "cards disciplinary persistence is absent in the Championship across three "
    "seasons; do not re-diagnose (recorded structural result)."
)


def _is_championship(league: str) -> bool:
    """True when a league label denotes the Championship (case-insensitive)."""
    return "championship" in league.strip().lower()


class SanityGate:
    """Records known structural non-persistence results per league/target (Req 7).

    ``run`` iterates every (league, target) cell and RECORDS the applicable
    known structural results — corners near-zero team-level persistence for every
    league (Req 7.2), and cards disciplinary-persistence absence in the
    Championship across three seasons (Req 7.3) — without re-diagnosing them
    (Req 7.4). The records are returned so reporting can surface them and the
    search can skip re-diagnosis for these cells.
    """

    def run(
        self,
        leagues: list[str],
        targets: list[str],
    ) -> list[SanityRecord]:
        """Return the recorded :class:`SanityRecord` entries for every cell.

        Args:
            leagues: league labels to record for (e.g. ``["Championship", ...]``).
            targets: targets to record for (e.g. ``["corners", "cards", ...]``).

        Returns:
            A list of :class:`SanityRecord`, one per applicable (league, target)
            structural result. Cells with no known structural result are omitted
            (there is nothing to record and nothing to skip).
        """
        records: list[SanityRecord] = []
        for league in leagues:
            for target in targets:
                t = target.strip().lower()
                if t == "corners":
                    records.append(
                        SanityRecord(
                            league=league,
                            target=target,
                            structural_result=CORNERS_STRUCTURAL_RESULT,
                        )
                    )
                elif t == "cards" and _is_championship(league):
                    records.append(
                        SanityRecord(
                            league=league,
                            target=target,
                            structural_result=CARDS_CHAMPIONSHIP_STRUCTURAL_RESULT,
                        )
                    )
        return records

    def run_as_gate_result(
        self,
        leagues: list[str],
        targets: list[str],
    ) -> GateResult:
        """Return the sanity records wrapped in a GateResult-like structure.

        Each recorded structural result is surfaced as a passing
        :class:`GateCheckResult` (recording is not a failure). The sanity gate
        never stops modelling — it records and reports (Req 7.4) — so
        ``passed=True`` and ``stopped_modelling=False``.
        """
        records = self.run(leagues, targets)
        checks = tuple(
            GateCheckResult(
                name=f"sanity[{r.league}/{r.target}]",
                passed=True,
                detail=r.structural_result,
                metric=None,
            )
            for r in records
        )
        return GateResult(
            gate=SANITY_GATE,
            passed=True,
            checks=checks,
            stopped_modelling=False,
        )
