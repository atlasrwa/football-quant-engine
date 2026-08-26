"""Comprehensive tests for Batch 12 — Closing Odds, Scheduler & Real-Data Validation.

Test categories:
A. ClosingOddsProvider (contract, deterministic, availability)
B. Odds Normalization (markets, selections, bookmakers, fixture mapping)
C. Closing Line Validation (10 rules, timestamp semantics)
D. CLV Mathematics (price-based, probability-based, overround)
E. CLV Integrity (genuine vs estimated, missing data)
F. Scheduler Lifecycle (jobs, dependencies, retry, timeout)
G. Scheduler Safety (bounded, no infinite loops)
H. Health Monitoring
I. Temporal Leakage: Closing Odds Attacks (12 adversarial tests)
J. Provider Failures
K. Security (no credentials in artifacts)
L. Idempotency & Determinism
M. AI Boundary
N. Integration (end-to-end CLV pipeline)
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from src.research.closing.clv_engine import CLVCalculation, CLVEngine, CLVMethodology
from src.research.closing.normalization import (
    MappingConfidence,
    NormalizedFixtureMapping,
    OddsNormalizer,
)
from src.research.closing.provider import (
    ClosingOddsObservation,
    ClosingOddsStatus,
    DeterministicClosingOddsProvider,
    TimestampSemantics,
)
from src.research.closing.validation import ClosingLineValidator, ClosingValidationResult
from src.research.scheduler.engine import SchedulerConfig, SchedulerEngine
from src.research.scheduler.health import HealthMonitor, HealthStatus, SystemHealth
from src.research.scheduler.jobs import (
    JOB_DEPENDENCIES,
    JobResult,
    JobStatus,
    JobType,
    SchedulerJob,
)


# ═══════════════════════════════════════════════════════════════════
# A. CLOSING ODDS PROVIDER
# ═══════════════════════════════════════════════════════════════════


class TestClosingOddsProvider:
    def test_deterministic_provider_available(self):
        provider = DeterministicClosingOddsProvider()
        assert provider.is_available() is True
        assert provider.provider_name == "deterministic_test"

    def test_add_and_retrieve_observation(self):
        provider = DeterministicClosingOddsProvider()
        obs = ClosingOddsObservation(
            fixture_id="fix1", market="CORNERS_TOTAL", selection="OVER",
            line=9.5, decimal_odds=1.95, bookmaker="pinnacle",
            source="test", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
        )
        provider.add_observation(obs)
        results = provider.get_closing_odds("fix1")
        assert len(results) == 1
        assert results[0].decimal_odds == 1.95

    def test_filter_by_market(self):
        provider = DeterministicClosingOddsProvider()
        provider.add_observation(ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
        ))
        provider.add_observation(ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.80, source="test", closing_timestamp=1700099000,
        ))
        corners = provider.get_closing_odds("f1", market="CORNERS_TOTAL")
        assert len(corners) == 1
        assert corners[0].market == "CORNERS_TOTAL"

    def test_observation_id_deterministic(self):
        obs1 = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.85, source="pin", closing_timestamp=1700000,
        )
        obs2 = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.85, source="pin", closing_timestamp=1700000,
        )
        assert obs1.observation_id == obs2.observation_id

    def test_is_genuine_exact_close(self):
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="pinnacle", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            status=ClosingOddsStatus.VALID,
        )
        assert obs.is_genuine is True

    def test_is_not_genuine_estimated(self):
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="footystats", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.PROVIDER_ESTIMATED,
            status=ClosingOddsStatus.VALID,
        )
        assert obs.is_genuine is False

    def test_implied_probability(self):
        obs = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=2.0, source="test", closing_timestamp=1700000,
        )
        assert obs.implied_probability == pytest.approx(0.5)


# ═══════════════════════════════════════════════════════════════════
# B. ODDS NORMALIZATION
# ═══════════════════════════════════════════════════════════════════


class TestOddsNormalization:
    def test_normalize_market_aliases(self):
        n = OddsNormalizer()
        assert n.normalize_market("over_under_2.5") == "GOALS_TOTAL"
        assert n.normalize_market("total_corners") == "CORNERS_TOTAL"
        assert n.normalize_market("1x2") == "MATCH_RESULT_1X2"
        assert n.normalize_market("btts") == "BTTS"

    def test_normalize_selection(self):
        n = OddsNormalizer()
        assert n.normalize_selection("over") == "OVER"
        assert n.normalize_selection("1") == "HOME"
        assert n.normalize_selection("x") == "DRAW"
        assert n.normalize_selection("2") == "AWAY"

    def test_normalize_bookmaker(self):
        n = OddsNormalizer()
        assert n.normalize_bookmaker("Pinnacle") == "pinnacle"
        assert n.normalize_bookmaker("PinnacleSports") == "pinnacle"
        assert n.normalize_bookmaker("betfair_exchange") == "betfair"

    def test_fixture_mapping_exact(self):
        n = OddsNormalizer()
        known = {"fix_abc": {"source_fixture_id": "12345", "home_team_id": 101, "away_team_id": 202}}
        result = n.map_fixture("12345", 101, 202, 1700000000, known)
        assert result.confidence == MappingConfidence.EXACT
        assert result.is_usable is True

    def test_fixture_mapping_by_teams(self):
        n = OddsNormalizer()
        known = {"fix_abc": {"source_fixture_id": "99999", "home_team_id": 101,
                             "away_team_id": 202, "kickoff_timestamp": 1700000000}}
        result = n.map_fixture("different_id", 101, 202, 1700000100, known)
        assert result.confidence == MappingConfidence.HIGH
        assert result.is_usable is True

    def test_fixture_mapping_rejected(self):
        n = OddsNormalizer()
        known = {"fix_abc": {"source_fixture_id": "99999", "home_team_id": 101, "away_team_id": 202}}
        result = n.map_fixture("unknown", 999, 888, 1700000000, known)
        assert result.confidence == MappingConfidence.REJECTED
        assert result.is_usable is False


# ═══════════════════════════════════════════════════════════════════
# C. CLOSING LINE VALIDATION
# ═══════════════════════════════════════════════════════════════════


class TestClosingLineValidation:
    def test_valid_observation(self):
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="pinnacle", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            kickoff_timestamp=1700100000,
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert result.valid is True
        assert result.status == ClosingOddsStatus.VALID

    def test_fixture_mismatch_rejected(self):
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f2", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert result.valid is False
        assert any("Fixture mismatch" in e for e in result.errors)

    def test_market_mismatch_rejected(self):
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert result.valid is False

    def test_closing_before_entry_rejected(self):
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700040000,  # Before entry!
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert result.valid is False
        assert any("entry timestamp" in e for e in result.errors)

    def test_invalid_odds_rejected(self):
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=0.5, source="test", closing_timestamp=1700099000,  # Invalid odds
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert result.valid is False

    def test_duplicate_rejected(self):
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
        )
        seen = {obs.observation_id}
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000, seen)
        assert result.valid is False
        assert any("Duplicate" in e for e in result.errors)

    def test_estimated_timestamp_marked(self):
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.PROVIDER_ESTIMATED,
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert result.valid is True  # Valid but estimated
        assert result.status == ClosingOddsStatus.ESTIMATED


# ═══════════════════════════════════════════════════════════════════
# D. CLV MATHEMATICS
# ═══════════════════════════════════════════════════════════════════


class TestCLVMathematics:
    def test_price_based_positive_clv(self):
        """Entry odds 2.10, closing 1.95 → positive CLV."""
        engine = CLVEngine(methodology=CLVMethodology.PRICE_BASED, require_genuine=False)
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            kickoff_timestamp=1700100000,
        )
        result = engine.calculate(
            trade_id="t1", entry_odds=2.10, closing_observation=obs,
            trade_fixture_id="f1", trade_market="CORNERS_TOTAL",
            trade_selection="OVER", trade_entry_timestamp=1700050000,
            trade_kickoff_timestamp=1700100000,
        )
        assert result is not None
        # CLV = (2.10 / 1.95) - 1 ≈ 0.0769
        assert result.clv == pytest.approx((2.10 / 1.95) - 1.0, abs=1e-6)
        assert result.is_positive is True

    def test_price_based_negative_clv(self):
        """Entry odds 1.85, closing 2.00 → negative CLV."""
        engine = CLVEngine(methodology=CLVMethodology.PRICE_BASED, require_genuine=False)
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=2.00, source="test", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            kickoff_timestamp=1700100000,
        )
        result = engine.calculate(
            trade_id="t1", entry_odds=1.85, closing_observation=obs,
            trade_fixture_id="f1", trade_market="CORNERS_TOTAL",
            trade_selection="OVER", trade_entry_timestamp=1700050000,
            trade_kickoff_timestamp=1700100000,
        )
        assert result is not None
        assert result.clv < 0
        assert result.is_positive is False

    def test_price_based_zero_clv(self):
        """Same entry and closing odds → CLV = 0."""
        engine = CLVEngine(methodology=CLVMethodology.PRICE_BASED, require_genuine=False)
        obs = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=2.00, source="test", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            kickoff_timestamp=1700100000,
        )
        result = engine.calculate(
            trade_id="t1", entry_odds=2.00, closing_observation=obs,
            trade_fixture_id="f1", trade_market="GOALS_TOTAL",
            trade_selection="OVER", trade_entry_timestamp=1700050000,
            trade_kickoff_timestamp=1700100000,
        )
        assert result is not None
        assert result.clv == pytest.approx(0.0)

    def test_probability_based_clv(self):
        """Test probability-based methodology."""
        engine = CLVEngine(methodology=CLVMethodology.PROBABILITY_BASED, require_genuine=False)
        obs = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            kickoff_timestamp=1700100000,
        )
        result = engine.calculate(
            trade_id="t1", entry_odds=2.10, closing_observation=obs,
            trade_fixture_id="f1", trade_market="GOALS_TOTAL",
            trade_selection="OVER", trade_entry_timestamp=1700050000,
            trade_kickoff_timestamp=1700100000,
        )
        assert result is not None
        # CLV_prob = closing_implied - entry_implied = 1/1.95 - 1/2.10
        expected = (1.0/1.95) - (1.0/2.10)
        assert result.clv == pytest.approx(expected, abs=1e-6)

    def test_overround_adjusted_clv(self):
        engine = CLVEngine(require_genuine=False)
        obs = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
        )
        result = engine.calculate_with_overround(
            trade_id="t1", entry_odds=2.10,
            closing_over_odds=1.95, closing_under_odds=1.95,
            closing_observation=obs,
        )
        assert result is not None
        assert result.overround is not None
        assert result.overround == pytest.approx(1.0/1.95 + 1.0/1.95, abs=1e-6)


# ═══════════════════════════════════════════════════════════════════
# E. CLV INTEGRITY
# ═══════════════════════════════════════════════════════════════════


class TestCLVIntegrity:
    def test_require_genuine_rejects_estimated(self):
        """CLV engine with require_genuine=True rejects estimated data."""
        engine = CLVEngine(require_genuine=True)
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="footystats", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.PROVIDER_ESTIMATED,  # Not genuine
            kickoff_timestamp=1700100000,
        )
        result = engine.calculate(
            trade_id="t1", entry_odds=2.10, closing_observation=obs,
            trade_fixture_id="f1", trade_market="CORNERS_TOTAL",
            trade_selection="OVER", trade_entry_timestamp=1700050000,
            trade_kickoff_timestamp=1700100000,
        )
        assert result is None  # Rejected — not genuine

    def test_invalid_odds_returns_none(self):
        engine = CLVEngine(require_genuine=False)
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=0.5, source="test", closing_timestamp=1700099000,  # Invalid
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            kickoff_timestamp=1700100000,
        )
        result = engine.calculate(
            trade_id="t1", entry_odds=2.10, closing_observation=obs,
            trade_fixture_id="f1", trade_market="CORNERS_TOTAL",
            trade_selection="OVER", trade_entry_timestamp=1700050000,
            trade_kickoff_timestamp=1700100000,
        )
        assert result is None

    def test_clv_result_immutable(self):
        """CLVCalculation is frozen."""
        calc = CLVCalculation(
            trade_id="t1", entry_odds=2.10, closing_odds=1.95,
            clv=0.077, methodology=CLVMethodology.PRICE_BASED,
            entry_implied_prob=0.476, closing_implied_prob=0.513,
            is_positive=True, is_genuine=True,
        )
        with pytest.raises(AttributeError):
            calc.clv = 0.5  # type: ignore


# ═══════════════════════════════════════════════════════════════════
# F. SCHEDULER LIFECYCLE
# ═══════════════════════════════════════════════════════════════════


class TestSchedulerLifecycle:
    def test_register_and_execute_handler(self):
        engine = SchedulerEngine()
        engine.register_handler(
            JobType.REFRESH_FIXTURES,
            lambda: JobResult(job_id="j1", job_type=JobType.REFRESH_FIXTURES, success=True, items_processed=5),
        )
        results = engine.run_cycle()
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].items_processed == 5

    def test_dependency_enforcement(self):
        """Jobs with unmet dependencies are skipped."""
        engine = SchedulerEngine()
        # Register SETTLE_TRADES but NOT its dependency DETECT_COMPLETED
        engine.register_handler(
            JobType.SETTLE_TRADES,
            lambda: JobResult(job_id="j1", job_type=JobType.SETTLE_TRADES, success=True),
        )
        results = engine.run_cycle()
        # SETTLE_TRADES should be skipped (DETECT_COMPLETED not completed)
        assert len(results) == 0

    def test_dependency_chain_executes(self):
        """Jobs execute in dependency order."""
        executed = []
        engine = SchedulerEngine()
        engine.register_handler(
            JobType.REFRESH_FIXTURES,
            lambda: (executed.append("FIXTURES"), JobResult(job_id="j1", job_type=JobType.REFRESH_FIXTURES, success=True))[1],
        )
        engine.register_handler(
            JobType.DETECT_COMPLETED,
            lambda: (executed.append("DETECT"), JobResult(job_id="j2", job_type=JobType.DETECT_COMPLETED, success=True))[1],
        )
        engine.register_handler(
            JobType.SETTLE_TRADES,
            lambda: (executed.append("SETTLE"), JobResult(job_id="j3", job_type=JobType.SETTLE_TRADES, success=True))[1],
        )
        engine.run_cycle()
        assert "FIXTURES" in executed
        assert "DETECT" in executed
        assert "SETTLE" in executed
        assert executed.index("FIXTURES") < executed.index("DETECT")
        assert executed.index("DETECT") < executed.index("SETTLE")

    def test_failed_job_marked(self):
        engine = SchedulerEngine()
        engine.register_handler(
            JobType.REFRESH_FIXTURES,
            lambda: (_ for _ in ()).throw(RuntimeError("API down")),
        )
        results = engine.run_cycle()
        assert len(results) == 1
        assert results[0].success is False

    def test_job_events_emitted(self):
        engine = SchedulerEngine()
        engine.register_handler(
            JobType.REFRESH_FIXTURES,
            lambda: JobResult(job_id="j1", job_type=JobType.REFRESH_FIXTURES, success=True),
        )
        engine.run_cycle()
        events = engine.events
        event_types = [e["event_type"] for e in events]
        assert "SCHEDULER_CYCLE_STARTED" in event_types
        assert "JOB_STARTED" in event_types
        assert "JOB_COMPLETED" in event_types
        assert "SCHEDULER_CYCLE_COMPLETED" in event_types


# ═══════════════════════════════════════════════════════════════════
# G. SCHEDULER SAFETY
# ═══════════════════════════════════════════════════════════════════


class TestSchedulerSafety:
    def test_max_jobs_per_cycle_enforced(self):
        config = SchedulerConfig(max_jobs_per_cycle=2)
        engine = SchedulerEngine(config=config)
        # Register 5 independent jobs
        for jt in [JobType.REFRESH_FIXTURES, JobType.MONITOR_OPEN_TRADES, JobType.AI_RESEARCH_CYCLE]:
            engine.register_handler(jt, lambda jt=jt: JobResult(
                job_id="j", job_type=jt, success=True,
            ))
        results = engine.run_cycle()
        assert len(results) <= 2

    def test_job_has_timeout(self):
        job = SchedulerJob(job_type=JobType.REFRESH_FIXTURES, timeout_seconds=60.0)
        assert job.timeout_seconds == 60.0

    def test_job_max_attempts(self):
        job = SchedulerJob(job_type=JobType.REFRESH_FIXTURES, max_attempts=3, attempt_count=3)
        assert job.can_retry is False

    def test_job_dependency_graph_has_no_cycles(self):
        """Verify the dependency graph is a DAG (no circular dependencies)."""
        visited: set[JobType] = set()
        in_stack: set[JobType] = set()

        def has_cycle(node: JobType) -> bool:
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for dep in JOB_DEPENDENCIES.get(node, []):
                if has_cycle(dep):
                    return True
            in_stack.remove(node)
            return False

        for jt in JobType:
            assert has_cycle(jt) is False, f"Cycle detected at {jt}"


# ═══════════════════════════════════════════════════════════════════
# H. HEALTH MONITORING
# ═══════════════════════════════════════════════════════════════════


class TestHealthMonitoring:
    def test_initial_state_unknown(self):
        monitor = HealthMonitor()
        health = monitor.check_health()
        # Never refreshed → degraded/unhealthy
        assert health.overall_status != HealthStatus.HEALTHY

    def test_healthy_after_refresh(self):
        monitor = HealthMonitor(fixture_freshness_seconds=600, odds_freshness_seconds=3600)
        monitor.record_fixture_refresh()
        monitor.record_odds_refresh()
        monitor.record_heartbeat()
        health = monitor.check_health()
        assert health.fixtures_fresh is True
        assert health.odds_fresh is True
        assert health.scheduler_alive is True
        assert health.overall_status == HealthStatus.HEALTHY

    def test_degraded_on_stale_fixtures(self):
        monitor = HealthMonitor(fixture_freshness_seconds=0.001)  # Extremely short
        monitor.record_fixture_refresh()
        import time; time.sleep(0.01)
        monitor.record_heartbeat()
        health = monitor.check_health()
        assert health.fixtures_fresh is False

    def test_unhealthy_no_heartbeat(self):
        monitor = HealthMonitor(heartbeat_timeout_seconds=0.001)
        health = monitor.check_health()
        assert health.scheduler_alive is False
        assert health.overall_status == HealthStatus.UNHEALTHY

    def test_health_to_dict(self):
        monitor = HealthMonitor()
        monitor.record_heartbeat()
        health = monitor.check_health()
        d = health.to_dict()
        assert "overall_status" in d
        assert "checks" in d
        # No credentials
        assert "api_key" not in json.dumps(d).lower()


# ═══════════════════════════════════════════════════════════════════
# I. TEMPORAL LEAKAGE: CLOSING ODDS ATTACKS
# ═══════════════════════════════════════════════════════════════════


class TestClosingOddsLeakageAttacks:
    """Adversarial tests ensuring closing odds NEVER leak into prediction path."""

    def test_01_closing_odds_not_in_feature_generation(self):
        """Closing odds have no path to feature engine."""
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
        )
        # ClosingOddsObservation has no method to inject into features
        # It's a separate type from ResearchMatch/PreMatchSnapshot
        assert not hasattr(obs, "to_research_match")
        assert not hasattr(obs, "to_feature_dict")

    def test_02_closing_odds_not_in_ai_context_before_settlement(self):
        """AI context should never contain closing odds before trade settles."""
        from src.research.ai.context import ResearchContext
        ctx = ResearchContext(market_type="CORNERS_TOTAL")
        ctx_str = ctx.to_prompt_section()
        assert "closing" not in ctx_str.lower()

    def test_03_closing_odds_not_in_entry_snapshot(self):
        """Closing odds cannot appear in pre-match snapshot."""
        from src.research.forward.snapshot import PreMatchSnapshot
        snap = PreMatchSnapshot(
            fixture_id="f1", prediction_timestamp=1700050000,
            kickoff_timestamp=1700100000,
            features={"avg_goals_home": 2.5},
        )
        # Snapshot has no closing_odds field
        assert not hasattr(snap, "closing_odds")
        snap_dict = snap.to_dict()
        assert "closing_odds" not in snap_dict

    def test_04_closing_odds_not_in_staking(self):
        """Staking model has no closing odds input."""
        from src.research.paper.staking import StakingModel
        model = StakingModel()
        # calculate_stake only takes model_probability and decimal_odds (entry)
        import inspect
        sig = inspect.signature(model.calculate_stake)
        params = list(sig.parameters.keys())
        assert "closing_odds" not in params

    def test_05_closing_odds_not_in_eligibility(self):
        """Paper eligibility has no closing odds criterion."""
        from src.research.paper.eligibility import PaperEligibility
        elig = PaperEligibility()
        import inspect
        sig = inspect.signature(elig.evaluate)
        params = list(sig.parameters.keys())
        assert "closing_odds" not in params
        assert "clv" not in params

    def test_06_closing_odds_cannot_alter_entry_odds(self):
        """Paper trade entry odds are immutable — closing cannot overwrite."""
        from src.research.paper.paper_trade import PaperTrade
        trade = PaperTrade(
            strategy_id="s1", fixture_id="f1",
            odds_at_prediction=2.10, stake=100,
        )
        with pytest.raises(AttributeError):
            trade.odds_at_prediction = 1.95  # type: ignore

    def test_07_future_odds_rejected_by_validator(self):
        """Odds with timestamp after kickoff are rejected."""
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test",
            closing_timestamp=1700200000,  # WAY after kickoff
            kickoff_timestamp=1700100000,
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert result.valid is False

    def test_08_duplicate_closing_rejected(self):
        """Same observation submitted twice → second rejected."""
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
        )
        seen = {obs.observation_id}
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000, seen)
        assert result.valid is False

    def test_09_post_kickoff_closing_warning(self):
        """Closing timestamp slightly after kickoff triggers warning."""
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test",
            closing_timestamp=1700100500,  # 500s after kickoff
            kickoff_timestamp=1700100000,
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert len(result.warnings) > 0

    def test_10_clv_never_modifies_trade(self):
        """CLV calculation produces a separate artifact, never modifies trade."""
        from src.research.paper.paper_trade import PaperTrade, PaperTradeStatus
        trade = PaperTrade(
            strategy_id="s1", fixture_id="f1",
            odds_at_prediction=2.10, stake=100,
            prediction_timestamp=1700050000,
        )
        # CLV is computed separately
        engine = CLVEngine(require_genuine=False)
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            kickoff_timestamp=1700100000,
        )
        clv = engine.calculate(
            trade_id=trade.trade_id, entry_odds=2.10, closing_observation=obs,
            trade_fixture_id="f1", trade_market="CORNERS_TOTAL",
            trade_selection="OVER", trade_entry_timestamp=1700050000,
            trade_kickoff_timestamp=1700100000,
        )
        # Trade unchanged
        assert trade.odds_at_prediction == 2.10
        assert trade.closing_odds is None  # Not attached until settlement

    def test_11_source_earlier_than_kickoff_rejected(self):
        """Source timestamp claiming to be before entry is suspicious."""
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test",
            closing_timestamp=1700040000,  # Before entry (1700050000)
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert result.valid is False

    def test_12_missing_source_rejected(self):
        """Observation without source provenance is rejected."""
        validator = ClosingLineValidator()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="",  # Missing!
            closing_timestamp=1700099000,
        )
        result = validator.validate(obs, "f1", "CORNERS_TOTAL", "OVER", 1700050000, 1700100000)
        assert result.valid is False


# ═══════════════════════════════════════════════════════════════════
# J. PROVIDER FAILURES
# ═══════════════════════════════════════════════════════════════════


class TestProviderFailures:
    def test_unavailable_provider_returns_empty(self):
        """Provider that's unavailable returns empty, never fabricates."""
        provider = DeterministicClosingOddsProvider()
        # No observations added → empty results, not fabricated
        results = provider.get_closing_odds("nonexistent_fixture")
        assert results == []

    def test_scheduler_handles_handler_failure(self):
        engine = SchedulerEngine()
        engine.register_handler(
            JobType.REFRESH_FIXTURES,
            lambda: (_ for _ in ()).throw(ConnectionError("Network down")),
        )
        results = engine.run_cycle()
        assert results[0].success is False
        assert "ConnectionError" in results[0].errors[0]


