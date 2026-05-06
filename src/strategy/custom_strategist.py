"""Custom strategy interface for user-defined trading strategies"""

import importlib.util
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

from src.config import Config
from src.utils.logging import get_logger
from .base import BaseStrategy, Signal, SignalType


logger = get_logger(__name__)


class CustomStrategy(BaseStrategy):
    """
    Custom strategy that loads user-defined strategy from Python file.

    Users can create their own strategies by subclassing BaseStrategy
    and implementing the required methods.
    """

    def __init__(self, config: Config):
        super().__init__(config)

        # Load custom strategy from file
        strategy_path = config.get("custom_strategy_path", "strategies/custom_strategy.py")
        self.custom_strategy = self._load_strategy(strategy_path)

    def _load_strategy(self, path: str) -> Optional[BaseStrategy]:
        """Load custom strategy class from Python file"""
        try:
            file_path = Path(path)

            if not file_path.exists():
                logger.warning(f"Custom strategy file not found: {path}")
                return None

            # Load module from file
            spec = importlib.util.spec_from_file_location("custom_strategy", file_path)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to load strategy spec: {path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules["custom_strategy"] = module
            spec.loader.exec_module(module)

            # Find strategy class
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseStrategy) and attr != BaseStrategy:
                    logger.info(f"Loaded custom strategy: {attr_name}")
                    return attr(self.config)

            logger.warning(f"No strategy class found in {path}")
            return None

        except Exception as e:
            logger.error(f"Failed to load custom strategy: {e}")
            return None

    async def analyze(self, market: Dict[str, Any]) -> Optional[Signal]:
        """Delegate to custom strategy if loaded"""
        if self.custom_strategy:
            return await self.custom_strategy.analyze(market)
        return None

    async def on_tick(self, markets: List[Dict[str, Any]]) -> List[Signal]:
        """Delegate to custom strategy if loaded"""
        if self.custom_strategy:
            return await self.custom_strategy.on_tick(markets)
        return []


class StrategyPlugin:
    """
    Base class for strategy plugins.

    Users can inherit from this to create modular strategies.
    """

    def __init__(self, config: Config):
        self.config = config

    async def pre_analyze(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Hook called before main analysis"""
        return market

    async def post_analyze(self, signal: Optional[Signal]) -> Optional[Signal]:
        """Hook called after main analysis"""
        return signal

    async def on_trade_executed(self, signal: Signal, result: Dict) -> None:
        """Hook called when trade is executed"""
        pass

    async def on_trade_closed(self, signal: Signal, pnl: float) -> None:
        """Hook called when trade is closed"""
        pass


def create_strategy_from_config(config: Dict[str, Any]) -> BaseStrategy:
    """
    Factory function to create strategy from configuration dict.

    Example config:
    {
        "type": "ai",
        "params": {
            "temperature": 0.7,
            "max_tokens": 1024
        }
    }
    """
    strategy_type = config.get("type", "ai")

    if strategy_type == "ai":
        from .ai_strategist import AIStrategist
        return AIStrategist.__new__(AIStrategist)
    elif strategy_type == "ml":
        from .ml_strategist import MLStrategist
        return MLStrategist.__new__(MLStrategist)
    elif strategy_type == "custom":
        from .custom_strategist import CustomStrategy
        return CustomStrategy.__new__(CustomStrategy)
    else:
        raise ValueError(f"Unknown strategy type: {strategy_type}")