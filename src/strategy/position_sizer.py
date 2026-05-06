"""Position sizing using Kelly criterion and risk management"""

import math
from dataclasses import dataclass
from typing import Optional

from src.utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class PositionSize:
    """Calculated position size"""
    size: float  # Size in USDC
    fraction: float  # Kelly fraction used
    expected_return: float
    risk_adjusted_size: float


class PositionSizer:
    """
    Position sizing using Kelly criterion and risk management.

    The Kelly criterion calculates the optimal fraction of bankroll
    to bet based on edge and odds.
    """

    def __init__(
        self,
        kelly_fraction: float = 0.25,
        max_position_pct: float = 0.1,  # Max 10% of bankroll
        max_daily_loss_pct: float = 0.1,  # Max 10% daily loss
        bankroll: float = 0,
    ):
        self.kelly_fraction = kelly_fraction
        self.max_position_pct = max_position_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.bankroll = bankroll
        self.daily_loss = 0.0
        self.daily_loss_reset_hour = 24  # Reset at midnight UTC

    def calculate_size(
        self,
        price: float,
        win_probability: float,
        odds: Optional[float] = None,
        confidence: float = 1.0,
    ) -> PositionSize:
        """
        Calculate optimal position size using Kelly criterion.

        Args:
            price: Current price of the asset
            win_probability: Estimated probability of winning (0-1)
            odds: Payout odds (for prediction markets, this is 1/price)
            confidence: Strategy confidence (0-1)

        Returns:
            PositionSize with calculated sizes
        """
        # Default odds from price
        if odds is None:
            odds = 1 / price

        # Kelly formula: f* = (bp - q) / b
        # where b = odds - 1, p = win probability, q = 1 - p
        b = odds - 1
        p = win_probability
        q = 1 - p

        if b <= 0:
            logger.warning("Invalid odds, returning zero size")
            return PositionSize(0, 0, 0, 0)

        kelly = (b * p - q) / b

        # Apply Kelly fraction (typically use fractional Kelly for safety)
        adjusted_kelly = kelly * self.kelly_fraction

        # Ensure positive Kelly
        if adjusted_kelly <= 0:
            logger.info("Negative expected value, skipping")
            return PositionSize(0, 0, 0, 0)

        # Calculate base size
        if self.bankroll > 0:
            base_size = self.bankroll * adjusted_kelly
        else:
            # If no bankroll, use price as base
            base_size = adjusted_kelly * 1000

        # Apply confidence multiplier
        risk_adjusted = base_size * confidence

        # Apply maximum position limit
        if self.bankroll > 0:
            max_size = self.bankroll * self.max_position_pct
            risk_adjusted = min(risk_adjusted, max_size)

        # Apply daily loss limit
        remaining_daily_loss = self.max_daily_loss_pct * self.bankroll - self.daily_loss
        if remaining_daily_loss <= 0:
            logger.warning("Daily loss limit reached")
            return PositionSize(0, adjusted_kelly, kelly, 0)

        risk_adjusted = min(risk_adjusted, remaining_daily_loss)

        # Minimum size check
        min_size = 1.0  # $1 minimum
        if risk_adjusted < min_size:
            risk_adjusted = 0

        return PositionSize(
            size=risk_adjusted,
            fraction=adjusted_kelly,
            expected_return=kelly,
            risk_adjusted_size=risk_adjusted,
        )

    def calculate_kelly(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """
        Calculate Kelly fraction from historical performance.

        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning amount
            avg_loss: Average losing amount

        Returns:
            Kelly fraction
        """
        if avg_loss == 0:
            return 0

        win_loss_ratio = avg_win / avg_loss
        q = 1 - win_rate
        p = win_rate

        # Kelly with ratio: f = (p(b+1) - 1) / b
        b = win_loss_ratio
        kelly = (p * (b + 1) - 1) / b

        return max(0, min(kelly, 1))  # Clamp to [0, 1]

    def update_bankroll(self, pnl: float) -> None:
        """Update bankroll after a trade"""
        self.bankroll += pnl
        self.daily_loss += min(0, pnl)  # Track only losses

    def check_risk_limits(self) -> bool:
        """Check if any risk limits are hit"""
        if self.daily_loss >= self.max_daily_loss_pct * self.bankroll:
            logger.warning("Daily loss limit reached")
            return False

        if self.bankroll <= 0:
            logger.error("Bankroll depleted")
            return False

        return True

    def reset_daily_loss(self) -> None:
        """Reset daily loss counter"""
        self.daily_loss = 0

    def set_bankroll(self, amount: float) -> None:
        """Set the current bankroll"""
        self.bankroll = amount

    def get_kelly_recommendation(self, price: float) -> dict:
        """
        Get Kelly recommendation for a given price.

        Returns dict with recommended action and size.
        """
        if price <= 0.1:
            # Very cheap, high potential
            return {
                "action": "BUY",
                "size_pct": 0.5,  # 50% of Kelly
                "reason": "High potential at low cost"
            }
        elif price >= 0.9:
            # Very expensive, limited upside
            return {
                "action": "SELL",
                "size_pct": 0.25,
                "reason": "Limited upside at high price"
            }
        else:
            # Normal range
            return {
                "action": "BUY" if price < 0.5 else "SELL",
                "size_pct": 0.25,
                "reason": "Standard Kelly sizing"
            }


class RiskManager:
    """Manages overall trading risk"""

    def __init__(self, config: dict = None):
        config = config or {}
        self.max_positions = config.get("max_positions", 5)
        self.max_correlation = config.get("max_correlation", 0.7)
        self.stop_loss_pct = config.get("stop_loss", 0.02)
        self.take_profit_pct = config.get("take_profit", 0.05)

        self.positions = []
        self.daily_pnl = 0

    def should_open_position(self, market_id: str, correlation: float = 0) -> bool:
        """Check if a new position should be opened"""
        # Check position limit
        if len(self.positions) >= self.max_positions:
            logger.info("Max positions reached")
            return False

        # Check correlation
        if correlation > self.max_correlation:
            logger.info(f"Position correlation too high: {correlation}")
            return False

        # Check daily loss limit
        if self.daily_pnl < -self.max_positions * self.stop_loss_pct * 100:
            logger.info("Daily loss limit reached")
            return False

        return True

    def add_position(self, position: dict) -> None:
        """Add an open position"""
        self.positions.append(position)

    def remove_position(self, market_id: str) -> None:
        """Remove a closed position"""
        self.positions = [p for p in self.positions if p.get("market_id") != market_id]

    def check_stop_loss(self, position: dict, current_price: float) -> bool:
        """Check if stop loss is hit"""
        entry_price = position.get("entry_price", 0)
        if entry_price == 0:
            return False

        pnl_pct = (current_price - entry_price) / entry_price
        return pnl_pct <= -self.stop_loss_pct

    def check_take_profit(self, position: dict, current_price: float) -> bool:
        """Check if take profit is hit"""
        entry_price = position.get("entry_price", 0)
        if entry_price == 0:
            return False

        pnl_pct = (current_price - entry_price) / entry_price
        return pnl_pct >= self.take_profit_pct

    def update_daily_pnl(self, pnl: float) -> None:
        """Update daily PnL"""
        self.daily_pnl += pnl

    def reset_daily(self) -> None:
        """Reset daily tracking"""
        self.daily_pnl = 0