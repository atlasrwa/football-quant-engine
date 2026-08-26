"""Tests for market abstraction."""

import pytest

from src.research.market import (
    ALL_MARKETS,
    ALL_RESEARCH_MARKETS,
    AWAY_CARDS_OVER_UNDER,
    AWAY_CORNERS_OVER_UNDER,
    AWAY_GOALS_OVER_UNDER,
    BTTS_MARKET,
    CARDS_OVER_UNDER,
    CORNERS_OVER_UNDER,
    DefaultSettlementAdapter,
    GOALS_OVER_UNDER,
    HOME_CARDS_OVER_UNDER,
    HOME_CORNERS_OVER_UNDER,
    HOME_GOALS_OVER_UNDER,
    MATCH_RESULT_1X2,
    MarketCategory,
    MarketDirection,
    MarketOutcome,
    MarketRegistry,
    MarketType,
    OFFSIDES_OVER_UNDER,
    ProbabilityModelType,
    ResearchMarket,
    create_default_registry,
)


class TestResearchMarket:
    """Tests for ResearchMarket."""

    def test_resolve_outcome_over(self):
        market = CORNERS_OVER_UNDER  # line=9.5
        result = market.resolve_outcome(10.0)
        assert result == MarketDirection.OVER

    def test_resolve_outcome_under(self):
        market = CORNERS_OVER_UNDER  # line=9.5
        result = market.resolve_outcome(9.0)
        assert result == MarketDirection.UNDER

    def test_resolve_outcome_push(self):
        market = ResearchMarket(
            market_type=MarketType.GOALS_TOTAL,
            target_field="total_goals",
            line=2.0,  # integer line allows push
            odds_over_field="odds_over",
            odds_under_field="odds_under",
        )
        result = market.resolve_outcome(2.0)
        assert result is None  # Push

    def test_half_line_no_push(self):
        """Half-point lines (e.g., 9.5) should never produce a push."""
        market = CORNERS_OVER_UNDER
        # Integer outcomes can never equal 9.5
        for val in range(0, 20):
            result = market.resolve_outcome(float(val))
            assert result is not None

    def test_implied_probability(self):
        market = GOALS_OVER_UNDER
        # Odds of 2.0 → implied prob = 0.5
        assert abs(market.implied_probability(2.0) - 0.5) < 0.001
        # Odds of 1.5 → implied prob = 0.667
        assert abs(market.implied_probability(1.5) - 2.0 / 3.0) < 0.001

    def test_implied_probability_edge_case(self):
        market = GOALS_OVER_UNDER
        # Odds <= 1.0 should return 1.0
        assert market.implied_probability(1.0) == 1.0
        assert market.implied_probability(0.5) == 1.0

    def test_fair_probability_strips_margin(self):
        market = GOALS_OVER_UNDER
        # 5% overround: over=1.90, under=2.00
        fair_over, fair_under = market.fair_probability(1.90, 2.00)
        assert abs(fair_over + fair_under - 1.0) < 0.001
        assert fair_over > fair_under  # Lower odds = higher probability

    def test_fair_probability_symmetric_odds(self):
        market = GOALS_OVER_UNDER
        fair_over, fair_under = market.fair_probability(2.0, 2.0)
        assert abs(fair_over - 0.5) < 0.001
        assert abs(fair_under - 0.5) < 0.001

    def test_all_markets_defined(self):
        assert len(ALL_MARKETS) == 4
        types = {m.market_type for m in ALL_MARKETS}
        assert MarketType.GOALS_TOTAL in types
        assert MarketType.CORNERS_TOTAL in types
        assert MarketType.CARDS_TOTAL in types
        assert MarketType.OFFSIDES_TOTAL in types

    def test_market_type_enum_values(self):
        assert MarketType.GOALS_TOTAL.value == "GOALS_TOTAL"
        assert MarketType.CORNERS_TOTAL.value == "CORNERS_TOTAL"
        assert MarketType.CARDS_TOTAL.value == "CARDS_TOTAL"
        assert MarketType.OFFSIDES_TOTAL.value == "OFFSIDES_TOTAL"

    def test_market_direction_enum(self):
        assert MarketDirection.OVER.value == "OVER"
        assert MarketDirection.UNDER.value == "UNDER"

    def test_corners_market_definition(self):
        assert CORNERS_OVER_UNDER.line == 9.5
        assert CORNERS_OVER_UNDER.target_field == "total_corners"
        assert CORNERS_OVER_UNDER.odds_over_field == "odds_over_corners"
        assert CORNERS_OVER_UNDER.odds_under_field == "odds_under_corners"


