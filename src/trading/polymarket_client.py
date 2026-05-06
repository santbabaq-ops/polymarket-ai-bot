"""Polymarket CLOB API Client"""

import asyncio
from typing import Optional
from decimal import Decimal

import httpx
from web3 import Web3

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType

from src.config import Config
from src.utils.logging import get_logger


logger = get_logger(__name__)


# Polymarket contract addresses on Polygon
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"  # Conditional Token Framework
CLOB_EXCHANGE_ADDRESS = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"

GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"


class PolymarketClient:
    """Client for interacting with Polymarket's CLOB API and Gamma API"""

    def __init__(self, config: Config):
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config.polygon_rpc_url))

        # Initialize CLOB client
        self.clob = ClobClient(
            host=CLOB_API_URL,
            key=config.wallet_private_key,
            chain_id=config.gelato_chain_id,
        )

        # HTTP client for Gamma API
        self.http = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close connections"""
        await self.aclose()

    async def aclose(self):
        """Async close"""
        await self.http.aclose()

    @property
    def address(self) -> str:
        """Get wallet address"""
        return self.w3.eth.account.from_key(self.config.wallet_private_key).address

    async def get_markets(self, limit: int = 100) -> list[dict]:
        """Get active markets from Gamma API"""
        try:
            response = await self.http.get(
                f"{GAMMA_API_URL}/markets",
                params={
                    "closed": "false",
                    "limit": limit,
                    "active": "true",
                }
            )
            response.raise_for_status()
            data = response.json()
            # API returns a list directly
            if isinstance(data, list):
                return data
            return data.get("markets", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []

    async def get_market_by_id(self, market_id: str) -> Optional[dict]:
        """Get a specific market by ID"""
        try:
            response = await self.http.get(f"{GAMMA_API_URL}/markets/{market_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch market {market_id}: {e}")
            return None

    async def get_order_book(self, token_id: str) -> dict:
        """Get order book for a token"""
        try:
            response = await self.http.get(
                f"{CLOB_API_URL}/orderbooks",
                params={"token_id": token_id}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch order book: {e}")
            return {"bids": [], "asks": []}

    async def get_filled_orders(self, token_id: str, limit: int = 50) -> list[dict]:
        """Get recent filled orders for a token"""
        try:
            response = await self.http.get(
                f"{CLOB_API_URL}/orders",
                params={
                    "token_id": token_id,
                    "limit": limit,
                    "filled": "true",
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch orders: {e}")
            return []

    async def get_positions(self) -> list[dict]:
        """Get current positions"""
        try:
            response = await self.http.get(
                f"{CLOB_API_URL}/positions",
                params={"address": self.address}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []

    async def get_usdc_balance(self) -> Decimal:
        """Get USDC balance"""
        try:
            usdc_abi = [
                {
                    "inputs": [],
                    "name": "balanceOf",
                    "outputs": [{"type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function"
                }
            ]
            usdc = self.w3.eth.contract(
                address=Web3.to_checksum_address(USDC_ADDRESS),
                abi=usdc_abi
            )
            balance = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: usdc.functions.balanceOf(self.address).call()
            )
            return Decimal(balance) / Decimal(1e6)
        except Exception as e:
            logger.error(f"Failed to get USDC balance: {e}")
            return Decimal(0)

    async def get_token_balances(self, token_id: str) -> Decimal:
        """Get balance of a conditional token"""
        try:
            ctf_abi = [
                {
                    "inputs": [
                        {"name": "account", "type": "address"},
                        {"name": "id", "type": "uint256"}
                    ],
                    "name": "balanceOf",
                    "outputs": [{"type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function"
                }
            ]
            ctf = self.w3.eth.contract(
                address=Web3.to_checksum_address(CTF_ADDRESS),
                abi=ctf_abi
            )
            balance = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ctf.functions.balanceOf(self.address, int(token_id)).call()
            )
            return Decimal(balance) / Decimal(1e18)
        except Exception as e:
            logger.error(f"Failed to get token balance: {e}")
            return Decimal(0)

    async def create_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        price: float,
        size: float,
    ) -> str:
        """Create and post a limit order"""
        try:
            order_args = OrderArgs(
                price=price,
                size=size,
                side=side,
                token_id=token_id,
            )
            order_result = self.clob.create_and_post_order(order_args)
            logger.info(f"Order created: {order_result}")
            return order_result
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            raise

    async def create_market_order(
        self,
        token_id: str,
        amount: float,
        side: str,
    ) -> str:
        """Create and post a market order (FOK)"""
        try:
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount,
                side=side,
            )
            signed_order = self.clob.create_market_order(order_args)
            result = self.clob.post_order(signed_order, orderType=OrderType.FOK)
            logger.info(f"Market order posted: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to create market order: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        try:
            result = self.clob.cancel_order(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    async def cancel_all_orders(self) -> bool:
        """Cancel all open orders"""
        try:
            result = self.clob.cancel_all_orders()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False

    def get_order_calldata(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
    ) -> bytes:
        """Get encoded calldata for an order (for gasless execution)"""
        # Build order data for signing
        from py_order_utils.builders import OrderBuilder
        from py_order_utils.model import OrderData
        from py_order_utils.signer import Signer

        signer = Signer(self.config.wallet_private_key)
        builder = OrderBuilder(CLOB_EXCHANGE_ADDRESS, self.config.gelato_chain_id, signer)

        order_data = OrderData(
            maker=self.address,
            tokenId=token_id,
            makerAmount=int(size * 1e6),  # USDC has 6 decimals
            takerAmount=int((1 - price) * size * 1e6) if side == "BUY" else int(price * size * 1e6),
            feeRateBps="100",  # 1% fee
            nonce=0,  # Will be fetched from contract
            side=side,
            expiration=0,  # No expiration
        )

        order = builder.build_signed_order(order_data)
        return order