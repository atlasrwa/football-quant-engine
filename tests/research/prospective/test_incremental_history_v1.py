from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.research.prospective.capture import ProspectiveApiClient
from src.research.prospective.incremental_history import (
    build_incremental_history_snapshot,
    load_incremental_history_snapshot,
)


HEADERS={
    "X-RateLimit-Limit":"120",
    "X-RateLimit-Remaining":"119",
    "X-RateLimit-Reset":"9999999999",
    "X-Monthly-Quota-Limit":"100000",
    "X-Monthly-Quota-Remaining":"99999",
    "X-Monthly-Quota-Reset":"9999999999",
}


def _fixture(mid="mt_900000001"):
    return {
        "id":mid,
        "utc_date":"2026-09-20T15:00:00.000Z",
        "status":"finished",
        "competition_id":"comp_3039",
        "season_id":"sn_8406098",
        "score":{
            "home":2,"away":1,"final_score":None,
            "regulation":{"home":2,"away":1},
            "after_extra_time":None,"penalty_shootout":None,
            "went_to_extra_time":False,"went_to_penalties":False,
            "winner":"home",
        },
        "home_team":{"id":"tm_9001","name":"Home"},
        "away_team":{"id":"tm_9002","name":"Away"},
    }


def _stats(mid="mt_900000001"):
    return {
        "data":{
            "match_id":mid,
            "overview":{
                "corner_kicks":{"all":{"home":6,"away":4},"first_half":None,"second_half":None},
                "total_shots":{"all":{"home":12,"away":9},"first_half":None,"second_half":None},
                "shots_on_target":{"all":{"home":5,"away":3},"first_half":None,"second_half":None},
                "expected_goals":{"all":{"home":1.7,"away":0.9},"first_half":None,"second_half":None},
                "ball_possession":{"all":{"home":55,"away":45},"first_half":None,"second_half":None},
                "yellow_cards":{"all":{"home":2,"away":3},"first_half":None,"second_half":None},
                "red_cards":{"all":None,"first_half":None,"second_half":None},
                "fouls":{"all":{"home":10,"away":12},"first_half":None,"second_half":None},
            }
        }
    }


def _client(monkeypatch, *, missing_stats=False, two_pages=False):
    monkeypatch.setenv("THESTATSAPI_API_KEY","dummy-test-key")
    calls=[]
    def transport(url, headers, params):
        assert headers.get("Authorization")=="Bearer dummy-test-key"
        calls.append((url,dict(params)))
        if url.endswith("/stats"):
            return (404,None,HEADERS) if missing_stats else (200,_stats(),HEADERS)
        comp=params["competition_id"]
        page=int(params["page"])
        if comp=="comp_3039":
            if two_pages:
                if page==1:
                    return 200,{"data":[],"meta":{"total_pages":2}},HEADERS
                return 200,{"data":[_fixture()],"meta":{"total_pages":2}},HEADERS
            return 200,{"data":[_fixture()],"meta":{"total_pages":1}},HEADERS
        return 200,{"data":[],"meta":{"total_pages":1}},HEADERS
    return ProspectiveApiClient(transport=transport),calls


def _clock():
    return datetime(2026,10,5,12,0,0,tzinfo=timezone.utc).timestamp()


def test_complete_six_comp_snapshot_normalizes_and_reloads(tmp_path, monkeypatch):
    client,calls=_client(monkeypatch,two_pages=True)
    manifest,matches=build_incremental_history_snapshot(
        repo_root=Path(__file__).resolve().parents[3],
        output_root=tmp_path,
        client=client,
        now_fn=_clock,
    )
    assert manifest["prediction_eligible"] is True
    assert manifest["incremental_fixture_count"]==1
    assert manifest["stats_success_count"]==1
    assert manifest["stats_missing_fixture_ids"]==[]
    assert manifest["normalized_match_count"]==1
    assert len(matches)==1
    m=matches[0]
    assert m.source_match_ref=="mt_900000001"
    assert m.home_goals==2 and m.away_goals==1
    assert m.corners_home==6 and m.corners_away==4
    assert set(manifest["competition_universe"])=={
        "comp_0256","comp_0976","comp_3039","comp_8321","comp_8814","comp_9777"
    }
    # 7 discovery page calls (one extra page for EPL) + one stats request.
    assert manifest["request_count"]==8
    root=tmp_path/manifest["snapshot_id"]
    loaded_manifest,loaded=load_incremental_history_snapshot(root)
    assert loaded_manifest["snapshot_hash"]==manifest["snapshot_hash"]
    assert loaded==matches


def test_missing_stats_makes_snapshot_ineligible(tmp_path, monkeypatch):
    client,_=_client(monkeypatch,missing_stats=True)
    manifest,matches=build_incremental_history_snapshot(
        repo_root=Path(__file__).resolve().parents[3],
        output_root=tmp_path,
        client=client,
        now_fn=_clock,
    )
    assert manifest["prediction_eligible"] is False
    assert manifest["stats_missing_fixture_ids"]==["mt_900000001"]
    assert matches==()
    with pytest.raises(ValueError,match="not prediction-eligible"):
        load_incremental_history_snapshot(tmp_path/manifest["snapshot_id"])


def test_insufficient_quota_aborts_before_stats(tmp_path, monkeypatch):
    monkeypatch.setenv("THESTATSAPI_API_KEY","dummy-test-key")
    calls=[]
    low=dict(HEADERS)
    low["X-Monthly-Quota-Remaining"]="50"
    def transport(url, headers, params):
        calls.append((url,dict(params)))
        if url.endswith("/stats"):
            raise AssertionError("stats call must not occur after failed quota gate")
        comp=params["competition_id"]
        rows=[_fixture()] if comp=="comp_3039" else []
        return 200,{"data":rows,"meta":{"total_pages":1}},low
    client=ProspectiveApiClient(transport=transport)
    with pytest.raises(RuntimeError,match="insufficient monthly quota"):
        build_incremental_history_snapshot(
            repo_root=Path(__file__).resolve().parents[3],
            output_root=tmp_path,
            client=client,
            now_fn=_clock,
            quota_reserve=100,
        )
    assert len(calls)==6


def test_raw_payload_tamper_is_detected(tmp_path, monkeypatch):
    client,_=_client(monkeypatch)
    manifest,_=build_incremental_history_snapshot(
        repo_root=Path(__file__).resolve().parents[3],
        output_root=tmp_path,
        client=client,
        now_fn=_clock,
    )
    root=tmp_path/manifest["snapshot_id"]
    stats=root/"raw/stats_mt_900000001.json"
    stats.write_text("{}\n")
    with pytest.raises(ValueError,match="raw payload hash mismatch"):
        load_incremental_history_snapshot(root)


def test_fixture_at_or_before_base_boundary_not_reingested(tmp_path, monkeypatch):
    monkeypatch.setenv("THESTATSAPI_API_KEY","dummy-test-key")
    old=_fixture()
    old["utc_date"]="2026-09-14T19:00:00.000Z"  # exact EPL audited boundary
    def transport(url, headers, params):
        if url.endswith("/stats"):
            raise AssertionError("base-boundary fixture must not be refetched")
        rows=[old] if params["competition_id"]=="comp_3039" else []
        return 200,{"data":rows,"meta":{"total_pages":1}},HEADERS
    manifest,matches=build_incremental_history_snapshot(
        repo_root=Path(__file__).resolve().parents[3],
        output_root=tmp_path,
        client=ProspectiveApiClient(transport=transport),
        now_fn=_clock,
    )
    assert manifest["prediction_eligible"] is True
    assert manifest["incremental_fixture_count"]==0
    assert matches==()
