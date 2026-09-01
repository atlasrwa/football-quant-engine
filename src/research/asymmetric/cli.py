"""Analysis_CLI core — narrative + EV rendering with a load-bearing caveat.

Responsibility:
    The importable core behind ``scripts/asymmetric_analyze.py``. Given a resolved
    fixture, point-in-time profiles, a fitted (or default) InteractionModel, and
    an optional per-side odds map, it produces the matchup narrative (Req 9.2-9.6),
    the explicit asymmetry statement (Req 9.5), and the distinct EV section
    (Req 9.9-9.11, 15), and it appends the mandatory caveat to EVERY output —
    success, reduced-coverage, and every error path (Req 9.12, Property 20).

Design decision — the caveat is structurally unavoidable:
    Every rendered string is produced by :func:`finalize`, which appends
    :data:`MANDATORY_CAVEAT`. All public render entry points return their body to
    :func:`finalize`, so no output path can omit the caveat. This is the single
    guarantee Property 20 checks across all seven output kinds.

Isolation: imports only the isolated package + general-purpose building blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from src.research.asymmetric.derived import DerivedOutcomeCombiner
from src.research.asymmetric.ev_layer import (
    PER_SIDE_PRICED_MARKETS,
    TEAM_CARDS_MARKET,
    EVLayer,
    PerSideEV,
    books_for_league,
    per_side_ev_coverage,
)
from src.research.asymmetric.interaction import (
    ATT_DIMS,
    DEF_DIMS,
    DIRECTION_A,
    DIRECTION_B,
    FixtureContext,
    InteractionModel,
    _default_line,
)
from src.research.asymmetric.models import (
    DirectionPrediction,
    FixturePrediction,
    TeamMatchProfiles,
)
from src.research.asymmetric.derived import pmf_mean

# ─────────────────────────────────────────────────────────────────────────────
# The mandatory caveat (Req 9.12, Property 20)
# ─────────────────────────────────────────────────────────────────────────────
MANDATORY_CAVEAT = (
    "CAVEAT: A single fixture demonstrates nothing about edge. This engine has "
    "NOT beaten market prices in systematic out-of-sample testing — the decisive "
    "asymmetry-vs-marginal backtest returned a negative result. Treat this "
    "output as a mechanism/prediction explainer only, never as a betting signal."
)

#: The map of Per_Side_Priced_Market -> the per-side target it is priced on.
_MARKET_TO_TARGET = {
    "team_corners": "corners",
    "team_total_goals": "goals",
    "team_shots_on_target": "sot",
}


def finalize(body: str) -> str:
    """Append the mandatory caveat to any output body (Req 9.12, Property 20).

    This is the ONLY way a CLI output is produced, so the caveat is present on
    success, reduced-coverage, unrecognised, ambiguous, no-fixture, zero-history,
    and cap-exceeded outputs alike.
    """
    body = body.rstrip("\n")
    return f"{body}\n\n{MANDATORY_CAVEAT}\n"


# ─────────────────────────────────────────────────────────────────────────────
# Error / rejection outputs (Req 9.8, 9.13-9.15, 12.4) — never predict
# ─────────────────────────────────────────────────────────────────────────────
def render_rejection(title: str, detail: str) -> str:
    """Render a rejection/no-prediction output with the caveat (Property 20)."""
    return finalize(f"{title}\n{detail}\nNo predictions were produced.")


def render_zero_history(team: str) -> str:
    """Zero cached history for a team -> no profile, no predictions (Req 9.8)."""
    return render_rejection(
        "NO PROFILE — insufficient data",
        f"Team {team!r} has zero cached completed matches; no profile can be "
        "produced.",
    )


def render_cap_exceeded(spend_units: float, cap: float) -> str:
    """Live-fetch cap exceeded -> terminate with caveat (Req 12.4)."""
    return render_rejection(
        "LIVE-FETCH CAP EXCEEDED",
        f"A required live fetch would breach the spend cap "
        f"(spent {spend_units:.2f} of {cap:.2f} units). Fetch refused; no "
        "predictions were produced.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Profile / coverage rendering (Req 9.2, 9.6, 9.7)
# ─────────────────────────────────────────────────────────────────────────────
def _render_profile_block(label: str, profiles: TeamMatchProfiles) -> list[str]:
    """Render one team's profile as named dimensions with numeric values (Req 9.2)."""
    lines = [f"{label}: {profiles.team}  (history: {profiles.n_history} matches"
             f"{', REDUCED-COVERAGE' if profiles.insufficient else ''})"]
    lines.append("  Attacking dimensions:")
    for dim in ATT_DIMS:
        d = getattr(profiles.attacking, dim)
        miss = f"  [missing: {', '.join(d.missing_fields)}]" if d.missing_fields else ""
        lines.append(f"    {dim:<22} {d.value:+.4f}{miss}")
    lines.append("  Defensive dimensions:")
    for dim in DEF_DIMS:
        d = getattr(profiles.defensive, dim)
        miss = f"  [missing: {', '.join(d.missing_fields)}]" if d.missing_fields else ""
        lines.append(f"    {dim:<22} {d.value:+.4f}{miss}")
    return lines