class TestExtendedMarkets:
    """Tests for new market types added in Batch 1."""

    def test_all_research_markets_count(self):
        """12 markets total in extended set."""
        assert len(ALL_RESEARCH_MARKETS) == 12

    def test_team_goals_markets(self):
        assert HOME_GOALS_OVER_UNDER.market_type == MarketType.HOME_GOALS
        assert HOME_GOALS_OVER_UNDER.target_field == "home_goals"
        assert HOME_GOALS_OVER_UNDER.line == 1.5
        assert AWAY_GOALS_OVER_UNDER.market_type == MarketType.AWAY_GOALS
        assert AWAY_GOALS_OVER_UNDER.target_field == "away_goals"
        assert AWAY_GOALS_OVER_UNDER.line == 1.5

    def test_team_corners_markets(self):
        assert HOME_CORNERS_OVER_UNDER.market_type == MarketType.HOME_CORNERS
        assert HOME_CORNERS_OVER_UNDER.target_field == "corners_home"
        assert HOME_CORNERS_OVER_UNDER.line == 4.5
        assert AWAY_CORNERS_OVER_UNDER.market_type == MarketType.AWAY_CORNERS
        assert AWAY_CORNERS_OVER_UNDER.target_field == "corners_away"

    def test_team_cards_markets(self):
        assert HOME_CARDS_OVER_UNDER.market_type == MarketType.HOME_CARDS
        assert HOME_CARDS_OVER_UNDER.target_field == "yellow_cards_home"
        assert HOME_CARDS_OVER_UNDER.line == 1.5
        assert AWAY_CARDS_OVER_UNDER.market_type == MarketType.AWAY_CARDS
        assert AWAY_CARDS_OVER_UNDER.target_field == "yellow_cards_away"

    def test_btts_market(self):
        assert BTTS_MARKET.market_type == MarketType.BTTS
        assert BTTS_MARKET.line is None
        assert BTTS_MARKET.category == MarketCategory.YES_NO
        assert BTTS_MARKET.is_yes_no is True
        assert BTTS_MARKET.is_over_under is False

    def test_match_result_1x2(self):
        assert MATCH_RESULT_1X2.market_type == MarketType.MATCH_RESULT_1X2
        assert MATCH_RESULT_1X2.line is None
        assert MATCH_RESULT_1X2.category == MarketCategory.THREE_WAY
        assert MATCH_RESULT_1X2.is_three_way is True
        assert MATCH_RESULT_1X2.odds_third_field == "odds_away_win"

    def test_market_categories(self):
        # Over/Under markets
        for m in [GOALS_OVER_UNDER, CORNERS_OVER_UNDER, CARDS_OVER_UNDER,
                  OFFSIDES_OVER_UNDER, HOME_GOALS_OVER_UNDER, AWAY_GOALS_OVER_UNDER,
                  HOME_CORNERS_OVER_UNDER, AWAY_CORNERS_OVER_UNDER,
                  HOME_CARDS_OVER_UNDER, AWAY_CARDS_OVER_UNDER]:
            assert m.category == MarketCategory.OVER_UNDER
            assert m.is_over_under is True

    def test_market_id_deterministic(self):
        """market_id should be consistent across calls."""
        id1 = GOALS_OVER_UNDER.market_id
        id2 = GOALS_OVER_UNDER.market_id
        assert id1 == id2
        assert len(id1) == 16

    def test_market_id_unique_per_market(self):
        """Different markets have different IDs."""
        ids = {m.market_id for m in ALL_RESEARCH_MARKETS}
        assert len(ids) == len(ALL_RESEARCH_MARKETS)

    def test_required_fields(self):
        assert GOALS_OVER_UNDER.required_fields == ("total_goals",)
        assert BTTS_MARKET.required_fields == ("home_goals", "away_goals")
        assert MATCH_RESULT_1X2.required_fields == ("home_goals", "away_goals")

    def test_outcome_count(self):
        assert GOALS_OVER_UNDER.get_outcome_count() == 2
        assert BTTS_MARKET.get_outcome_count() == 2
        assert MATCH_RESULT_1X2.get_outcome_count() == 3


