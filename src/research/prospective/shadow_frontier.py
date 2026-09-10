"""Persisted live-processing frontier for prospective shadow instrumentation.

This module establishes and persists the moment the shadow instrumentation
became OPERATIONAL — the "prospective frontier" ``F``. It exists to close a
provenance hole: PIT-reconstructability is NOT the same as having been
prospectively frozen while live.

Why a frontier is required
--------------------------
A shadow candidate is only legitimately ``PROSPECTIVE_SHADOW`` if the
instrumentation was actually running and froze the candidate WHILE IT WAS LIVE
(i.e. before that fixture's market had moved on / kicked off). A processor run
executed for the first time AFTER historical candidate data already exists must
never be able to retroactively relabel that historical model<->market join as
"prospectively frozen", even though every underlying input was captured
PIT-safe.

The frontier is the smallest robust mechanism that establishes this: a single
persisted timestamp ``F`` recorded the first time a live processing run occurs.

Prospective-eligibility rule
-----------------------------
A candidate frozen at information cutoff ``T`` (the observed_at of the market
snapshot it was frozen against) may be ``PROSPECTIVE_SHADOW`` only if::

    T >= F   (the candidate was frozen at/after the instrumentation went live)

Candidates with ``T < F`` are pre-frontier history. They are NEVER emitted as
prospective; they may only ever be produced explicitly as
``RECONSTRUCTED_SHADOW`` (diagnostics).

Establishment & restart survival
---------------------------------
- The frontier is established exactly once, on the first live processing run,
  and persisted to :data:`FRONTIER_FILENAME` under the shadow root. Once
  written it is immutable: subsequent live runs load and reuse it, so a
  restart / reboot preserves the exact same frontier and therefore the exact
  same prospective/reconstructed partition of history.
- The file records the establishing timestamp, an ISO mirror for humans, and
  an integrity hash over the payload.

Fail-closed semantics
---------------------
- Missing frontier on a live run: this is only legitimate on genuine first
  deployment, so we ESTABLISH a fresh frontier at "now" and admit only
  candidates at/after it. Pre-existing history (T < now) is therefore excluded
  from prospective, never silently relabeled.
- Corrupt / tampered / unreadable frontier: we REFUSE to treat any candidate as
  prospective (raise :class:`ShadowFrontierError`). We never fall back to a
  permissive "everything is prospective" behavior and never rewrite history
  prospective.

No provider calls, no network, no model. Pure persisted operational state.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: Frontier state file (git-ignored research/ops data dir, like the ledgers).
FRONTIER_FILENAME = "shadow_frontier.json"
FRONTIER_CONTRACT_VERSION = "shadow-frontier/v1"


class ShadowFrontierError(RuntimeError):
    """Raised when the frontier state exists but cannot be trusted.

    A live prospective run that hits this MUST fail closed: no candidate may be
    classified prospective. History is never relabeled as a side effect.
    """


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def _integrity_hash(established_at: float) -> str:
    """Deterministic integrity hash pinning the establishing timestamp.

    Detects truncation / hand-editing / corruption of the frontier file so a
    tampered frontier fails closed rather than silently shifting the boundary.
    """
    payload = json.dumps(
        {
            "contract": FRONTIER_CONTRACT_VERSION,
            "established_at": round(float(established_at), 6),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ShadowFrontier:
    """The persisted moment shadow instrumentation became operational."""

    established_at: float

    def to_dict(self) -> dict:
        return {
            "contract_version": FRONTIER_CONTRACT_VERSION,
            "established_at": float(self.established_at),
            "established_at_iso": _iso(self.established_at),
            "integrity_hash": _integrity_hash(self.established_at),
        }

    def allows_prospective(self, information_cutoff: float) -> bool:
        """Whether a candidate frozen at ``information_cutoff`` may be prospective.

        Only candidates whose freeze instant is at/after the frontier were
        frozen while the instrumentation was live.
        """
        return float(information_cutoff) >= self.established_at


def frontier_path(shadow_root: Path) -> Path:
    return Path(shadow_root) / FRONTIER_FILENAME


def load_frontier(shadow_root: Path) -> Optional[ShadowFrontier]:
    """Load the persisted frontier, or ``None`` if it has never been established.

    Raises:
        ShadowFrontierError: if the file exists but is unreadable, malformed, or
            fails its integrity check (fail closed — never trust a bad file).
    """
    path = frontier_path(shadow_root)
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # unreadable => cannot trust => fail closed
        raise ShadowFrontierError(f"frontier unreadable at {path}: {exc}") from exc
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ShadowFrontierError(f"frontier corrupt (invalid JSON) at {path}") from exc
    if not isinstance(d, dict):
        raise ShadowFrontierError(f"frontier corrupt (not an object) at {path}")
    established_at = d.get("established_at")
    stored_hash = d.get("integrity_hash")
    if established_at is None or stored_hash is None:
        raise ShadowFrontierError(f"frontier corrupt (missing fields) at {path}")
    try:
        established_at = float(established_at)
    except (TypeError, ValueError) as exc:
        raise ShadowFrontierError(f"frontier corrupt (bad timestamp) at {path}") from exc
    if _integrity_hash(established_at) != stored_hash:
        raise ShadowFrontierError(
            f"frontier integrity check failed at {path}; refusing to trust it"
        )
    return ShadowFrontier(established_at=established_at)


def _atomic_write(path: Path, payload: str) -> None:
    """Write the frontier atomically so a crash cannot leave a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def establish_frontier(shadow_root: Path, *, now: Optional[float] = None) -> ShadowFrontier:
    """Establish the frontier at ``now`` if absent; otherwise return the existing one.

    Idempotent and immutable: once a frontier exists it is NEVER moved, so a
    restart/reboot preserves the exact prospective/reconstructed partition. A
    corrupt existing frontier raises (fail closed) rather than being overwritten.
    """
    existing = load_frontier(shadow_root)  # raises on corrupt (fail closed)
    if existing is not None:
        return existing
    ts = time.time() if now is None else float(now)
    frontier = ShadowFrontier(established_at=ts)
    _atomic_write(
        frontier_path(shadow_root),
        json.dumps(frontier.to_dict(), separators=(",", ":")),
    )
    return frontier
