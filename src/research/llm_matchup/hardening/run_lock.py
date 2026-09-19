"""Process-level exclusive lock for live (paid) experiment runners.

Checkpoint mandate: one generation + one live experiment = one writer. A duplicate `resume()`
invocation previously ran concurrently against the same execution ledger (caught and killed
by hand during the Sonnet 4.5 resume). This module makes that structurally impossible instead
of relying on an operator noticing a stray process.

Uses `flock(2)` via `fcntl`, NOT a PID file or a boolean flag: a PID file can go stale (the
recorded PID may be reused by an unrelated process after a crash, or the file may simply be
left behind), and a boolean flag has no way to detect that its owning process died. An flock
held via an open file descriptor is released by the kernel the instant the holding process
exits for ANY reason -- normal exit, exception, or SIGKILL -- so a crashed runner can never
wedge a future run. There is no cleanup step to forget.
"""
from __future__ import annotations
import fcntl
import os


class AlreadyRunningError(Exception):
    """Raised when another process already holds the exclusive lock for this generation.
    Callers should treat this as ABORT_ALREADY_RUNNING and make zero Bedrock calls."""


class LiveRunLock:
    """`with LiveRunLock(path):` acquires an exclusive, non-blocking flock on `path`, raising
    AlreadyRunningError immediately if another live process already holds it. Safe across
    process crashes: the lock is released by the kernel when the fd closes, however that
    happens."""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self._fh = None

    def __enter__(self) -> "LiveRunLock":
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        fh = open(self.lock_path, "a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            fh.close()
            raise AlreadyRunningError(
                f"ABORT_ALREADY_RUNNING: another live runner already holds "
                f"{self.lock_path!r}; refusing to make any Bedrock call") from e
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        self._fh = fh
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._fh is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None
        return False


def acquire(lock_path: str) -> LiveRunLock:
    """`with acquire(lock_path) as lock: ...` -- raises AlreadyRunningError on contention."""
    return LiveRunLock(lock_path)
