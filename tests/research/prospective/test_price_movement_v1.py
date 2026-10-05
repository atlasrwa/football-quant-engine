from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import src.research.prospective.price_movement as pm
from src.research.dataset.manifest import sha256_json
from src.research.prospective.capture import CaptureRecord, ProspectiveApiClient
from src.research.prospective.storage import CaptureStore


def _iso(ts):
    return datetime.fromtimestamp(float(ts),timezone.utc).isoformat()


def _identity(fid,event):
    return {
        "fixture_id":fid,
        "event_time":float(event),
        "competition_ref":"comp_3039",
        "season_ref":"sn_1",
        "home_team_ref":"tm_h",
        "away_team_ref":"tm_a",
        "home_team_name":"Home",
        "away_team_name":"Away",
    }


def _bound(monkeypatch,movement_root,event=200000.0):
    cohort={"fixtures":[{"fixture_id":"mt_a","event_time":float(event)}],"cohort_hash":pm.COHORT_HASH}
    identities={"mt_a":_identity("mt_a",event)}
    protocol={"artifacts":{"root":str(movement_root)}}
    monkeypatch.setattr(pm,"_load_bound_evidence",lambda repo:(protocol,cohort,identities))
    return cohort,identities


def _prediction(cohort_root):
    p=cohort_root/"predictions/mt_a.json"
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('{"frozen":true}\n')
    return p


def _client(monkeypatch,events,identity,quotes=None,schedule_shift=0,status="scheduled"):
    monkeypatch.setenv("THESTATS_API_KEY","dummy")
    quotes=quotes or {"Pinnacle":(1.91,1.97)}
    def transport(url,headers,params):
        if url.endswith("/odds"):
            events.append("odds")
            books=[]
            for book,(over,under) in quotes.items():
                books.append({"bookmaker":book,"markets":{
                    "total_goals":{"2.5":{"over":{"last_seen":str(over)},"under":{"last_seen":str(under)}}},
                    "match_corners":{"9.5":{"over":{"last_seen":"2.00"},"under":{"last_seen":"2.00"}}},
                }})
            return 200,{"data":{"match_id":"mt_a","bookmakers":books}},{}
        events.append("detail")
        return 200,{"data":{"id":"mt_a","utc_date":_iso(identity["event_time"]+schedule_shift),"status":status}},{}
    return ProspectiveApiClient(transport=transport)


def _entry_record(cohort_root,obs,book="pinnacle",over=2.0,under=2.0,raw="entry"):
    store=CaptureStore(cohort_root/"market/captures.jsonl.gz")
    cutoff=200000.0-pm.HORIZON
    rows=[
        CaptureRecord("thestatsapi","mt_a","mt_a",f"odds:total_goals:over:2.5:{book}",over,obs,obs,raw,
                      event_time=200000.0,forecast_cutoff=cutoff,vintage="T6"),
        CaptureRecord("thestatsapi","mt_a","mt_a",f"odds:total_goals:under:2.5:{book}",under,obs,obs,raw,
                      event_time=200000.0,forecast_cutoff=cutoff,vintage="T6"),
    ]
    store.extend(rows)


def test_no_scan_without_frozen_prediction(monkeypatch,tmp_path):
    cohort_root=tmp_path/"cohort"; movement=cohort_root/"market_movement"
    _,ids=_bound(monkeypatch,movement)
    events=[]
    client=_client(monkeypatch,events,ids["mt_a"])
    cutoff=200000.0-pm.HORIZON
    result=pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                       client=client,now_fn=lambda:cutoff+10)
    assert events==[]
    assert result["captured"]==[]


def test_no_odds_before_t6_even_with_prediction(monkeypatch,tmp_path):
    cohort_root=tmp_path/"cohort"; movement=cohort_root/"market_movement"
    _,ids=_bound(monkeypatch,movement)
    pred=_prediction(cohort_root); before=pred.read_bytes()
    events=[]; client=_client(monkeypatch,events,ids["mt_a"])
    cutoff=200000.0-pm.HORIZON
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:cutoff-1)
    assert events==[]
    assert pred.read_bytes()==before


def test_capture_normalizes_only_goals_and_never_mutates_prediction(monkeypatch,tmp_path):
    cohort_root=tmp_path/"cohort"; movement=cohort_root/"market_movement"
    _,ids=_bound(monkeypatch,movement)
    pred=_prediction(cohort_root); before=pred.read_bytes()
    events=[]; client=_client(monkeypatch,events,ids["mt_a"],{"Pinnacle":(1.9,2.0)})
    cutoff=200000.0-pm.HORIZON
    result=pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                       client=client,now_fn=lambda:cutoff+60)
    assert events==["detail","odds"]
    rows=list(CaptureStore(movement/"captures.jsonl.gz").read_all())
    assert len(rows)==2
    assert all(r.concept.startswith("odds:total_goals:") for r in rows)
    assert not any("corner" in r.concept for r in rows)
    raw=json.loads(next((movement/"raw/mt_a").glob("*.json")).read_text())
    assert "match_corners" in raw["data"]["bookmakers"][0]["markets"]
    assert pred.read_bytes()==before
    assert result["captured"][0]["status"]=="CAPTURED"