# ═══════════════════════════════════════════════════════════════════
# K. SECURITY
# ═══════════════════════════════════════════════════════════════════


class TestSecurity:
    def test_no_credentials_in_observation(self):
        obs = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="pinnacle", closing_timestamp=1700099000,
        )
        d = json.dumps(obs.to_dict())
        assert "api_key" not in d.lower()
        assert "password" not in d.lower()
        assert "secret" not in d.lower()
        assert "aws_access" not in d.lower()

    def test_no_credentials_in_clv_result(self):
        calc = CLVCalculation(
            trade_id="t1", entry_odds=2.10, closing_odds=1.95,
            clv=0.077, methodology=CLVMethodology.PRICE_BASED,
            entry_implied_prob=0.476, closing_implied_prob=0.513,
            is_positive=True, is_genuine=True, closing_source="pinnacle",
        )
        d = json.dumps(calc.to_dict())
        assert "api_key" not in d.lower()
        assert "secret" not in d.lower()

    def test_no_credentials_in_scheduler_events(self):
        engine = SchedulerEngine()
        engine.register_handler(
            JobType.REFRESH_FIXTURES,
            lambda: JobResult(job_id="j1", job_type=JobType.REFRESH_FIXTURES, success=True),
        )
        engine.run_cycle()
        for event in engine.events:
            event_str = json.dumps(event)
            assert "api_key" not in event_str.lower()
            assert "secret" not in event_str.lower()


