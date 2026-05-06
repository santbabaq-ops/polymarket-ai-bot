"""AI Strategist using Claude API for market analysis"""

import json
from typing import Optional, Dict, Any

from anthropic import Anthropic

from src.config import Config
from src.utils.logging import get_logger
from .base import BaseStrategy, Signal, SignalType, MarketData


logger = get_logger(__name__)


SYSTEM_PROMPT = """You are an expert trading analyst for prediction markets on Polymarket.
You analyze market questions, order book data, and recent trades to generate trading signals.

Your task is to determine whether to BUY, SELL, or HOLD based on:
1. Market question and outcomes
2. Current prices and liquidity
3. Volume trends
4. Market sentiment indicators

Output your analysis in JSON format with the following structure:
{
    "signal": "BUY" | "SELL" | "HOLD" | "CLOSE",
    "confidence": 0.0-1.0,
    "target_outcome": 0 or 1 (for YES/NO markets),
    "price": target_price or null,
    "reason": "brief explanation"
}

Considerations:
- Only signal BUY/SELL when confidence > 0.6
- Consider Kelly criterion for position sizing based on odds
- Factor in market liquidity for slippage risk
- Avoid trading very low liquidity markets
"""


class AIStrategist(BaseStrategy):
    """
    AI-powered strategy using Claude for market analysis.

    Analyzes market data and generates trading signals based on
    natural language reasoning.
    """

    def __init__(self, config: Config):
        super().__init__(config)
        self.client = Anthropic(api_key=config.anthropic_api_key)
        self.max_tokens = 1024
        self.temperature = 0.7

    async def analyze(self, market: Dict[str, Any]) -> Optional[Signal]:
        """Analyze a single market and generate a signal"""
        try:
            # Build analysis prompt
            prompt = self._build_prompt(market)

            # Call Claude
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse response
            content = response.content[0].text
            signal_data = self._parse_response(content)

            if signal_data and signal_data.get("signal") != "HOLD":
                return Signal(
                    signal_type=SignalType(signal_data["signal"]),
                    market_id=market.get("id", ""),
                    token_id=self._get_token_id(market, signal_data.get("target_outcome", 0)),
                    confidence=signal_data.get("confidence", 0.5),
                    price=signal_data.get("price"),
                    reason=signal_data.get("reason", ""),
                )

            return None

        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return None

    async def on_tick(self, markets: list[dict]) -> list[Signal]:
        """Analyze multiple markets and return signals"""
        signals = []

        for market in markets:
            signal = await self.analyze(market)
            if signal:
                signals.append(signal)

        return signals

    def _build_prompt(self, market: Dict[str, Any]) -> str:
        """Build analysis prompt from market data"""
        prompt = f"""Analyze the following Polymarket prediction:

Question: {market.get('question', 'Unknown')}
Volume: ${float(market.get('volume', 0)):,.2f}
Liquidity: ${float(market.get('liquidity', 0)):,.2f}

"""

        # Add outcomes if available
        outcomes = market.get('outcomes', ['YES', 'NO'])
        outcome_prices = market.get('outcomePrices', ['0.5', '0.5'])

        for i, (outcome, price) in enumerate(zip(outcomes, outcome_prices)):
            prompt += f"Outcome {i} ({outcome}): {float(price):.2%}\n"

        # Add order book summary if available
        if market.get('order_book'):
            bids = market['order_book'].get('bids', [])[:3]
            asks = market['order_book'].get('asks', [])[:3]
            if bids:
                prompt += f"\nTop Bids: " + ", ".join(f"{float(b.get('price', 0)):.2f}" for b in bids) + "\n"
            if asks:
                prompt += f"Top Asks: " + ", ".join(f"{float(a.get('price', 0)):.2f}" for a in asks) + "\n"

        prompt += "\nProvide your trading signal in JSON format."

        return prompt

    def _parse_response(self, content: str) -> Optional[Dict]:
        """Parse JSON signal from Claude response"""
        try:
            # Try to extract JSON from response
            content = content.strip()

            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            return json.loads(content)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Claude response: {e}")
            return None

    def _get_token_id(self, market: Dict, outcome_index: int) -> str:
        """Get token ID for a specific outcome"""
        try:
            token_ids = market.get('clob_token_ids', [])
            if isinstance(token_ids, str):
                import ast
                token_ids = ast.literal_eval(token_ids)

            if outcome_index < len(token_ids):
                return token_ids[outcome_index]

            # Default to YES token
            return token_ids[1] if len(token_ids) > 1 else token_ids[0]

        except Exception as e:
            logger.error(f"Failed to get token ID: {e}")
            return ""