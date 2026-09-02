"""Public attestation for calibrated predictions — a SEPARATE, isolated ledger.

Every published calibrated prediction is committed pre-kickoff, hash-bound to the
prediction + fixture + timestamp, anchored from the ledger's own clock, and NEVER
backdated. After the match it is revealed and settled. Settled predictions are
published **whether they were right or wrong** — publishing only the hits is
exactly what makes tipster records worthless.

Structural isolation (the ground rule)
=======================================
This ledger is STRUCTURALLY separate from Pilot C, Pipeline A, the manual
predictor, and the edge scanner — the same isolation discipline already
established and test-enforced elsewhere:

* **Literal filenames, no directory globbing.** The ledger paths below are
  hard-coded literals containing ``calibrated_`` and none of the reserved
  basenames (``pilotC_*`` / ``manual_*`` / ``scanner_*`` / bare
  ``commitments.jsonl``). This module never globs ``data/forward/``.
* **Namespaced prediction ids.** Every id is prefixed ``calibrated:`` via
  :func:`calibrated_prediction_id`, so even a hypothetical file mixup could not
  collide with another pipeline's ids.

``tests/test_calibrated_exclusion.py`` enforces both facts against the real code.

This module does NOT touch Pilot C's ledger, cron, pre-registration, or forward
collection. It reuses the shared commit-reveal infrastructure
(:class:`src.research.forward.attestation_ledger.AttestationLedger`) only as a
building block, with its own literal paths.

Independent verifiability
==========================
Anyone can recompute a published commitment hash from the published prediction
and confirm it against the chain — they do not have to trust a displayed string.
See :func:`verify_commitment` and the recipe in :data:`VERIFICATION_RECIPE`.

NO STAKE SIZING: this module attests probabilities. It never records or derives a
stake, Kelly fraction, or bankroll figure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.research.forward.attestation_ledger import (
    AttestationLedger,
    CommitResult,
    compute_commitment_hash,
)

# ─────────────────────────────────────────────────────────────────────────────
# Literal, isolated ledger paths (NO globbing, distinct basenames)
# ─────────────────────────────────────────────────────────────────────────────
_FORWARD_DIR = "/home/ubuntu/data/forward"

#: Commit chain for published calibrated predictions.
CALIBRATED_COMMIT_LEDGER = f"{_FORWARD_DIR}/calibrated_commitments.jsonl"
#: Reveal chain (settled outcomes) for published calibrated predictions.
CALIBRATED_REVEAL_LEDGER = f"{_FORWARD_DIR}/calibrated_reveals.jsonl"
#: Human/consumer-facing published predictions log (append-only).
CALIBRATED_PREDICTIONS_LOG = f"{_FORWARD_DIR}/calibrated_predictions.jsonl"
#: Settled-outcomes log — published whether the prediction was right OR wrong.
CALIBRATED_SETTLED_LOG = f"{_FORWARD_DIR}/calibrated_settled_log.json"

#: The namespace every calibrated prediction id carries.
CALIBRATED_ID_PREFIX = "calibrated:"

#: The model tag recorded on calibrated attestations.
CALIBRATED_MODEL_TAG = "calibrated_prediction_engine"


def calibrated_prediction_id(fixture_id: str, market: str, kind: str = "prob") -> str:
    """Build a namespaced calibrated prediction id.

    Format: ``calibrated:<fixture_id>:<market>:<kind>`` — e.g.
    ``calibrated:mt_12345:corners:prob`` or ``...:corners:direction``. The
    ``calibrated:`` prefix guarantees ids never collide with ``pilotC:`` /
    ``manual:`` / ``flagged:``.
    """
    return f"{CALIBRATED_ID_PREFIX}{fixture_id}:{market}:{kind}"


# ─────────────────────────────────────────────────────────────────────────────
# The isolated ledger wrapper
# ─────────────────────────────────────────────────────────────────────────────
class CalibratedAttestationLedger:
    """A commit-reveal ledger dedicated to published calibrated predictions.

    Thin wrapper over the shared :class:`AttestationLedger` bound to the literal
    ``calibrated_*`` paths. All behaviour (pre-kickoff enforcement, own-clock
    anchor, no backdating, hash chain, tamper detection) comes from the shared
    ledger; this class only fixes the paths, the ``calibrated:`` namespace, and
    the "publish whether right or wrong" settlement policy.
    """

    def __init__(
        self,
        *,
        commit_path: str = CALIBRATED_COMMIT_LEDGER,
        reveal_path: str = CALIBRATED_REVEAL_LEDGER,
        settled_log: str = CALIBRATED_SETTLED_LOG,
        clock=None,
    ) -> None:
        # Reject any attempt to point this at another pipeline's ledger.
        for p in (commit_path, reveal_path, settled_log):
            base = Path(p).name
            for reserved in ("pilotC_", "manual_", "scanner_"):
                if reserved in base:
                    raise ValueError(
                        f"refusing to use a reserved ledger basename {base!r}: the "
                        "calibrated ledger must stay structurally isolated"
                    )
            if base == "commitments.jsonl":
                raise ValueError(
                    "refusing to use the bare Pipeline A ledger 'commitments.jsonl'"
                )
        self._settled_log = Path(settled_log)
        if clock is not None:
            self._ledger = AttestationLedger(
                commit_path=commit_path, reveal_path=reveal_path, clock=clock
            )
        else:
            self._ledger = AttestationLedger(
                commit_path=commit_path, reveal_path=reveal_path
            )

    @property
    def ledger(self) -> AttestationLedger:
        return self._ledger

    # ── commit (pre-kickoff, never backdated) ───────────────────────────────
    def commit_prediction(
        self,
        *,
        fixture_id: str,
        market: str,
        kickoff_unix: float,
        p_over: Optional[float] = None,
        p_under: Optional[float] = None,
        kind: str = "prob",
        extra: Optional[dict] = None,
    ) -> CommitResult:
        """Commit a calibrated prediction before kickoff.

        The prediction id is namespaced ``calibrated:``. No ``reference_price`` is
        recorded — this engine makes NO market claim, so its commitments bind only
        the prediction content and timestamp (``reference_price=None``). Returns
        the shared :class:`CommitResult`; on ``committed=False`` the caller MUST
        flag the prediction unattested and MUST NOT backdate.
        """
        pid = calibrated_prediction_id(fixture_id, market, kind)
        # Persist p_over/p_under in the record so the commitment hash is
        # INDEPENDENTLY recomputable from the published record alone (the base
        # ledger uses them only to compute the hash, not to store them).
        merged_extra = {
            "market": market,
            "kind": kind,
            "p_over": p_over,
            "p_under": p_under,
        }
        if extra:
            merged_extra.update(extra)
        return self._ledger.commit(
            prediction_id=pid,
            fixture_id=fixture_id,
            model=CALIBRATED_MODEL_TAG,
            kickoff_unix=kickoff_unix,
            p_over=p_over,
            p_under=p_under,
            reference_price=None,  # no market comparison; not a product claim
            extra=merged_extra,
        )

    # ── reveal + settle (publish whether right or wrong) ─────────────────────
    def settle_prediction(
        self,
        *,
        fixture_id: str,
        market: str,
        outcome: dict,
        kind: str = "prob",
        extra: Optional[dict] = None,
    ) -> CommitResult:
        """Reveal and settle a previously committed calibrated prediction.

        The ``outcome`` dict should carry the realised result (e.g.
        ``{"actual_value": 11, "over_line": 9.5, "hit": True}``). The prediction is
        settled and published **whether it was right or wrong** — see
        :meth:`publish_settled`. Requires a prior commitment (else
        ``committed=False``); an outcome with no commitment proves nothing.
        """
        pid = calibrated_prediction_id(fixture_id, market, kind)
        res = self._ledger.reveal(
            prediction_id=pid,
            fixture_id=fixture_id,
            model=CALIBRATED_MODEL_TAG,
            outcome=outcome,
            extra=extra,
        )
        if res.committed:
            self.publish_settled(pid, fixture_id, market, outcome, kind=kind)
        return res

    def publish_settled(
        self,
        prediction_id: str,
        fixture_id: str,
        market: str,
        outcome: dict,
        *,
        kind: str = "prob",
    ) -> None:
        """Append a settled row to the public settled log — hit OR miss.

        Publishing only the hits is exactly what makes tipster records worthless,
        so every settled prediction is recorded here regardless of ``outcome``.
        """
        row = {
            "prediction_id": prediction_id,
            "fixture_id": str(fixture_id),
            "market": market,
            "kind": kind,
            "outcome": outcome,
        }
        self._settled_log.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {"settled": []}
        if self._settled_log.exists():
            try:
                existing = json.loads(self._settled_log.read_text())
            except (json.JSONDecodeError, ValueError):
                existing = {"settled": []}
        existing.setdefault("settled", []).append(row)
        existing["n_settled_total"] = len(existing["settled"])
        self._settled_log.write_text(json.dumps(existing, indent=2))

    # ── verification passthroughs ────────────────────────────────────────────
    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify the commit chain (tamper detection)."""
        return self._ledger.verify_chain()

    def commitments_by_prediction(self) -> dict[str, dict]:
        return self._ledger.commitments_by_prediction()

    def reveals_by_prediction(self) -> dict[str, dict]:
        return self._ledger.reveals_by_prediction()


