"""Order executor for Polymarket CLOB with native gasless support"""

from typing import Optional
from dataclasses import dataclass
from decimal import Decimal

from src.config import Config
from src.utils.logging import get_logger
from .polymarket_client import PolymarketClient
from .gelato_relay import GelatoRelay


logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of an order execution"""
    success: bool
    order_id: Optional[str] = None
    transaction_hash: Optional[str] = None
    error: Optional[str] = None
    gas_used: Optional[int] = None


class OrderExecutor:
    """
    Executes orders on Polymarket using native gasless CLOB trading.

    Key insight: Polymarket CLOB client already supports gasless trading
    via EIP-712 off-chain signing. Orders are signed locally and submitted
    to Polymarket's API, which handles gas payment via their relayer.

    Gelato is reserved for:
    - Token approvals (USDC/CTF)
    - Conditional automation (stop-loss, take-profit via Web3 Functions)
    """

    def __init__(
        self,
        polymarket: PolymarketClient,
        gelato: Optional[GelatoRelay] = None,
        config: Optional[Config] = None,
    ):
        self.polymarket = polymarket
        self.gelato = gelato
        self.config = config

    async def execute_limit_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        price: float,
        size: float,
    ) -> ExecutionResult:
        """
        Execute a limit order using native Polymarket gasless CLOB.

        This uses EIP-712 off-chain signing - no gas fees required.
        The order is signed locally and submitted to Polymarket's API,
        which relays it via their gasless relayer.
        """
        try:
            order_id = await self.polymarket.create_order(
                token_id=token_id,
                side=side,
                price=price,
                size=size,
            )

            return ExecutionResult(
                success=True,
                order_id=order_id,
            )

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

            return ExecutionResult(
                success=True,
                order_id=order_id,
            )

        except Exception as e:
            logger.error(f"Market order failed: {e}")
            return ExecutionResult(success=False, error=str(e))

    async def execute_cancel(
        self,
        order_id: str,
    ) -> ExecutionResult:
        """Cancel an existing order"""
        try:
            success = await self.polymarket.cancel_order(order_id)

            if success:
                return ExecutionResult(success=True)
            else:
                return ExecutionResult(success=False, error="Cancel failed")

        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return ExecutionResult(success=False, error=str(e))

    async def execute_batch(
        self,
        orders: list[dict],
    ) -> list[ExecutionResult]:
        """
        Execute multiple orders in batch.

        Each order is submitted via native Polymarket gasless CLOB.
        """
        results = []

        for order in orders:
            result = await self.execute_limit_order(
                token_id=order["token_id"],
                side=order["side"],
                price=order["price"],
                size=order["size"],
            )
            results.append(result)

            # Small delay to avoid rate limiting
            import asyncio
            await asyncio.sleep(0.5)

        return results

    async def approve_token_gelato(
        self,
        token_address: str,
        spender_address: str,
        amount: int,
    ) -> ExecutionResult:
        """
        Approve token spending via Gelato (on-chain operation requiring gas).

        This is the primary use case for Gelato - handling on-chain approvals
        that cannot be done through the CLOB API.
        """
        if not self.gelato:
            return ExecutionResult(
                success=False,
                error="Gelato relay not configured",
            )

        try:
            # Build ERC20 approve calldata
            from web3 import Web3
            w3 = Web3()

            # ERC20 approve(address,uint256)
            selector = w3.keccak(text="approve(address,uint256)")[:4]
            params = (
                w3.to_bytes(hexstr=spender_address).rjust(32, b'\x00')
                + amount.to_bytes(32, 'big')
            )
            data = "0x" + (selector + params).hex()

            receipt = await self.gelato.send_transaction_sync(
                target=token_address,
                data=data,
            )

            return ExecutionResult(
                success=True,
                transaction_hash=receipt.transaction_hash,
            )

        except Exception as e:
            logger.error(f"Token approval via Gelato failed: {e}")
            return ExecutionResult(success=False, error=str(e))

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
                # Best ask for buy order
                return min(float(o["price"]) for o in orderbook["asks"])
            elif side == "SELL" and orderbook.get("bids"):
                # Best bid for sell order
                return max(float(o["price"]) for o in orderbook["bids"])

            return None

        except Exception as e:
            logger.error(f"Failed to get execution price: {e}")
            return None

    async def estimate_slippage(
        self,
        token_id: str,
        side: str,
        size: float,
    ) -> float:
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
                # Get mid price for slippage calculation
                if side == "BUY" and levels:
                    mid_price = levels[0]["price"]
                elif side == "SELL" and levels:
                    mid_price = levels[0]["price"]
                else:
                    mid_price = avg_price

                return abs(avg_price - mid_price) / mid_price

            return 0.0

        except Exception as e:
            logger.error(f"Slippage estimation failed: {e}")
            return 0.0
