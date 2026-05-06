"""Historical data fetcher for Polymarket markets"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

import httpx

from src.utils.logging import get_logger


logger = get_logger(__name__)


GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"


class HistoricalFetcher:
    """
    Fetches historical data from Polymarket for backtesting.

    Retrieves:
    - Market metadata
    - Price history
    - Volume history
    - Order book snapshots
    """

    def __init__(self, cache_dir: str = "data/cache"):
        self.http = httpx.AsyncClient(timeout=60.0)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def close(self):
        """Close HTTP client"""
        await self.http.aclose()

    async def get_market_history(
        self,
        market_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get historical data for a market.

        Returns dict with:
        - prices: List of price data points
        - volumes: List of volume data points
        - trades: List of trade data
        """
        # Check cache first
        cache_file = self.cache_dir / f"{market_id}.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)

        data = {
            "market_id": market_id,
            "prices": [],
            "volumes": [],
            "trades": [],
            "fetched_at": datetime.now().isoformat(),
        }

        # Try to fetch from API
        try:
            # Get market info
            market = await self._fetch_market(market_id)
            if market:
                data["market"] = market

            # Get price history (if available)
            prices = await self._fetch_price_history(market_id, start_date, end_date)
            data["prices"] = prices

            # Get volume history
            volumes = await self._fetch_volume_history(market_id, start_date, end_date)
            data["volumes"] = volumes

            # Cache result
            with open(cache_file, 'w') as f:
                json.dump(data, f, default=str)

        except Exception as e:
            logger.error(f"Failed to fetch market history: {e}")

        return data

    async def _fetch_market(self, market_id: str) -> Optional[Dict]:
        """Fetch market metadata"""
        try:
            response = await self.http.get(f"{GAMMA_API_URL}/markets/{market_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch market: {e}")
            return None

    async def _fetch_price_history(
        self,
        market_id: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> List[Dict]:
        """Fetch price history for a market"""
        try:
            params = {"market": market_id}
            if start_date:
                params["start_date"] = start_date.isoformat()
            if end_date:
                params["end_date"] = end_date.isoformat()

            response = await self.http.get(
                f"{GAMMA_API_URL}/prices-history",
                params=params
            )
            response.raise_for_status()
            return response.json().get("history", [])
        except Exception as e:
            logger.warning(f"Price history not available: {e}")
            return []

    async def _fetch_volume_history(
        self,
        market_id: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> List[Dict]:
        """Fetch volume history for a market"""
        try:
            params = {"market": market_id}
            if start_date:
                params["start_date"] = start_date.isoformat()
            if end_date:
                params["end_date"] = end_date.isoformat()

            response = await self.http.get(
                f"{GAMMA_API_URL}/volume-history",
                params=params
            )
            response.raise_for_status()
            return response.json().get("history", [])
        except Exception as e:
            logger.warning(f"Volume history not available: {e}")
            return []

    async def get_markets_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        categories: List[str] = None,
    ) -> List[Dict]:
        """Get all markets that were active in a date range"""
        try:
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "limit": 500,
            }
            if categories:
                params["categories"] = ",".join(categories)

            response = await self.http.get(f"{GAMMA_API_URL}/markets", params=params)
            response.raise_for_status()
            data = response.json()

            return data.get("markets", [])

        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    async def get_trade_history(
        self,
        token_id: str,
        limit: int = 1000,
    ) -> List[Dict]:
        """Get trade history for a token"""
        try:
            response = await self.http.get(
                f"{CLOB_API_URL}/trades",
                params={"token_id": token_id, "limit": limit}
            )
            response.raise_for_status()
            return response.json().get("trades", [])
        except Exception as e:
            logger.error(f"Failed to fetch trades: {e}")
            return []

    async def get_order_book_snapshots(
        self,
        token_id: str,
        intervals: int = 10,
    ) -> List[Dict]:
        """
        Get periodic order book snapshots.

        Useful for backtesting order book dynamics.
        """
        snapshots = []
        try:
            for _ in range(intervals):
                orderbook = await self.http.get(
                    f"{CLOB_API_URL}/orderbooks",
                    params={"token_id": token_id}
                )
                if orderbook.status_code == 200:
                    snapshots.append({
                        "timestamp": datetime.now().isoformat(),
                        "data": orderbook.json()
                    })

                await asyncio.sleep(6)  # 10 snapshots per minute

        except Exception as e:
            logger.error(f"Failed to get order book snapshots: {e}")

        return snapshots

    def generate_synthetic_data(
        self,
        duration_minutes: int,
        start_price: float = 0.5,
        volatility: float = 0.02,
    ) -> List[Dict]:
        """
        Generate synthetic price data for testing.

        Used when historical data is not available.
        """
        import random
        import numpy as np

        data = []
        current_price = start_price
        base_volatility = volatility / (60 / duration_minutes)  # Per interval

        for i in range(60 * 24):  # 24 hours of 1-minute data
            # Random walk with mean reversion
            change = np.random.normal(0, base_volatility)
            change += (start_price - current_price) * 0.1  # Mean reversion
            current_price = max(0.01, min(0.99, current_price + change))

            data.append({
                "timestamp": (datetime.now() - timedelta(minutes=60*24-i)).isoformat(),
                "price": current_price,
                "volume": random.uniform(100, 10000),
            })

        return data