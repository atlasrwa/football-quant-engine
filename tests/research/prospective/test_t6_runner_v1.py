from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import src.research.prospective.t6_runner as runner
from src.research.prospective.capture import ProspectiveApiClient
from src.research.prospective.storage import CaptureStore


def _iso(ts):
    return datetime.fromtimestamp(float(ts),timezone.utc).isoformat()


def _identity(fid,event):
    return {
        "fixture_id":fid,
        "event_time":float(event),
        "competition_ref":"comp_3039",
        "season_ref":"sn_8406098",
        "home_team_ref":"tm_home_"+fid,
        "away_team_ref":"tm_away_"+fid,
        "home_team_name":"Home "+fid,
        "away_team_name":"Away "+fid,
    }


def _bound(monkeypatch,root,fixtures):
    cohort={
        "version":"qfe-prospective-cohort-v1",
        "status":"FROZEN_OUTCOME_BLIND",
        "frozen_at":"2026-10-05T00:00:00+00:00",
        "fixtures":[{"fixture_id":fid,"event_time":float(event)} for fid,event in fixtures],
        "cohort_hash":runner.COHORT_HASH,
    }
    identities={fid:_identity(fid,event) for fid,event in fixtures}
    protocol={"operational_artifacts":{"root":str(root)}}
    monkeypatch.setattr(runner,"_load_bound_evidence",lambda repo:(protocol,cohort,identities))
    return cohort,identities


def _client(monkeypatch,events,identities,price_fn=None,schedule_shift=0):
    monkeypatch.setenv("THESTATSAPI_API_KEY","dummy")
    price_fn=price_fn or (lambda n:(1.91,1.97))
    counts={"odds":0}
    def transport(url,headers,params):
        fid=url.split("/matches/")[1].split("/")[0]
        if url.endswith("/odds"):
            events.append("odds:"+fid)
            counts["odds"]+=1
            over,under=price_fn(counts["odds"])
            body={
                "data":{
                    "match_id":fid,
                    "bookmakers":[{
                        "bookmaker":"Pinnacle",
                        "markets":{
                            "total_goals":{"2.5":{
                                "over":{"last_seen":str(over)},
                                "under":{"last_seen":str(under)},
                            }},
                            "match_corners":{"9.5":{
                                "over":{"last_seen":"2.00"},
                                "under":{"last_seen":"2.00"},
                            }},
                        },
                    }],
                },
            }
            return 200,body,{}
        events.append("detail:"+fid)
        ident=identities[fid]
        return 200,{
            "data":{
                "id":fid,
                "utc_date":_iso(ident["event_time"]+schedule_shift),
                "status":"scheduled",
            }
        },{}
    return ProspectiveApiClient(transport=transport)


def _deps(events,completed_at,prediction_value="p1"):
    def base_loader(path):
        events.append("base")
        return ()
    def history_builder(**kwargs):
        events.append("history")
        return ({
            "prediction_eligible":True,
            "completed_at":float(completed_at),
            "snapshot_hash":"snap_1",
            "competition_universe":list(runner.COMPETITION_UNIVERSE),
            "request_count":6,
        },())
    def prediction_builder(**kwargs):
        fid=kwargs["target_match"].source_match_ref
        events.append("predict:"+fid)
        return {"bundle_hash":"bundle-"+fid+"-"+prediction_value,"rows":[]}
    return base_loader,history_builder,prediction_builder


def _run(monkeypatch,tmp_path,fixtures,now,*,schedule_shift=0,history_completed=None,
         history_builder_override=None,price_fn=None,events=None):
    root=tmp_path/"out"
    _,identities=_bound(monkeypatch,root,fixtures)
    events=events if events is not None else []
    client=_client(monkeypatch,events,identities,price_fn=price_fn,schedule_shift=schedule_shift)
    cutoff=min(event-runner.HORIZON for _,event in fixtures)
    completed_at=history_completed if history_completed is not None else now+10
    base_loader,hist,pred=_deps(events,completed_at)
    if history_builder_override is not None:
        hist=history_builder_override
    result=runner.run_t6_cycle(
        repo_root=tmp_path,
        output_root=root,
        history_snapshot_root=tmp_path/"history",
        base_data_dir=tmp_path/"base",
        client=client,
        now_fn=lambda:float(now),
        history_builder=hist,
        base_loader=base_loader,
        prediction_builder=pred,
    )
    return root,result,events


def test_no_api_or_history_calls_when_nothing_due(monkeypatch,tmp_path):
    event=200000.0
    cutoff=event-runner.HORIZON
    events=[]
    root,result,events=_run(monkeypatch,tmp_path,[("mt_a",event)],cutoff-5000,events=events)
    assert events==[]
    assert result["due_fixture_ids"]==[]
    assert result["predicted_fixture_ids"]==[]


def test_history_then_all_predictions_then_any_odds(monkeypatch,tmp_path):
    event=200000.0
    cutoff=event-runner.HORIZON
    events=[]
    root,result,events=_run(
        monkeypatch,tmp_path,[("mt_a",event),("mt_b",event)],cutoff-1500,events=events
    )
    assert result["predicted_fixture_ids"]==["mt_a","mt_b"]
    assert events[0:2]==["base","history"]
    pred_indices=[i for i,x in enumerate(events) if x.startswith("predict:")]
    odds_indices=[i for i,x in enumerate(events) if x.startswith("odds:")]
    assert len(pred_indices)==2 and len(odds_indices)==2
    assert max(pred_indices)<min(odds_indices)