def _render_coverage_block(
    home: TeamMatchProfiles, away: TeamMatchProfiles, min_history: int
) -> list[str]:
    """Per-team coverage: match count and populated-vs-absent rich fields (Req 9.6)."""
    lines = ["COVERAGE (per team: match count and populated-vs-absent rich fields)"]
    for label, prof in (("home", home), ("away", away)):
        absent = _absent_rich_fields(prof)
        populated = _populated_dim_count(prof)
        lines.append(
            f"  {label} {prof.team}: {prof.n_history} matches, "
            f"{populated}/10 dimensions populated"
            + (f"; absent: {', '.join(absent)}" if absent else "")
        )
        if prof.n_history < min_history:
            lines.append(
                f"    REDUCED-COVERAGE: {prof.n_history} < required minimum "
                f"{min_history}; continuing on a reduced profile (Req 9.7)."
            )
    return lines


def _absent_rich_fields(prof: TeamMatchProfiles) -> list[str]:
    absent: list[str] = []
    for dim in ATT_DIMS:
        d = getattr(prof.attacking, dim)
        absent.extend(d.missing_fields)
    for dim in DEF_DIMS:
        d = getattr(prof.defensive, dim)
        absent.extend(d.missing_fields)
    # De-dup preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for f in absent:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _populated_dim_count(prof: TeamMatchProfiles) -> int:
    count = 0
    for dim in ATT_DIMS:
        if getattr(prof.attacking, dim).n_matches_used > 0:
            count += 1
    for dim in DEF_DIMS:
        if getattr(prof.defensive, dim).n_matches_used > 0:
            count += 1
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Per-side predictions + derived + asymmetry statement (Req 9.3-9.5)
# ─────────────────────────────────────────────────────────────────────────────
def _render_predictions_block(fixture: FixturePrediction) -> list[str]:
    """Per-side predictions for each target with named driving features (Req 9.3)."""
    lines = ["PER-SIDE PREDICTIONS (expected count and named driving features)"]
    for dp in fixture.directions:
        side = "home" if dp.direction == DIRECTION_A else "away"
        sub = " [referee card-rate SUBSTITUTED with league rate]" if (
            dp.target == "cards" and dp.referee_substituted
        ) else ""
        lines.append(
            f"  [{side}] {dp.attacker} vs {dp.defender} — {dp.target}: "
            f"E[count]={dp.expected_value:.3f}{sub}"
        )
        lines.append(
            "      driving features: " + ", ".join(dp.driving_features)
        )
    return lines


def _render_derived_block(fixture: FixturePrediction) -> list[str]:
    """Derived totals + BTTS + clean sheets (Req 9.4)."""
    d = fixture.derived
    lines = ["DERIVED MATCH OUTCOMES (combined under the stated independence assumption)"]
    lines.append(f"  independence assumption: {fixture.independence_assumption}")
    lines.append(f"  E[total corners] = {pmf_mean(d.total_corners):.3f}")
    lines.append(f"  E[total cards]   = {pmf_mean(d.total_cards):.3f}")
    lines.append(f"  E[total goals]   = {pmf_mean(d.total_goals):.3f}")
    lines.append(f"  BTTS (yes)       = {d.btts_yes:.3f}")
    lines.append(f"  clean sheet home = {d.clean_sheet_home:.3f}, "
                 f"clean sheet away = {d.clean_sheet_away:.3f}")
    if d.correlation_red_flags:
        lines.append("  correlation red flags:")
        for rf in d.correlation_red_flags:
            lines.append(f"    - {rf}")
    return lines


def _render_asymmetry_statement(fixture: FixturePrediction) -> list[str]:
    """Explicit asymmetry statement naming the dominating side per outcome (Req 9.5)."""
    lines = ["ASYMMETRY STATEMENT (which side dominates each outcome and why)"]
    by_key = {(dp.direction, dp.target): dp for dp in fixture.directions}
    for target in ("corners", "cards", "goals"):
        a = by_key.get((DIRECTION_A, target))
        b = by_key.get((DIRECTION_B, target))
        if a is None or b is None:
            continue
        if a.expected_value >= b.expected_value:
            dom_side, dom, oth = "home", a, b
        else:
            dom_side, dom, oth = "away", b, a
        driver = dom.driving_features[0] if dom.driving_features else "n/a"
        lines.append(
            f"  {target}: {dom_side} side dominates "
            f"(E={dom.expected_value:.3f} vs {oth.expected_value:.3f}); "
            f"responsible driving feature: {driver}"
        )
    # BTTS is symmetric-ish; state which side's scoring pressure leads.
    lines.append(
        f"  BTTS: driven by both sides' goals distributions "
        f"(P={fixture.derived.btts_yes:.3f})"
    )
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# EV section (Req 9.9-9.11, 15)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class OddsQuote:
    """An over/under price for one (market, book, side, line)."""

    market: str
    book: str
    side: str      # "home" | "away"
    line: float
    over_odds: float
    under_odds: float


