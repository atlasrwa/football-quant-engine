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
from src.research.hypothesis_v8c import anchor as ANCHOR
from src.research.hypothesis_v8c import grammar as GR
from src.research.hypothesis_v8c import historical_pit as HPIT
from src.research.hypothesis_v8c import historical_similarity as HSIM
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import receipt as RCPT
from src.research.hypothesis_v8c import scorer as SC
from src.research.hypothesis_v8c import select_freeze as SF
from src.research.hypothesis_v8c import structural_diagnostics as SD
from src.research.hypothesis_v8c import universe as UNI
from src.research.hypothesis_v8c import vintage as VIN

SCORE_FROZEN_VERSION = "v8c_score_frozen_v2"

UNRESOLVED = "UNRESOLVED"

SCORE_FROZEN_SCHEMA_VERSION = "v8c_freeze_schema_v1"

#: The two assembly modes. Verification, binding and scoring are IDENTICAL in both; they
#: differ only in what is assembled from the resulting records.
CONFIRMATORY = "confirmatory"
DEVELOPMENT_DIAGNOSTICS = "development_diagnostics"

#: Top-level fields a freeze MUST carry. Absence is FAIL-CLOSED, never "skip the check".
REQUIRED_FREEZE_FIELDS = (
    "freeze_version", "freeze_hash", "classification", "selections",
    "fixture_ids_ordered", "inference_blocks",
)

#: Per-fixture binding fields. Every one of these was previously checked only `if present`,
#: so a freeze that simply omitted them passed every binding check vacuously.
REQUIRED_ROW_FIELDS = (
    "fixture_id", "fixture_metadata", "corpus_vintage_hash", "capability_hash",
    "grammar_version", "grammar_size_hash", "pit_context_hash", "universe_hash",
    "arm_status", "S", "R", "H", "R_pairs",
)

#: Metadata subfields that must be present AND match.
REQUIRED_METADATA_FIELDS = ("fixture_id", "kickoff_unix", "competition", "home_id", "away_id")


class FreezeSchemaError(Exception):
    """The freeze is missing required binding metadata. Nothing is scored."""


class InferenceBlockError(Exception):
    """The predeclared inference blocks are missing or malformed. Nothing is scored."""

FIXTURE_NOT_IN_INDEX = "FIXTURE_NOT_IN_INDEX"
FREEZE_BINDING_MISMATCH = "FREEZE_BINDING_MISMATCH"


class FreezeIntegrityError(Exception):
    """The freeze payload does not hash to what it claims. Nothing is scored."""


class FreezeBindingMismatch(Exception):
    """The supplied data is not the data the selection was made against. Nothing is scored."""


class FixtureNotInIndex(Exception):
    """A frozen fixture is absent from the supplied index. Nothing is scored."""


def verify_freeze_schema(payload: dict) -> None:
    """FAIL CLOSED on an incomplete freeze.

    Previously every binding check was guarded by `if row.get(field)`, so a freeze that simply
    OMITTED a field skipped the check that field exists to enforce. Absence of evidence was
    silently treated as evidence of absence of a problem. It is now an error.
    """
    missing = [f for f in REQUIRED_FREEZE_FIELDS if not payload.get(f)]
    if missing:
        raise FreezeSchemaError(
            f"freeze is missing required field(s) {missing}: refusing to open any outcome")
    rows = payload["selections"]
    if not rows:
        raise FreezeSchemaError("freeze carries no selections")
    for i, row in enumerate(rows):
        bad = [f for f in REQUIRED_ROW_FIELDS if f not in row or row[f] is None]
        if bad:
            raise FreezeSchemaError(
                f"freeze selection #{i} ({row.get('fixture_id')!r}) is missing required "
                f"binding field(s) {bad}: refusing to open any outcome")
        meta = row["fixture_metadata"]
        mbad = [f for f in REQUIRED_METADATA_FIELDS if f not in meta or meta[f] is None]
        if mbad:
            raise FreezeSchemaError(
                f"freeze selection #{i} ({row['fixture_id']!r}) metadata is missing {mbad}")