def test_schedule_change_is_terminal_abstention_no_replacement(monkeypatch,tmp_path):
    event=200000.0; cutoff=event-runner.HORIZON
    root,result,events=_run(
        monkeypatch,tmp_path,[("mt_a",event)],cutoff-1500,schedule_shift=60
    )
    assert result["predicted_fixture_ids"]==[]
    terminal=(root/"status/mt_a/TERMINAL.json").read_text()
    assert "SCHEDULE_CHANGED" in terminal
    # Re-running does not query the terminal fixture again.
    before=list(events)
    _,result2,events2=_run(
        monkeypatch,tmp_path,[("mt_a",event)],cutoff-1400,schedule_shift=60,events=events
    )
    assert events2==before
    assert result2["predicted_fixture_ids"]==[]


def test_history_completed_after_cutoff_rejects_predictions(monkeypatch,tmp_path):
    event=200000.0; cutoff=event-runner.HORIZON
    root,result,events=_run(
        monkeypatch,tmp_path,[("mt_a",event)],cutoff-1500,history_completed=cutoff+1
    )
    assert result["predicted_fixture_ids"]==[]
    assert not any(x.startswith("detail:") for x in events)
    assert not any(x.startswith("odds:") for x in events)
    assert "HISTORY_COMPLETED_AFTER_CUTOFF" in (root/"status/mt_a/TERMINAL.json").read_text()


def test_late_first_wakeup_cannot_backfill(monkeypatch,tmp_path):
    event=200000.0; cutoff=event-runner.HORIZON
    root,result,events=_run(monkeypatch,tmp_path,[("mt_a",event)],cutoff-1000)
    assert events==[]
    assert result["predicted_fixture_ids"]==[]
    assert "MISSED_EXECUTION_WINDOW" in (root/"status/mt_a/TERMINAL.json").read_text()


def test_on_time_operational_failure_can_retry_before_cutoff(monkeypatch,tmp_path):
    event=200000.0; cutoff=event-runner.HORIZON
    root=tmp_path/"out"
    _,identities=_bound(monkeypatch,root,[("mt_a",event)])
    events=[]
    client=_client(monkeypatch,events,identities)
    base_loader,hist,pred=_deps(events,cutoff-1400)
    def fail_history(**kwargs):
        events.append("history_fail")
        raise RuntimeError("temporary provider failure")
    first=runner.run_t6_cycle(
        repo_root=tmp_path,output_root=root,history_snapshot_root=tmp_path/"h",
        base_data_dir=tmp_path/"b",client=client,now_fn=lambda:cutoff-1500,
        history_builder=fail_history,base_loader=base_loader,prediction_builder=pred,
    )
    assert first["predicted_fixture_ids"]==[]
    assert (root/"status/mt_a/ATTEMPT_STARTED.json").exists()
    # Now inside 20-minute threshold, but retry is allowed because attempt started on time.
    second=runner.run_t6_cycle(
        repo_root=tmp_path,output_root=root,history_snapshot_root=tmp_path/"h",
        base_data_dir=tmp_path/"b",client=client,now_fn=lambda:cutoff-1000,
        history_builder=hist,base_loader=base_loader,prediction_builder=pred,
    )
    assert second["predicted_fixture_ids"]==["mt_a"]


def test_repeated_market_capture_never_mutates_prediction_and_only_goals_are_normalized(monkeypatch,tmp_path):
    event=200000.0; cutoff=event-runner.HORIZON
    root=tmp_path/"out"
    _,identities=_bound(monkeypatch,root,[("mt_a",event)])
    events=[]
    prices=[(1.91,1.97),(1.80,2.10)]
    client=_client(monkeypatch,events,identities,price_fn=lambda n:prices[min(n-1,1)])
    base_loader,hist,pred=_deps(events,cutoff-1400)
    runner.run_t6_cycle(
        repo_root=tmp_path,output_root=root,history_snapshot_root=tmp_path/"h",
        base_data_dir=tmp_path/"b",client=client,now_fn=lambda:cutoff-1500,
        history_builder=hist,base_loader=base_loader,prediction_builder=pred,
    )
    prediction_path=root/"predictions/mt_a.json"
    before=prediction_path.read_bytes()
    # Second cycle: prediction already frozen; only another market snapshot is appended.
    runner.run_t6_cycle(
        repo_root=tmp_path,output_root=root,history_snapshot_root=tmp_path/"h",
        base_data_dir=tmp_path/"b",client=client,now_fn=lambda:cutoff-900,
        history_builder=hist,base_loader=base_loader,prediction_builder=pred,
    )
    assert prediction_path.read_bytes()==before
    records=list(CaptureStore(root/"market/captures.jsonl.gz").read_all())
    assert len(records)==4
    assert all(r.concept.startswith("odds:total_goals:") for r in records)
    assert not any("corner" in r.concept or "card" in r.concept for r in records)
    assert len(list((root/"market/raw/mt_a").glob("*.json")))==2


def test_scientific_prediction_binding_error_aborts_before_odds(monkeypatch,tmp_path):
    event=200000.0; cutoff=event-runner.HORIZON
    root=tmp_path/"out"
    _,identities=_bound(monkeypatch,root,[("mt_a",event)])
    events=[]
    client=_client(monkeypatch,events,identities)
    base_loader,hist,_=_deps(events,cutoff-1400)
    def bad_prediction(**kwargs):
        events.append("predict:mt_a")
        raise ValueError("Layer4 binding mismatch")
    with pytest.raises(runner.RunnerScientificAbort):
        runner.run_t6_cycle(
            repo_root=tmp_path,output_root=root,history_snapshot_root=tmp_path/"h",
            base_data_dir=tmp_path/"b",client=client,now_fn=lambda:cutoff-1500,
            history_builder=hist,base_loader=base_loader,prediction_builder=bad_prediction,
        )
    assert not any(x.startswith("odds:") for x in events)
