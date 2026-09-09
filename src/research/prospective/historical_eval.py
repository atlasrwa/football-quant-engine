"""Historical information-decomposition evaluation (M0-M4).

Runs the M0-M4 ladder on existing corpus data where it is DEFENSIBLE:

    M0 climatology              : global base rate of the selection
    M1 league identity          : base rate within the fixture's league
    M2 champion fundamentals     : HierarchicalCountModel probability
    M3 market only               : de-vigged PRE-MATCH bookmaker probability
    M4 market + residual         : ridge-logistic residual on (fundamental-market)
                                   disagreement, with the market logit as offset

M5 (confirmed lineup delta) is deliberately OMITTED here and reported as
"M5 HISTORICAL PIT UNSUPPORTED": the corpus carries no lineups, and the live
lineups endpoint attaches no capture timestamp, so no historical confirmed XI
can be proven available before a forecast cutoff.

Odds honesty: the corpus over/under prices are PRE-MATCH prices. They are used
strictly as a pre-match market prior (an "opening"-grade comparison), never as
a genuine closing line. All scoring is on a single COMMON SUPPORT set of
fixtures so incremental deltas reflect information, not changing fixtures.

Leakage safety: M0-M2 are fit on a strictly earlier chronological split than
the evaluation fixtures; the M4 residual is fit on the training split only and
its standardization is frozen from that fold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.research.models.market_family import family_by_name
from src.research.models.hierarchical_market_model import HierarchicalCountModel
from src.research.models.side_rows import build_fixture_rows, training_rows
from src.research.prospective.decomposition import LayerScore, run_decomposition
from src.research.prospective.residual_model import RidgeLogisticResidualModel, ResidualSample
from src.research.reconciliation.devig import devig

# Corpus odds keys per family (PRE-MATCH prices, used as opening-grade market).
_ODDS_KEYS = {
    "goals": ("odds_ft_over25", "odds_ft_under25", 2.5),
    "corners": ("odds_corners_over_95", "odds_corners_under_95", 9.5),
}
# Realized total-count fields per family.
_COUNT_FIELDS = {
    "goals": ("homeGoalCount", "awayGoalCount"),
    "corners": ("team_a_corners", "team_b_corners"),
}


@dataclass
class HistoricalEvalResult:
    family: str
    line: float
    n_common: int
    scores: list[LayerScore]
    m5_status: str = "M5 HISTORICAL PIT UNSUPPORTED"

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "line": self.line,
            "n_common": self.n_common,
            "m5_status": self.m5_status,
            "layers": [s.to_dict() for s in self.scores],
        }


def _market_over_prob(match: dict, over_key: str, under_key: str) -> Optional[float]:
    o = match.get(over_key)
    u = match.get(under_key)
    try:
        o = float(o)
        u = float(u)
    except (TypeError, ValueError):
        return None
    if o <= 1.0 or u <= 1.0:
        return None
    try:
        return devig({"OVER": o, "UNDER": u}).fair_probabilities["OVER"]
    except ValueError:
        return None


def _total_over_outcome(match: dict, family: str, line: float) -> Optional[bool]:
    ha, ab = _COUNT_FIELDS[family]
    a = match.get(ha)
    b = match.get(ab)
    if a is None or b is None:
        return None
    return (a + b) > line


def run_historical_eval(
    matches: Sequence[dict],
    *,
    family: str = "goals",
    train_fraction: float = 0.5,
    l2: float = 5.0,
) -> HistoricalEvalResult:
    """Run the M0-M4 decomposition for one family on a chronological split.

    ``matches`` are raw corpus dicts (must carry ``date_unix``). The earliest
    ``train_fraction`` by kickoff trains M1/M2/M4; the rest is evaluated. Only
    fixtures with all of {champion prediction, market prior, outcome} present
    form the common support.
    """
    over_key, under_key, line = _ODDS_KEYS[family]
    fam = family_by_name(family)

    ordered = sorted(
        (m for m in matches if m.get("date_unix")),
        key=lambda m: m["date_unix"],
    )
    if not ordered:
        return HistoricalEvalResult(family, line, 0, [])
    split = int(len(ordered) * train_fraction)
    train, test = ordered[:split], ordered[split:]

    # --- fit champion on the training split only ------------------------
    train_family_rows = build_fixture_rows(train, [fam]).get(family, [])
    rows = training_rows(train_family_rows)
    model = HierarchicalCountModel(fam)
    try:
        model.fit(rows)
    except ValueError:
        # Too few labelled rows to fit the champion on this slice. The
        # decomposition cannot include M2/M4; return an empty result rather
        # than fabricating predictions.
        return HistoricalEvalResult(family, line, 0, [])

    # Build test-side rows keyed by fixture id for prediction.
    test_family_rows = build_fixture_rows(test, [fam]).get(family, [])
    fr_by_fixture = {fr.fixture_id: fr for fr in test_family_rows}

    # --- climatology / league base rates from the training split -------
    def _outcome(m):
        return _total_over_outcome(m, family, line)

    train_outcomes = [(_outcome(m)) for m in train]
    global_rate = _rate([o for o in train_outcomes if o is not None])
    league_rate: dict[str, float] = {}
    by_league: dict[str, list[bool]] = {}
    for m, o in zip(train, train_outcomes):
        if o is None:
            continue
        by_league.setdefault(str(m.get("_league", "")), []).append(o)
    for lg, outs in by_league.items():
        league_rate[lg] = _rate(outs)

    # --- assemble per-key predictions on common support ----------------
    m0, m1, m2, m3, outcomes = {}, {}, {}, {}, {}
    residual_train: list[ResidualSample] = []

    # Fit the residual on the TRAIN split (fundamental vs market disagreement).
    train_fr = {fr.fixture_id: fr for fr in train_family_rows}
    for m in train:
        fid = _fid(m)
        if fid is None or fid not in train_fr:
            continue
        out = _outcome(m)
        mk = _market_over_prob(m, over_key, under_key)
        if out is None or mk is None:
            continue
        fr = train_fr[fid]
        try:
            p_fund = model.predict_match(fr.home_row, fr.away_row).p_over(line)
        except Exception:
            continue
        residual_train.append(
            ResidualSample(
                p_market=mk,
                features={"fund_minus_market": _logit(p_fund) - _logit(mk)},
                outcome=out,
            )
        )

    residual = RidgeLogisticResidualModel(l2=l2)
    if residual_train:
        residual.fit(residual_train)

    m4 = {}
    for m in test:
        fid = _fid(m)
        if fid is None or fid not in fr_by_fixture:
            continue
        out = _outcome(m)
        mk = _market_over_prob(m, over_key, under_key)
        if out is None or mk is None:
            continue
        fr = fr_by_fixture[fid]
        try:
            p_fund = model.predict_match(fr.home_row, fr.away_row).p_over(line)
        except Exception:
            continue
        key = (fid,)
        outcomes[key] = out
        m0[key] = global_rate
        m1[key] = league_rate.get(str(m.get("_league", "")), global_rate)
        m2[key] = p_fund
        m3[key] = mk
        sample = ResidualSample(
            p_market=mk, features={"fund_minus_market": _logit(p_fund) - _logit(mk)}
        )
        m4[key] = residual.predict(sample)

    layers = {"M0": m0, "M1": m1, "M2": m2, "M3": m3, "M4": m4}
    scores = run_decomposition(layers, outcomes, layer_order=["M0", "M1", "M2", "M3", "M4"])
    n_common = scores[0].n if scores else 0
    return HistoricalEvalResult(family, line, n_common, scores)


# --- small helpers ------------------------------------------------------

import math


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def _rate(outs: list[bool]) -> float:
    if not outs:
        return 0.5
    r = sum(1 for o in outs if o) / len(outs)
    return min(max(r, 1e-6), 1 - 1e-6)


def _fid(m: dict) -> Optional[str]:
    for k in ("id", "match_id", "fixture_id"):
        v = m.get(k)
        if v is not None:
            return str(v)
    return None
