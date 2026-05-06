"""Base strategy interface for trading bots"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List
import time


class SignalType(str, Enum):
    """Types of trading signals"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


@dataclass
class Signal:
    """A trading signal with metadata"""
    signal_type: SignalType
    market_id: str
    token_id: str
    confidence: float  # 0.0 to 1.0
    price: Optional[float] = None  # Target price for limit orders
    size: Optional[float] = None  # Position size
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""  # Human-readable reason for the signal
    metadata: Dict[str, Any] = None  # Additional data

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @property
    def is_actionable(self) -> bool:
        """Check if signal is actionable (not HOLD)"""
        return self.signal_type in (SignalType.BUY, SignalType.SELL, SignalType.CLOSE)


@dataclass
class MarketData:
    """Market data for analysis"""
    market_id: str
    question: str
    tokens: List[Dict[str, Any]]  # Outcome tokens
    volume: float
    liquidity: float
    order_book: Dict[str, List] = None
    recent_trades: List[Dict] = None
    historical_data: List[Dict] = None

    def __post_init__(self):
        if self.order_book is None:
            self.order_book = {"bids": [], "asks": []}
        if self.recent_trades is None:
            self.recent_trades = []
        if self.historical_data is None:
            self.historical_data = []


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    Implement this interface to create custom strategies.
    """

    def __init__(self, config):
        self.config = config
        self.name = self.__class__.__name__

    @abstractmethod
    async def analyze(self, market: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze a market and generate a trading signal.

        Args:
            market: Market data dictionary from Polymarket

        Returns:
            Signal if actionable, None otherwise
        """
        pass

    @abstractmethod
    async def on_tick(self, markets: List[Dict[str, Any]]) -> List[Signal]:
        """
        Called periodically to analyze multiple markets.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of signals for all markets
        """
        pass

    async def learn(self, historical_data: List[Dict]) -> None:
        """
        Optional: Update strategy based on historical performance.

        Override for strategies that learn from past trades.
        """
        pass

    async def reset(self) -> None:
        """Reset strategy state"""
        pass

    def get_parameters(self) -> Dict[str, Any]:
        """Get strategy parameters"""
        return {}

    def set_parameters(self, **kwargs) -> None:
        """Set strategy parameters"""
        pass


class StrategyType(str, Enum):
    """Available strategy types"""
    AI = "ai"
    ML = "ml"
    CUSTOM = "custom"


class StrategyRegistry:
    """Registry for available strategies"""

    _strategies: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a strategy"""
        def decorator(strategy_class):
            cls._strategies[name] = strategy_class
            return strategy_class
        return decorator

    @classmethod
    def get(cls, name: str) -> type:
        """Get a strategy class by name"""
        return cls._strategies.get(name)

    @classmethod
    def list(cls) -> List[str]:
        """List all registered strategies"""
        return list(cls._strategies.keys())