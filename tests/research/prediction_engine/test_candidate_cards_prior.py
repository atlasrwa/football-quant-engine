"""Tests for the candidate cards + league card-environment prior (eval-only).

Covers: leak-free league prior (strictly-prior, fail-closed), cards concept
identity with champion/settlement, candidate model versioning (cannot collide
with or overwrite champion), probability validity, and evaluation-only isolation
(the candidate module writes no evidence and defines no publication path).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/home/ubuntu/scripts")
import pilotC_stat_mixer as mix  # noqa: E402

from src.research.prediction_engine.eval import candidate_cards_league_prior as cand


def _match(comp, d, cards_num_a=2, cards_num_b=2):
    return {"competition_id": comp, "date_unix": d,
            "team_a_cards_num": cards_num_a, "team_b_cards_num": cards_num_b}


# ── league card-env prior is strictly prior + fail-closed ───────────────────
def test_league_prior_uses_only_matches_before_cutoff():
    matches = [_match("L1", 100, 2, 2), _match("L1", 200, 3, 3),
               _match("L1", 300, 4, 4), _match("L1", 400, 5, 5)]
    env = cand.build_league_card_env(matches, mix)
    # before=350 -> only the first 3 (100,200,300) count: totals 4,6,8 -> mean 6.0
    assert cand.league_card_env_prior(env, "L1", 350) == pytest.approx(6.0)
    # before=150 -> only 1 prior match (<3) -> fail closed None
    assert cand.league_card_env_prior(env, "L1", 150) is None


def test_league_prior_fails_closed_under_min_matches():
    matches = [_match("L2", 100), _match("L2", 200)]
    env = cand.build_league_card_env(matches, mix)
    assert cand.league_card_env_prior(env, "L2", 300) is None  # only 2 prior


def test_league_prior_none_for_unknown_competition():
    env = cand.build_league_card_env([_match("L1", 100)], mix)
    assert cand.league_card_env_prior(env, "UNKNOWN", 999) is None


def test_cards_total_uses_champion_concept_with_fallback():
    # cards_num present -> used directly
    assert cand._cards_total({"team_a_cards_num": 3, "team_b_cards_num": 2}) == 5.0
    # cards_num missing -> yellow+red fallback (same as champion target/settlement)
    m = {"team_a_cards_num": None, "team_b_cards_num": None,
         "team_a_yellow_cards": 2, "team_b_yellow_cards": 1,
         "team_a_red_cards": 1, "team_b_red_cards": 0}
    assert cand._cards_total(m) == 4.0  # (2+1) + (1+0)
    # entirely missing -> None (never fabricate zero)
    assert cand._cards_total({"team_a_cards_num": None, "team_b_cards_num": None}) is None


# ── model versioning: candidate never collides with champion ────────────────
def test_candidate_version_is_distinct_and_namespaced():
    v = cand.candidate_model_version("someChampionHashABC")
    assert v.startswith("cand:")
    assert "someChampionHashABC" != v
    # deterministic
    assert v == cand.candidate_model_version("someChampionHashABC")
    # different champion base -> different candidate version
    assert v != cand.candidate_model_version("otherChampion")


# ── candidate augments champion features by exactly one ─────────────────────
def test_candidate_adds_exactly_one_feature():
    champ_names = mix.feat_names("cards")
    cand_names = cand._augmented_names(mix)
    assert len(cand_names) == len(champ_names) + 1
    assert cand_names[-1] == "league_cards_env_s2d"
    assert cand_names[:-1] == list(champ_names)


# ── evaluation-only isolation ───────────────────────────────────────────────
def test_candidate_module_has_no_publication_or_commitment_path():
    src = Path("/home/ubuntu/src/research/prediction_engine/eval/candidate_cards_league_prior.py").read_text()
    for banned in ("append_commitment", "publish", "VALIDATED_SIGNAL",
                   "BroadcastLedger", "shadow_residuals", "telegram", "SIGNAL"):
        assert banned not in src, f"candidate must not reference {banned!r}"


def test_candidate_does_not_import_or_modify_champion_writer():
    src = Path("/home/ubuntu/src/research/prediction_engine/eval/candidate_cards_league_prior.py").read_text()
    # It may read mix (feat_names/outcome/match_features) but must not write the
    # champion artifact or corpus.
    assert "pilotC_stat_mixer.json" not in src
    assert "load_corpus" not in src  # candidate operates on injected matches only
