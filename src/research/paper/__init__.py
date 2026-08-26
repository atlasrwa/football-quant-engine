"""Batch 10 — Paper Trading Foundation.

Research-only paper trading for evaluating strategy forward performance.

Paper trading is research evaluation ONLY.
It does NOT constitute production betting authorization.
No real money. No wallets. No brokers. No bookmaker execution.

Architecture:
    Eligible Strategy → Prediction → Odds → Paper Trade → Settlement → CLV → Report
"""

from src.research.paper.paper_trade import PaperTrade, PaperTradeStatus
from src.research.paper.staking import StakingModel, StakingType, StakingConfig
from src.research.paper.settlement import settle_trade, SettlementResult
from src.research.paper.clv import compute_clv, CLVResult
from src.research.paper.eligibility import PaperEligibility, EligibilityCriteria

__all__ = [
    "PaperTrade",
    "PaperTradeStatus",
    "StakingModel",
    "StakingType",
    "StakingConfig",
    "settle_trade",
    "SettlementResult",
    "compute_clv",
    "CLVResult",
    "PaperEligibility",
    "EligibilityCriteria",
]
