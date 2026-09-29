import hashlib
from pathlib import Path
from src.research.v31_pilot.config import load_scope
from src.research.v31_pilot.freeze import freeze_hash, load_freeze

def test_v31_freeze_and_colombia_scope():
    assert len(freeze_hash())==64
    scope=load_scope(); assert len(scope)>=25
    row=next(r for r in scope if r['competition_id']=='comp_720692')
    assert 'Colombia' in row['name']

def test_v3_corners_protected_byte_identical():
    f=load_freeze(); root=Path(__file__).resolve().parents[3]
    observed=hashlib.sha256((root/'src/research/v3_pilot/model.py').read_bytes()).hexdigest()
    assert observed==f['corners']['protected_v3_model_sha256']

def test_missing_provider_stats_policy_is_abstain_not_zero_fill():
    from src.research.v31_pilot.freeze import load_freeze
    assert load_freeze()['integrity']['missing_data_action']=='ABSTAIN'
