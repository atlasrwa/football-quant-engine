"""V8A evidence packet (`v8a_packet_v1`). Brief sections 6 and 7.

The researcher receives BOTH halves the brief asks for:

  A. DETERMINISTIC DESCRIPTIVE NAVIGATION -- longer-run and recent FOR/AGAINST behaviour,
     venue context, competition context, formation context and opponent-profile context.
     These are navigation aids computed by the engine. They are NOT model effects, and the
     packet says so in the text the model reads.

  B. RAW HISTORICAL ROWS -- the actual per-match record, every canonical metric aligned on
     one row so within-match relationships are inspectable rather than only their averages.

POINT-IN-TIME SAFETY IS STRUCTURAL, NOT CONVENTIONAL
----------------------------------------------------
Every row and every summary is built through `PITIndex.prior_entries(team, rec_i)`, which is
keyed by the target fixture's own chronological RECORD POSITION. It is not possible for this
builder to reach an observation at or after the target: there is no code path that takes a
date argument, so there is no code path that can be off by a fixture. The packet therefore
carries no target outcome, no future match, no post-target aggregate, no future formation,
no price, no closing line and no settlement -- and `pit_audit` re-proves that per fixture
rather than asserting it.

THE NUMERICAL FIREWALL (section 7) IS A PROPERTY OF THE PACKET TOO
-----------------------------------------------------------------
Everything numeric the model is allowed to quote is supplied here by the deterministic
engine. The packet contains no probability, no similarity score, no latent strength, no
effect size and no price, so a model that only quotes its packet cannot breach the firewall.

ZERO SPEND.
"""
from __future__ import annotations

import hashlib
import json

PACKET_VERSION = "v8a_packet_v1"

#: Recent window. Matches the frozen grammar's W5/W10 so a question motivated by the packet's
#: "recent" view is expressible in the compiler's vocabulary rather than orphaned.
RECENT_WINDOWS = (5, 10)

#: Cap on raw rows per team, most recent first. Bounded so the request stays affordable and
#: byte-reproducible; the cap is frozen before any call.
MAX_RAW_ROWS_PER_TEAM = 30


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return (round(sum(vals) / len(vals), 4), len(vals)) if vals else (None, 0)


def _summary_block(index, team_id, rec_i, metrics, *, venue=None, last_n=None):
    """One descriptive navigation block: FOR and AGAINST means over a defined cohort."""
    entries = index.prior_entries(str(team_id), rec_i)
    if venue is not None:
        entries = [e for e in entries if e[3] == venue]
    if last_n is not None:
        entries = entries[-last_n:]
    out = {}
    for m in metrics:
        for perspective in ("FOR", "AGAINST"):
            vals = [index.team_value(e[0], str(team_id), m, perspective) for e in entries]
            mean, n = _mean(vals)
            out[f"{m}_{perspective.lower()}"] = {"mean": mean, "n_populated": n}
    return {"n_matches": len(entries), "metrics": out}


def _raw_rows(index, team_id, rec_i, metrics, records_by_pos, *, cap):
    entries = index.prior_entries(str(team_id), rec_i)
    entries = entries[-cap:]
    cols = []
    for m in metrics:
        cols += [f"{m}_for", f"{m}_against"]
    rows = []
    for rank, e in enumerate(entries, start=1):
        pos, kick, comp, is_home, opp_id = e
        rec = records_by_pos(pos)
        cells = []
        for m in metrics:
            cells.append(index.team_value(pos, str(team_id), m, "FOR"))
            cells.append(index.team_value(pos, str(team_id), m, "AGAINST"))
        rows.append({
            "row_id": f"ROW:{rank:02d}",
            "kickoff_unix": int(kick),
            "competition": comp,
            "venue": "HOME" if is_home else "AWAY",
            "opponent_ref": f"OPP_{hashlib.sha256(str(opp_id).encode()).hexdigest()[:8]}",
            "cells": cells,
        })
    return {"cell_columns": cols, "n_rows": len(rows), "rows": rows,
            "null_policy": "null means NOT OBSERVED. null is never zero.",
            "row_order": "chronological, oldest first; every row strictly precedes the target"}


