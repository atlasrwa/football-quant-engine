from pathlib import Path
from research.target_aware_market_panel import v1_4_make_binding as B

def test_frozen_inputs_pinned():
    assert B.EXPECTED[B.FEATURE_FREEZE]=="c366abea89c98622f7e923c7206a6a719f2a68972b3a880d425a54d12786521a"
    assert B.EXPECTED[B.P0_SOURCE]=="8c61de90e4de128ee070b9df84525b52016e543cd89c084cfc021534af251d08"
    assert B.EXPECTED[B.V124_EVAL]=="df9882e64ac9a9c265ae8c74d9ac94e96d0598a72e62dd5c91f188ebffcdda00"
    assert B.EXPECTED[B.V13_EVAL]=="59b3925a1dfae8d87095de203fe9cb42d5d15b1508ba293a628c3c2368e43a97"

def test_binding_generator_no_network():
    src=Path("research/target_aware_market_panel/v1_4_make_binding.py").read_text()
    for forbidden in ("requests.","httpx","boto3","THESTATS_API_KEY","FOOTYSTATS_API_KEY"):
        assert forbidden not in src
