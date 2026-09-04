"""Focused tests for immutable quote provenance and capture policy."""

from datetime import datetime, timedelta, timezone

import pytest

from src.domain.market import (
    MarketPrice,
    MarketType,
    PriceSide,
    PriceType,
    QuoteStatus,
    TimestampSemantics,
)
from src.domain.market_price_capture_policy import (
    CLVComparisonLabel,
    CaptureCadence,
    QuoteForClassification,
    capture_window_for,
    classify_quote_series,
    clv_comparison_label,
)
from src.research.closing.provider import ClosingOddsObservation
from src.research.closing.validation import ClosingLineValidator


def _price(**overrides) -> MarketPrice:
    values = {
        "match_id": 7,
        "market_type": MarketType.OVER_UNDER,
        "line": 2.5,
        "side": PriceSide.OVER,
        "price_type": PriceType.SNAPSHOT,
        "odds": 1.95,
        "timestamp": 1_700_000_000,
        "source": "provider-a",
        "bookmaker": "book-a",
        "provider_source_time": 1_700_000_000,
        "retrieved_at": 1_700_000_005,
        "kickoff_at": 1_700_001_000,
        "timestamp_semantics": TimestampSemantics.PROVIDER_SOURCE_TIME,
    }
    values.update(overrides)
    return MarketPrice(**values)


def test_market_price_hash_is_deterministic_and_classification_independent():
    snapshot = _price(price_type=PriceType.SNAPSHOT)
    closing = _price(price_type=PriceType.CLOSING)
    assert snapshot.quote_hash == closing.quote_hash
    assert snapshot.bookmaker == "book-a"
    assert snapshot.to_dict()["timestamp_semantics"] == "PROVIDER_SOURCE_TIME"


def test_market_price_old_constructor_remains_supported():
    price = MarketPrice(
        1, MarketType.OVER_UNDER, 2.5, PriceSide.OVER,
        PriceType.ENTRY, 2.0, 100, "pinnacle",
    )
    assert price.bookmaker == "pinnacle"
    assert price.retrieved_at == 100
    assert len(price.quote_hash or "") == 64


def test_market_price_rejects_provider_time_after_default_retrieval():
    with pytest.raises(ValueError, match="provider_source_time"):
        _price(
            timestamp=1_700_000_000,
            retrieved_at=None,
            provider_source_time=1_700_000_001,
        )


def test_market_price_rejects_post_kickoff_prematch_quote():
    with pytest.raises(ValueError, match="strictly before kickoff"):
        _price(timestamp=1_700_001_000, retrieved_at=1_700_001_000)


def test_capture_cadence_escalates_toward_kickoff():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert capture_window_for(now, now + timedelta(days=2)).cadence == CaptureCadence.DAILY
    assert capture_window_for(now, now + timedelta(hours=12)).cadence == CaptureCadence.EVERY_30_MINUTES
    assert capture_window_for(now, now + timedelta(hours=3)).cadence == CaptureCadence.EVERY_5_TO_10_MINUTES
    assert capture_window_for(now, now + timedelta(minutes=30)).cadence == CaptureCadence.EVERY_1_TO_2_MINUTES
    assert capture_window_for(now, now).cadence == CaptureCadence.STOPPED


def test_classification_retains_every_quote_and_excludes_live_from_clv():
    kickoff = datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc)
    quotes = [
        QuoteForClassification("opening", kickoff - timedelta(hours=2), "book-a", 2.1),
        QuoteForClassification("entry", kickoff - timedelta(hours=1), "book-a", 2.0),
        QuoteForClassification(
            "suspended", kickoff - timedelta(minutes=30), "book-a", 1.99,
            QuoteStatus.SUSPENDED,
        ),
        QuoteForClassification("closing", kickoff - timedelta(minutes=1), "book-a", 1.95),
        QuoteForClassification("live", kickoff, "book-a", 1.9),
    ]
    classified = classify_quote_series(quotes, kickoff, entry_quote_hash="entry")
    assert len(classified) == len(quotes)
    assert [item.price_type for item in classified] == [
        PriceType.OPENING, PriceType.ENTRY, PriceType.SNAPSHOT,
        PriceType.CLOSING, PriceType.LIVE,
    ]
    assert classified[-1].clv_eligible is False
    assert classified[2].clv_eligible is False


def test_clv_comparison_is_explicitly_labeled():
    assert clv_comparison_label("Pinnacle", "pinnacle") == CLVComparisonLabel.SAME_BOOK_CLV
    assert clv_comparison_label("pinnacle", "bet365") == CLVComparisonLabel.CROSS_BOOK_CLV


def _observation(**overrides) -> ClosingOddsObservation:
    values = {
        "fixture_id": "fixture-1",
        "market": "GOALS_TOTAL",
        "selection": "OVER",
        "line": 2.5,
        "decimal_odds": 1.95,
        "bookmaker": "pinnacle",
        "source": "provider-a",
        "closing_timestamp": 900.0,
    }
    values.update(overrides)
    return ClosingOddsObservation(**values)


@pytest.mark.parametrize("odds", [1.0, 0.9])
def test_validator_rejects_odds_not_above_one(odds):
    result = ClosingLineValidator().validate(
        _observation(decimal_odds=odds), "fixture-1", "GOALS_TOTAL", "OVER", 100, 1000
    )
    assert result.valid is False
    assert any("Invalid odds" in error for error in result.errors)


def test_validator_rejects_at_or_after_kickoff():
    result = ClosingLineValidator().validate(
        _observation(closing_timestamp=1000),
        "fixture-1", "GOALS_TOTAL", "OVER", 100, 1000,
    )
    assert result.valid is False
    assert any("strictly before kickoff" in error for error in result.errors)


def test_validator_enforces_expected_line_and_requested_same_book():
    result = ClosingLineValidator().validate(
        _observation(line=3.5, bookmaker="bet365"),
        "fixture-1", "GOALS_TOTAL", "OVER", 100, 1000,
        expected_line=2.5,
        expected_bookmaker="pinnacle",
        require_same_book=True,
    )
    assert result.valid is False
    assert any("Line mismatch" in error for error in result.errors)
    assert any("Bookmaker mismatch" in error for error in result.errors)