# ─────────────────────────────────────────────────────────────────────────────
# Independent verification (recompute the hash from the published record)
# ─────────────────────────────────────────────────────────────────────────────
VERIFICATION_RECIPE = (
    "To verify a published calibrated prediction WITHOUT trusting the displayed "
    "hash:\n"
    "  1. Take the published commitment record's fields: prediction_id, "
    "fixture_id, model, p_over, p_under, reference_price (null for this engine), "
    "and prediction_timestamp.\n"
    "  2. Canonicalise them as JSON with sort_keys=True and separators (',',':') "
    "— i.e. compute_commitment_hash(...) in "
    "src.research.forward.attestation_ledger.\n"
    "  3. SHA-256 the canonical bytes. The result MUST equal the record's "
    "commitment_hash.\n"
    "  4. Confirm chain integrity: each record's prev_hash equals the prior "
    "record's link_hash, each link_hash recomputes, and anchor_unix is "
    "non-decreasing (verify_chain()). A pre-kickoff commitment has "
    "anchor_unix < kickoff_timestamp.\n"
    "Because the anchor is the ledger's own clock at append time and the chain is "
    "tamper-evident, a commitment cannot be backdated or edited undetected."
)


@dataclass(frozen=True)
class VerificationResult:
    """The outcome of independently verifying one committed prediction."""

    prediction_id: str
    found: bool
    recomputed_matches: bool
    recomputed_hash: Optional[str]
    stored_hash: Optional[str]
    pre_kickoff: Optional[bool]
    chain_ok: bool