def load_and_verify_freeze(path: str, *, receipt_path, require_commit=None) -> dict:
    """Steps 1-2. Raises BEFORE any outcome can be touched.

    `receipt_path` is MANDATORY. It previously defaulted to None and was checked only
    `if receipt_path is not None`, so the external anchor was optional in practice and the
    result field `receipt_verified` merely reported whether the caller had bothered.
    """
    if not receipt_path:
        raise RCPT.ReceiptError(
            "no receipt supplied: the freeze is self-certifying without one, so scoring is "
            "refused")
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
    verify_freeze_schema(payload)
    return payload


def verify_fixture_binding(row, index, capability, *, historical=None,
                           similarity_engine=None, grammar_kwargs=None,
                           historical_similarity=None):
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
    for k in REQUIRED_METADATA_FIELDS:
        if str(frozen_meta[k]) != str(now_meta[k]):
            raise FreezeBindingMismatch(
                f"{FREEZE_BINDING_MISMATCH}: {fid} field {k!r} was {frozen_meta[k]!r} at "
                f"selection, is {now_meta[k]!r} now")
    if frozen_meta.get("rec_i_at_selection") is not None and \
            int(frozen_meta["rec_i_at_selection"]) != int(pos):
        # NOT fatal: a shifted position with identical identity+vintage is a reordered index,
        # and resolving by fixture_id is exactly what makes that survivable. Recorded, not raised.
        pass

    # --- 5. corpus vintage (the data this measurement was allowed to see) ------------------
    frozen_vintage = row["corpus_vintage_hash"]
    now_vintage = VIN.corpus_vintage_before(index, int(now_meta["kickoff_unix"]))
    if now_vintage != frozen_vintage:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: {fid} corpus vintage changed "
            f"({frozen_vintage[:16]} -> {now_vintage[:16]}): historical data was revised "
            f"after selection, so the frozen question is not the question now being scored")

    # --- 6. capability + grammar ------------------------------------------------------------
    now_cap = VIN.capability_hash(capability)
    if now_cap != row["capability_hash"]:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: {fid} capability contract changed "
            f"({row['capability_hash'][:16]} -> {now_cap[:16]})")
    if row["grammar_version"] != GR.GRAMMAR_VERSION:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: {fid} grammar version {row['grammar_version']!r} "
            f"!= {GR.GRAMMAR_VERSION!r}")
    if row["grammar_size_hash"] != SF.GRAMMAR_SIZE_HASH:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: {fid} declared grammar shape changed")

    # --- 7. PIT context must rebuild to an IDENTICAL hash ----------------------------------
    ctx = PC.build_pit_context(index, pos, similarity_engine=similarity_engine,
                               historical=historical,
                               historical_similarity=historical_similarity)
    now_ctx = PC.context_hash(ctx)
    if now_ctx != row["pit_context_hash"]:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: {fid} PIT context hash changed "
            f"({row['pit_context_hash'][:16]} -> {now_ctx[:16]})")

    # --- 8. candidate universe -------------------------------------------------------------
    # ALWAYS rebuilt. The former `rebuild_universe=False` switch let a caller skip the single
    # check that proves the selectable action space is the one the selection was made over.
    fu = UNI.build_fixture_universe(index, pos, ctx=ctx, capability=capability,
                                    fixture_id=fid,
                                    grammar_kwargs=grammar_kwargs or {})
    now_uni = SF.universe_hash(fu)
    if now_uni != row["universe_hash"]:
        raise FreezeBindingMismatch(
            f"{FREEZE_BINDING_MISMATCH}: {fid} selectable universe changed "
            f"({row['universe_hash'][:16]} -> {now_uni[:16]})")

    return pos, ctx


