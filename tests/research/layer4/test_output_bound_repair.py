import json
from pathlib import Path
from src.research.layer4.output_bound_repair import _clip

def test_output_bound_clip_is_strictly_inside_unit_interval():
    eps=1e-6
    assert _clip(1.0,eps)==1-eps
    assert _clip(0.0,eps)==eps
    assert _clip(0.42,eps)==0.42

def test_v3_protocol_forbids_reselection():
    p=json.loads((Path(__file__).resolve().parents[3]/"evidence/layer4/QFE_LAYER4_OUTPUT_BOUND_V3_PROTOCOL.json").read_text())
    assert p["repair"]["selection_research_reopened"] is False
    assert p["immutable_from_v2"]["selected_methods_change"] is False
    assert p["output_probability_clip"]==1e-6
