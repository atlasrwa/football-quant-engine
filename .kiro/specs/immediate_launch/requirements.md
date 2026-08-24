# Requirements: Frontend Strategy Builder UI, Community Signal Pipeline & Execution Deep-Linker

## Overview

Build a production-ready No-Code Strategy Builder API with pre-built benchmark templates, deploy an automated community signal distribution pipeline for Telegram/Discord, and implement 1-click bet deep-linking for crypto betting platforms.

## Functional Requirements

### FR-1: Builder Templates API
- **FR-1.1:** Expose `GET /api/v1/builder/templates` returning 10 pre-built benchmark strategies using xC, xB, and xO models.
- **FR-1.2:** Templates are categorized by metric type: 4× xC (Corner Pressure), 3× xB (Booking Friction), 3× xO (High-Line Offside).
- **FR-1.3:** Each template includes: name, description, metric, market, conditions, direction, min_odds, and target leagues.
- **FR-1.4:** Templates are loadable directly into `StrategyBuilder.from_dict()` for immediate backtesting.

### FR-2: Community Signal Distribution Service
- **FR-2.1:** Implement a `CommunityBroadcaster` that polls for promoted strategies from `QuarantineTracker`.
- **FR-2.2:** Consume live daily fixtures from `FootyStatsAPIClient`, evaluate strategy conditions, and generate signals.
- **FR-2.3:** Dispatch formatted alerts to Telegram (Markdown) and Discord (rich embeds) via webhook.
- **FR-2.4:** Include in each alert: match details, Kelly unit recommendation, BTBR %, confidence badge, and Proof-of-Alpha hash.
- **FR-2.5:** Support configurable broadcast schedule (poll interval, quiet hours).
- **FR-2.6:** Non-blocking: webhook failures logged but do not halt the pipeline.

### FR-3: 1-Click Bet Deep-Linker
- **FR-3.1:** Generate platform-specific deep-link URLs from `Signal` objects for: Stake, Rollbit, and Polymarket.
- **FR-3.2:** Deep-links encode: sport, event name, market type, and direction.
- **FR-3.3:** Generate Telegram inline keyboard buttons: "Place Bet on Stake", "Place Bet on Rollbit", "View Proof Hash".
- **FR-3.4:** Support affiliate tag injection for monetization.
- **FR-3.5:** URL-encode all parameters safely.

### FR-4: Seed Benchmark Strategy Suite
- **FR-4.1:** Create 10 production-grade JSON strategy files in `data/strategies/benchmarks/`.
- **FR-4.2:** Strategies target high-volume European leagues (Premier League, La Liga, Serie A, Bundesliga, Ligue 1).
- **FR-4.3:** Each JSON file is valid input for `StrategyEvaluator.load_strategies()`.
- **FR-4.4:** Strategies use realistic thresholds derived from x-Metric distributions.

## Non-Functional Requirements

### NFR-1: Backward Compatibility
- All existing 416 tests must continue passing.
- No modifications to existing module interfaces.

### NFR-2: Resilience
- Broadcaster tolerates API failures, missing data, and webhook timeouts gracefully.
- Deep-linker produces valid URLs even with missing optional fields.

### NFR-3: Security
- No API keys or webhook URLs hardcoded — all via environment variables.
- Affiliate tags configurable but never expose user data.

### NFR-4: Performance
- Template endpoint responds in < 50ms (static data).
- Deep-link generation < 1ms per signal.
- Broadcaster processes 100 fixtures in < 5 seconds.
