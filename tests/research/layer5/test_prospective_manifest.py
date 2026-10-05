import gzip
import json
from pathlib import Path

import pytest

from src.research.dataset.manifest import sha256_json
from src.research.layer5.market_manifest import snapshot_capture_prefix
from src.research.layer5.prospective_manifest import (
    build_prospective_market_manifest,
    validate_prospective_cohort_manifest,
    write_prospective_market_manifest,
)


def _cohort(fixtures=(("mt_a",100000.0),), frozen_at="1970-01-01T00:00:00+00:00"):
    rows=[{"fixture_id":fid,"event_time":ts} for fid,ts in fixtures]
    base={
        "version":"qfe-prospective-cohort-v1",
        "status":"FROZEN_OUTCOME_BLIND",
        "frozen_at":frozen_at,
        "fixtures":rows,
    }
    return {**base,"cohort_hash":sha256_json(base)}


def _row(fid, concept, value, *, ko=100000.0, obs=78000.0, raw="h"):
    return {
        "provider":"thestatsapi",
        "canonical_entity_id":fid,
        "concept":concept,
        "value":value,
        "event_time":ko,
        "observed_at":obs,
        "retrieved_at":obs,
        "raw_payload_hash":raw,
        "raw_status":"PROSPECTIVE_SNAPSHOT",
    }


def _gz(path, rows):
    raw="".join(json.dumps(r,separators=(",",":"))+"\n" for r in rows).encode()
    path.write_bytes(gzip.compress(raw,mtime=0))


def test_future_cohort_schema_is_outcome_blind_and_pre_t6():
    c=_cohort()
    rows=validate_prospective_cohort_manifest(c)
    assert rows[0].fixture_id=="mt_a"

    bad=json.loads(json.dumps(c))
    bad["fixtures"][0]["score"]="1-0"
    base={k:bad[k] for k in ("version","status","frozen_at","fixtures")}
    bad["cohort_hash"]=sha256_json(base)
    with pytest.raises(ValueError,match="schema"):
        validate_prospective_cohort_manifest(bad)

    late=_cohort(frozen_at="1970-01-02T00:00:00+00:00")
    with pytest.raises(ValueError,match="T-6h"):
        validate_prospective_cohort_manifest(late)


def test_prospective_manifest_uses_goals_only_and_corners_fail_closed(tmp_path):
    cap=tmp_path/"captures.gz"
    rows=[]
    for book,over,under in (("pinnacle",1.9,1.9),("bet365",4.0,1.3)):
        rows += [
            _row("mt_a",f"odds:total_goals:over:2.5:{book}",over,raw=book),
            _row("mt_a",f"odds:total_goals:under:2.5:{book}",under,raw=book),
        ]
    rows += [
        _row("mt_a","odds:match_corners:over:9.5:pinnacle",2.0,raw="corner"),
        _row("mt_a","odds:match_corners:under:9.5:pinnacle",2.0,raw="corner"),
    ]
    _gz(cap,rows)
    manifest,kept=build_prospective_market_manifest(
        capture_prefix=snapshot_capture_prefix(cap),
        cohort_manifest=_cohort(),
    )
    f=manifest["fixture_rows"][0]
    assert f["markets"]["GOALS_TOTAL"]["status"]=="OK"
    assert f["markets"]["GOALS_TOTAL"]["bookmaker"]=="pinnacle"
    assert f["markets"]["CORNERS_TOTAL"]["reason"]=="SETTLEMENT_SEMANTICS_UNVERIFIED"
    assert f["markets"]["CORNERS_SIDE"]["reason"]=="SETTLEMENT_SEMANTICS_UNVERIFIED"
    assert manifest["valid_matched_market_counts"]=={"GOALS_TOTAL":1,"CORNERS_TOTAL":0,"CORNERS_SIDE":0}
    assert manifest["legacy_317_used"] is False
    assert manifest["outcomes_read"] is False
    assert all(r["market_key"]=="GOALS_TOTAL" for r in kept)
    assert manifest["source_counts"]["corner_odds_rows_seen_but_ineligible"]==2


def test_prospective_manifest_rejects_capture_kickoff_drift(tmp_path):
    cap=tmp_path/"captures.gz"
    _gz(cap,[
        _row("mt_a","odds:total_goals:over:2.5:pinnacle",2.0,ko=100001),
        _row("mt_a","odds:total_goals:under:2.5:pinnacle",2.0,ko=100001),
    ])
    with pytest.raises(ValueError,match="kickoff conflicts"):
        build_prospective_market_manifest(
            capture_prefix=snapshot_capture_prefix(cap),
            cohort_manifest=_cohort(),
        )


def test_prospective_manifest_writer_is_immutable(tmp_path):
    cap=tmp_path/"captures.gz"
    _gz(cap,[
        _row("mt_a","odds:total_goals:over:2.5:pinnacle",2.0),
        _row("mt_a","odds:total_goals:under:2.5:pinnacle",2.0),
    ])
    manifest,rows=build_prospective_market_manifest(
        capture_prefix=snapshot_capture_prefix(cap),
        cohort_manifest=_cohort(),
    )
    p1,p2=write_prospective_market_manifest(output_dir=tmp_path/"out",manifest=manifest,retained_rows=rows)
    before=(p1.read_bytes(),p2.read_bytes())
    write_prospective_market_manifest(output_dir=tmp_path/"out",manifest=manifest,retained_rows=rows)
    assert before==(p1.read_bytes(),p2.read_bytes())
    p1.write_text("{}\n")
    with pytest.raises(FileExistsError):
        write_prospective_market_manifest(output_dir=tmp_path/"out",manifest=manifest,retained_rows=rows)