# ═══════════════════════════════════════════════════════════════════
# L. IDEMPOTENCY & DETERMINISM
# ═══════════════════════════════════════════════════════════════════


class TestIdempotency:
    def test_observation_id_stable(self):
        obs = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.85, source="pin", bookmaker="pinnacle",
            closing_timestamp=1700099000,
        )
        assert obs.observation_id == obs.observation_id  # Trivial but confirms property
        # Create identical
        obs2 = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.85, source="pin", bookmaker="pinnacle",
            closing_timestamp=1700099000,
        )
        assert obs.observation_id == obs2.observation_id

    def test_clv_deterministic(self):
        """Same inputs → same CLV result."""
        engine = CLVEngine(require_genuine=False)
        obs = ClosingOddsObservation(
            fixture_id="f1", market="GOALS_TOTAL", selection="OVER",
            decimal_odds=1.95, source="test", closing_timestamp=1700099000,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            kickoff_timestamp=1700100000,
        )
        r1 = engine.calculate("t1", 2.10, obs, "f1", "GOALS_TOTAL", "OVER", 1700050000, 1700100000)
        r2 = engine.calculate("t1", 2.10, obs, "f1", "GOALS_TOTAL", "OVER", 1700050000, 1700100000)
        assert r1.clv == r2.clv


