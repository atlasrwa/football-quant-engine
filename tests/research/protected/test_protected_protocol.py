from pathlib import Path
from src.research.protected.protocol import PROTECTED_EVALUATION_CONTRACT_HASH, load_contract


def test_contract_is_hash_bound_and_two_phase():
    d=load_contract(Path('.'))
    assert d['contract_hash']==PROTECTED_EVALUATION_CONTRACT_HASH
    assert d['prediction_phase']['must_complete_and_commit_before_scoring'] is True
    assert d['prediction_phase']['prediction_artifact_outcome_fields_forbidden'] is True
    assert d['prediction_phase']['odds_or_market_inputs_forbidden'] is True
    assert d['scoring_phase']['may_begin_only_after_prediction_artifact_commit'] is True


def test_same_kickoff_and_future_leakage_are_forbidden():
    d=load_contract(Path('.'))['prediction_phase']['dynamic_walk_forward']
    assert d['current_fixture_outcome_for_prediction']=='forbidden'
    assert d['future_protected_outcome_for_prediction']=='forbidden'
    assert 'same pre-kickoff state' in d['same_kickoff_rule']


def test_market_scope_cannot_expand_after_outcomes():
    d=load_contract(Path('.'))['scoring_phase']['market_relative_scorecard']
    assert 'frozen Layer5 matched-market manifest' in d['universe']
    assert 'no source/horizon expansion after outcomes' in d['universe']


def test_scoring_defect_requires_abort_not_patch():
    rules=load_contract(Path('.'))['abort_rules']
    assert any('abort V1 and create V2' in x for x in rules)
