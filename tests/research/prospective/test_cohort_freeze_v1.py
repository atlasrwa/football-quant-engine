from __future__ import annotations

from datetime import datetime,timezone
from pathlib import Path

import pytest

from src.research.prospective.capture import ProspectiveApiClient
from src.research.prospective.cohort_freeze import build_future_cohort,load_frozen_cohort


HEADERS={
    "X-RateLimit-Limit":"120","X-RateLimit-Remaining":"119","X-RateLimit-Reset":"9999999999",
    "X-Monthly-Quota-Limit":"100000","X-Monthly-Quota-Remaining":"99999","X-Monthly-Quota-Reset":"9999999999",
}


def _fx(mid,utc,comp,season,home="Home",away="Away"):
    return {
        "id":mid,"utc_date":utc,"status":"scheduled",
        "competition_id":comp,"season_id":season,
        "home_team":{"id":"tm_"+mid[-3:]+"1","name":home},
        "away_team":{"id":"tm_"+mid[-3:]+"2","name":away},
    }


def _clock_at(text):
    ts=datetime.fromisoformat(text).timestamp()
    return lambda: ts


def _client(monkeypatch,rows_by_comp):
    monkeypatch.setenv("THESTATSAPI_API_KEY","dummy")
    calls=[]
    def transport(url,headers,params):
        calls.append((url,dict(params)))
        comp=params["competition_id"]
        rows=rows_by_comp.get(comp,[])
        return 200,{"data":rows,"meta":{"total_pages":1}},HEADERS
    return ProspectiveApiClient(transport=transport),calls


def test_all_window_fixtures_included_without_subsampling(tmp_path,monkeypatch):
    rows={
        "comp_3039":[
            _fx("mt_900000003","2026-10-10T15:00:00.000Z","comp_3039","sn_8406098"),
            _fx("mt_900000001","2026-10-08T20:00:00.000Z","comp_3039","sn_8406098"),
        ],
        "comp_0976":[
            _fx("mt_900000002","2026-10-08T18:00:00.000Z","comp_0976","sn_1368511"),
        ],
    }
    client,calls=_client(monkeypatch,rows)
    cohort,disc,ids=build_future_cohort(
        repo_root=Path(__file__).resolve().parents[3],output_root=tmp_path,client=client,
        now_fn=_clock_at("2026-10-05T13:00:00+00:00"),
    )
    assert len(calls)==6
    assert disc["cohort_size"]==3
    assert [x.fixture_id for x in ids]==["mt_900000002","mt_900000001","mt_900000003"]
    assert cohort["fixtures"]==[
        {"fixture_id":"mt_900000002","event_time":ids[0].event_time},
        {"fixture_id":"mt_900000001","event_time":ids[1].event_time},
        {"fixture_id":"mt_900000003","event_time":ids[2].event_time},
    ]
    assert disc["market_data_used"] is False
    assert disc["model_predictions_used"] is False
    assert disc["outcomes_used"] is False
    loaded=load_frozen_cohort(tmp_path/disc["discovery_id"])
    assert loaded[0]==cohort and loaded[1]==disc and loaded[2]==ids


def test_outside_window_is_excluded_only_by_time_rule(tmp_path,monkeypatch):
    rows={"comp_3039":[
        _fx("mt_900000010","2026-10-06T23:59:59.000Z","comp_3039","sn_8406098"),
        _fx("mt_900000011","2026-10-07T00:00:00.000Z","comp_3039","sn_8406098"),
        _fx("mt_900000012","2026-10-20T23:59:59.000Z","comp_3039","sn_8406098"),
        _fx("mt_900000013","2026-10-21T00:00:00.000Z","comp_3039","sn_8406098"),
    ]}
    c,_,ids=build_future_cohort(
        repo_root=Path(__file__).resolve().parents[3],output_root=tmp_path,
        client=_client(monkeypatch,rows)[0],
        now_fn=_clock_at("2026-10-05T13:00:00+00:00"),
    )
    assert [x.fixture_id for x in ids]==["mt_900000011","mt_900000012"]


def test_inside_t6_aborts_whole_cohort(tmp_path,monkeypatch):
    rows={"comp_3039":[
        _fx("mt_900000020","2026-10-07T04:00:00.000Z","comp_3039","sn_8406098")
    ]}
    with pytest.raises(RuntimeError,match="inside T-6h"):
        build_future_cohort(
            repo_root=Path(__file__).resolve().parents[3],output_root=tmp_path,
            client=_client(monkeypatch,rows)[0],
            now_fn=_clock_at("2026-10-07T00:00:01+00:00"),
        )


def test_empty_window_fails_closed(tmp_path,monkeypatch):
    with pytest.raises(RuntimeError,match="contains no scheduled fixtures"):
        build_future_cohort(
            repo_root=Path(__file__).resolve().parents[3],output_root=tmp_path,
            client=_client(monkeypatch,{})[0],
            now_fn=_clock_at("2026-10-05T13:00:00+00:00"),
        )


def test_raw_schedule_tamper_is_detected(tmp_path,monkeypatch):
    rows={"comp_3039":[_fx("mt_900000030","2026-10-10T15:00:00.000Z","comp_3039","sn_8406098")]}
    _,disc,_=build_future_cohort(
        repo_root=Path(__file__).resolve().parents[3],output_root=tmp_path,
        client=_client(monkeypatch,rows)[0],
        now_fn=_clock_at("2026-10-05T13:00:00+00:00"),
    )
    root=tmp_path/disc["discovery_id"]
    rec=next(x for x in disc["raw_records"] if x["competition_id"]=="comp_3039")
    (root/rec["relative_path"]).write_text("{}\n")
    with pytest.raises(ValueError,match="raw scheduled-discovery payload hash mismatch"):
        load_frozen_cohort(root)


def test_team_identity_is_preserved_separately_not_in_membership(tmp_path,monkeypatch):
    rows={"comp_3039":[_fx("mt_900000040","2026-10-10T15:00:00.000Z","comp_3039","sn_8406098","Alpha","Beta")]}
    cohort,disc,ids=build_future_cohort(
        repo_root=Path(__file__).resolve().parents[3],output_root=tmp_path,
        client=_client(monkeypatch,rows)[0],
        now_fn=_clock_at("2026-10-05T13:00:00+00:00"),
    )
    assert set(cohort["fixtures"][0])=={"fixture_id","event_time"}
    assert ids[0].home_team_name=="Alpha" and ids[0].away_team_name=="Beta"
    assert disc["fixture_identity_hash"]
