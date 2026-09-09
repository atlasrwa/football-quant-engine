"""Integration test: the capture runner's single-instance flock.

A 15-minute scheduler must never launch a second collector while one is still
running. The runner uses ``flock -n`` on a fixed lock file; the second holder
must fail to acquire and exit cleanly. This test reproduces that contract at
the shell level (skipped if ``flock`` is unavailable).
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap

import pytest

flock_bin = shutil.which("flock")
pytestmark = pytest.mark.skipif(flock_bin is None, reason="flock not available")


def test_second_flock_holder_is_refused(tmp_path):
    lock = tmp_path / "capture.lock"
    # First shell grabs the lock and holds it for 2s. Second shell tries a
    # non-blocking acquire and must be refused immediately.
    script = textwrap.dedent(
        f"""
        set -e
        ( exec 9>"{lock}"; flock -n 9; sleep 2 ) &
        HOLDER=$!
        sleep 0.4
        if flock -n "{lock}" -c 'true'; then
            echo ACQUIRED_SECOND
        else
            echo REFUSED_SECOND
        fi
        wait $HOLDER
        """
    )
    out = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=30
    )
    assert "REFUSED_SECOND" in out.stdout
    assert "ACQUIRED_SECOND" not in out.stdout


def test_lock_released_allows_next_acquire(tmp_path):
    lock = tmp_path / "capture.lock"
    script = textwrap.dedent(
        f"""
        set -e
        ( exec 9>"{lock}"; flock -n 9; true ) &
        wait
        # After the first holder exits, a fresh non-blocking acquire succeeds.
        if flock -n "{lock}" -c 'true'; then
            echo ACQUIRED_AFTER_RELEASE
        else
            echo STILL_LOCKED
        fi
        """
    )
    out = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=30
    )
    assert "ACQUIRED_AFTER_RELEASE" in out.stdout
