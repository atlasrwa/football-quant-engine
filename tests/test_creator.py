"""Tests for the creator hypothesis testing system.

Verifies: hypothesis definition, validation pipeline, honest verdicts,
anti-p-hacking guardrails, forking, and quarantine enrollment.
"""

from __future__ import annotations

import pytest

from src.creator.features import build_creator_feature_catalog, get_feature_catalog_summary
from src.creator.hypothesis import (
    CreatorHypothesis,
    HypothesisBuilder,
    HypothesisCondition,
    HypothesisStatus,
    ConditionOperator,
    PredictionTarget,
)
from src.creator.pipeline import ValidationPipeline, VerdictStatus
from src.creator.guardrails import SubmissionGuardrails


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def feature_catalog():
    catalog = build_creator_feature_catalog()
    return {f.feature_id: f for f in catalog}


@pytest.fixture
def builder(feature_catalog):
    return HypothesisBuilder(feature_catalog=feature_catalog)


@pytest.fixture
def sample_matches():
    """Generate synthetic match data for testing."""
    import random
    random.seed(42)
    matches = []
    for i in range(500):
        home_corners = random.randint(2, 10)
        away_corners = random.randint(2, 10)
        matches.append({
            "id": i,
            "status": "complete",
            "team_a_corners": home_corners,
            "team_b_corners": away_corners,
            "team_a_yellow_cards": random.randint(0, 4),
            "team_b_yellow_cards": random.randint(0, 4),
            "team_a_red_cards": random.choice([0, 0, 0, 0, 1]),
            "team_b_red_cards": random.choice([0, 0, 0, 0, 1]),
            "homeGoalCount": random.randint(0, 4),
            "awayGoalCount": random.randint(0, 3),
            "overallGoalCount": random.randint(0, 6),
            "team_a_shots": random.randint(5, 20),
            "team_b_shots": random.randint(5, 20),
            "team_a_shotsOnTarget": random.randint(1, 8),
            "team_b_shotsOnTarget": random.randint(1, 8),
            "team_a_possession": random.randint(30, 70),
            "team_b_possession": 100 - random.randint(30, 70),
            "team_a_dangerous_attacks": random.randint(20, 60),
            "team_b_dangerous_attacks": random.randint(20, 60),
            "team_a_fouls": random.randint(5, 20),
            "team_b_fouls": random.randint(5, 20),
            "team_a_offsides": random.randint(0, 5),
            "team_b_offsides": random.randint(0, 5),
            "team_a_freekicks": random.randint(5, 20),
            "team_b_freekicks": random.randint(5, 20),
            "team_a_throwins": random.randint(10, 30),
            "team_b_throwins": random.randint(10, 30),
            "team_a_xg": round(random.uniform(0.5, 3.0), 2),
            "team_b_xg": round(random.uniform(0.5, 3.0), 2),
            "team_a_xg_prematch": round(random.uniform(0.5, 2.5), 2),
            "team_b_xg_prematch": round(random.uniform(0.5, 2.5), 2),
            "pre_match_home_ppg": round(random.uniform(0.5, 2.5), 2),
            "pre_match_away_ppg": round(random.uniform(0.5, 2.5), 2),
            "team_a_cards_num": random.randint(0, 5),
            "team_b_cards_num": random.randint(0, 5),
            "league": random.choice(["EPL", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]),
            "season": "20252026",
        })
    return matches


# ═══════════════════════════════════════════════════════════════
# FEATURE CATALOG
# ═══════════════════════════════════════════════════════════════

class TestFeatureCatalog:
    def test_catalog_not_empty(self):
        catalog = build_creator_feature_catalog()
        assert len(catalog) > 100  # Should have 160+ features

    def test_catalog_includes_xmetrics(self):
        catalog = build_creator_feature_catalog()
        xmetrics = [f for f in catalog if f.category.value == "xmetrics"]
        assert len(xmetrics) == 24  # 6 base + 18 rolling

    def test_catalog_includes_raw_stats(self):
        catalog = build_creator_feature_catalog()
        corners = [f for f in catalog if f.category.value == "corners"]
        assert len(corners) > 0

    def test_pre_kickoff_usability(self):
        catalog = build_creator_feature_catalog()
        pre_kickoff = [f for f in catalog if f.usable_pre_kickoff]
        post_match = [f for f in catalog if not f.usable_pre_kickoff]
        assert len(pre_kickoff) > 50
        assert len(post_match) > 0  # Some raw stats are post-match only

    def test_summary_has_all_categories(self):
        summary = get_feature_catalog_summary()
        expected = {"xmetrics", "corners", "cards", "goals", "shots",
                    "possession", "discipline", "set_pieces", "form"}
        assert set(summary["categories"].keys()) == expected


