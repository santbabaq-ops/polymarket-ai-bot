"""Tests for strategy modules"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.strategy.base import BaseStrategy, Signal, SignalType, StrategyType
from src.strategy.position_sizer import PositionSizer, PositionSize


class TestSignal:
    """Tests for Signal dataclass"""

    def test_signal_creation(self):
        """Test creating a signal"""
        signal = Signal(
            signal_type=SignalType.BUY,
            market_id="test-market",
            token_id="token-123",
            confidence=0.8,
            price=0.55,
            reason="Test signal"
        )

        assert signal.signal_type == SignalType.BUY
        assert signal.market_id == "test-market"
        assert signal.confidence == 0.8
        assert signal.is_actionable is True

    def test_signal_hold_not_actionable(self):
        """Test that HOLD signals are not actionable"""
        signal = Signal(
            signal_type=SignalType.HOLD,
            market_id="test",
            token_id="token",
            confidence=0.5
        )

        assert signal.is_actionable is False


class TestPositionSizer:
    """Tests for PositionSizer"""

    def test_kelly_calculation(self):
        """Test Kelly criterion calculation"""
        sizer = PositionSizer(kelly_fraction=0.25, bankroll=10000)

        # 60% win rate, 2:1 odds
        position = sizer.calculate_size(
            price=0.4,
            win_probability=0.6,
            confidence=1.0
        )

        assert position.size > 0
        assert position.size <= 10000 * 0.25  # Max Kelly fraction

    def test_kelly_negative_edge(self):
        """Test Kelly with negative edge"""
        sizer = PositionSizer(kelly_fraction=0.25, bankroll=10000)

        # 30% win rate at even odds (negative edge)
        position = sizer.calculate_size(
            price=0.5,
            win_probability=0.3,
            confidence=1.0
        )

        assert position.size == 0  # No position with negative edge

    def test_confidence_adjustment(self):
        """Test that confidence adjusts position size"""
        sizer = PositionSizer(kelly_fraction=0.25, bankroll=10000)

        high_conf = sizer.calculate_size(0.5, 0.7, confidence=1.0)
        low_conf = sizer.calculate_size(0.5, 0.7, confidence=0.5)

        assert high_conf.size > low_conf.size

    def test_risk_limits(self):
        """Test risk limit checks"""
        sizer = PositionSizer(
            kelly_fraction=0.25,
            bankroll=10000,
            max_position_pct=0.1
        )

        position = sizer.calculate_size(
            price=0.5,
            win_probability=0.7,
            confidence=1.0
        )

        # Should be limited by max_position_pct
        assert position.size <= 10000 * 0.1

    def test_bankroll_update(self):
        """Test bankroll updates after trades"""
        sizer = PositionSizer(bankroll=10000)
        initial_bankroll = sizer.bankroll

        sizer.update_bankroll(500)  # Win
        assert sizer.bankroll == initial_bankroll + 500

        sizer.update_bankroll(-300)  # Loss
        assert sizer.bankroll == initial_bankroll + 500 - 300
        assert sizer.daily_loss == 300

    def test_daily_loss_limit(self):
        """Test daily loss limit"""
        sizer = PositionSizer(
            bankroll=10000,
            max_daily_loss_pct=0.1,
            kelly_fraction=1.0  # Full Kelly
        )

        # Simulate daily loss (exceeds 10% = 1000 limit)
        sizer.update_bankroll(-600)
        sizer.update_bankroll(-500)

        # Next position should be blocked
        position = sizer.calculate_size(0.5, 0.7, confidence=1.0)
        assert position.size == 0

    def test_kelly_recommendation(self):
        """Test Kelly recommendation helper"""
        sizer = PositionSizer()

        # Low price - high potential
        rec = sizer.get_kelly_recommendation(0.05)
        assert rec["action"] == "BUY"
        assert rec["size_pct"] == 0.5

        # High price - limited upside
        rec = sizer.get_kelly_recommendation(0.95)
        assert rec["action"] == "SELL"
        assert rec["size_pct"] == 0.25


class TestStrategyBase:
    """Tests for BaseStrategy"""

    def test_strategy_type_enum(self):
        """Test StrategyType enum values"""
        assert StrategyType.AI.value == "ai"
        assert StrategyType.ML.value == "ml"
        assert StrategyType.CUSTOM.value == "custom"


# Example custom strategy for testing
class MockStrategy(BaseStrategy):
    """Mock strategy for testing"""

    async def analyze(self, market):
        return Signal(
            signal_type=SignalType.BUY,
            market_id=market.get("id", ""),
            token_id="mock-token",
            confidence=0.7,
            reason="Mock strategy signal"
        )

    async def on_tick(self, markets):
        signals = []
        for market in markets:
            signal = await self.analyze(market)
            if signal:
                signals.append(signal)
        return signals


class TestMockStrategy:
    """Tests for mock strategy"""

    @pytest.mark.asyncio
    async def test_analyze(self):
        """Test strategy analysis"""
        config = MagicMock()
        strategy = MockStrategy(config)

        market = {"id": "test-market", "price": 0.5}
        signal = await strategy.analyze(market)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.7

    @pytest.mark.asyncio
    async def test_on_tick_multiple_markets(self):
        """Test strategy with multiple markets"""
        config = MagicMock()
        strategy = MockStrategy(config)

        markets = [
            {"id": "market-1"},
            {"id": "market-2"},
            {"id": "market-3"},
        ]

        signals = await strategy.on_tick(markets)

        assert len(signals) == 3
        assert all(s.signal_type == SignalType.BUY for s in signals)