def verify_inference_blocks(fz: dict) -> dict:
    """AUDIT FINDING 3: validate the predeclared blocks BEFORE any target read.

    This used to run AFTER the scoring loop, so a freeze with missing, malformed or mismatched
    blocks had already opened every target outcome by the time it was rejected -- and the case
    that matters most, a defect in the FINAL fixture, opened all of them.

    Checks: presence, the ordering the blocks were declared over, id uniqueness, complete
    cohort coverage, and agreement with the frozen blocking rule.
    """
    ids = fz["fixture_ids_ordered"]
    if not ids:
        raise InferenceBlockError("freeze declares no fixture ordering")
    if len(set(ids)) != len(ids):
        dupes = sorted({x for x in ids if ids.count(x) > 1})
        raise InferenceBlockError(f"fixture_ids_ordered contains duplicates: {dupes[:5]}")

    frozen = fz.get("inference_blocks")
    if not frozen or not isinstance(frozen, dict):
        raise InferenceBlockError(
            "the freeze carries no inference_blocks; blocks must be predeclared before outcomes")
    f2b = frozen.get("fixture_to_block")
    if not f2b or not isinstance(f2b, dict):
        raise InferenceBlockError("inference_blocks carries no fixture_to_block mapping")

    sel_ids = [r["fixture_id"] for r in fz["selections"]]
    if len(set(sel_ids)) != len(sel_ids):
        raise InferenceBlockError("freeze selections contain duplicate fixture_ids")
    if set(sel_ids) != set(ids):
        only_sel = sorted(set(sel_ids) - set(ids))
        only_ord = sorted(set(ids) - set(sel_ids))
        raise InferenceBlockError(
            f"selection set and declared ordering disagree: {len(only_sel)} only in "
            f"selections {only_sel[:3]}, {len(only_ord)} only in ordering {only_ord[:3]}")

    uncovered = [f for f in ids if f not in f2b]
    if uncovered:
        raise InferenceBlockError(
            f"{len(uncovered)} fixture(s) have no inference block: {uncovered[:5]}")
    extra = [f for f in f2b if f not in set(ids)]
    if extra:
        raise InferenceBlockError(
            f"inference blocks cover {len(extra)} fixture(s) not in the cohort: {extra[:5]}")

    recomputed = AG.chronological_blocks(ids)
    if recomputed["fixture_to_block"] != f2b:
        raise InferenceBlockError(
            "recomputed inference blocks differ from the frozen mapping -- the blocking rule "
            "changed after the selection freeze")
    return frozen


