"""Order executor for Polymarket CLOB with native gasless support"""

from typing import Optional
from dataclasses import dataclass

from src.utils.logging import get_logger
from .polymarket_client import PolymarketClient


logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of an order execution"""
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None


class OrderExecutor:
    """
    Executes orders on Polymarket using native gasless CLOB trading.

    Polymarket CLOB client supports gasless trading via EIP-712 off-chain
    signing. Orders are signed locally and submitted to Polymarket's API,
    which handles gas payment via their relayer.
    """

    def __init__(self, polymarket: PolymarketClient):
        self.polymarket = polymarket

    async def execute_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
    ) -> ExecutionResult:
        """
        Execute a limit order using native Polymarket gasless CLOB.

        Uses EIP-712 off-chain signing - no gas fees required.
        """
        try:
            order_id = await self.polymarket.create_order(
                token_id=token_id,
                side=side,
                price=price,
                size=size,
            )
            return ExecutionResult(success=True, order_id=order_id)

        except Exception as e:
            logger.error(f"Order execution failed: {e}")
            return ExecutionResult(success=False, error=str(e))

    async def execute_market_order(
        self,
        token_id: str,
        amount: float,
        side: str,
    ) -> ExecutionResult:
        """Execute a market order (FOK - Fill or Kill)"""
        try:
            order_id = await self.polymarket.create_market_order(
                token_id=token_id,
                amount=amount,
                side=side,
            )
            return ExecutionResult(success=True, order_id=order_id)

        except Exception as e:
            logger.error(f"Market order failed: {e}")
            return ExecutionResult(success=False, error=str(e))

    async def execute_cancel(self, order_id: str) -> ExecutionResult:
        """Cancel an existing order"""
        try:
            success = await self.polymarket.cancel_order(order_id)
            return ExecutionResult(success=success, error=None if success else "Cancel failed")
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return ExecutionResult(success=False, error=str(e))

    async def execute_batch(self, orders: list[dict]) -> list[ExecutionResult]:
        """Execute multiple orders in batch"""
        import asyncio

        results = []
        for order in orders:
            result = await self.execute_limit_order(
                token_id=order["token_id"],
                side=order["side"],
                price=order["price"],
                size=order["size"],
            )
            results.append(result)
            await asyncio.sleep(0.5)  # Rate limiting

        return results

    async def get_execution_price(
        self,
        token_id: str,
        side: str,
        size: float,
    ) -> Optional[float]:
        """Get the expected execution price for an order"""
        try:
            orderbook = await self.polymarket.get_order_book(token_id)

            if side == "BUY" and orderbook.get("asks"):
                return min(float(o["price"]) for o in orderbook["asks"])
            elif side == "SELL" and orderbook.get("bids"):
                return max(float(o["price"]) for o in orderbook["bids"])

            return None
        except Exception as e:
            logger.error(f"Failed to get execution price: {e}")
            return None

    async def estimate_slippage(self, token_id: str, side: str, size: float) -> float:
        """Estimate slippage for a given order size"""
        try:
            orderbook = await self.polymarket.get_order_book(token_id)

            if side == "BUY":
                levels = sorted(orderbook.get("asks", []), key=lambda x: float(x["price"]))
            else:
                levels = sorted(orderbook.get("bids", []), key=lambda x: float(x["price"]), reverse=True)

            remaining = size
            total_cost = 0
            filled = 0

            for level in levels:
                price = float(level["price"])
                size_at_level = float(level["size"])
                fill = min(remaining, size_at_level)
                total_cost += fill * price
                filled += fill
                remaining -= fill
                if remaining <= 0:
                    break

            if filled > 0:
                avg_price = total_cost / filled
                mid_price = float(levels[0]["price"]) if levels else avg_price
                return abs(avg_price - mid_price) / mid_price if mid_price else 0.0

            return 0.0
        except Exception as e:
            logger.error(f"Slippage estimation failed: {e}")
            return 0.0
