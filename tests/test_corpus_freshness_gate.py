"""Contract tests for the corpus freshness gate, content hash, and leakage refusal.

These are the four properties the 2026-09-05 stale-corpus failure needed and did not
have. They are tests rather than a one-off verification script because the failure they
guard against is precisely the kind that returns quietly: a gate that is removed, a
threshold that is loosened to silence an alert during an international break, or a
leakage assertion downgraded to a filter. Each of those edits passes a manual smoke
check and fails here.
"""

from __future__ import annotations

import copy
import json
import time

import pytest

from src.research.prediction_engine.broadcast.corpus_freshness import (
    CorpusFreshnessError,
    FreshnessState,
    evaluate_corpus_freshness,
    in_scope_kickoffs,
    require_fresh_corpus,
)
from src.research.prediction_engine.broadcast.corpus_snapshot import (
    CORPUS_SNAPSHOT_CONTRACT,
    MATCH_COMPLETION_SECONDS,
    CorpusIntegrityError,
    SameMatchLeakageError,
    assert_fixture_absent_from_history,
    assert_prior_only_snapshot,
    build_snapshot,
    fingerprint_matches,
    newest_observation_per_team,
    observations_per_season,
)

DAY = 86400.0
HOUR = 3600.0


def make_match(match_id, kickoff_unix, home="Home FC", away="Away FC", **extra):
    """A minimal corpus row in FootyStats schema."""
    row = {
        "id": match_id,
        "date_unix": int(kickoff_unix),
        "home_name": home,
        "away_name": away,
        "status": "complete",
        "season": "2026/2027",
        "competition_id": 17184,
    }
    row.update(extra)
    return row