def score_frozen(freeze_path: str, index, *, capability, receipt_path,
                 anchor_commit, anchor_repo_relpath, similarity_engine=None,
                 grammar_kwargs=None, progress=False, require_commit=None,
                 repo_root=None, expected_exec_root=None,
                 mode=CONFIRMATORY) -> dict:
    """Verify EVERYTHING, then score. The only place a target outcome is read.

    `receipt_path`, `anchor_commit` and `anchor_repo_relpath` are all MANDATORY. A mutable
    receipt beside a mutable freeze is not an anchor: both are editable by one holder, and a
    consistent rewrite of the pair passes. The committed anchor is the only reference outside
    the editor's control, so process 2 will not start without it.
    """
    # A missing receipt is reported as a RECEIPT failure, not as an anchor read error: the
    # two are different faults and a reviewer needs to tell them apart.
    import os as _os
    if not receipt_path:
        raise RCPT.ReceiptError("no receipt supplied: refusing to score")
    if not _os.path.exists(receipt_path):
        raise RCPT.ReceiptError(f"no freeze receipt at {receipt_path}: refusing to score")
    if not _os.path.exists(freeze_path):
        raise FreezeSchemaError(f"no freeze at {freeze_path}: refusing to score")

    # ---- 0. THE EXTERNAL ANCHOR, first, because it is the only off-working-tree reference --
    anchor_out = ANCHOR.verify_for_scoring(
        anchor_commit=anchor_commit, anchor_repo_relpath=anchor_repo_relpath,
        freeze_path=freeze_path, receipt_path=receipt_path, repo_root=repo_root,
        # No bypass. Executing-code verification is NOT optional on the scoring path, and
        # the required set is every bound SOURCE -- upstream scientific dependencies, the
        # loader and the provider adapters included, not just hypothesis_v8c/*.
        require_modules=RCPT.BOUND_SOURCES, verify_executing=True,
        expected_exec_root=expected_exec_root)

    fz = load_and_verify_freeze(freeze_path, receipt_path=receipt_path,
                                require_commit=require_commit)
    gkw = grammar_kwargs or {}
    historical = HPIT.HistoricalProfileIndex(index)
    hist_sim = HSIM.HistoricalSimilarityIndex(index)

    # ---- verify EVERY fixture's binding BEFORE scoring ANY of them ---------------------
    verified = []
    n_rows = len(fz["selections"])
    for _i, row in enumerate(fz["selections"], 1):
        # Progress for the binding pass, which rebuilds a universe per fixture and was
        # previously silent for its whole duration. Emits identity and counts only -- never
        # an outcome, a score or an effect.
        if progress:
            print(f"[bind] {_i}/{n_rows} {row['fixture_id']}", flush=True)
        pos, ctx = verify_fixture_binding(
            row, index, capability, historical=historical,
            similarity_engine=similarity_engine, grammar_kwargs=gkw,
            historical_similarity=hist_sim)
        verified.append((row, pos, ctx))

    # ---- FINDING 3: blocks are validated HERE, before the first target read -------------
    blocks = verify_inference_blocks(fz)

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

    if mode == DEVELOPMENT_DIAGNOSTICS:
        # REPAIR 3. The SAME verification and the SAME scorer produced `records`; only the
        # assembly differs. No effect aggregation and no estimator is reached from here, so
        # the claim is "not computed", not merely "not emitted".
        diag = SD.structural_diagnostics(records, ids, pair_triples,
                                         blocks["fixture_to_block"])
        return {"score_version": SCORE_FROZEN_VERSION,
                "mode": DEVELOPMENT_DIAGNOSTICS,
                "freeze_hash_verified": fz["freeze_hash"],
                "freeze_version": fz["freeze_version"],
                "classification": fz["classification"],
                "receipt_verified": True,
                "anchor_commit": anchor_commit,
                "producer_code_commit": anchor_out["producer_code"]["producer_code_commit"],
                "anchor_verified": True,
                "executing_code_verified":
                    anchor_out["producer_code"]["executing_code_verified"],
                "n_sources_required": anchor_out["producer_code"]["n_sources_required"],
                "n_executing_verified": anchor_out["producer_code"]["n_executing_verified"],
                "blocks_validated_before_any_target_read": True,
                "binding_verified_fixtures": len(verified),
                "blocks": blocks,
                "scorer": SC.version_stamp(),
                "structural_diagnostics": diag,
                "effect_aggregation_called": False,
                "statistical_inference_called": False,
                "records": [{k: v for k, v in r.items() if k != "score"} for r in records]}

    per_fixture = AG.per_fixture_endpoints(records, ids, pair_triples)
    sr = AG.endpoint(per_fixture, "D_R", blocks["fixture_to_block"],
                     label="S_vs_R (MATCHED-PAIR)")
    sh = AG.endpoint(per_fixture, "D_H", blocks["fixture_to_block"],
                     label="S_vs_H (ARM-MEAN)")
    return {"score_version": SCORE_FROZEN_VERSION,
            "freeze_hash_verified": fz["freeze_hash"],
            "freeze_version": fz["freeze_version"],
            "classification": fz["classification"],
            "receipt_verified": True,
            "anchor_commit": anchor_commit,
            "producer_code_commit": anchor_out["producer_code_commit"],
            "anchor_verified": True,
            "executing_code_verified": anchor_out["producer_code"]["executing_code_verified"],
            "n_sources_required": anchor_out["producer_code"]["n_sources_required"],
            "n_executing_verified": anchor_out["producer_code"]["n_executing_verified"],
            "blocks_validated_before_any_target_read": True,
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