def _pmf_for_side_target(fixture: FixturePrediction, side: str, target: str):
    direction = DIRECTION_A if side == "home" else DIRECTION_B
    for dp in fixture.directions:
        if dp.direction == direction and dp.target == target:
            return dp.distribution
    return None


def _render_ev_block(
    fixture: FixturePrediction,
    league_label: str,
    odds: Sequence[OddsQuote],
) -> list[str]:
    """Distinct, labelled EV section per book (unblended); cards has no per-side EV.

    Per-side EV is computed ONLY for Per_Side_Priced_Markets from the league's
    Priced_Books (Req 9.9, 9.10, 15). Team cards is presented WITHOUT a per-side
    EV, stating no per-side price is available (Req 9.11, 15.5, 15.7). A priced
    (market, book) pair with no supplied odds is recorded as such.
    """
    lines = ["EXPECTED VALUE (per-side, per book, UNBLENDED — research only)"]
    books = books_for_league(league_label)
    if not books:
        lines.append(
            f"  No Priced_Books for league {league_label!r}; no per-side EV "
            "is available."
        )
        _append_cards_no_ev(lines)
        return lines

    lines.append(f"  League {league_label}: books = {', '.join(books)}")
    layer = EVLayer()
    odds_by_key = {(q.market, q.book, q.side): q for q in odds}
    coverage = per_side_ev_coverage(league_label)

    any_ev = False
    for cell in coverage:
        if not cell.priced:
            lines.append(
                f"  [{cell.book}] {cell.market}: OMITTED — {cell.reason}"
            )
            continue
        target = _MARKET_TO_TARGET[cell.market]
        for side in ("home", "away"):
            q = odds_by_key.get((cell.market, cell.book, side))
            if q is None:
                lines.append(
                    f"  [{cell.book}] {cell.market} ({side}): priced by book but "
                    "no odds supplied for this fixture — EV unavailable."
                )
                continue
            pmf = _pmf_for_side_target(fixture, side, target)
            if pmf is None:
                continue
            entry = layer.compute_entry(
                market=cell.market,
                book=cell.book,
                side=side,
                line=q.line,
                pmf=pmf,
                over_odds=q.over_odds,
                under_odds=q.under_odds,
            )
            if entry is None:
                continue
            any_ev = True
            lines.append(_format_ev_entry(entry))

    if not any_ev:
        lines.append("  (no per-side odds were supplied; EV section is empty)")

    _append_cards_no_ev(lines)
    return lines


def _append_cards_no_ev(lines: list[str]) -> None:
    """State that team cards has no per-side price in any book (Req 9.11, 15.5)."""
    lines.append(
        f"  {TEAM_CARDS_MARKET}: NO per-side price is available in any book; "
        "the model cards prediction is presented without a per-side EV. "
        "Team-cards EV is only available via the derived total-cards market "
        "where that total is priced."
    )


def _format_ev_entry(e: PerSideEV) -> str:
    return (
        f"  [{e.book}] {e.market} ({e.side}) line {e.line}: "
        f"P(over)={e.p_over:.3f}, over {e.over_odds} -> EV {e.ev_over:+.3f}, "
        f"under {e.under_odds} -> EV {e.ev_under:+.3f} "
        f"(best: {e.best_side})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Full success narrative (Req 9.2-9.6, 9.9)
# ─────────────────────────────────────────────────────────────────────────────
def render_analysis(
    *,
    home_profiles: TeamMatchProfiles,
    away_profiles: TeamMatchProfiles,
    fixture: FixturePrediction,
    league_label: str,
    date_iso: str,
    min_history: int = 5,
    odds: Optional[Sequence[OddsQuote]] = None,
) -> str:
    """Render the full matchup narrative + EV, then append the caveat (Req 9.2-9.12)."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(
        f"ASYMMETRIC MATCHUP ANALYSIS — {fixture.home_team} vs "
        f"{fixture.away_team} ({date_iso}, {league_label})"
    )
    lines.append("=" * 78)
    lines.append("")

    # Profiles (Req 9.2).
    lines.append("TEAM PROFILES (named dimensions with numeric values)")
    lines.extend(_render_profile_block("HOME", home_profiles))
    lines.append("")
    lines.extend(_render_profile_block("AWAY", away_profiles))
    lines.append("")

    # Coverage (Req 9.6, 9.7).
    lines.extend(_render_coverage_block(home_profiles, away_profiles, min_history))
    lines.append("")

    # Per-side predictions (Req 9.3).
    lines.extend(_render_predictions_block(fixture))
    lines.append("")

    # Derived (Req 9.4).
    lines.extend(_render_derived_block(fixture))
    lines.append("")

    # Asymmetry statement (Req 9.5).
    lines.extend(_render_asymmetry_statement(fixture))
    lines.append("")

    # EV section (Req 9.9-9.11, 15).
    lines.extend(_render_ev_block(fixture, league_label, odds or ()))
    lines.append("")

    return finalize("\n".join(lines))
