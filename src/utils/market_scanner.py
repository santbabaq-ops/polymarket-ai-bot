"""Market scanner for finding 5min/15min time-based markets"""

import re
from typing import List, Optional

from src.utils.logging import get_logger
from src.trading.polymarket_client import PolymarketClient


logger = get_logger(__name__)


# Patterns for time-based markets
TIME_PATTERNS = [
    r'(\d+)\s*min(?:ute)?s?',  # "5 min", "15 minutes"
    r'(\d+)\s*hour',            # "1 hour", "2 hours"
    r'(?:over|under)\s*(\d+)',  # "over/under 5"
    r'(?:before|after)\s*\d+',  # time comparisons
]

# Keywords that indicate time-based markets
TIME_KEYWORDS = ['min', 'minute', 'hour', 'day', 'week', 'above', 'below', 'over', 'under']


class MarketScanner:
    """Scanner for finding relevant Polymarket markets"""

    def __init__(self, client: PolymarketClient):
        self.client = client
        self._cached_markets: List[dict] = []
        self._cache_time: float = 0
        self._cache_duration: int = 30  # seconds

    async def scan_time_based_markets(
        self,
        durations: List[str] = None,
        min_volume: float = 1000,
        min_liquidity: float = 500,
    ) -> List[dict]:
        """
        Scan for time-based markets (5min, 15min, etc.)

        Args:
            durations: List of durations to filter (e.g., ['5min', '15min'])
            min_volume: Minimum market volume in USDC
            min_liquidity: Minimum market liquidity in USDC

        Returns:
            List of matching market dictionaries
        """
        import time

        # Use cache if still valid
        current_time = time.time()
        if self._cached_markets and (current_time - self._cache_time) < self._cache_duration:
            return self._filter_markets(self._cached_markets, durations, min_volume, min_liquidity)

        # Fetch fresh markets
        markets = await self.client.get_markets(limit=200)

        if markets:
            self._cached_markets = markets
            self._cache_time = current_time

        return self._filter_markets(markets, durations, min_volume, min_liquidity)

    def _filter_markets(
        self,
        markets: List[dict],
        durations: List[str] = None,
        min_volume: float = 1000,
        min_liquidity: float = 500,
    ) -> List[dict]:
        """Filter markets based on criteria"""
        filtered = []

        for market in markets:
            # Volume filter
            volume = float(market.get('volume', 0) or 0)
            if volume < min_volume:
                continue

            # Liquidity filter
            liquidity = float(market.get('liquidity', 0) or 0)
            if liquidity < min_liquidity:
                continue

            # Time-based filter
            question = market.get('question', '').lower()
            if not self._is_time_based_market(question, durations):
                continue

            filtered.append(market)

        return filtered

    def _is_time_based_market(self, question: str, durations: List[str] = None) -> bool:
        """Check if a market question is time-based"""
        question_lower = question.lower()

        # Check for time-related keywords
        has_time_keyword = any(kw in question_lower for kw in TIME_KEYWORDS)

        if not has_time_keyword:
            return False

        # If specific durations are requested, match them
        if durations:
            for duration in durations:
                duration_num = re.sub(r'[^\d]', '', duration)
                if duration_num and duration_num in question_lower:
                    return True
            return False

        return True

    def parse_market_duration(self, question: str) -> Optional[str]:
        """Parse the duration from a market question"""
        patterns = [
            (r'(\d+)\s*min(?:ute)?s?', 'min'),
            (r'(\d+)\s*hour', 'hour'),
            (r'(\d+)\s*day', 'day'),
            (r'(\d+)\s*week', 'week'),
        ]

        for pattern, unit in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                return f"{match.group(1)}{unit}"

        return None

    async def get_market_price(self, market: dict) -> dict:
        """Get current prices for a market's outcomes"""
        try:
            # Extract token IDs from market
            token_ids_raw = market.get('clob_token_ids')
            if not token_ids_raw:
                return {}

            import ast
            token_ids = ast.literal_eval(token_ids_raw)

            prices = {}
            for i, token_id in enumerate(token_ids):
                orderbook = await self.client.get_order_book(token_id)
                if orderbook.get('asks'):
                    best_ask = min(float(o['price']) for o in orderbook['asks'])
                    prices[f'outcome_{i}'] = best_ask
                else:
                    prices[f'outcome_{i}'] = None

            return prices
        except Exception as e:
            logger.error(f"Failed to get market price: {e}")
            return {}

    async def find_arb_opportunities(self, min_spread: float = 0.02) -> List[dict]:
        """Find potential arbitrage opportunities"""
        markets = await self.scan_time_based_markets()

        opportunities = []
        for market in markets:
            prices = await self.get_market_price(market)
            if len(prices) >= 2:
                # Check if prices sum to more than 1 (arbitrage opportunity)
                valid_prices = [p for p in prices.values() if p is not None]
                if len(valid_prices) == 2:
                    spread = sum(valid_prices) - 1.0
                    if spread > min_spread:
                        opportunities.append({
                            'market': market,
                            'prices': prices,
                            'spread': spread,
                            'arb_profit': spread * 100,
                        })

        return opportunities