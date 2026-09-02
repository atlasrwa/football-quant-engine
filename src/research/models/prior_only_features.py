"""Leak-free (strictly-prior) feature construction for CountRegressionModel.

WHY THIS EXISTS
===============
An internal forensic audit found that the DEFAULT way callers populated
``CountRegressionModel`` features fed the PREDICTED match's OWN final statistics
into the model (``shots_home`` = that match's realized shots, ``fouls_home`` = that
match's realized fouls, etc.). Because the leak is WITHIN-ROW — feature and label
come from the same match — the walk-forward temporal split did not catch it. Zeroing
those features dropped corners BSS +8.11% -> +1.03% and cards +6.06% -> +1.32%, i.e.
most of the reported skill was leakage.

This module builds the SAME feature schema the model expects, but every feature is a
rolling mean over the team's matches STRICTLY BEFORE the fixture (``d < date_unix``),
mirroring the discipline the rich-field path already uses
(``ev_test_metrics_vs_bet365.get_team_rolling_stat``). It does NOT touch the model's
maths (``_fit_regression`` / ``_predict_lambda`` were found sound).

STRUCTURAL GUARANTEE
====================
:func:`assert_no_same_match_leakage` proves — not by convention but by construction —
that no feature value equals the predicted match's own realized statistic (except by
numerical coincidence, which is checked to be within the prior window). Callers should
run it (or the test in ``tests/test_prior_only_features.py``) so this bug class, which
has now appeared twice, cannot silently return.

The count target (``total_corners`` / ``total_cards``) IS carried on the feature dict
because ``CountRegressionModel.fit`` reads the label from it — that is the OUTCOME,
not a feature, and it is never added to ``FEATURE_FIELDS``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np


# The model's feature schema (must match CountRegressionModel defaults).
CORNERS_FEATURES: tuple[str, ...] = (
    "dangerous_attacks_home", "dangerous_attacks_away",
    "attacks_home", "attacks_away",
    "possession_home", "possession_away",
    "shots_home", "shots_away",
)
CARDS_FEATURES: tuple[str, ...] = (
    "fouls_home", "fouls_away",
    "dangerous_attacks_home", "dangerous_attacks_away",
    "possession_home", "possession_away",
)

#: Feature field -> (raw per-team stat key, side). side in {"home","away"}.
#: The raw keys are the corpus/normalizer per-team POST-MATCH stat names; we only
#: ever read them for PRIOR matches to form a rolling mean, never for the fixture.
_FEATURE_SOURCE: dict[str, tuple[str, str]] = {
    "shots_home": ("shots", "home"),
    "shots_away": ("shots", "away"),
    "dangerous_attacks_home": ("dangerous_attacks", "home"),
    "dangerous_attacks_away": ("dangerous_attacks", "away"),
    "attacks_home": ("attacks", "home"),
    "attacks_away": ("attacks", "away"),
    "possession_home": ("possession", "home"),
    "possession_away": ("possession", "away"),
    "fouls_home": ("fouls", "home"),
    "fouls_away": ("fouls", "away"),
}

#: Raw per-team stat -> (home_key, away_key) in the corpus match dict.
_RAW_KEYS: dict[str, tuple[str, str]] = {
    "shots": ("team_a_shots", "team_b_shots"),
    "dangerous_attacks": ("team_a_dangerous_attacks", "team_b_dangerous_attacks"),
    "attacks": ("team_a_attacks", "team_b_attacks"),
    "possession": ("team_a_possession", "team_b_possession"),
    "fouls": ("team_a_fouls", "team_b_fouls"),
}

DEFAULT_WINDOW = 10  # rolling window (matches the current w5/w10 design; 10 = "recent form")
MIN_PRIOR = 3        # need at least this many prior matches for a usable rolling mean


def _num(v) -> Optional[float]:
    """Corpus values use -1 / None as 'not recorded'."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f == -1:
        return None
    return f


@dataclass
class _TeamRoll:
    """A team's own realized stat values from its PRIOR matches, most-recent last."""
    values: dict[str, list[float]]  # stat -> chronological list of that team's own values


def _team_own_stat(match: dict, team_id, stat: str) -> Optional[float]:
    """The team's OWN realized value of ``stat`` in ``match`` (home slot if it was
    home, away slot if it was away). Used only for PRIOR matches."""
    hk, ak = _RAW_KEYS[stat]
    if match.get("homeID") == team_id:
        return _num(match.get(hk))
    if match.get("awayID") == team_id:
        return _num(match.get(ak))
    return None