class TestResolveOutcomeGeneral:
    """Tests for resolve_outcome_general() across market types."""

    def test_over_under_over(self):
        match_data = {"total_goals": 4}
        result = GOALS_OVER_UNDER.resolve_outcome_general(match_data)
        assert result == MarketOutcome.OVER

    def test_over_under_under(self):
        match_data = {"total_goals": 1}
        result = GOALS_OVER_UNDER.resolve_outcome_general(match_data)
        assert result == MarketOutcome.UNDER

    def test_over_under_push(self):
        market = ResearchMarket(
            market_type=MarketType.GOALS_TOTAL,
            target_field="total_goals",
            line=3.0,
            odds_over_field="o",
            odds_under_field="u",
        )
        result = market.resolve_outcome_general({"total_goals": 3})
        assert result == MarketOutcome.PUSH

    def test_over_under_missing_data(self):
        result = GOALS_OVER_UNDER.resolve_outcome_general({"total_goals": None})
        assert result is None

    def test_btts_yes(self):
        match_data = {"home_goals": 2, "away_goals": 1}
        result = BTTS_MARKET.resolve_outcome_general(match_data)
        assert result == MarketOutcome.YES

    def test_btts_no_home_nil(self):
        match_data = {"home_goals": 0, "away_goals": 3}
        result = BTTS_MARKET.resolve_outcome_general(match_data)
        assert result == MarketOutcome.NO

    def test_btts_no_away_nil(self):
        match_data = {"home_goals": 2, "away_goals": 0}
        result = BTTS_MARKET.resolve_outcome_general(match_data)
        assert result == MarketOutcome.NO

    def test_btts_no_both_nil(self):
        match_data = {"home_goals": 0, "away_goals": 0}
        result = BTTS_MARKET.resolve_outcome_general(match_data)
        assert result == MarketOutcome.NO

    def test_btts_missing_data(self):
        result = BTTS_MARKET.resolve_outcome_general({"home_goals": 1})
        assert result is None

    def test_1x2_home_win(self):
        match_data = {"home_goals": 2, "away_goals": 0}
        result = MATCH_RESULT_1X2.resolve_outcome_general(match_data)
        assert result == MarketOutcome.HOME

    def test_1x2_draw(self):
        match_data = {"home_goals": 1, "away_goals": 1}
        result = MATCH_RESULT_1X2.resolve_outcome_general(match_data)
        assert result == MarketOutcome.DRAW

    def test_1x2_away_win(self):
        match_data = {"home_goals": 0, "away_goals": 3}
        result = MATCH_RESULT_1X2.resolve_outcome_general(match_data)
        assert result == MarketOutcome.AWAY

    def test_1x2_missing_data(self):
        result = MATCH_RESULT_1X2.resolve_outcome_general({})
        assert result is None

    def test_team_goals_over(self):
        match_data = {"home_goals": 2}
        result = HOME_GOALS_OVER_UNDER.resolve_outcome_general(match_data)
        assert result == MarketOutcome.OVER  # 2 > 1.5

    def test_team_goals_under(self):
        match_data = {"home_goals": 1}
        result = HOME_GOALS_OVER_UNDER.resolve_outcome_general(match_data)
        assert result == MarketOutcome.UNDER  # 1 < 1.5


class TestFairProbabilityThreeWay:
    """Tests for three-way fair probability calculation."""

    def test_symmetric_odds(self):
        """Equal odds → equal probabilities."""
        h, d, a = MATCH_RESULT_1X2.fair_probability_three_way(3.0, 3.0, 3.0)
        assert abs(h - 1 / 3) < 0.001
        assert abs(d - 1 / 3) < 0.001
        assert abs(a - 1 / 3) < 0.001

    def test_probabilities_sum_to_one(self):
        h, d, a = MATCH_RESULT_1X2.fair_probability_three_way(2.0, 3.5, 4.0)
        assert abs(h + d + a - 1.0) < 0.001

    def test_lower_odds_higher_probability(self):
        """Home favorite: lower home odds → higher home probability."""
        h, d, a = MATCH_RESULT_1X2.fair_probability_three_way(1.5, 4.0, 6.0)
        assert h > d
        assert h > a

    def test_margin_stripped(self):
        """Input with margin still produces fair (sum=1) output."""
        # 10% overround
        h, d, a = MATCH_RESULT_1X2.fair_probability_three_way(1.8, 3.0, 5.0)
        assert abs(h + d + a - 1.0) < 0.001


class TestValidateMatchData:
    """Tests for match data validation."""

    def test_goals_market_valid(self):
        assert GOALS_OVER_UNDER.validate_match_data({"total_goals": 3})

    def test_goals_market_missing(self):
        assert not GOALS_OVER_UNDER.validate_match_data({"total_corners": 10})

    def test_goals_market_none_value(self):
        assert not GOALS_OVER_UNDER.validate_match_data({"total_goals": None})

    def test_btts_valid(self):
        assert BTTS_MARKET.validate_match_data({"home_goals": 1, "away_goals": 2})

    def test_btts_partial(self):
        assert not BTTS_MARKET.validate_match_data({"home_goals": 1})

    def test_1x2_valid(self):
        assert MATCH_RESULT_1X2.validate_match_data({"home_goals": 0, "away_goals": 0})


