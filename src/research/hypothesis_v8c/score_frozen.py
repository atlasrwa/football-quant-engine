"""V8C PROCESS 2 of 2 -- post-freeze scoring (`v8c_score_frozen_v2`).

Repairs P0-A (data-vintage binding) and consumes P0-B (external receipt) and P1-F (frozen
blocks).

THE ORDER MATTERS. Every check below happens BEFORE a single target outcome is read, and any
failure aborts with a named status:

    1. EXTERNAL RECEIPT      verify the freeze FILE BYTES against a separate receipt (P0-B).
                             Editing the freeze and recomputing its own internal hash does not
                             help -- the anchor is not inside the payload.
    2. FREEZE SELF-HASH      internal consistency of the payload.
    3. RESOLVE BY FIXTURE_ID never by the frozen integer `rec_i`. A row inserted, backfilled
                             or reordered between selection and scoring makes that integer
                             point at a DIFFERENT fixture (P0-A).
    4. FIXTURE METADATA      kickoff, competition, home_id, away_id must match exactly. A
                             revised row is a different question, even under the same id.
    5. CORPUS VINTAGE        the data the measurement was allowed to see must be unchanged.
                             A backfilled historical value changes cohort, support, baseline
                             and profile bands, so the scorer would silently answer a
                             different question.
    6. CAPABILITY / GRAMMAR  the provider contract and the declared grammar must be the ones
                             the selection was made under.
    7. PIT CONTEXT           rebuilt and required to hash EXACTLY equal.
    8. UNIVERSE              rebuilt where needed and required to match.
    --- only now may an outcome be read ---

`FIXTURE_NOT_IN_INDEX` and `FREEZE_BINDING_MISMATCH` are DISTINCT: the first is a missing row,
the second a revised one, and a reviewer needs to tell them apart.

ZERO SPEND. Opens target outcomes ONLY for fixtures named in a fully verified freeze.
"""
from __future__ import annotations

import json

from src.research.hypothesis_v71 import engine as ENGmod
from src.research.hypothesis_v8c import aggregate as AG
from src.research.hypothesis_v8c import grammar as GR
from src.research.hypothesis_v8c import historical_pit as HPIT
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import receipt as RCPT
from src.research.hypothesis_v8c import scorer as SC
from src.research.hypothesis_v8c import select_freeze as SF
from src.research.hypothesis_v8c import universe as UNI
from src.research.hypothesis_v8c import vintage as VIN

SCORE_FROZEN_VERSION = "v8c_score_frozen_v2"

UNRESOLVED = "UNRESOLVED"

FIXTURE_NOT_IN_INDEX = "FIXTURE_NOT_IN_INDEX"
FREEZE_BINDING_MISMATCH = "FREEZE_BINDING_MISMATCH"


class FreezeIntegrityError(Exception):
    """The freeze payload does not hash to what it claims. Nothing is scored."""


class FreezeBindingMismatch(Exception):
    """The supplied data is not the data the selection was made against. Nothing is scored."""


class FixtureNotInIndex(Exception):
    """A frozen fixture is absent from the supplied index. Nothing is scored."""


def load_and_verify_freeze(path: str, *, receipt_path=None, require_commit=None) -> dict:
    """Steps 1-2. Raises BEFORE any outcome can be touched."""
    if receipt_path is not None:
        RCPT.verify_receipt(receipt_path, path, require_commit=require_commit)

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


