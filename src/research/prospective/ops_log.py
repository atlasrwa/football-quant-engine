"""Operational run logging for the prospective collector (separate from research).

Every scheduler invocation of ``capture-due`` appends ONE structured record
here describing HOW THE RUN WENT (timing, counts, quota, health). This is
deliberately kept apart from the append-only research capture store
(``data/prospective/captures.jsonl.gz``): operational metadata must never leak
into model inputs, and it has a different lifecycle (bounded, rotated) than the
research observations (permanent provenance).

Design constraints:

- Append-only JSONL, one object per run. Never rewrites earlier lines.
- Bounded growth: size-based rotation with a small retained history, so a
  15-minute cadence cannot grow the file without limit.
- Never stores secrets. Only the fields enumerated below are written.
- ``quota_remaining`` is the monthly remaining read from the LIVE response
  headers when available, else ``None`` (never fabricated / coerced to 0).

The scheduler-health command (:mod:`src.research.prospective.scheduler_health`)
reads this log to decide whether a functioning API but a DEAD timer is healthy
(it is not).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional


#: Default location of the operational run log (git-ignored data dir).
DEFAULT_OPS_LOG = Path("data/prospective/ops_runs.jsonl")

#: Rotation policy. Small: a run record is a few hundred bytes; 5 MB across a
#: couple of files is many thousands of runs, far more than the health command
#: needs (it only reads the tail). Chosen for bounded growth, not tuned.
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


@dataclass(frozen=True)
class OpsRunRecord:
    """One operational run's metadata. Never part of any model input."""

    run_started_at: float
    run_finished_at: float
    duration_seconds: float
    exit_status: str  # OK | PARTIAL_FAILURE | QUOTA_LIMITED | AUTH_FAILED | ERROR | LOCKED
    health_state: str  # the collector's own health label for the run
    fixtures_discovered: int = 0
    fixtures_inside_horizon: int = 0
    fixtures_due: int = 0
    odds_captured: int = 0
    lineups_captured: int = 0
    availability_captured: int = 0
    referees_captured: int = 0
    errors: int = 0
    quota_remaining: Optional[int] = None
    quota_limited: bool = False
    competitions_active: int = 0
    hostname: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _rotate_if_needed(path: Path, *, max_bytes: int = MAX_BYTES, backups: int = BACKUP_COUNT) -> None:
    """Size-based rotation: ops_runs.jsonl -> ops_runs.jsonl.1 -> ... (bounded)."""
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return
    except OSError:  # pragma: no cover - stat race
        return

    def _numbered(n: int) -> Path:
        return path.parent / f"{path.name}.{n}"

    # Drop the oldest, shift the rest up by one.
    oldest = _numbered(backups)
    if oldest.exists():
        try:
            oldest.unlink()
        except OSError:  # pragma: no cover
            pass
    for i in range(backups - 1, 0, -1):
        src = _numbered(i)
        dst = _numbered(i + 1)
        if src.exists():
            src.replace(dst)
    path.replace(_numbered(1))


def append_run(record: OpsRunRecord, *, path: Path = DEFAULT_OPS_LOG) -> None:
    """Append one run record as a JSON line, rotating first if oversized.

    Fails soft: an ops-logging failure must never crash a capture run (the
    research capture already happened and is what matters). We swallow write
    errors after best-effort, since this is diagnostic metadata.
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(path, max_bytes=MAX_BYTES)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), separators=(",", ":")) + "\n")
    except OSError:  # pragma: no cover - diagnostic best-effort
        pass


def read_runs(*, path: Path = DEFAULT_OPS_LOG, limit: Optional[int] = None) -> List[OpsRunRecord]:
    """Read run records (oldest-first). ``limit`` keeps only the most recent N.

    Only reads the active file; rotated backups are historical and not needed
    by the health command. Malformed lines are skipped, never guessed.
    """
    path = Path(path)
    out: List[OpsRunRecord] = []
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.append(_record_from_dict(d))
    if limit is not None and limit > 0:
        out = out[-limit:]
    return out


def iter_runs(*, path: Path = DEFAULT_OPS_LOG) -> Iterator[OpsRunRecord]:
    yield from read_runs(path=path)


def latest_run(*, path: Path = DEFAULT_OPS_LOG) -> Optional[OpsRunRecord]:
    runs = read_runs(path=path, limit=1)
    return runs[-1] if runs else None


def _record_from_dict(d: dict) -> OpsRunRecord:
    known = OpsRunRecord.__dataclass_fields__  # type: ignore[attr-defined]
    filtered = {k: v for k, v in d.items() if k in known}
    return OpsRunRecord(**filtered)


def hostname() -> str:
    """Best-effort short hostname for provenance (never a secret)."""
    try:
        return os.uname().nodename
    except Exception:  # pragma: no cover
        return "unknown"