def build_prior_only_features(
    matches: Sequence[dict],
    *,
    target_field: str,
    window: int = DEFAULT_WINDOW,
    min_prior: int = MIN_PRIOR,
) -> list[dict]:
    """Build leak-free feature dicts for a chronological list of corpus matches.

    Each output feature value is the rolling mean of the team's OWN realized stat
    over its up-to-``window`` matches STRICTLY BEFORE the current fixture. Matches
    without ``min_prior`` prior games for BOTH teams are still emitted (so the
    walk-forward has rows) but with the feature set to the running global mean of
    that stat (a neutral prior), never the fixture's own value.

    Args:
        matches: corpus match dicts (must carry homeID/awayID/date_unix and the raw
            per-team stat keys). Sorted internally by date_unix.
        target_field: "total_corners" or "total_cards" — the OUTCOME, carried through
            for the model to read as the label. Never added as a feature.
        window: rolling window length.
        min_prior: minimum prior matches for a real rolling value (else neutral prior).

    Returns:
        List of feature dicts (chronological) with the model feature schema populated
        from prior data only, plus home_team_id/away_team_id/date_unix and the target.
    """
    ms = sorted(matches, key=lambda m: m.get("date_unix", 0))
    # team_id -> stat -> chronological list of the team's own prior values
    hist: dict[object, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    # running global mean per stat (neutral prior), updated only with PAST data
    running_sum: dict[str, float] = defaultdict(float)
    running_n: dict[str, int] = defaultdict(int)

    out: list[dict] = []
    for m in ms:
        hid, aid = m.get("homeID"), m.get("awayID")
        feat: dict = {"home_team_id": hid, "away_team_id": aid,
                      "date_unix": m.get("date_unix", 0)}

        for fname, (stat, side) in _FEATURE_SOURCE.items():
            tid = hid if side == "home" else aid
            prior_vals = hist[tid][stat][-window:]
            if len(prior_vals) >= min_prior:
                feat[fname] = float(np.mean(prior_vals))
            else:
                # neutral prior = global mean of PAST matches (never this fixture)
                gm = (running_sum[stat] / running_n[stat]) if running_n[stat] > 0 else 0.0
                feat[fname] = float(gm)

        # target/outcome (label), carried but never a feature
        if target_field == "total_corners":
            tc = _num(m.get("totalCornerCount"))
            feat["total_corners"] = tc
        elif target_field == "total_cards":
            ya = _num(m.get("team_a_yellow_cards")); yb = _num(m.get("team_b_yellow_cards"))
            ra = _num(m.get("team_a_red_cards")) or 0.0; rb = _num(m.get("team_b_red_cards")) or 0.0
            feat["total_cards"] = (ya + yb + ra + rb) if (ya is not None and yb is not None) else None

        out.append(feat)

        # AFTER emitting the row, fold THIS match into history (so it is only ever
        # available to LATER fixtures — strictly-prior guarantee).
        for stat in _RAW_KEYS:
            hv = _team_own_stat(m, hid, stat)
            av = _team_own_stat(m, aid, stat)
            if hv is not None:
                hist[hid][stat].append(hv); running_sum[stat] += hv; running_n[stat] += 1
            if av is not None:
                hist[aid][stat].append(av); running_sum[stat] += av; running_n[stat] += 1

    return out


def assert_no_same_match_leakage(
    matches: Sequence[dict],
    features: Sequence[dict],
    *,
    window: int = DEFAULT_WINDOW,
    min_prior: int = MIN_PRIOR,
    tolerance: float = 1e-9,
) -> None:
    """STRUCTURAL anti-leakage guard.

    Independently re-derives every feature as a rolling mean over the team's OWN
    values in matches STRICTLY BEFORE the fixture, and asserts the builder's output
    equals that prior-only quantity. Because the re-derivation is computed from a
    history that, by construction, EXCLUDES the current match, a pass proves no
    feature can carry the predicted match's own realized statistic. It also directly
    asserts that no feature key is one of the raw current-match stat keys.

    Raises:
        AssertionError: if any feature depends on the predicted match's own stats,
            or a raw same-match stat key appears among the feature fields.
    """
    ms = sorted(matches, key=lambda m: m.get("date_unix", 0))
    if len(ms) != len(features):
        raise AssertionError("matches and features length mismatch")

    # 1) No feature field may BE a raw same-match per-team stat key.
    raw_keys = {k for pair in _RAW_KEYS.values() for k in pair}
    for f in features:
        offending = raw_keys & set(f.keys())
        if offending:
            raise AssertionError(
                f"feature dict contains raw same-match stat keys: {sorted(offending)}")

    # 2) Every feature must equal the independently recomputed STRICTLY-PRIOR rolling
    #    mean (or the strictly-prior running global mean when history is too short).
    #    This recomputation never reads the current match, so equality proves the
    #    builder is prior-only.
    hist: dict[object, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    running_sum: dict[str, float] = defaultdict(float)
    running_n: dict[str, int] = defaultdict(int)
    leaks: list[str] = []

    for i, m in enumerate(ms):
        hid, aid = m.get("homeID"), m.get("awayID")
        for fname, (stat, side) in _FEATURE_SOURCE.items():
            if fname not in features[i]:
                continue
            tid = hid if side == "home" else aid
            prior_vals = hist[tid][stat][-window:]
            if len(prior_vals) >= min_prior:
                expected = float(np.mean(prior_vals))
            else:
                expected = (running_sum[stat] / running_n[stat]) if running_n[stat] > 0 else 0.0
            got = features[i].get(fname)
            if got is None or abs(float(got) - expected) > tolerance:
                leaks.append(f"match#{i} {fname}: builder={got} vs strictly-prior={expected}")
                if len(leaks) >= 5:
                    break
        if len(leaks) >= 5:
            break
        # fold current match into history AFTER checking (strictly-prior)
        for stat in _RAW_KEYS:
            hv = _team_own_stat(m, hid, stat)
            av = _team_own_stat(m, aid, stat)
            if hv is not None:
                hist[hid][stat].append(hv); running_sum[stat] += hv; running_n[stat] += 1
            if av is not None:
                hist[aid][stat].append(av); running_sum[stat] += av; running_n[stat] += 1

    if leaks:
        raise AssertionError(
            "SAME-MATCH LEAKAGE DETECTED — features do not match strictly-prior "
            "recomputation:\n  " + "\n  ".join(leaks))