# ═══════════════════════════════════════════════════════════════
# HYPOTHESIS BUILDER
# ═══════════════════════════════════════════════════════════════

class TestHypothesisBuilder:
    def test_build_valid_hypothesis(self, builder):
        h = builder.build(
            creator_id="creator_1",
            name="Test hypothesis",
            description="Testing",
            target="corners_over_under",
            direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 6.0}],
            logic="AND",
            line=9.5,
        )
        assert h.hypothesis_id
        assert h.content_hash
        assert h.status == HypothesisStatus.DRAFT
        assert h.version == 1
        assert len(h.conditions) == 1

    def test_content_hash_deterministic(self, builder):
        """Same conditions produce the same hash regardless of name/creator/time."""
        h1 = builder.build(
            creator_id="alice", name="A", description="",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 6.0}],
        )
        h2 = builder.build(
            creator_id="bob", name="B", description="different",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 6.0}],
        )
        assert h1.content_hash == h2.content_hash

    def test_different_conditions_different_hash(self, builder):
        h1 = builder.build(
            creator_id="alice", name="A", description="",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 6.0}],
        )
        h2 = builder.build(
            creator_id="alice", name="A", description="",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 7.0}],
        )
        assert h1.content_hash != h2.content_hash

    def test_rejects_empty_name(self, builder):
        with pytest.raises(ValueError, match="cannot be empty"):
            builder.build(
                creator_id="x", name="", description="",
                target="corners_over_under", direction="OVER",
                conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 6.0}],
            )

    def test_rejects_invalid_target(self, builder):
        with pytest.raises(ValueError, match="Invalid target"):
            builder.build(
                creator_id="x", name="test", description="",
                target="invalid_market", direction="OVER",
                conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 6.0}],
            )

    def test_rejects_invalid_feature(self, builder):
        with pytest.raises(ValueError, match="not found in the feature catalog"):
            builder.build(
                creator_id="x", name="test", description="",
                target="corners_over_under", direction="OVER",
                conditions=[{"feature_id": "fake_feature", "operator": ">", "threshold": 6.0}],
            )

    def test_rejects_too_many_conditions(self, builder):
        with pytest.raises(ValueError, match="Maximum 5 conditions"):
            builder.build(
                creator_id="x", name="test", description="",
                target="corners_over_under", direction="OVER",
                conditions=[
                    {"feature_id": "raw_home_corners", "operator": ">", "threshold": i}
                    for i in range(6)
                ],
            )

    def test_rejects_no_conditions(self, builder):
        with pytest.raises(ValueError, match="At least one condition"):
            builder.build(
                creator_id="x", name="test", description="",
                target="corners_over_under", direction="OVER",
                conditions=[],
            )

    def test_default_line_applied(self, builder):
        h = builder.build(
            creator_id="x", name="test", description="",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 6.0}],
        )
        assert h.line == 9.5  # Default for corners

    def test_forked_from_preserved(self, builder):
        h = builder.build(
            creator_id="bob", name="fork", description="",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 6.0}],
            forked_from="original_id_123",
        )
        assert h.forked_from == "original_id_123"


# ═══════════════════════════════════════════════════════════════
# VALIDATION PIPELINE
# ═══════════════════════════════════════════════════════════════

class TestValidationPipeline:
    def test_fails_on_insufficient_sample(self, builder, sample_matches):
        """Hypothesis with very specific conditions should fail sample gate."""
        h = builder.build(
            creator_id="x", name="Specific", description="",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 99.0}],
        )
        # No match will have >99 corners
        pipeline = ValidationPipeline(match_data=sample_matches)
        verdict = pipeline.validate(h, creator_submission_count=1)
        assert verdict.verdict == VerdictStatus.FAILED_SAMPLE_SIZE

    def test_fails_on_vs_naive(self, builder, sample_matches):
        """A trivially broad hypothesis should fail vs-naive."""
        h = builder.build(
            creator_id="x", name="Everything", description="",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">=", "threshold": 0.0}],
            line=9.5,
        )
        pipeline = ValidationPipeline(match_data=sample_matches, min_sample=10)
        verdict = pipeline.validate(h, creator_submission_count=1)
        # Matches everything → same as naive → fails
        assert verdict.verdict in (VerdictStatus.FAILED_VS_NAIVE, VerdictStatus.FAILED_SIGNIFICANCE)

    def test_verdict_includes_league_breakdown(self, builder, sample_matches):
        """Even failed verdicts should include per-league data when available."""
        h = builder.build(
            creator_id="x", name="Test", description="",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">=", "threshold": 2.0}],
            line=9.5,
        )
        pipeline = ValidationPipeline(match_data=sample_matches, min_sample=10)
        verdict = pipeline.validate(h, creator_submission_count=1)
        # Should have some league results
        if verdict.qualifying_matches > 0 and verdict.verdict != VerdictStatus.FAILED_SAMPLE_SIZE:
            assert len(verdict.league_results) > 0

    def test_verdict_has_honest_failure_message(self, builder, sample_matches):
        """Failed verdicts should have clear, honest plain-language explanations."""
        h = builder.build(
            creator_id="x", name="Test", description="",
            target="corners_over_under", direction="OVER",
            conditions=[{"feature_id": "raw_home_corners", "operator": ">", "threshold": 99.0}],
        )
        pipeline = ValidationPipeline(match_data=sample_matches)
        verdict = pipeline.validate(h, creator_submission_count=1)
        assert verdict.plain_language
        assert len(verdict.plain_language) > 50
        # Should explain the failure honestly
        assert "matched" in verdict.plain_language.lower() or "need" in verdict.plain_language.lower()

    def test_same_pipeline_as_internal(self, sample_matches):
        """Verify we use the same FDR alpha and criteria as internal models."""
        pipeline = ValidationPipeline(match_data=sample_matches)
        assert pipeline._fdr.alpha == 0.05  # Same as internal
        assert pipeline._min_sample == 250  # Same as StatisticalValidator