class TestMarketRegistry:
    """Tests for MarketRegistry."""

    def test_create_default_registry(self):
        registry = create_default_registry()
        assert len(registry.all_markets) == 12

    def test_get_by_type(self):
        registry = create_default_registry()
        market = registry.get(MarketType.GOALS_TOTAL)
        assert market is not None
        assert market.target_field == "total_goals"

    def test_get_unknown_type(self):
        registry = MarketRegistry()
        assert registry.get(MarketType.GOALS_TOTAL) is None

    def test_register_custom_market(self):
        registry = MarketRegistry()
        custom = ResearchMarket(
            market_type=MarketType.GOALS_TOTAL,
            target_field="total_goals",
            line=3.5,
            odds_over_field="o",
            odds_under_field="u",
        )
        registry.register(custom)
        assert registry.get(MarketType.GOALS_TOTAL) == custom

    def test_get_by_category(self):
        registry = create_default_registry()
        ou_markets = registry.get_by_category(MarketCategory.OVER_UNDER)
        assert len(ou_markets) == 10  # 4 total + 6 team-specific
        yn_markets = registry.get_by_category(MarketCategory.YES_NO)
        assert len(yn_markets) == 1
        tw_markets = registry.get_by_category(MarketCategory.THREE_WAY)
        assert len(tw_markets) == 1

    def test_get_compatible_with_model(self):
        registry = create_default_registry()
        poisson = registry.get_compatible_with_model(ProbabilityModelType.POISSON)
        # ALL markets with ALL compatibility + specific poisson markets
        assert len(poisson) >= 4  # At minimum the 4 total markets

    def test_settle_over_under(self):
        registry = create_default_registry()
        result = registry.settle(MarketType.GOALS_TOTAL, {"total_goals": 4})
        assert result == MarketOutcome.OVER

    def test_settle_btts(self):
        registry = create_default_registry()
        result = registry.settle(MarketType.BTTS, {"home_goals": 1, "away_goals": 1})
        assert result == MarketOutcome.YES

    def test_settle_1x2(self):
        registry = create_default_registry()
        result = registry.settle(
            MarketType.MATCH_RESULT_1X2, {"home_goals": 3, "away_goals": 1}
        )
        assert result == MarketOutcome.HOME

    def test_settle_unknown_market(self):
        registry = MarketRegistry()
        result = registry.settle(MarketType.GOALS_TOTAL, {"total_goals": 3})
        assert result is None

    def test_market_types_property(self):
        registry = create_default_registry()
        types = registry.market_types
        assert MarketType.GOALS_TOTAL in types
        assert MarketType.BTTS in types
        assert MarketType.MATCH_RESULT_1X2 in types


class TestDefaultSettlementAdapter:
    """Tests for the default settlement adapter."""

    def test_can_settle_with_data(self):
        adapter = DefaultSettlementAdapter()
        assert adapter.can_settle(GOALS_OVER_UNDER, {"total_goals": 3})

    def test_cannot_settle_without_data(self):
        adapter = DefaultSettlementAdapter()
        assert not adapter.can_settle(GOALS_OVER_UNDER, {"corners_home": 5})

    def test_settle_returns_outcome(self):
        adapter = DefaultSettlementAdapter()
        result = adapter.settle(CORNERS_OVER_UNDER, {"total_corners": 12})
        assert result == MarketOutcome.OVER

    def test_settle_returns_none_when_data_missing(self):
        adapter = DefaultSettlementAdapter()
        result = adapter.settle(CORNERS_OVER_UNDER, {})
        assert result is None


class TestMarketToDict:
    """Tests for market serialization."""

    def test_to_dict_contains_required_fields(self):
        d = GOALS_OVER_UNDER.to_dict()
        assert d["market_type"] == "GOALS_TOTAL"
        assert d["target_field"] == "total_goals"
        assert d["line"] == 2.5
        assert d["category"] == "OVER_UNDER"
        assert "market_id" in d

    def test_btts_to_dict(self):
        d = BTTS_MARKET.to_dict()
        assert d["market_type"] == "BTTS"
        assert d["line"] is None
        assert d["category"] == "YES_NO"

    def test_1x2_to_dict(self):
        d = MATCH_RESULT_1X2.to_dict()
        assert d["market_type"] == "MATCH_RESULT_1X2"
        assert d["category"] == "THREE_WAY"
