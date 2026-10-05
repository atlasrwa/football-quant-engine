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

def test_v3_rebuild_reuses_selection_and_bounds_all_outputs():
    from src.research.layer4.output_bound_repair import build_v3
    root=Path(__file__).resolve().parents[3]
    result,rows,freeze=build_v3(root)
    assert result["selection_reused_from_v2"] is True
    assert result["selected_methods"] == {
        "GOALS_TOTAL":"ISOTONIC_GLOBAL",
        "CORNERS_SIDE":"PLATT_GLOBAL",
        "CORNERS_TOTAL":"PLATT_ROLE_COMP_RIDGE_L1",
    }
    eps=result["output_probability_clip"]
    assert eps == 1e-6
    assert rows
    assert all(eps <= float(r["p_model"]) <= 1-eps for r in rows)
    assert all(float(r["p_model"]) not in {0.0,1.0} for r in rows)
    assert freeze["selection_reused_from_v2"] is True
    assert freeze["output_probability_clip"] == {"lower":eps,"upper":1-eps}


def test_v3_writer_refuses_mutation(tmp_path):
    from src.research.layer4.output_bound_repair import write_v3
    e=tmp_path/"evidence/layer4"; e.mkdir(parents=True)
    # Minimal valid serialization payload for writer immutability behavior.
    result={"x":1}; rows=[{"a":1}]; freeze={"y":2}
    write_v3(tmp_path,result,rows,freeze)
    write_v3(tmp_path,result,rows,freeze)
    (e/"QFE_LAYER4_MODEL_FREEZE_V3_BOUND.json").write_text("{}\n")
    import pytest
    with pytest.raises(FileExistsError):
        write_v3(tmp_path,result,rows,freeze)