# ═══════════════════════════════════════════════════════════════════
# M. AI BOUNDARY
# ═══════════════════════════════════════════════════════════════════


class TestAIBoundary:
    def test_ai_cannot_access_closing_odds(self):
        """No path from AI agent to closing odds data."""
        from src.research.ai.agent import ResearchAgent
        from src.research.ai.provider import MockLLMProvider
        agent = ResearchAgent(provider=MockLLMProvider())
        # Agent has no method to access closing odds
        assert not hasattr(agent, "get_closing_odds")
        assert not hasattr(agent, "closing_odds")

    def test_ai_cannot_modify_clv(self):
        """CLVCalculation is frozen — AI cannot alter it."""
        calc = CLVCalculation(
            trade_id="t1", entry_odds=2.10, closing_odds=1.95,
            clv=0.077, methodology=CLVMethodology.PRICE_BASED,
            entry_implied_prob=0.476, closing_implied_prob=0.513,
            is_positive=True, is_genuine=True,
        )
        with pytest.raises(AttributeError):
            calc.clv = 0.999  # type: ignore


# ═══════════════════════════════════════════════════════════════════
# N. INTEGRATION
# ═══════════════════════════════════════════════════════════════════


class TestIntegration:
    def test_end_to_end_clv_pipeline(self):
        """Full pipeline: provider → validation → CLV calculation."""
        # 1. Provider supplies closing odds
        provider = DeterministicClosingOddsProvider()
        obs = ClosingOddsObservation(
            fixture_id="f1", market="CORNERS_TOTAL", selection="OVER",
            line=9.5, decimal_odds=1.92, bookmaker="pinnacle",
            source="pinnacle", closing_timestamp=1700099500,
            timestamp_semantics=TimestampSemantics.EXACT_CLOSE,
            kickoff_timestamp=1700100000,
            status=ClosingOddsStatus.VALID,
        )
        provider.add_observation(obs)

        # 2. Retrieve for fixture
        closing = provider.get_closing_odds("f1", market="CORNERS_TOTAL")
        assert len(closing) == 1

        # 3. Validate
        validator = ClosingLineValidator()
        validation = validator.validate(
            closing[0], "f1", "CORNERS_TOTAL", "OVER",
            trade_entry_timestamp=1700060000,
            trade_kickoff_timestamp=1700100000,
        )
        assert validation.valid is True
        assert validation.status == ClosingOddsStatus.VALID

        # 4. Calculate CLV
        engine = CLVEngine()
        clv = engine.calculate(
            trade_id="trade1", entry_odds=2.05, closing_observation=closing[0],
            trade_fixture_id="f1", trade_market="CORNERS_TOTAL",
            trade_selection="OVER", trade_entry_timestamp=1700060000,
            trade_kickoff_timestamp=1700100000,
        )
        assert clv is not None
        assert clv.is_genuine is True
        expected_clv = (2.05 / 1.92) - 1.0
        assert clv.clv == pytest.approx(expected_clv, abs=1e-6)
        assert clv.is_positive is True  # Got better odds than closing

    def test_scheduler_full_cycle(self):
        """Scheduler executes a complete job cycle with dependencies."""
        results_log = []
        engine = SchedulerEngine()

        def make_handler(name, jtype):
            def handler():
                results_log.append(name)
                return JobResult(job_id=name, job_type=jtype, success=True, items_processed=1)
            return handler

        engine.register_handler(JobType.REFRESH_FIXTURES, make_handler("fix", JobType.REFRESH_FIXTURES))
        engine.register_handler(JobType.DETECT_COMPLETED, make_handler("detect", JobType.DETECT_COMPLETED))
        engine.register_handler(JobType.SETTLE_TRADES, make_handler("settle", JobType.SETTLE_TRADES))
        engine.register_handler(JobType.RETRIEVE_CLOSING_ODDS, make_handler("closing", JobType.RETRIEVE_CLOSING_ODDS))
        engine.register_handler(JobType.CALCULATE_CLV, make_handler("clv", JobType.CALCULATE_CLV))

        results = engine.run_cycle()
        # All should execute in order
        assert len(results) == 5
        assert all(r.success for r in results)
        assert results_log.index("fix") < results_log.index("detect")
        assert results_log.index("detect") < results_log.index("settle")
        assert results_log.index("settle") < results_log.index("closing")
        assert results_log.index("closing") < results_log.index("clv")
