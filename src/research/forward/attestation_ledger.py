"""Tamper-evident commit-reveal attestation ledger for file-based forward pipelines.

The forward research pipelines (``scripts/quarantine_forward_loop.py`` and the
Pilot C predictor) log predictions to JSONL before matches kick off. A logged
prediction is only credible as a *forward* prediction if we can prove it existed,
unchanged, before kickoff. This module provides that proof without a database.

Design goals (from the hardening brief):

1. Every prediction is COMMITTED before kickoff. The commitment hash binds
   ``prediction + fixture + reference price + timestamp`` (SHA-256 over canonical
   JSON, same convention as ``src/persistence/broadcast_hashing.py``).
2. Automatic REVEAL after settlement, binding the outcome to the commitment.
3. Commitments are persisted IMMUTABLY and cannot be backdated:
     - The commit timestamp is taken from THIS process's clock at append time.
       Caller-supplied timestamps are never trusted for the anchor.
     - Records form a HASH CHAIN (each record carries ``prev_hash``), so any
       reorder, edit, or insertion is detectable by ``verify_chain``.
     - A monotonic guard rejects any append whose anchor time is earlier than
       the last record's anchor time.
4. If commitment fails (e.g. the match has already kicked off, or the ledger is
   tampered), the caller is told so it can flag the prediction UNATTESTED rather
   than silently proceeding. Backdating is never performed under any circumstance.

The ledger is deliberately append-only JSONL. It does not delete or rewrite.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


GENESIS_PREV_HASH = "0" * 64


class AttestationError(Exception):
    """Raised when a commitment/reveal cannot be created honestly.

    The caller MUST treat this as "prediction is unattested" — never as a
    reason to backdate or fabricate a commitment.
    """


class LedgerTamperError(AttestationError):
    """Raised when the on-disk ledger fails chain verification."""


def _canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_commitment_hash(
    *,
    prediction_id: str,
    fixture_id: str,
    model: str,
    p_over: Optional[float],
    p_under: Optional[float],
    reference_price: Optional[dict],
    prediction_timestamp: str,
) -> str:
    """Commitment hash binding prediction + fixture + reference price + timestamp.

    ``reference_price`` is the market reference used for the edge claim — e.g.
    ``{"book": "betfair-exchange", "over_odds": 1.95, "under_odds": 2.02,
    "fair_p_over": 0.51}``. It may be ``None`` for pipelines that log no odds
    (the corners/cards quarantine loop), in which case the hash still binds the
    prediction content and timestamp. When present, the reference price is part
    of the cryptographic commitment so the edge claim cannot be re-benchmarked
    after the fact against a different price.
    """
    canonical = _canonical_json({
        "prediction_id": prediction_id,
        "fixture_id": str(fixture_id),
        "model": model,
        "p_over": p_over,
        "p_under": p_under,
        "reference_price": reference_price,
        "prediction_timestamp": prediction_timestamp,
    })
    return _sha256(canonical)


def compute_reveal_hash(
    *,
    commitment_hash: str,
    prediction_id: str,
    fixture_id: str,
    model: str,
    outcome: dict,
    settled_at: str,
) -> str:
    """Reveal hash binding the settled outcome to the original commitment."""
    canonical = _canonical_json({
        "commitment_hash": commitment_hash,
        "prediction_id": prediction_id,
        "fixture_id": str(fixture_id),
        "model": model,
        "outcome": outcome,
        "settled_at": settled_at,
    })
    return _sha256(canonical)


def _record_link_hash(record: dict) -> str:
    """Hash of a ledger record's immutable content, for chaining.

    Excludes ``link_hash`` itself (which is derived) but includes ``prev_hash``
    so the chain is order-dependent and tamper-evident.
    """
    payload = {k: v for k, v in record.items() if k != "link_hash"}
    return _sha256(_canonical_json(payload))


@dataclass
class CommitResult:
    committed: bool
    record: Optional[dict]
    reason: Optional[str] = None


def compute_document_hash(path: Path | str) -> str:
    """SHA-256 of a file's raw bytes — used to attest a pre-registration document."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def attest_document(
    ledger_path: Path | str,
    *,
    document_path: Path | str,
    document_id: str,
    clock=time.time,
) -> dict:
    """Append an immutable, hash-chained attestation of a document (e.g. a
    pre-registration plan). Idempotent per (document_id, document_hash): if the
    exact same document is already attested, returns the existing record.

    The recorded ``anchor_unix`` is this process's clock at append time, so the
    registration time cannot be backdated. Any later edit to the document changes
    its hash, so a stale attestation is trivially detected by re-hashing the file.
    """
    ledger_path = Path(ledger_path)
    doc_hash = compute_document_hash(document_path)

    rows: list[dict] = []
    if ledger_path.exists():
        with open(ledger_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    for r in rows:
        if r.get("document_id") == document_id and r.get("document_hash") == doc_hash:
            return r  # already attested, unchanged

    now = float(clock())
    prev = rows[-1]["link_hash"] if rows else GENESIS_PREV_HASH
    record = {
        "document_id": document_id,
        "document_path": str(document_path),
        "document_hash": doc_hash,
        "anchor_unix": now,
        "registered_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "prev_hash": prev,
    }
    record["link_hash"] = _record_link_hash(record)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


class AttestationLedger:
    """Append-only, hash-chained commit/reveal ledger backed by two JSONL files.

    Commitments and reveals live in separate files but each is an independent
    hash chain. The commit ledger's anchor timestamp is authoritative and is
    always taken from ``time.time()`` at append time.
    """

    def __init__(self, commit_path: Path | str, reveal_path: Path | str,
                 clock=time.time):
        self.commit_path = Path(commit_path)
        self.reveal_path = Path(reveal_path)
        self._clock = clock

    # ── loading / verification ────────────────────────────────────────────

    @staticmethod
    def _load(path: Path) -> list[dict]:
        rows: list[dict] = []
        if path.exists():
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        return rows

    def load_commitments(self) -> list[dict]:
        return self._load(self.commit_path)

    def load_reveals(self) -> list[dict]:
        return self._load(self.reveal_path)

    def commitments_by_prediction(self) -> dict[str, dict]:
        return {r["prediction_id"]: r for r in self.load_commitments()}

    def reveals_by_prediction(self) -> dict[str, dict]:
        return {r["prediction_id"]: r for r in self.load_reveals()}

    def verify_chain(self, path: Optional[Path] = None) -> tuple[bool, list[str]]:
        """Verify the hash chain and monotonic timestamps of a ledger file.

        Returns ``(ok, problems)``. This is the mechanism that makes backdating
        and silent edits detectable: any reorder, mutation, or inserted record
        breaks the ``prev_hash`` chain or the monotonic ``anchor_unix`` guard.
        """
        target = Path(path) if path is not None else self.commit_path
        rows = self._load(target)
        problems: list[str] = []
        prev = GENESIS_PREV_HASH
        last_anchor = None
        for i, r in enumerate(rows):
            if r.get("prev_hash") != prev:
                problems.append(
                    f"row {i} ({r.get('prediction_id')}): prev_hash mismatch "
                    f"(expected {prev[:12]}, got {str(r.get('prev_hash'))[:12]})"
                )
            recomputed = _record_link_hash(r)
            if r.get("link_hash") != recomputed:
                problems.append(
                    f"row {i} ({r.get('prediction_id')}): link_hash mismatch "
                    f"— record content was altered"
                )
            anchor = r.get("anchor_unix")
            if anchor is not None and last_anchor is not None and anchor < last_anchor:
                problems.append(
                    f"row {i} ({r.get('prediction_id')}): anchor_unix {anchor} "
                    f"< previous {last_anchor} — backdating / reorder detected"
                )
            if anchor is not None:
                last_anchor = anchor
            prev = r.get("link_hash", "")
        return (len(problems) == 0, problems)

    # ── commit ────────────────────────────────────────────────────────────

    def commit(
        self,
        *,
        prediction_id: str,
        fixture_id: str,
        model: str,
        kickoff_unix: float,
        p_over: Optional[float] = None,
        p_under: Optional[float] = None,
        reference_price: Optional[dict] = None,
        prediction_timestamp: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> CommitResult:
        """Create a pre-kickoff commitment. Refuses to backdate.

        Returns a ``CommitResult``. On failure ``committed=False`` and the caller
        must flag the prediction UNATTESTED. Failure modes:
          - the match has already kicked off (``now >= kickoff_unix``)
          - the ledger fails chain verification (tampered)
          - a monotonic-timestamp violation (should not happen with a real clock)
        """
        # Anchor time is OUR clock, never caller-supplied. This is what makes
        # the "cannot be backdated" guarantee real.
        now = float(self._clock())

        if now >= float(kickoff_unix):
            return CommitResult(
                committed=False, record=None,
                reason=(
                    f"match already kicked off (now={now:.0f} >= "
                    f"kickoff={float(kickoff_unix):.0f}); cannot prove pre-kickoff "
                    f"commitment — flagging UNATTESTED, NOT backdating"
                ),
            )

        existing = self.load_commitments()
        # verify chain before appending so we never extend a tampered ledger
        ok, problems = self.verify_chain(self.commit_path)
        if not ok:
            raise LedgerTamperError(
                f"refusing to append to tampered commit ledger: {problems[:3]}"
            )

        prev_link = existing[-1]["link_hash"] if existing else GENESIS_PREV_HASH
        last_anchor = existing[-1].get("anchor_unix") if existing else None
        if last_anchor is not None and now < last_anchor:
            # Clock moved backwards; refuse rather than write a backdated record.
            return CommitResult(
                committed=False, record=None,
                reason=(f"clock regression: now={now:.0f} < last anchor "
                        f"{last_anchor:.0f}; refusing to write out-of-order record"),
            )

        pred_ts = prediction_timestamp or datetime.fromtimestamp(
            now, tz=timezone.utc
        ).isoformat()

        commitment_hash = compute_commitment_hash(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            model=model,
            p_over=p_over,
            p_under=p_under,
            reference_price=reference_price,
            prediction_timestamp=pred_ts,
        )

        record = {
            "prediction_id": prediction_id,
            "fixture_id": str(fixture_id),
            "model": model,
            "commitment_hash": commitment_hash,
            "reference_price": reference_price,
            "prediction_timestamp": pred_ts,
            "kickoff_timestamp": float(kickoff_unix),
            # anchor_* are OUR clock at append time — the attestation anchor.
            "anchor_unix": now,
            "committed_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "pre_kickoff": True,
            "prev_hash": prev_link,
        }
        if extra:
            # extra metadata must not shadow protected keys
            for k, v in extra.items():
                record.setdefault(k, v)
        record["link_hash"] = _record_link_hash(record)

        self.commit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.commit_path, "a") as f:
            f.write(json.dumps(record) + "\n")

        return CommitResult(committed=True, record=record)

    # ── reveal ──────────────────────────────────────────────────────────────

    def reveal(
        self,
        *,
        prediction_id: str,
        fixture_id: str,
        model: str,
        outcome: dict,
        settled_at: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> CommitResult:
        """Reveal a settled outcome, binding it to the prior commitment.

        Requires an existing commitment for ``prediction_id``. Refuses to reveal
        without one (an outcome with no prior commitment proves nothing).
        """
        commitments = self.commitments_by_prediction()
        commitment = commitments.get(prediction_id)
        if commitment is None:
            return CommitResult(
                committed=False, record=None,
                reason="no prior commitment exists for this prediction; "
                       "cannot reveal an unattested prediction",
            )

        reveals = self.load_reveals()
        ok, problems = self.verify_chain(self.reveal_path)
        if not ok:
            raise LedgerTamperError(
                f"refusing to append to tampered reveal ledger: {problems[:3]}"
            )
        prev_link = reveals[-1]["link_hash"] if reveals else GENESIS_PREV_HASH

        now = float(self._clock())
        settled_ts = settled_at or datetime.fromtimestamp(
            now, tz=timezone.utc
        ).isoformat()

        reveal_hash = compute_reveal_hash(
            commitment_hash=commitment["commitment_hash"],
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            model=model,
            outcome=outcome,
            settled_at=settled_ts,
        )
        record = {
            "prediction_id": prediction_id,
            "fixture_id": str(fixture_id),
            "model": model,
            "commitment_hash": commitment["commitment_hash"],
            "reveal_hash": reveal_hash,
            "outcome": outcome,
            "settled_at": settled_ts,
            "revealed_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "anchor_unix": now,
            "prev_hash": prev_link,
        }
        if extra:
            for k, v in extra.items():
                record.setdefault(k, v)
        record["link_hash"] = _record_link_hash(record)

        self.reveal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.reveal_path, "a") as f:
            f.write(json.dumps(record) + "\n")

        return CommitResult(committed=True, record=record)
