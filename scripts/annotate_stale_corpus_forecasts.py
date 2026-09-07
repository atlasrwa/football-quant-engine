#!/usr/bin/env python3
"""Mark the forecasts published on the stale corpus — append-only, never edited.

WHAT HAPPENED
=============
Between the broadcast engine going live and 2026-09-06, the training corpus held only
the last two *completed* seasons. Nothing wrote current-season matches into it. Every
forecast published in that window was fitted on observations ending 2026-05-31, so its
rolling "recent form" windows described last season, not this one.

WHY THESE RECORDS ARE NOT EDITED
================================
``broadcasts.jsonl`` is append-only and every row carries a commitment hash over the
payload exactly as published. Editing a row to add a caveat would change its hash and
make ``verify_commitment_hashes()`` report it as altered — converting a data-quality
problem into an indistinguishable tamper signal, and destroying the evidence that the
forecast was made in that form at that time.

So this script writes to a separate annotation ledger keyed by commitment hash. The
published records stay byte-identical and keep verifying; the annotation states what
was later found out. That is the only correction mechanism this record supports, and it
is the right one.

WHAT THE EVIDENCE FIELD CONTAINS
================================
Per fixture, for both teams: the date of the newest match the engine actually had, and
how many days before kick-off that was. This is the concrete measure of the defect —
"the corpus was stale" is a claim, "Cardiff City's newest observed match was 490 days
before kick-off" is a fact a reader can check.

USAGE
=====
    python3 scripts/annotate_stale_corpus_forecasts.py --dry-run
    python3 scripts/annotate_stale_corpus_forecasts.py
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.prediction_engine.broadcast.record import (
    AnnotationType,
    BroadcastLedger,
    DEFAULT_RECORD_ROOT,
)

#: The failure-ledger entry this annotation belongs to.
FAILURE_LEDGER_ENTRY = "F025"

#: The data cutoff that identifies an affected forecast. Every commitment whose
#: payload declares this cutoff was fitted on the pre-refresh corpus.
STALE_DATA_CUTOFF_UTC = "2026-05-31T16:30:00+00:00"

#: FootyStats season ids for the 2026/27 seasons added by the corpus refresh. Excluded
#: when reconstructing what the engine actually had at forecast time.
CURRENT_SEASON_IDS = ("17184", "17146", "17117", "17269")

CORPUS_DIR = Path("/home/ubuntu/data/discovery/corpus")

logger = logging.getLogger("annotate_stale_corpus")


def load_pre_refresh_corpus() -> list[dict[str, Any]]:
    """Reconstruct the corpus as it stood when the affected forecasts were published.

    Rebuilt by excluding the season files the refresh added, rather than by trusting a
    remembered description of the old state. The evidence in the annotation has to be
    derived from the data, not asserted.
    """
    matches: list[dict[str, Any]] = []
    for path in sorted(glob.glob(str(CORPUS_DIR / "league-matches_*.json"))):
        if any(f"season_id:_{sid}" in path for sid in CURRENT_SEASON_IDS):
            continue
        try:
            matches += json.loads(Path(path).read_text(encoding="utf-8")).get("data", [])
        except (json.JSONDecodeError, OSError):
            continue
    matches = [
        m for m in matches
        if m.get("date_unix") and m.get("home_name") and m.get("away_name")
        and str(m.get("status") or "").casefold() == "complete"
    ]
    matches.sort(key=lambda m: m["date_unix"])
    return matches


def build_evidence(
    histories: dict[str, list], payload: dict[str, Any]
) -> dict[str, Any]:
    """Per-team feature staleness for one affected forecast."""
    kickoff = float(payload["kickoff_unix"])
    teams: dict[str, Any] = {}
    for team in (payload["home_team"], payload["away_team"]):
        prior = [d for d, _m, _r in histories.get(team, []) if d < kickoff]
        if not prior:
            teams[team] = {"newest_observation_utc": None, "days_before_kickoff": None,
                           "note": "no prior match in corpus"}
            continue
        newest = max(prior)
        teams[team] = {
            "newest_observation_utc": datetime.fromtimestamp(
                newest, timezone.utc
            ).isoformat(),
            "days_before_kickoff": round((kickoff - newest) / 86400.0, 1),
            "prior_matches_available": len(prior),
        }
    ages = [
        t["days_before_kickoff"] for t in teams.values()
        if t.get("days_before_kickoff") is not None
    ]
    return {
        "data_cutoff_utc": payload.get("data_cutoff_utc"),
        "kickoff_utc": payload.get("kickoff_utc"),
        "model_version": payload.get("model_version"),
        "teams": teams,
        "max_feature_staleness_days": max(ages) if ages else None,
        "min_feature_staleness_days": min(ages) if ages else None,
    }


def annotate(*, dry_run: bool = False, record_root: Path = DEFAULT_RECORD_ROOT) -> dict:
    """Annotate every commitment fitted on the stale corpus.

    Idempotent: a commitment already annotated for this failure entry is skipped, so
    re-running cannot inflate the annotation ledger with duplicates.
    """
    import pilotC_stat_mixer as mix

    ledger = BroadcastLedger(record_root)
    histories = mix.build_histories(load_pre_refresh_corpus())
    already = {
        str(row.get("commitment_hash"))
        for row in ledger.annotations()
        if row.get("failure_ledger_entry") == FAILURE_LEDGER_ENTRY
    }

    summary: dict[str, Any] = {
        "failure_ledger_entry": FAILURE_LEDGER_ENTRY,
        "dry_run": dry_run,
        "annotated": [],
        "already_annotated": 0,
        "examined": 0,
    }

    detail = (
        "Fitted on a training corpus whose newest observation was "
        f"{STALE_DATA_CUTOFF_UTC}, because no process wrote completed current-season "
        "(2026/27) matches into data/discovery/corpus/. The rolling 5- and 10-match "
        "form windows behind these probabilities therefore describe the 2025/26 "
        "season, not the season being played: different squads, in some cases "
        "different managers, and a different competitive context. This forecast is "
        "recorded as published and is NOT representative of the engine's behaviour "
        "once current-season ingestion and the freshness gate are in place. The "
        "record is unchanged and still verifies; this annotation is additive."
    )

    for record in ledger.commitments():
        payload = record.get("payload") or {}
        if payload.get("data_cutoff_utc") != STALE_DATA_CUTOFF_UTC:
            continue
        summary["examined"] += 1
        commitment = str(record.get("commitment_hash"))
        if commitment in already:
            summary["already_annotated"] += 1
            continue
        evidence = build_evidence(histories, payload)
        entry = {
            "commitment_hash": commitment,
            "fixture_id": record.get("fixture_id"),
            "fixture": f"{payload.get('home_team')} vs {payload.get('away_team')}",
            "max_feature_staleness_days": evidence["max_feature_staleness_days"],
        }
        if not dry_run:
            ledger.append_annotation(
                commitment_hash=commitment,
                annotation_type=AnnotationType.AFFECTED_BY_STALE_CORPUS,
                detail=detail,
                failure_ledger_entry=FAILURE_LEDGER_ENTRY,
                evidence=evidence,
                fixture_id=record.get("fixture_id"),
            )
        summary["annotated"].append(entry)

    summary["annotated_count"] = len(summary["annotated"])
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be annotated; write nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="annotate_stale_corpus: %(levelname)s %(message)s")
    summary = annotate(dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
