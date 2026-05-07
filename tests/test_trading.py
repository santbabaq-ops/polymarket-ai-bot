"""Tests for trading module"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.trading.polymarket_client import PolymarketClient
from src.trading.order_executor import OrderExecutor


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = MagicMock()
    config.wallet_private_key = "0x" + "a" * 64
    config.polygon_rpc_url = "https://polygon-rpc.com"
    config.max_position_size = 100.0
    config.stop_loss = 0.02
    config.take_profit = 0.05
    return config


class TestPolymarketClient:
    """Tests for PolymarketClient"""

    @pytest.fixture
    def client(self, mock_config):
        """Create client with mocked dependencies"""
        with patch('src.trading.polymarket_client.ClobClient'):
            with patch('src.trading.polymarket_client.Web3'):
                return PolymarketClient(mock_config)

    def test_client_initialization(self, client):
        """Test client initializes correctly"""
        assert client is not None
        assert hasattr(client, 'clob')
        assert hasattr(client, 'http')

    @pytest.mark.asyncio
    async def test_get_markets(self, client):
        """Test fetching markets"""
        client.http.get = AsyncMock(return_value=MagicMock(
            json=MagicMock(return_value=[{"id": "test"}]),
            raise_for_status=MagicMock()
        ))

        markets = await client.get_markets()
        assert len(markets) == 1
        assert markets[0]["id"] == "test"

    @pytest.mark.asyncio
    async def test_get_usdc_balance(self, client):
        """Test getting USDC balance"""
        client.w3.eth.contract.return_value.functions.balanceOf.return_value.call = MagicMock(
            return_value=1000000  # 1 USDC (6 decimals)
        )

        balance = await client.get_usdc_balance()
        assert balance == Decimal("1")


class TestOrderExecutor:
    """Tests for OrderExecutor"""

    @pytest.fixture
    def executor(self, mock_config):
        """Create executor with mocked dependencies"""
        polymarket = MagicMock(spec=PolymarketClient)
        polymarket.address = "0x1234567890123456789012345678901234567890"

        return OrderExecutor(polymarket)

    @pytest.mark.asyncio
    async def test_execute_market_order(self, executor):
        """Test market order execution"""
        executor.polymarket.create_market_order = AsyncMock(return_value="order-123")

        result = await executor.execute_market_order(
            token_id="123",
            amount=10.0,
            side="BUY"
        )

        assert result.success is True
        assert result.order_id == "order-123"

    @pytest.mark.asyncio
    async def test_execute_limit_order(self, executor):
        """Test limit order via native Polymarket gasless CLOB"""
        executor.polymarket.create_order = AsyncMock(return_value="clob-order-123")

        result = await executor.execute_limit_order(
            token_id="123",
            side="BUY",
            price=0.55,
            size=10.0,
        )

        assert result.success is True
        assert result.order_id == "clob-order-123"

    @pytest.mark.asyncio
    async def test_execute_cancel(self, executor):
        """Test order cancellation"""
        executor.polymarket.cancel_order = AsyncMock(return_value=True)

        result = await executor.execute_cancel("order-123")

        assert result.success is True