def verify_commitment(
    prediction_id: str,
    *,
    commit_path: str = CALIBRATED_COMMIT_LEDGER,
    reveal_path: str = CALIBRATED_REVEAL_LEDGER,
) -> VerificationResult:
    """Independently recompute a commitment's hash from the record alone.

    This is the machine form of :data:`VERIFICATION_RECIPE`: it re-derives the
    commitment hash from the stored fields and checks it against the stored
    ``commitment_hash``, confirms the record is pre-kickoff, and verifies the
    whole commit chain. It trusts nothing but the record's own content.
    """
    ledger = AttestationLedger(commit_path=commit_path, reveal_path=reveal_path)
    record = ledger.commitments_by_prediction().get(prediction_id)
    chain_ok, _ = ledger.verify_chain()
    if record is None:
        return VerificationResult(
            prediction_id=prediction_id, found=False, recomputed_matches=False,
            recomputed_hash=None, stored_hash=None, pre_kickoff=None,
            chain_ok=chain_ok,
        )
    recomputed = compute_commitment_hash(
        prediction_id=record["prediction_id"],
        fixture_id=record["fixture_id"],
        model=record["model"],
        p_over=record.get("p_over"),
        p_under=record.get("p_under"),
        reference_price=record.get("reference_price"),
        prediction_timestamp=record["prediction_timestamp"],
    )
    stored = record.get("commitment_hash")
    pre_kickoff = (
        record.get("anchor_unix") is not None
        and record.get("kickoff_timestamp") is not None
        and float(record["anchor_unix"]) < float(record["kickoff_timestamp"])
    )
    return VerificationResult(
        prediction_id=prediction_id,
        found=True,
        recomputed_matches=(recomputed == stored),
        recomputed_hash=recomputed,
        stored_hash=stored,
        pre_kickoff=pre_kickoff,
        chain_ok=chain_ok,
    )
