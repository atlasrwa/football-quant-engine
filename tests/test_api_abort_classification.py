"""Tests for API abort classification — the Pilot C silent-failure bug class.

WHY THIS FILE EXISTS
====================
Pilot C ran dead for 98.7 hours because callers caught ``SystemExit`` from the API
client WITHOUT INSPECTING THE EXIT CODE and treated every abort as a deliberate,
budget-protecting stop. A missing ``THESTATS_API_KEY`` raises ``SystemExit 2``; the
discovery layer recorded it as ``"hit_request_cap": true`` and the fetch layer returned
normally, so the loop reported ``fetch_ok=true`` with zero errors while authentication
was failing. Every monitor downstream inherited that lie.

The full account is in ``public_site/failure_ledger.json`` entry F024.

The fix is that ``thestatsapi_client`` owns the classification, so no caller has to
re-derive what a code means. These tests pin that contract, because the failure mode is
not "someone writes bad code" — it is "someone writes the *obvious* code",
``except SystemExit: # cap reached``, which reads as careful error handling and is in
fact a data-integrity bug.

An exception type is not a diagnosis.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, "/home/ubuntu/scripts")

import thestatsapi_client as api  # noqa: E402


class TestExitCodeContract:
    """The exit codes the client actually raises, and what they mean."""

    def test_every_documented_code_has_a_reason(self):
        for code in (2, 3, 4, 5, 6, 7):
            reason = api.api_exit_reason(code)
            assert reason and reason != "unknown API client abort", code

    def test_only_the_request_cap_is_a_clean_stop(self):
        assert api.CLEAN_STOP_EXIT_CODES == frozenset({3})

    def test_credential_codes_cover_missing_key_and_auth_rejection(self):
        # 2 = no key at all. 6 = unexpected HTTP status, which is what a 401/403
        # rejection from a bad or expired key produces. Both are broken plumbing.
        assert api.CREDENTIAL_EXIT_CODES == frozenset({2, 6})

    @pytest.mark.parametrize("code,clean", [
        (2, False),   # THESTATS_API_KEY missing  <- the Pilot C outage
        (3, True),    # local live-request cap    <- the ONLY clean stop
        (4, False),   # network failure
        (5, False),   # rate limit persisted
        (6, False),   # unexpected HTTP / auth rejection
        (7, False),   # invalid JSON
    ])
    def test_is_clean_stop_classifies_each_code(self, code, clean):
        assert api.is_clean_stop(SystemExit(code)) is clean

    def test_a_missing_key_is_never_a_clean_stop(self):
        """The single most important assertion in this file."""
        assert not api.is_clean_stop(SystemExit(2))

    @pytest.mark.parametrize("code", [None, "boom", 0, 1, 99])
    def test_unknown_or_non_integer_codes_default_to_not_clean(self, code):
        # Fail closed: an abort we cannot classify must not be assumed benign.
        assert not api.is_clean_stop(SystemExit(code) if code is not None
                                     else SystemExit())

    def test_describe_abort_returns_code_cleanliness_and_reason(self):
        code, clean, reason = api.describe_abort(SystemExit(2))
        assert code == 2
        assert clean is False
        assert "THESTATS_API_KEY" in reason

    def test_exit_code_of_defaults_to_one(self):
        assert api.exit_code_of(SystemExit()) == 1
        assert api.exit_code_of(SystemExit("text")) == 1
        assert api.exit_code_of(SystemExit(6)) == 6


class TestDiscoveryDoesNotMisreportAuthFailureAsQuota:
    """The exact regression that produced the outage artifact.

    ``data/discovery/pilotC_discovery_status.json`` was written with
    ``"errors": ["England Championship: client abort (SystemExit 2)"]`` sitting beside
    ``"hit_request_cap": true``. Pilot C is closed, but this module is the reference
    shape for the bug, so the behaviour is pinned rather than left to a comment.
    """

    def _run_with_exit(self, code):
        import pilotC_fixture_discovery as disc

        with tempfile.TemporaryDirectory() as tmp:
            status = Path(tmp) / "status.json"
            log = Path(tmp) / "log.jsonl"
            orig = (disc.STATUS_FILE, disc.DISCOVERY_LOG,
                    disc._fetch_league_scheduled)
            disc.STATUS_FILE, disc.DISCOVERY_LOG = status, log
            disc._fetch_league_scheduled = lambda *a, **k: (_ for _ in ()).throw(
                SystemExit(code))
            raised = None
            try:
                disc.discover(dry_run=False)
            except SystemExit as exc:
                raised = api.exit_code_of(exc)
            finally:
                (disc.STATUS_FILE, disc.DISCOVERY_LOG,
                 disc._fetch_league_scheduled) = orig
            rec = json.loads(status.read_text()) if status.exists() else {}
        return raised, rec

    @pytest.mark.parametrize("code", [2, 6])
    def test_credential_failure_fails_the_run_loudly(self, code):
        raised, rec = self._run_with_exit(code)
        assert raised == code, "a credential failure must propagate, not be swallowed"
        assert rec.get("hit_request_cap") is False, (
            "a missing/rejected key must NEVER be recorded as a quota outcome"
        )
        assert rec.get("hard_abort") is True
        assert rec.get("state") == "failed"
        assert api.api_exit_reason(code) in (rec.get("abort_reason") or "")

    def test_a_genuine_cap_stop_is_still_a_clean_partial_run(self):
        raised, rec = self._run_with_exit(3)
        assert raised is None, "a deliberate budget stop must not fail the run"
        assert rec.get("hit_request_cap") is True
        assert not rec.get("hard_abort")


class TestForecastPriceCaptureLabelsTheCause:
    """The successor must not inherit the pattern.

    The forecast layer publishes regardless of price capture, so a provider failure
    here cannot corrupt a forecast — but it must still be reported as a failure rather
    than as a tidy budget stop, or the CLV panel silently stops filling.
    """

    def _detail_for(self, code):
        import fixture_ev_engine as ev
        import forecast_broadcast as fb

        orig = ev.capture_odds
        ev.capture_odds = lambda *a, **k: (_ for _ in ()).throw(SystemExit(code))
        try:
            _written, detail = fb.capture_prices_for_fixture(
                fixture_id="mt_x", kickoff_unix=9e9,
                config=type("C", (), {"markets": (),
                                      "horizon_hours_before_kickoff": 8})(),
                store=None, dry_run=False,
            )
        finally:
            ev.capture_odds = orig
        return detail

    def test_budget_stop_is_labelled_a_budget_stop(self):
        detail = self._detail_for(3)
        assert detail.startswith("clean budget stop")
        assert "PROVIDER FAILURE" not in detail

    @pytest.mark.parametrize("code", [2, 6])
    def test_credential_failure_is_labelled_a_provider_failure(self, code):
        detail = self._detail_for(code)
        assert detail.startswith("PROVIDER FAILURE")
        assert api.api_exit_reason(code) in detail

    def test_dry_run_never_calls_the_metered_provider(self):
        import forecast_broadcast as fb
        import fixture_ev_engine as ev

        called = []
        orig = ev.capture_odds
        ev.capture_odds = lambda *a, **k: called.append(1)
        try:
            written, detail = fb.capture_prices_for_fixture(
                fixture_id="mt_x", kickoff_unix=9e9,
                config=type("C", (), {"markets": (),
                                      "horizon_hours_before_kickoff": 8})(),
                store=None, dry_run=True,
            )
        finally:
            ev.capture_odds = orig
        assert called == [], "a dry run must not spend provider budget"
        assert written == 0
        assert "dry-run" in detail