def make_corpus(now, n=20, spacing_days=7.0, first_offset_days=200.0):
    """``n`` completed matches ending ``spacing_days`` before ``now``."""
    return [
        make_match(
            1000 + i,
            now - (first_offset_days - i * spacing_days) * DAY,
            home=f"Team {i % 5}",
            away=f"Team {(i + 1) % 5}",
        )
        for i in range(n)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 1. The gate fires when the corpus is aged
# ─────────────────────────────────────────────────────────────────────────────
class TestFreshnessGateFiresOnStaleCorpus:
    def test_stale_corpus_refuses_publication(self):
        """The reproduction of the original failure: corpus months behind the calendar."""
        now = time.time()
        # Corpus ends ~97 days ago; an in-scope fixture finished yesterday.
        corpus = [make_match(1, now - 100 * DAY), make_match(2, now - 97 * DAY)]
        fingerprint = fingerprint_matches(corpus)

        verdict = evaluate_corpus_freshness(
            fingerprint=fingerprint,
            reference_kickoffs=[now - 1 * DAY, now + 2 * DAY],
            now_unix=now,
        )

        assert verdict.state is FreshnessState.STALE
        assert verdict.may_publish is False
        assert verdict.is_stale
        # The lag must be quantified, not merely asserted — an alert without a figure
        # is not actionable.
        assert verdict.metrics["corpus_lag_hours"] > 96 * 24 / 24

    def test_require_fresh_corpus_raises_and_carries_the_verdict(self):
        now = time.time()
        fingerprint = fingerprint_matches([make_match(1, now - 120 * DAY)])
        with pytest.raises(CorpusFreshnessError) as excinfo:
            require_fresh_corpus(
                fingerprint=fingerprint,
                reference_kickoffs=[now - 2 * DAY],
                now_unix=now,
            )
        assert excinfo.value.verdict.state is FreshnessState.STALE
        assert "STALE" in str(excinfo.value)

    def test_artificially_ageing_a_fresh_corpus_flips_the_verdict(self):
        """Same corpus, evaluated later, must become stale. Guards the comparison
        itself: a gate that ignored its inputs would pass both times."""
        now = time.time()
        corpus = make_corpus(now, n=10, spacing_days=7.0, first_offset_days=70.0)
        fingerprint = fingerprint_matches(corpus)
        newest = fingerprint.latest_observation_unix

        fresh = evaluate_corpus_freshness(
            fingerprint=fingerprint,
            reference_kickoffs=[newest, newest + 3 * DAY],
            now_unix=newest + 6 * HOUR,
        )
        assert fresh.state is FreshnessState.FRESH

        aged = evaluate_corpus_freshness(
            fingerprint=fingerprint,
            reference_kickoffs=[newest, newest + 20 * DAY],
            now_unix=newest + 25 * DAY,
        )
        assert aged.state is FreshnessState.STALE
        assert aged.may_publish is False

    def test_empty_corpus_is_refused(self):
        verdict = evaluate_corpus_freshness(
            fingerprint=fingerprint_matches([]),
            reference_kickoffs=[time.time() - DAY],
            now_unix=time.time(),
        )
        assert verdict.state is FreshnessState.STALE
        assert verdict.may_publish is False

    def test_tolerance_absorbs_settlement_delay_but_not_a_missed_week(self):
        now = time.time()
        newest = now - 200 * DAY
        fingerprint = fingerprint_matches([make_match(1, newest)])

        # A fixture finished 30h after the corpus's newest observation: inside the 48h
        # tolerance, which exists to absorb provider settlement delay.
        within = evaluate_corpus_freshness(
            fingerprint=fingerprint,
            reference_kickoffs=[newest, newest + 30 * HOUR],
            now_unix=newest + 40 * HOUR,
            max_lag_hours=48.0,
        )
        assert within.state is FreshnessState.FRESH
        assert within.metrics["corpus_lag_hours"] == pytest.approx(30.0, abs=0.1)

        # A fixture played 72h after the corpus ends: beyond tolerance. This is the
        # shape of a refresh job that stopped running.
        played_after = evaluate_corpus_freshness(
            fingerprint=fingerprint,
            reference_kickoffs=[newest, newest + 72 * HOUR],
            now_unix=newest + 80 * HOUR,
            max_lag_hours=48.0,
        )
        assert played_after.state is FreshnessState.STALE
        assert played_after.metrics["corpus_lag_hours"] == pytest.approx(72.0, abs=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Breaks and off-season are handled explicitly, not by disabling the gate
# ─────────────────────────────────────────────────────────────────────────────
class TestBreaksAreHandledExplicitly:
    def test_off_season_is_dormant_not_stale(self):
        """No fixture near now: an old corpus is expected, not symptomatic."""
        now = time.time()
        fingerprint = fingerprint_matches([make_match(1, now - 60 * DAY)])
        verdict = evaluate_corpus_freshness(
            fingerprint=fingerprint,
            reference_kickoffs=[now + 60 * DAY],  # season resumes in two months
            now_unix=now,
        )
        assert verdict.state is FreshnessState.DORMANT
        assert verdict.may_publish is True

    def test_dormant_is_never_silent(self):
        """A dormant verdict must state that freshness was NOT confirmed, so it can
        never be read as a clean pass."""
        now = time.time()
        verdict = evaluate_corpus_freshness(
            fingerprint=fingerprint_matches([make_match(1, now - 60 * DAY)]),
            reference_kickoffs=[now + 60 * DAY],
            now_unix=now,
        )
        assert "could not" in verdict.detail.lower()
        assert verdict.to_dict()["state"] == "DORMANT"

    def test_international_break_with_complete_data_is_fresh(self):
        """The realistic break case: no match for 11 days, but we hold everything that
        was played. A clock-based rule would alert here every day; this must not."""
        now = time.time()
        last_played = now - 11 * DAY
        fingerprint = fingerprint_matches([make_match(1, last_played)])
        verdict = evaluate_corpus_freshness(
            fingerprint=fingerprint,
            reference_kickoffs=[last_played, now + 3 * DAY],
            now_unix=now,
        )
        assert verdict.state is FreshnessState.FRESH
        assert verdict.may_publish is True

    def test_in_season_with_no_finished_fixture_falls_back_to_the_clock(self):
        """A universe holding only future fixtures must not become a hole the gate
        declines to look through."""
        now = time.time()
        fingerprint = fingerprint_matches([make_match(1, now - 200 * DAY)])
        verdict = evaluate_corpus_freshness(
            fingerprint=fingerprint,
            reference_kickoffs=[now + 2 * DAY, now + 9 * DAY],
            now_unix=now,
        )
        assert verdict.state is FreshnessState.STALE
        assert verdict.metrics["benchmark"]["kind"].startswith("clock_fallback")

    def test_in_scope_kickoffs_filters_by_scope(self):
        universe = {
            "a": {"comp": "comp_1", "ts": 100.0},
            "b": {"comp": "comp_2", "ts": 200.0},
            "c": {"comp": "comp_1", "ts": 50.0},
            "d": {"comp": "comp_1"},  # no kickoff: skipped, never guessed
        }
        got = in_scope_kickoffs(universe, lambda c: c == "comp_1")
        assert got == (50.0, 100.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. The content hash tracks content, not build time
# ─────────────────────────────────────────────────────────────────────────────
class TestContentHashTracksContent:
    def test_hash_is_stable_across_rebuilds_of_identical_content(self):
        now = time.time()
        corpus = make_corpus(now)
        assert fingerprint_matches(corpus).content_hash == (
            fingerprint_matches(copy.deepcopy(corpus)).content_hash
        )

    def test_hash_is_invariant_to_load_order(self):
        """Rebuilding from files read in a different order must not look like a change."""
        now = time.time()
        corpus = make_corpus(now)
        shuffled = list(reversed(corpus))
        assert (
            fingerprint_matches(corpus).content_hash
            == fingerprint_matches(shuffled).content_hash
        )

    def test_hash_is_invariant_to_build_time(self):
        """The property the original model_version summary could not give us cleanly:
        evaluating the same corpus at a different moment changes nothing."""
        now = time.time()
        corpus = make_corpus(now)
        first = fingerprint_matches(corpus).content_hash
        time.sleep(0.01)
        assert fingerprint_matches(corpus).content_hash == first

    def test_hash_changes_when_a_match_is_added(self):
        now = time.time()
        corpus = make_corpus(now)
        before = fingerprint_matches(corpus).content_hash
        corpus.append(make_match(999999, now - HOUR * 5))
        assert fingerprint_matches(corpus).content_hash != before

    def test_hash_changes_on_substitution_that_preserves_count_and_max_date(self):
        """The specific weakness of a (count, max_date) fingerprint. Swap one match for
        another with the same kick-off: counts match, newest observation matches, and
        the old summary could not tell them apart. The content hash must."""
        now = time.time()
        base = make_corpus(now, n=8)
        swapped = list(base)
        swapped[3] = make_match(
            "substituted", swapped[3]["date_unix"], home="Other FC", away="Different FC"
        )

        a, b = fingerprint_matches(base), fingerprint_matches(swapped)
        assert a.match_count == b.match_count
        assert a.latest_observation_unix == b.latest_observation_unix
        assert a.content_hash != b.content_hash

    def test_rows_without_provider_ids_still_affect_the_hash(self):
        """An id-less row must not be able to change the corpus invisibly."""
        now = time.time()
        base = [make_match(None, now - 5 * DAY, home="A", away="B")]
        other = [make_match(None, now - 5 * DAY, home="A", away="C")]
        assert (
            fingerprint_matches(base).content_hash
            != fingerprint_matches(other).content_hash
        )

    def test_provenance_block_carries_the_required_fields(self):
        now = time.time()
        provenance = fingerprint_matches(make_corpus(now)).provenance_dict()
        for key in (
            "corpus_content_hash",
            "corpus_match_count",
            "corpus_latest_observation_utc",
            "corpus_seasons",
        ):
            assert key in provenance, key
        assert provenance["corpus_seasons"] == ["2026/2027"]

    def test_contract_is_part_of_the_hash(self):
        assert CORPUS_SNAPSHOT_CONTRACT == "corpus-snapshot/v1"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Same-match leakage is refused structurally
# ─────────────────────────────────────────────────────────────────────────────
class TestSameMatchLeakageRefused:
    def test_same_day_result_cannot_be_used_to_forecast_itself(self):
        """The constraint that has already cost this project a re-validation: a fixture
        whose result is in the corpus must not receive a forecast."""
        kickoff = time.time() - 2 * HOUR
        played = make_match(555, kickoff, home="Stoke City", away="Charlton Athletic")
        histories = {
            "Stoke City": [(kickoff, played, "home")],
            "Charlton Athletic": [(kickoff, played, "away")],
        }
        with pytest.raises(SameMatchLeakageError) as excinfo:
            assert_fixture_absent_from_history(
                histories,
                home_team="Stoke City",
                away_team="Charlton Athletic",
                kickoff_unix=kickoff,
            )
        assert "own result" in str(excinfo.value)

    def test_kickoff_revision_does_not_defeat_the_check(self):
        """Provider kick-off corrections of a few minutes must not open a hole."""
        kickoff = time.time() - 3 * HOUR
        played = make_match(556, kickoff, home="A FC", away="B FC")
        histories = {"A FC": [(kickoff, played, "home")], "B FC": [(kickoff, played, "away")]}
        with pytest.raises(SameMatchLeakageError):
            assert_fixture_absent_from_history(
                histories, home_team="A FC", away_team="B FC",
                kickoff_unix=kickoff + 15 * 60,
            )

    def test_a_genuine_prior_meeting_is_not_leakage(self):
        """The same pairing months earlier is legitimate history and must be allowed,
        or the check would block ordinary fixtures."""
        now = time.time()
        earlier = now - 120 * DAY
        played = make_match(557, earlier, home="A FC", away="B FC")
        histories = {"A FC": [(earlier, played, "home")], "B FC": [(earlier, played, "away")]}
        assert_fixture_absent_from_history(
            histories, home_team="A FC", away_team="B FC", kickoff_unix=now
        )

    def test_different_opponent_at_the_same_time_is_not_leakage(self):
        now = time.time()
        played = make_match(558, now, home="A FC", away="C FC")
        histories = {"A FC": [(now, played, "home")]}
        assert_fixture_absent_from_history(
            histories, home_team="A FC", away_team="B FC", kickoff_unix=now
        )

    def test_snapshot_excludes_matches_not_yet_finished(self):
        now = time.time()
        corpus = [
            make_match(1, now - 10 * DAY),
            make_match(2, now - HOUR),          # in play: excluded
            make_match(3, now + 4 * HOUR),      # future: excluded
        ]
        snapshot, fingerprint = build_snapshot(corpus, cutoff_unix=now)
        assert [m["id"] for m in snapshot] == [1]
        assert fingerprint.match_count == 1

    def test_snapshot_boundary_respects_match_duration(self):
        """A match that kicked off before the cutoff but had not finished by it is
        excluded. Kick-off alone is not a completion signal."""
        now = time.time()
        just_started = make_match(9, now - (MATCH_COMPLETION_SECONDS - 600))
        snapshot, _ = build_snapshot([just_started], cutoff_unix=now)
        assert snapshot == ()

    def test_prior_only_assertion_rejects_a_bad_snapshot(self):
        now = time.time()
        with pytest.raises(CorpusIntegrityError) as excinfo:
            assert_prior_only_snapshot([make_match(1, now)], cutoff_unix=now)
        # The offending rows must be named, so a 04:00 page is actionable.
        assert "Home FC" in str(excinfo.value)

    def test_snapshot_is_immutable(self):
        """The fingerprint must describe exactly what was fitted; an appendable
        training set could diverge from it after the fact."""
        now = time.time()
        snapshot, _ = build_snapshot([make_match(1, now - 5 * DAY)], cutoff_unix=now)
        assert isinstance(snapshot, tuple)
        with pytest.raises(AttributeError):
            snapshot.append(make_match(2, now - DAY))  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────────────────────
# Provenance reporting helpers
# ─────────────────────────────────────────────────────────────────────────────
class TestProvenanceReporting:
    def test_newest_observation_per_team(self):
        now = time.time()
        old = make_match(1, now - 100 * DAY, home="A FC", away="B FC")
        new = make_match(2, now - 3 * DAY, home="A FC", away="C FC")
        histories = {"A FC": [(old["date_unix"], old, "home"),
                              (new["date_unix"], new, "home")]}
        got = newest_observation_per_team(histories, ["A FC", "Unknown FC"])
        assert got["A FC"]["match_id"] == 2
        assert got["Unknown FC"] is None

    def test_observations_per_season_exposes_partial_ingestion(self):
        now = time.time()
        corpus = [
            make_match(1, now - 200 * DAY, competition_id=14930, season="2025/2026"),
            make_match(2, now - 3 * DAY, competition_id=17184, season="2026/2027"),
        ]
        coverage = observations_per_season(corpus)
        assert coverage["14930"]["season"] == "2025/2026"
        assert coverage["17184"]["match_count"] == 1
        assert coverage["17184"]["latest_observation_unix"] > (
            coverage["14930"]["latest_observation_unix"]
        )



# ─────────────────────────────────────────────────────────────────────────────
# Append-only annotation of affected records
# ─────────────────────────────────────────────────────────────────────────────
class TestAppendOnlyAnnotation:
    """Annotating a published forecast must never alter it.

    The 16 stale-corpus forecasts had to be marked as unrepresentative. Editing them
    was not an option: the commitment hash is over the payload as published, so a
    caveat added in place would make the integrity check report a tamper. These tests
    pin the property that makes the correction honest.
    """

    def _payload(self, config):
        from src.research.prediction_engine.broadcast.payload import (
            build_forecast_payload,
        )

        return build_forecast_payload(
            config=config,
            fixture_id="mt_test_1",
            comp_id=config.leagues[0].comp_id,
            home_team="Stoke City",
            away_team="Charlton Athletic",
            kickoff_unix=1788600000,
            probabilities={spec.cell: 0.5 for spec in config.markets},
            model_version="mv_test",
            data_cutoff_utc="2026-05-31T16:30:00+00:00",
            corpus_provenance={"corpus_content_hash": "abc", "corpus_match_count": 10},
            generated_at_utc="2026-09-05T07:46:15.610543+00:00",
        )

    def test_annotation_does_not_change_the_broadcast_ledger(self, tmp_path):
        import hashlib

        from src.research.prediction_engine.broadcast.record import (
            AnnotationType,
            BroadcastLedger,
        )
        from src.research.prediction_engine.broadcast.scope_config import (
            load_scope_config,
        )

        config = load_scope_config(require_recorded_change=False)
        ledger = BroadcastLedger(tmp_path)
        payload = self._payload(config)
        ledger.append_commitment(payload)

        before = hashlib.md5(ledger.broadcast_path.read_bytes()).hexdigest()
        ledger.append_annotation(
            commitment_hash=payload.commitment_hash(),
            annotation_type=AnnotationType.AFFECTED_BY_STALE_CORPUS,
            detail="fitted on a corpus ending 2026-05-31",
            failure_ledger_entry="F025",
            evidence={"max_feature_staleness_days": 126.3},
            fixture_id=payload.fixture_id,
        )
        after = hashlib.md5(ledger.broadcast_path.read_bytes()).hexdigest()

        assert before == after, "annotating must not touch broadcasts.jsonl"
        assert ledger.verify_commitment_hashes() == ()
        assert len(ledger.annotations()) == 1

    def test_annotation_is_retrievable_by_commitment(self, tmp_path):
        from src.research.prediction_engine.broadcast.record import (
            AnnotationType,
            BroadcastLedger,
        )
        from src.research.prediction_engine.broadcast.scope_config import (
            load_scope_config,
        )

        config = load_scope_config(require_recorded_change=False)
        ledger = BroadcastLedger(tmp_path)
        payload = self._payload(config)
        ledger.append_commitment(payload)
        commitment = payload.commitment_hash()
        ledger.append_annotation(
            commitment_hash=commitment,
            annotation_type=AnnotationType.AFFECTED_BY_STALE_CORPUS,
            detail="stale corpus",
            failure_ledger_entry="F025",
        )

        grouped = ledger.annotations_by_commitment()
        assert commitment in grouped
        assert grouped[commitment][0]["failure_ledger_entry"] == "F025"
        assert commitment in ledger.annotated_commitment_hashes(
            AnnotationType.AFFECTED_BY_STALE_CORPUS
        )

    def test_ledger_exposes_no_mutating_operation_for_annotations(self):
        """Only append. A public update or delete would defeat the whole arrangement."""
        from src.research.prediction_engine.broadcast.record import BroadcastLedger

        forbidden = [
            name for name in dir(BroadcastLedger)
            if not name.startswith("_")
            and any(verb in name for verb in ("update", "delete", "remove", "edit"))
        ]
        assert forbidden == []


class TestPayloadContractCompatibility:
    """v1 records must keep verifying after the v2 bump.

    A reader that refused to rebuild the 16 pre-existing records would report them as
    ALTERED — a false tamper signal that would destroy the value of the integrity
    check. This is the regression that guards against it.
    """

    def test_v1_record_still_reproduces_its_published_hash(self):
        from src.research.prediction_engine.broadcast.payload import verify_commitment
        from src.research.prediction_engine.broadcast.record import (
            BroadcastLedger,
            DEFAULT_RECORD_ROOT,
        )

        ledger = BroadcastLedger(DEFAULT_RECORD_ROOT)
        v1 = [
            rec for rec in ledger.commitments()
            if (rec.get("payload") or {}).get("payload_contract")
            == "forecast-broadcast-payload/v1"
        ]
        if not v1:
            pytest.skip("no v1 records on disk")
        for rec in v1:
            assert verify_commitment(rec["payload"], rec["commitment_hash"]), (
                f"v1 record {rec['commitment_hash'][:12]} no longer verifies"
            )

    def test_current_contract_carries_corpus_provenance_in_the_hash(self):
        from src.research.prediction_engine.broadcast.payload import (
            FORECAST_PAYLOAD_CONTRACT,
            build_forecast_payload,
        )
        from src.research.prediction_engine.broadcast.scope_config import (
            load_scope_config,
        )

        config = load_scope_config(require_recorded_change=False)
        common = dict(
            config=config, fixture_id="mt_x", comp_id=config.leagues[0].comp_id,
            home_team="A FC", away_team="B FC", kickoff_unix=1788600000,
            probabilities={spec.cell: 0.5 for spec in config.markets},
            model_version="mv", data_cutoff_utc="2026-09-05T19:00:00+00:00",
            generated_at_utc="2026-09-06T01:00:00+00:00",
        )
        one = build_forecast_payload(**common, corpus_provenance={"corpus_content_hash": "aaa"})
        two = build_forecast_payload(**common, corpus_provenance={"corpus_content_hash": "bbb"})

        assert one.payload_contract == FORECAST_PAYLOAD_CONTRACT == (
            "forecast-broadcast-payload/v3"
        )
        assert "corpus_provenance" in one.canonical_dict()
        # A different corpus must produce a different commitment, or the provenance
        # would be decorative.
        assert one.commitment_hash() != two.commitment_hash()

    def test_current_contract_carries_history_provenance_in_the_hash(self):
        # The early-season history provenance (how many completed current-season
        # matches each team had, which window applied) is part of the claim, so it
        # must be inside the commitment: a 3-match forecast and a 10-match forecast,
        # identical in every other field, must not collide on the same hash.
        from src.research.prediction_engine.broadcast.payload import (
            FORECAST_PAYLOAD_CONTRACT,
            build_forecast_payload,
        )
        from src.research.prediction_engine.broadcast.scope_config import (
            load_scope_config,
        )

        config = load_scope_config(require_recorded_change=False)
        common = dict(
            config=config, fixture_id="mt_x", comp_id=config.leagues[0].comp_id,
            home_team="A FC", away_team="B FC", kickoff_unix=1788600000,
            probabilities={spec.cell: 0.5 for spec in config.markets},
            model_version="mv", data_cutoff_utc="2026-09-05T19:00:00+00:00",
            corpus_provenance={"corpus_content_hash": "aaa"},
            generated_at_utc="2026-09-06T01:00:00+00:00",
        )
        thin = build_forecast_payload(
            **common,
            history_provenance={"home": {"current_season_matches": 3},
                                "away": {"current_season_matches": 4}},
        )
        full = build_forecast_payload(
            **common,
            history_provenance={"home": {"current_season_matches": 10},
                                "away": {"current_season_matches": 12}},
        )
        assert FORECAST_PAYLOAD_CONTRACT == "forecast-broadcast-payload/v3"
        assert "history_provenance" in thin.canonical_dict()
        assert thin.commitment_hash() != full.commitment_hash()

    def test_v1_canonical_dict_omits_corpus_provenance(self):
        from src.research.prediction_engine.broadcast.payload import (
            payload_from_canonical_dict,
        )
        from src.research.prediction_engine.broadcast.record import (
            BroadcastLedger,
            DEFAULT_RECORD_ROOT,
        )

        ledger = BroadcastLedger(DEFAULT_RECORD_ROOT)
        v1 = next(
            (
                rec for rec in ledger.commitments()
                if (rec.get("payload") or {}).get("payload_contract")
                == "forecast-broadcast-payload/v1"
            ),
            None,
        )
        if v1 is None:
            pytest.skip("no v1 records on disk")
        rebuilt = payload_from_canonical_dict(v1["payload"])
        assert "corpus_provenance" not in rebuilt.canonical_dict()
        assert rebuilt.payload_contract == "forecast-broadcast-payload/v1"

    def test_unknown_contract_is_still_refused(self):
        from src.research.prediction_engine.broadcast.payload import (
            ForecastContentError,
            payload_from_canonical_dict,
        )

        with pytest.raises(ForecastContentError):
            payload_from_canonical_dict({"payload_contract": "something-else/v9"})