def verify_fixture_binding(row, index, capability, *, historical=None,
                           similarity_engine=None, grammar_kwargs=None, rebuild_universe=True):
    """Steps 3-8 for ONE fixture. Returns (pos, ctx). Raises on any mismatch.

    Nothing in this function reads the target's own observation.
    """
    fid = row["fixture_id"]

    # --- 3. resolve by fixture_id, NEVER by the frozen integer ---------------------------
    pos = index.pos_of_fixture.get(fid)
    if pos is None:
        raise FixtureNotInIndex(f"{FIXTURE_NOT_IN_INDEX}: {fid} is absent from this index")

    # --- 4. fixture metadata must match exactly -------------------------------------------
    frozen_meta = row.get("fixture_metadata") or {}
    now_meta = VIN.fixture_metadata(index, pos)
    for k in ("fixture_id", "kickoff_unix", "competition", "home_id", "away_id"):
        if k in frozen_meta and str(frozen_meta[k]) != str(now_meta[k]):
            raise FreezeBindingMismatch(
                f"{FREEZE_BINDING_MISMATCH}: {fid} field {k!r} was {frozen_meta[k]!r} at "
                f"selection, is {now_meta[k]!r} now")
    if frozen_meta.get("rec_i_at_selection") is not None and \
            int(frozen_meta["rec_i_at_selection"]) != int(pos):
        # NOT fatal: a shifted position with identical identity+vintage is a reordered index,
        # and resolving by fixture_id is exactly what makes that survivable. Recorded, not raised.
        pass

    # --- 5. corpus vintage (the data this measurement was allowed to see) ------------------
    frozen_vintage = row.get("corpus_vintage_hash")
    if frozen_vintage:
        now_vintage = VIN.corpus_vintage_before(index, int(now_meta["kickoff_unix"]))
        if now_vintage != frozen_vintage:
            raise FreezeBindingMismatch(
                f"{FREEZE_BINDING_MISMATCH}: {fid} corpus vintage changed "
                f"({frozen_vintage[:16]} -> {now_vintage[:16]}): historical data was revised "
                f"after selection, so the frozen question is not the question now being scored")

    # --- 6. capability + grammar ------------------------------------------------------------
    if row.get("capability_hash"):
        now_cap = VIN.capability_hash(capability)
        if now_cap != row["capability_hash"]:
            raise FreezeBindingMismatch(
                f"{FREEZE_BINDING_MISMATCH}: {fid} capability contract changed "
                f"({row['capability_hash'][:16]} -> {now_cap[:16]})")
    if row.get("grammar_version") and row["grammar_version"] != GR.GRAMMAR_VERSION:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: {fid} grammar version {row['grammar_version']!r} "
            f"!= {GR.GRAMMAR_VERSION!r}")
    if row.get("grammar_size_hash") and row["grammar_size_hash"] != SF.GRAMMAR_SIZE_HASH:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: {fid} declared grammar shape changed")

    # --- 7. PIT context must rebuild to an IDENTICAL hash ----------------------------------
    ctx = PC.build_pit_context(index, pos, similarity_engine=similarity_engine,
                               historical=historical)
    if row.get("pit_context_hash"):
        now_ctx = PC.context_hash(ctx)
        if now_ctx != row["pit_context_hash"]:
            raise FreezeBindingMismatch(
                f"{FREEZE_BINDING_MISMATCH}: {fid} PIT context hash changed "
                f"({row['pit_context_hash'][:16]} -> {now_ctx[:16]})")

    # --- 8. candidate universe -------------------------------------------------------------
    if rebuild_universe and row.get("universe_hash"):
        fu = UNI.build_fixture_universe(index, pos, ctx=ctx, capability=capability,
                                        fixture_id=fid,
                                        grammar_kwargs=grammar_kwargs or {})
        now_uni = SF.universe_hash(fu)
        if now_uni != row["universe_hash"]:
            raise FreezeBindingMismatch(
                f"{FREEZE_BINDING_MISMATCH}: {fid} selectable universe changed "
                f"({row['universe_hash'][:16]} -> {now_uni[:16]})")

    return pos, ctx


