"""Tests for trading module"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.trading.polymarket_client import PolymarketClient
from src.trading.gelato_relay import GelatoRelay, RelayReceipt
from src.trading.order_executor import OrderExecutor


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = MagicMock()
    config.wallet_private_key = "0x" + "a" * 64
    config.polygon_rpc_url = "https://polygon-rpc.com"
    config.gelato_chain_id = 137
    config.gelato_api_key = "test-api-key"
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
        # Mock response
        client.http.get = AsyncMock(return_value=MagicMock(
            json=MagicMock(return_value={"markets": [{"id": "test"}]}),
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


class TestGelatoRelay:
    """Tests for GelatoRelay"""

    @pytest.fixture
    def relay(self, mock_config):
        """Create relay with mocked HTTP"""
        return GelatoRelay(mock_config)

    @pytest.mark.asyncio
    async def test_get_balance(self, relay):
        """Test getting Gelato balance"""
        relay._http.get = AsyncMock(return_value=MagicMock(
            json=MagicMock(return_value={
                "balance": "1000000",
                "decimals": 18,
                "unit": "USDC"
            }),
            raise_for_status=MagicMock()
        ))

        balance = await relay.get_balance()
        assert balance["balance"] == "1000000"
        assert balance["unit"] == "USDC"

    @pytest.mark.asyncio
    async def test_send_transaction_sync(self, relay):
        """Test sending gasless transaction"""
        relay._http.post = AsyncMock(return_value=MagicMock(
            json=MagicMock(return_value={
                "taskId": "test-task-123",
                "txHash": "0x123"
            }),
            raise_for_status=MagicMock()
        ))

        receipt = await relay.send_transaction_sync(
            target="0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",
            data="0x1234"
        )

        assert receipt.task_id == "test-task-123"
        assert receipt.transaction_hash == "0x123"

    @pytest.mark.asyncio
    async def test_simulate_transaction(self, relay):
        """Test transaction simulation"""
        relay._http.post = AsyncMock(return_value=MagicMock(
            json=MagicMock(return_value={"success": True}),
            raise_for_status=MagicMock()
        ))

        result = await relay.simulate_transaction(
            target="0x...",
            data="0x..."
        )

        assert result["success"] is True


class TestOrderExecutor:
    """Tests for OrderExecutor"""

    @pytest.fixture
    def executor(self, mock_config):
        """Create executor with mocked dependencies"""
        polymarket = MagicMock(spec=PolymarketClient)
        polymarket.address = "0x1234567890123456789012345678901234567890"
        polymarket.CLOB_EXCHANGE_ADDRESS = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"

        gelato = MagicMock(spec=GelatoRelay)

        return OrderExecutor(polymarket, gelato, mock_config)

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
    async def test_execute_limit_order_native(self, executor):
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
    async def test_execute_limit_order_gelato(self, executor):
        """Test token approval via Gelato (on-chain operation)"""
        executor.gelato.send_transaction_sync = AsyncMock(return_value=RelayReceipt(
            task_id="task-123",
            transaction_hash="0xabc",
            status="success"
        ))

        result = await executor.approve_token_gelato(
            token_address="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
            spender_address="0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",  # CTF
            amount=1000000,
        )

        assert result.success is True
        assert result.transaction_hash == "0xabc"

    @pytest.mark.asyncio
    async def test_execute_cancel(self, executor):
        """Test order cancellation"""
        executor.polymarket.cancel_order = AsyncMock(return_value=True)

        result = await executor.execute_cancel("order-123")

        assert result.success is True