def test_schedule_change_abstains_close_and_stops_further_fetch(monkeypatch,tmp_path):
    cohort_root=tmp_path/"cohort"; movement=cohort_root/"market_movement"
    _,ids=_bound(monkeypatch,movement); _prediction(cohort_root)
    events=[]; client=_client(monkeypatch,events,ids["mt_a"],schedule_shift=60)
    cutoff=200000.0-pm.HORIZON
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:cutoff+60)
    assert events==["detail"]
    assert (movement/"status/mt_a/SCHEDULE_ABSTAIN.json").exists()
    events.clear()
    result=pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                       client=client,now_fn=lambda:200001.0)
    assert events==[]
    assert result["finalized"][0]["status"]=="ABSTAIN"
    assert result["finalized"][0]["reason"]=="SCHEDULE_CHANGED"


def test_post_kickoff_tick_makes_no_provider_call_and_finalizes_latest_verified_close(monkeypatch,tmp_path):
    cohort_root=tmp_path/"cohort"; movement=cohort_root/"market_movement"
    _,ids=_bound(monkeypatch,movement); _prediction(cohort_root)
    cutoff=200000.0-pm.HORIZON
    _entry_record(cohort_root,cutoff,over=2.0,under=2.0)
    events=[]
    now=[199500.0]
    client=_client(monkeypatch,events,ids["mt_a"],{"Pinnacle":(1.8,2.1)})
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:now[0])
    assert events==["detail","odds"]
    events.clear(); now[0]=200001.0
    result=pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                       client=client,now_fn=lambda:now[0])
    assert events==[]
    close=result["finalized"][0]
    assert close["status"]=="OK"
    assert close["bookmaker"]=="pinnacle"
    assert close["observed_at"]==199500.0
    movement_art=json.loads((movement/"movement/mt_a.json").read_text())
    assert movement_art["status"]=="OK"
    assert movement_art["movement"]["delta_over_decimal_odds"]==pytest.approx(-0.2)


def test_close_hierarchy_beats_more_attractive_lower_book_price(monkeypatch,tmp_path):
    cohort_root=tmp_path/"cohort"; movement=cohort_root/"market_movement"
    _,ids=_bound(monkeypatch,movement); _prediction(cohort_root)
    cutoff=200000.0-pm.HORIZON
    _entry_record(cohort_root,cutoff)
    events=[]; now=[199500.0]
    # Bet365 gives a much more attractive OVER price, but Pinnacle must still win hierarchy.
    client=_client(monkeypatch,events,ids["mt_a"],{"Pinnacle":(1.70,2.20),"Bet365":(4.00,1.25)})
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:now[0])
    now[0]=200001.0
    result=pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                       client=client,now_fn=lambda:now[0])
    close=result["finalized"][0]
    assert close["status"]=="OK"
    assert close["bookmaker"]=="pinnacle"
    assert close["over_odds"]==pytest.approx(1.70)


def test_latest_valid_bundle_wins_within_bookmaker(monkeypatch,tmp_path):
    cohort_root=tmp_path/"cohort"; movement=cohort_root/"market_movement"
    _,ids=_bound(monkeypatch,movement); _prediction(cohort_root)
    cutoff=200000.0-pm.HORIZON; _entry_record(cohort_root,cutoff)
    events=[]; now=[199300.0]
    prices=[{"Pinnacle":(3.50,1.30)},{"Pinnacle":(1.75,2.15)}]
    calls={"n":0}
    monkeypatch.setenv("THESTATS_API_KEY","dummy")
    def transport(url,headers,params):
        if url.endswith("/odds"):
            i=min(calls["n"],1); calls["n"]+=1
            over,under=prices[i]["Pinnacle"]
            return 200,{"data":{"bookmakers":[{"bookmaker":"Pinnacle","markets":{
                "total_goals":{"2.5":{"over":{"last_seen":str(over)},"under":{"last_seen":str(under)}}}}}]}},{}
        return 200,{"data":{"id":"mt_a","utc_date":_iso(200000.0),"status":"scheduled"}},{}
    client=ProspectiveApiClient(transport=transport)
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:now[0])
    now[0]=199700.0
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:now[0])
    now[0]=200001.0
    close=pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                      client=client,now_fn=lambda:now[0])["finalized"][0]
    assert close["over_odds"]==pytest.approx(1.75)
    assert close["observed_at"]==199700.0


def test_close_abstains_when_latest_available_quote_is_older_than_600_seconds(monkeypatch,tmp_path):
    cohort_root=tmp_path/"cohort"; movement=cohort_root/"market_movement"
    _,ids=_bound(monkeypatch,movement); _prediction(cohort_root)
    events=[]; client=_client(monkeypatch,events,ids["mt_a"])
    now=[199000.0]
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:now[0])
    now[0]=200001.0; events.clear()
    close=pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                      client=client,now_fn=lambda:now[0])["finalized"][0]
    assert events==[]
    assert close["status"]=="ABSTAIN"
    assert close["reason"]=="CLOSE_MARKET_MISSING"


def test_close_artifact_is_immutable(monkeypatch,tmp_path):
    cohort_root=tmp_path/"cohort"; movement=cohort_root/"market_movement"
    _,ids=_bound(monkeypatch,movement); _prediction(cohort_root)
    cutoff=200000.0-pm.HORIZON; _entry_record(cohort_root,cutoff)
    events=[]; now=[199500.0]; client=_client(monkeypatch,events,ids["mt_a"])
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:now[0])
    now[0]=200001.0
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:now[0])
    p=movement/"close/mt_a.json"; before=p.read_bytes()
    pm.run_price_movement_cycle(repo_root=tmp_path,cohort_root=cohort_root,movement_root=movement,
                                client=client,now_fn=lambda:now[0]+300)
    assert p.read_bytes()==before
