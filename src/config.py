"""Configuration management for Polymarket AI Bot"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

load_dotenv()


class StrategyType(str, Enum):
    """Available strategy types"""
    AI = "ai"
    ML = "ml"
    CUSTOM = "custom"


@dataclass
class Config:
    """Main configuration class"""

    # Wallet
    wallet_private_key: str = ""

    # API Keys
    anthropic_api_key: str = ""
    gelato_api_key: str = ""
    polymarket_api_key: str = ""

    # Strategy
    strategy_type: StrategyType = StrategyType.AI

    # Trading
    scan_interval: int = 30  # seconds
    max_position_size: float = 100.0  # USDC
    stop_loss: float = 0.02  # 2%
    take_profit: float = 0.05  # 5%

    # Risk Management
    max_daily_loss: float = 0.10  # 10%
    kelly_fraction: float = 0.25  # Kelly criterion fraction

    # Backtest
    backtest_start_date: Optional[str] = None
    backtest_end_date: Optional[str] = None

    # RPC
    polygon_rpc_url: str = "https://polygon-rpc.com"

    # Gelato
    gelato_chain_id: int = 137  # Polygon mainnet

    # Market filters
    min_market_volume: float = 1000.0  # USDC
    min_market_liquidity: float = 500.0  # USDC

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        """Load config from YAML file"""
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables"""
        return cls(
            wallet_private_key=os.getenv("POLYGON_WALLET_PRIVATE_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            gelato_api_key=os.getenv("GELATO_API_KEY", ""),
            polymarket_api_key=os.getenv("POLYMARKET_API_KEY", ""),
            strategy_type=StrategyType(os.getenv("STRATEGY_TYPE", "ai")),
            scan_interval=int(os.getenv("SCAN_INTERVAL", "30")),
            max_position_size=float(os.getenv("MAX_POSITION_SIZE", "100")),
            stop_loss=float(os.getenv("STOP_LOSS", "0.02")),
            take_profit=float(os.getenv("TAKE_PROFIT", "0.05")),
            polygon_rpc_url=os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com"),
            gelato_chain_id=int(os.getenv("GELATO_CHAIN_ID", "137")),
        )

    def validate(self) -> list[str]:
        """Validate config and return list of errors"""
        errors = []

        if not self.wallet_private_key:
            errors.append("POLYGON_WALLET_PRIVATE_KEY is required")

        if self.strategy_type == StrategyType.AI and not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is required for AI strategy")

        if not self.gelato_api_key:
            errors.append("GELATO_API_KEY is required")

        if self.max_position_size <= 0:
            errors.append("MAX_POSITION_SIZE must be positive")

        if not 0 < self.kelly_fraction <= 1:
            errors.append("KELLY_FRACTION must be between 0 and 1")

        return errors


_config: Optional[Config] = None


def load_config(config_path: Optional[str | Path] = None) -> Config:
    """Load configuration from file or environment"""
    global _config

    if _config is not None:
        return _config

    if config_path:
        _config = Config.from_yaml(config_path)
    else:
        _config = Config.from_env()

    # Validate
    errors = _config.validate()
    if errors:
        raise ValueError(f"Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    return _config


def reset_config():
    """Reset config (useful for testing)"""
    global _config
    _config = None