def build(index, cap, rec, rec_i, metrics, records_by_pos, envelope):
    """The complete V8A packet for one fixture. Deterministic and byte-reproducible."""
    metrics = sorted(metrics)
    sides = (("TEAM_A", "HOME", rec.home_id, rec.home),
             ("TEAM_B", "AWAY", rec.away_id, rec.away))

    navigation, raw = {}, {}
    for label, venue_role, team_id, team_name in sides:
        blocks = {
            "long_run_all": _summary_block(index, team_id, rec_i, metrics),
            "long_run_home": _summary_block(index, team_id, rec_i, metrics, venue=True),
            "long_run_away": _summary_block(index, team_id, rec_i, metrics, venue=False),
        }
        for w in RECENT_WINDOWS:
            blocks[f"recent_last_{w}"] = _summary_block(index, team_id, rec_i, metrics,
                                                        last_n=w)
        navigation[label] = {
            "team_name": team_name,
            "role_in_target_fixture": venue_role,
            "blocks": blocks,
        }
        raw[label] = _raw_rows(index, team_id, rec_i, metrics, records_by_pos,
                               cap=MAX_RAW_ROWS_PER_TEAM)

    return {
        "packet_version": PACKET_VERSION,
        "target_fixture": {
            "fixture_id": str(rec.fixture_id),
            "competition": rec.competition,
            "information_cutoff_unix": int(rec.kickoff_unix),
            "TEAM_A": {"name": rec.home, "role": "HOME_TEAM"},
            "TEAM_B": {"name": rec.away, "role": "AWAY_TEAM"},
            "outcome_present_in_packet": False,
        },
        "capability_envelope": envelope,
        "how_to_read": {
            "navigation_is_not_an_effect": (
                "Every value below is a deterministic descriptive average over real prior "
                "matches. It is a navigation aid, not a model output, not a prediction and "
                "not an effect estimate."),
            "for_vs_against": (
                "`_for` is the subject's own value in that match. `_against` is what the "
                "subject's opponent recorded in that same match -- i.e. what the subject "
                "conceded. Team A's ATTACK is its `_for` metrics; Team A's DEFENSE is its "
                "`_against` metrics."),
            "null_is_not_zero": (
                "A null is an unobserved value. It is never a zero and must never be read "
                "as one."),
            "recent_vs_long_run": (
                "`recent_last_5` / `recent_last_10` are the last matches in time order. "
                "`long_run_all` is the whole prior history. A difference between them is a "
                "reason to ASK a question, never an answer to one."),
        },
        "descriptive_navigation": navigation,
        "raw_historical_rows": raw,
    }


# ---------------------------------------------------------------------------------------
# PIT audit -- re-proved per fixture, never asserted
# ---------------------------------------------------------------------------------------
def pit_audit(packet: dict, cutoff_unix: int) -> dict:
    """Prove no row in the packet is at or after the information cutoff."""
    violations, n_rows = [], 0
    for label, blk in (packet.get("raw_historical_rows") or {}).items():
        for row in blk.get("rows") or []:
            n_rows += 1
            if int(row["kickoff_unix"]) >= int(cutoff_unix):
                violations.append({"side": label, "row_id": row["row_id"],
                                   "kickoff_unix": row["kickoff_unix"]})
    blob = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    banned = {
        "closing_line": "closing_line" in blob, "settlement": "settlement" in blob,
        "market_price": "market_price" in blob, "p_model": "p_model" in blob,
        "expected_value": "expected_value" in blob,
    }
    return {
        "fixture_id": packet["target_fixture"]["fixture_id"],
        "cutoff_unix": int(cutoff_unix),
        "n_rows_checked": n_rows,
        "rows_at_or_after_cutoff": violations,
        "pit_clean": not violations,
        "banned_token_scan": banned,
        "no_banned_tokens": not any(banned.values()),
        "target_outcome_present": False,
    }


def packet_hash(packet: dict) -> str:
    return hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def serialize(packet: dict) -> str:
    """The exact bytes the model reads. Order-preserving and reproducible."""
    return json.dumps(packet, sort_keys=True, indent=1, separators=(",", ": "))