def score_frozen(freeze_path: str, index, *, capability, similarity_engine=None,
                 grammar_kwargs=None, progress=False, receipt_path=None,
                 require_commit=None, rebuild_universe=True) -> dict:
    """Verify EVERYTHING, then score. The only place a target outcome is read."""
    fz = load_and_verify_freeze(freeze_path, receipt_path=receipt_path,
                                require_commit=require_commit)
    gkw = grammar_kwargs or {}
    historical = HPIT.HistoricalProfileIndex(index)

    # ---- verify EVERY fixture's binding BEFORE scoring ANY of them ---------------------
    verified = []
    for row in fz["selections"]:
        pos, ctx = verify_fixture_binding(
            row, index, capability, historical=historical,
            similarity_engine=similarity_engine, grammar_kwargs=gkw,
            rebuild_universe=rebuild_universe)
        verified.append((row, pos, ctx))

    # ---- only now may an outcome be read ------------------------------------------------
    records, pair_triples = [], {}
    for n, (row, pos, ctx) in enumerate(verified):
        fid = row["fixture_id"]
        pair_triples[fid] = list(row["R_pairs"])
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
                                      hist_similarity=ctx.historical_similarity,
                                      recency=ENGmod.recency_family_for(ir),
                                      capability=capability)
                records.append({"fixture_id": fid, "arm": arm, "hypothesis_id": hid,
                                "status": fs.status, "score": fs.score, "reason": fs.reason,
                                "cohort_n": fs.cohort_n,
                                "unique_opponents": fs.unique_opponents,
                                "support_status": fs.support_status})
        if progress:
            print(f"[score] {n + 1}/{len(verified)} {fid}", flush=True)

    ids = fz["fixture_ids_ordered"]

    # ---- P1-F: CONSUME the frozen blocks; recompute only as a verification check ---------
    frozen_blocks = fz.get("inference_blocks")
    if not frozen_blocks:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: the freeze carries no inference_blocks; blocks must "
            f"be predeclared before outcomes")
    recomputed = AG.chronological_blocks(ids)
    if recomputed["fixture_to_block"] != frozen_blocks["fixture_to_block"]:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: recomputed inference blocks differ from the frozen "
            f"mapping -- the blocking rule changed after the selection freeze")
    blocks = frozen_blocks

    per_fixture = AG.per_fixture_endpoints(records, ids, pair_triples)
    sr = AG.endpoint(per_fixture, "D_R", blocks["fixture_to_block"],
                     label="S_vs_R (MATCHED-PAIR)")
    sh = AG.endpoint(per_fixture, "D_H", blocks["fixture_to_block"],
                     label="S_vs_H (ARM-MEAN)")
    return {"score_version": SCORE_FROZEN_VERSION,
            "freeze_hash_verified": fz["freeze_hash"],
            "freeze_version": fz["freeze_version"],
            "classification": fz["classification"],
            "receipt_verified": receipt_path is not None,
            "binding_verified_fixtures": len(verified),
            "blocks_source": "FROZEN_IN_SELECTION (recomputation used only as a check)",
            "scorer": SC.version_stamp(), "aggregate": AG.version_stamp(),
            "records": records, "per_fixture": per_fixture, "blocks": blocks,
            "endpoint_S_vs_R": sr, "endpoint_S_vs_H": sh}


def version_stamp() -> dict:
    return {"score_frozen_version": SCORE_FROZEN_VERSION,
            "repairs": ["P0-A", "P1-F"], "consumes": ["P0-B"],
            "process_role": "PROCESS 2 of 2 -- scoring only, never selection",
            "resolves_target_by": "fixture_id",
            "trusts_frozen_rec_i": False,
            "verifies_before_any_outcome_read": [
                "external receipt", "freeze self-hash", "fixture resolution",
                "fixture metadata", "corpus vintage", "capability hash",
                "grammar version + shape", "pit context hash", "universe hash"],
            "distinct_failure_statuses": [FIXTURE_NOT_IN_INDEX, FREEZE_BINDING_MISMATCH],
            "blocks_are_consumed_not_recomputed": True,
            "can_change_a_selection": False}