# ═══════════════════════════════════════════════════════════════
# ANTI-P-HACKING GUARDRAILS
# ═══════════════════════════════════════════════════════════════

class TestGuardrails:
    def test_first_submission_allowed(self):
        g = SubmissionGuardrails()
        can, reason = g.check_can_submit("new_creator")
        assert can is True
        assert reason is None

    def test_rate_limit_24h(self):
        g = SubmissionGuardrails()
        for i in range(5):
            g.record_submission("alice", f"h{i}")
        can, reason = g.check_can_submit("alice")
        assert can is False
        assert "24 hours" in reason

    def test_rate_limit_per_creator(self):
        """Rate limits are per-creator, not global."""
        g = SubmissionGuardrails()
        for i in range(5):
            g.record_submission("alice", f"h{i}")
        can, _ = g.check_can_submit("alice")
        assert can is False
        can, _ = g.check_can_submit("bob")
        assert can is True  # Bob is unaffected

    def test_p_values_tracked(self):
        g = SubmissionGuardrails()
        g.record_submission("alice", "h1", p_value=0.03)
        g.record_submission("alice", "h2", p_value=0.12)
        family = g.get_fdr_family("alice")
        assert family == [0.03, 0.12]

    def test_submission_stats_visible(self):
        g = SubmissionGuardrails()
        g.record_submission("alice", "h1", p_value=0.03, passed=True)
        g.record_submission("alice", "h2", p_value=0.12, passed=False)
        stats = g.get_submission_stats("alice")
        assert stats["total_submissions"] == 2
        assert stats["hypotheses_passed"] == 1
        assert stats["hypotheses_failed"] == 1
        assert "policy" in stats
        assert "fdr_note" in stats

    def test_fdr_note_increases_with_submissions(self):
        g = SubmissionGuardrails()
        g.record_submission("alice", "h1")
        stats1 = g.get_submission_stats("alice")
        g.record_submission("alice", "h2")
        stats2 = g.get_submission_stats("alice")
        # The family size should increase
        assert "2" in stats1["fdr_note"]
        assert "3" in stats2["fdr_note"]


# ═══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

class TestCreatorAPI:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.creator.api import router
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_list_features(self):
        r = self.client.get("/api/v1/creator/features")
        assert r.status_code == 200
        data = r.json()
        assert data["total_features"] > 100
        assert "categories" in data

    def test_create_hypothesis(self):
        r = self.client.post("/api/v1/creator/hypotheses", json={
            "name": "Test",
            "target": "corners_over_under",
            "direction": "OVER",
            "conditions": [{"feature_id": "raw_home_corners", "operator": ">", "threshold": 6.0}],
        }, params={"creator_id": "test_user"})
        assert r.status_code == 200
        assert r.json()["hypothesis"]["status"] == "DRAFT"

    def test_create_rejects_invalid(self):
        r = self.client.post("/api/v1/creator/hypotheses", json={
            "name": "Bad",
            "target": "corners_over_under",
            "direction": "OVER",
            "conditions": [{"feature_id": "nonexistent", "operator": ">", "threshold": 6.0}],
        })
        assert r.status_code == 422

    def test_policy_endpoint(self):
        r = self.client.get("/api/v1/creator/policy")
        assert r.status_code == 200
        data = r.json()
        assert "validation_pipeline" in data
        assert "anti_p_hacking" in data
        assert "quarantine" in data
        assert "what_we_do_not_do" in data
        assert len(data["what_we_do_not_do"]) >= 4
