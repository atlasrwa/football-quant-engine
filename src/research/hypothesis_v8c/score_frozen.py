"""V8C PROCESS 2 of 2 -- post-freeze scoring (`v8c_score_frozen_v1`).

REPAIRS P0 OUTCOME-SEAL (the second half).

Reads the durable freeze written by `select_freeze.py`, RE-VERIFIES ITS HASH, and only then
opens target outcomes. It cannot select, and it cannot change a selection: every hypothesis it
scores is read from the frozen file.

The refusal is the point. If the freeze file's recomputed hash does not match the hash stored
inside it, the selections are not the ones that were frozen, and this process exits without
reading a single outcome.

ZERO SPEND. Opens target outcomes ONLY for the fixtures named in the freeze.
"""
from __future__ import annotations

import json

from src.research.hypothesis_v71 import engine as ENGmod
from src.research.hypothesis_v8c import aggregate as AG
from src.research.hypothesis_v8c import grammar as GR
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import scorer as SC
from src.research.hypothesis_v8c import select_freeze as SF

SCORE_FROZEN_VERSION = "v8c_score_frozen_v1"

UNRESOLVED = "UNRESOLVED"


class FreezeIntegrityError(Exception):
    """The freeze file does not hash to what it claims. Nothing is scored."""


def load_and_verify_freeze(path: str) -> dict:
    """Read the freeze and re-verify its self-hash BEFORE any outcome is touched."""
    payload = json.load(open(path))
    claimed = payload.get("freeze_hash")
    recomputed = SF.freeze_hash(payload)
    if not claimed or claimed != recomputed:
        raise FreezeIntegrityError(
            f"freeze hash mismatch: file claims {claimed!r}, recomputed {recomputed!r} -- "
            f"refusing to open any target outcome")
    if payload.get("totals", {}).get("target_outcomes_viewed"):
        raise FreezeIntegrityError(
            "the freeze records that target outcomes were viewed during selection")
    return payload


def score_frozen(freeze_path: str, index, *, capability, similarity_engine=None,
                 grammar_kwargs=None, progress=False) -> dict:
    """Score every frozen selection. The ONLY place a target outcome is read."""
    fz = load_and_verify_freeze(freeze_path)
    records, pair_triples = [], {}
    gkw = grammar_kwargs or {}

    for n, row in enumerate(fz["selections"]):
        fid, pos = row["fixture_id"], int(row["rec_i"])
        ctx = PC.build_pit_context(index, pos, similarity_engine=similarity_engine)
        pair_triples[fid] = [p for p in row["R_pairs"]]
        for arm in ("S", "R", "H"):
            for hid in row[arm]:
                ir = GR.resolve(hid, capability, **gkw)
                if ir is None:
                    records.append({"fixture_id": fid, "arm": arm, "hypothesis_id": hid,
                                    "status": UNRESOLVED, "score": None,
                                    "reason": "id does not resolve under the frozen grammar"})
                    continue
                fs = SC.score_fixture(ir, index, pos, metric=ir.target_metrics[0],
                                      terciles=ctx.terciles, axis_cache=ctx.axis_cache,
                                      similarity=ctx.similarity,
                                      recency=ENGmod.recency_family_for(ir),
                                      capability=capability)
                records.append({"fixture_id": fid, "arm": arm, "hypothesis_id": hid,
                                "status": fs.status, "score": fs.score, "reason": fs.reason,
                                "cohort_n": fs.cohort_n,
                                "unique_opponents": fs.unique_opponents,
                                "support_status": fs.support_status})
        if progress:
            print(f"[score] {n + 1}/{len(fz['selections'])} {fid}", flush=True)

    ids = fz["fixture_ids_ordered"]
    blocks = AG.chronological_blocks(ids)
    per_fixture = AG.per_fixture_endpoints(records, ids, pair_triples)
    sr = AG.endpoint(per_fixture, "D_R", blocks["fixture_to_block"],
                     label="S_vs_R (MATCHED-PAIR)")
    sh = AG.endpoint(per_fixture, "D_H", blocks["fixture_to_block"],
                     label="S_vs_H (ARM-MEAN)")
    return {"score_version": SCORE_FROZEN_VERSION,
            "freeze_hash_verified": fz["freeze_hash"],
            "freeze_version": fz["freeze_version"],
            "classification": fz["classification"],
            "scorer": SC.version_stamp(), "aggregate": AG.version_stamp(),
            "records": records, "per_fixture": per_fixture, "blocks": blocks,
            "endpoint_S_vs_R": sr, "endpoint_S_vs_H": sh}


def version_stamp() -> dict:
    return {"score_frozen_version": SCORE_FROZEN_VERSION,
            "repairs": ["P0-OUTCOME-SEAL"],
            "process_role": "PROCESS 2 of 2 -- scoring only, never selection",
            "verifies_freeze_hash_before_any_outcome_read": True,
            "refuses_on_hash_mismatch": True,
            "can_change_a_selection": False,
            "scorer": SC.SCORER_VERSION}
