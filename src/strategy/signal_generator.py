"""Signal generator combining multiple indicators"""

from typing import Optional, Dict, Any, List
import statistics

from src.utils.logging import get_logger
from .base import Signal, SignalType


logger = get_logger(__name__)


class SignalGenerator:
    """
    Generates trading signals from multiple indicators.

    Combines various technical and market-based indicators to
    produce consensus signals.
    """

    def __init__(self, min_confidence: float = 0.6):
        self.min_confidence = min_confidence
        self.indicators = []

    def add_indicator(self, indicator: callable) -> None:
        """Add an indicator function to the generator"""
        self.indicators.append(indicator)

    async def generate(
        self,
        market: Dict[str, Any],
        indicators_override: List[callable] = None,
    ) -> Optional[Signal]:
        """
        Generate signal by combining indicator outputs.

        Each indicator should be a callable that takes market data
        and returns a dict with 'signal', 'confidence', and 'weight'.
        """
        indicators = indicators_override or self.indicators

        if not indicators:
            logger.warning("No indicators available")
            return None

        votes = {SignalType.BUY: 0.0, SignalType.SELL: 0.0, SignalType.HOLD: 0.0}

        for indicator in indicators:
            try:
                result = await indicator(market) if hasattr(indicator, '__aenter__') else indicator(market)

                if result:
                    signal = SignalType(result.get('signal', 'HOLD'))
                    confidence = result.get('confidence', 0.5)
                    weight = result.get('weight', 1.0)

                    votes[signal] += confidence * weight

            except Exception as e:
                logger.error(f"Indicator failed: {e}")
                continue

        # Normalize votes
        total = sum(votes.values())
        if total > 0:
            for signal in votes:
                votes[signal] /= total

        # Determine final signal
        max_signal = max(votes, key=votes.get)
        max_confidence = votes[max_signal]

        if max_signal == SignalType.HOLD or max_confidence < self.min_confidence:
            return None

        return Signal(
            signal_type=max_signal,
            market_id=market.get("id", ""),
            token_id=self._get_target_token(market, max_signal),
            confidence=max_confidence,
            price=self._get_target_price(market, max_signal),
            reason=f"Consensus from {len(indicators)} indicators",
        )

    def _get_target_token(self, market: Dict, signal: SignalType) -> str:
        """Get token ID for signal"""
        try:
            token_ids = market.get('clob_token_ids', [])
            if isinstance(token_ids, str):
                import ast
                token_ids = ast.literal_eval(token_ids)

            # BUY = YES (index 1), SELL = NO (index 0)
            if signal == SignalType.BUY:
                return token_ids[1] if len(token_ids) > 1 else token_ids[0]
            else:
                return token_ids[0]

        except Exception:
            return ""

    def _get_target_price(self, market: Dict, signal: SignalType) -> Optional[float]:
        """Get target price for signal"""
        try:
            prices = market.get('outcomePrices', [])
            if len(prices) >= 2:
                if signal == SignalType.BUY:
                    return float(prices[1])  # YES price
                else:
                    return float(prices[0])  # NO price
        except Exception:
            pass
        return None


# Built-in indicator functions

def price_momentum_indicator(market: Dict[str, Any]) -> Dict:
    """Indicator based on price momentum"""
    try:
        prices = market.get('outcomePrices', [])
        if len(prices) < 2:
            return None

        current = float(prices[1])
        previous = market.get('previous_price', current)
        momentum = (current - previous) / max(previous, 0.01)

        if momentum > 0.05:  # 5% increase
            return {'signal': 'BUY', 'confidence': min(abs(momentum) * 5, 1.0), 'weight': 1.0}
        elif momentum < -0.05:
            return {'signal': 'SELL', 'confidence': min(abs(momentum) * 5, 1.0), 'weight': 1.0}
        else:
            return {'signal': 'HOLD', 'confidence': 0.5, 'weight': 0.5}

    except Exception:
        return None


def volume_indicator(market: Dict[str, Any]) -> Dict:
    """Indicator based on volume analysis"""
    try:
        volume = float(market.get('volume', 0))
        avg_volume = market.get('avg_volume', volume)

        volume_ratio = volume / max(avg_volume, 1)

        if volume_ratio > 2.0:
            return {'signal': 'BUY', 'confidence': min(volume_ratio / 4, 1.0), 'weight': 0.8}
        elif volume_ratio < 0.5:
            return {'signal': 'SELL', 'confidence': min((1 - volume_ratio) * 2, 1.0), 'weight': 0.8}
        else:
            return {'signal': 'HOLD', 'confidence': 0.5, 'weight': 0.3}

    except Exception:
        return None


def liquidity_indicator(market: Dict[str, Any]) -> Dict:
    """Indicator based on liquidity"""
    try:
        liquidity = float(market.get('liquidity', 0))
        min_liquidity = 1000  # Minimum viable liquidity

        if liquidity < min_liquidity:
            return {'signal': 'HOLD', 'confidence': 1.0, 'weight': 1.5}

        # High liquidity supports larger positions
        liquidity_score = min(liquidity / 10000, 1.0)

        return {'signal': 'HOLD', 'confidence': liquidity_score, 'weight': 0.5}

    except Exception:
        return None


def spread_indicator(market: Dict[str, Any]) -> Dict:
    """Indicator based on bid-ask spread"""
    try:
        prices = market.get('outcomePrices', [])
        if len(prices) < 2:
            return None

        yes_price = float(prices[1])
        no_price = float(prices[0])

        spread = abs(yes_price - (1 - no_price))
        max_spread = 0.1  # 10% max acceptable spread

        if spread > max_spread:
            return {'signal': 'HOLD', 'confidence': 1.0, 'weight': 1.0}

        # Tighter spreads = higher confidence
        confidence = 1 - (spread / max_spread)

        return {'signal': 'HOLD', 'confidence': confidence, 'weight': 0.7}

    except Exception:
        return None