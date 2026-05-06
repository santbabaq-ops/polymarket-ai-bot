"""Order executor combining Polymarket client with Gelato relay"""

from typing import Optional
from dataclasses import dataclass
from decimal import Decimal

from src.config import Config
from src.utils.logging import get_logger
from .polymarket_client import PolymarketClient, CLOB_EXCHANGE_ADDRESS
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
    Executes orders on Polymarket using gasless transactions via Gelato.

    Supports two modes:
    1. Direct CLOB (for CLOB-only orders, gasless by nature)
    2. Gelato relay (for on-chain settlement)
    """

    def __init__(
        self,
        polymarket: PolymarketClient,
        gelato: GelatoRelay,
        config: Config,
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
        use_gelato: bool = True,
    ) -> ExecutionResult:
        """
        Execute a limit order.

        For CLOB orders (matches against order book), Gelato is not needed.
        For on-chain settlement, uses Gelato for gasless execution.
        """
        try:
            if use_gelato:
                # Get calldata for gasless execution
                calldata = self._build_order_calldata(token_id, side, price, size)

                # Simulate first
                sim_result = await self.gelato.simulate_transaction(
                    target=CLOB_EXCHANGE_ADDRESS,
                    data=calldata,
                )

                if not sim_result.get("success", False):
                    error = sim_result.get("error", "Simulation failed")
                    logger.warning(f"Order simulation failed: {error}")

                # Send via Gelato
                receipt = await self.gelato.send_transaction_sync(
                    target=CLOB_EXCHANGE_ADDRESS,
                    data=calldata,
                )

                return ExecutionResult(
                    success=True,
                    transaction_hash=receipt.transaction_hash,
                )
            else:
                # Direct CLOB order (no gas needed for matching)
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

        Orders are submitted via Gelato relay for gas efficiency.
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

    def _build_order_calldata(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
    ) -> str:
        """
        Build calldata for order execution.

        This encodes the order data for the CLOB exchange contract.
        """
        from eth_abi import encode

        # Encode function call for the CLOB exchange
        # Function signature: function createOrder(address maker, uint256 tokenId, uint256 makerAmount, uint256 takerAmount, bytes32 side, uint256 nonce, uint256 expiration)
        maker = self.polymarket.address
        maker_amount = int(size * 1e6)  # USDC has 6 decimals
        taker_amount = int((1 - price) * size * 1e6) if side == "BUY" else int(price * size * 1e6)
        side_bytes = b'\x00' if side == "BUY" else b'\x01'  # 0 for BUY, 1 for SELL
        nonce = 0  # Contract will assign
        expiration = 0  # No expiration

        # Simplified - in reality would use py_order_utils properly
        import struct

        # Pack into bytes for relay
        data = struct.pack(
            'address uint256 uint256 uint256 bytes1 uint256 uint256',
            bytes.fromhex(maker[2:]),
            int(token_id),
            maker_amount,
            taker_amount,
            side_bytes,
            nonce,
            expiration,
        )

        # Function selector (simplified)
        func_selector = bytes.fromhex('a9059cbb')  # transfer function (placeholder)

        return func_selector.hex() + data.hex()

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
                levels = sorted(orderbook.get("bids", []), []), key=lambda x: float(x["price"]), reverse=True

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