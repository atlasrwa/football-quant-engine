"""CANDIDATE model variant: cards market + a leak-free league card-environment prior.

MOTIVATION (evidence-driven, Phase 3)
=====================================
The champion cards model is well-calibrated in the body but OVERCONFIDENT in its
high-confidence tail (walk-forward: cards@4.5 chosen>=0.70 predicted ~72.7% vs
observed ~54.8%). Its high-confidence predictions are overwhelmingly UNDER, and
the misses spread across many competitions. The champion has NO explicit league
card-rate context: it extrapolates team rolling form across leagues with very
different carding baselines, so a low-form pairing in a high-carding league is
graded too confidently UNDER.

This candidate adds ONE feature per fixture: the league's current-season-to-date
mean total cards (a "league card environment" prior), computed strictly from
matches before kickoff in the same season-instance. Everything else — the
elastic-net, the existing feature pool, the min-history gate, the target — is
identical to the champion, so any metric change is attributable to the added
prior alone (an ablation of exactly one feature family).

STRICTLY DERIVED / EVALUATION-ONLY
==================================
This is a CANDIDATE evaluated in the walk-forward harness. It does NOT modify the
champion (scripts/pilotC_stat_mixer.py), does NOT write forecast commitments, and
CANNOT become a consumer/validated signal. It carries its own candidate model
version string so it can never be confused with the champion or rewrite
provenance. Old prospective records are untouched and were NOT produced by it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

_SCRIPTS = str(Path("/home/ubuntu/scripts"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

CANDIDATE_MODEL_FAMILY = "candidate.cards_league_card_environment_prior"


def candidate_model_version(champion_version: str) -> str:
    """Deterministic candidate version, distinct from any champion version."""
    payload = json.dumps(
        {
            "family": CANDIDATE_MODEL_FAMILY,
            "base_champion_version": champion_version,
            "added_feature": "league_cards_env_season_to_date",
            "contract": "candidate-eval/v1",
        },
        sort_keys=True,
    )
    return "cand:" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def _cards_total(m) -> Optional[float]:
    """Match total cards using the SAME concept as the champion target/settlement
    (cards_num if present, else yellow+red), read leak-free from a prior match."""
    a = m.get("team_a_cards_num")
    b = m.get("team_b_cards_num")
    if a in (None, -1) or b in (None, -1):
        ya, yb = m.get("team_a_yellow_cards"), m.get("team_b_yellow_cards")
        if ya in (None, -1) or yb in (None, -1):
            return None
        a = (ya or 0) + (m.get("team_a_red_cards") or 0)
        b = (yb or 0) + (m.get("team_b_red_cards") or 0)
    return float(a) + float(b)


def build_league_card_env(matches, mix) -> dict:
    """Index: for each season-instance (competition_id), the chronologically
    sorted list of (date_unix, total_cards) so a strictly-prior mean can be taken.

    Leak-free: only completed matches from the corpus, never the fixture itself
    (the caller filters by date < kickoff)."""
    idx: dict = {}
    for m in matches:
        comp = m.get("competition_id")
        d = m.get("date_unix")
        tc = _cards_total(m)
        if comp is None or d is None or tc is None:
            continue
        idx.setdefault(comp, []).append((d, tc))
    for comp in idx:
        idx[comp].sort(key=lambda t: t[0])
    return idx


def league_card_env_prior(env_idx: dict, comp, before: float) -> Optional[float]:
    """Season-to-date mean total cards for ``comp`` strictly before ``before``.

    Fail-closed: returns None if the league has < 3 prior completed matches this
    season-instance (no fabricated precision), which the imputer then fills with
    the training median just like any other sparse feature.
    """
    rows = env_idx.get(comp)
    if not rows:
        return None
    prior = [tc for (d, tc) in rows if d < before]
    if len(prior) < 3:
        return None
    return float(np.mean(prior))


# ── candidate fit / predict (champion features + one league prior) ──────────
def _augmented_features(hist, m, mix, env_idx):
    """Champion cards features + the league card-environment prior appended."""
    base = mix.match_features(hist, m, "cards")
    comp = m.get("competition_id")
    prior = league_card_env_prior(env_idx, comp, m.get("date_unix"))
    return list(base) + [prior]


def _augmented_names(mix):
    return list(mix.feat_names("cards")) + ["league_cards_env_s2d"]


def fit_candidate(ms, hist, line, C, l1r, env_idx, mix):
    """Fit the candidate cards classifier (champion pool + league prior)."""
    from sklearn.linear_model import LogisticRegression

    names = _augmented_names(mix)
    X, y = [], []
    for m in ms:
        o = mix.outcome(m, "cards", line)
        if o is None:
            continue
        X.append(_augmented_features(hist, m, mix, env_idx))
        y.append(o)
    if len(y) < 400:
        return None
    cov = np.mean([[v is not None for v in r] for r in X], axis=0)
    keep = [i for i in range(len(names)) if cov[i] >= 0.6]
    if len(keep) < 3:
        return None
    M = np.array([[(np.nan if r[i] is None else r[i]) for i in keep] for r in X], float)
    med = np.nanmedian(M, 0)
    med = np.where(np.isnan(med), 0, med)
    idx = np.where(np.isnan(M))
    M[idx] = np.take(med, idx[1])
    mu, sd = M.mean(0), M.std(0)
    sd[sd == 0] = 1
    Ms = (M - mu) / sd
    clf = LogisticRegression(penalty="elasticnet", solver="saga", C=C, l1_ratio=l1r, max_iter=4000)
    clf.fit(Ms, np.array(y))
    return {"clf": clf, "keep": keep, "names_all": names, "med": med, "mu": mu, "sd": sd}


def predict_candidate(model, hist, m, mix, env_idx) -> Optional[float]:
    if model is None:
        return None
    raw = _augmented_features(hist, m, mix, env_idx)
    keep = model["keep"]
    vec = np.array([raw[i] for i in keep], float)
    nanidx = np.where(np.isnan(vec))
    vec[nanidx] = np.take(model["med"], nanidx[1] if vec.ndim > 1 else nanidx[0])
    vec = (vec - model["mu"]) / model["sd"]
    if np.all(np.isnan(vec)):
        return None
    p = float(np.clip(model["clf"].predict_proba(vec.reshape(1, -1))[0, 1], 0.01, 0.99))
    return p
