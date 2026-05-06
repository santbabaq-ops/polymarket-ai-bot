"""Backtesting engine using VectorBT for strategy validation"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
import vectorbt as vbt

from src.config import Config
from src.utils.logging import get_logger
from src.strategy.base import BaseStrategy, Signal, SignalType
from .historical_fetcher import HistoricalFetcher


logger = get_logger(__name__)


@dataclass
class BacktestResult:
    """Results from a backtest run"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    avg_trade_return: float
    avg_trade_duration: Optional[float]
    trades: List[Dict]
    equity_curve: List[float]


class BacktestEngine:
    """
    Backtesting engine for Polymarket trading strategies.

    Uses VectorBT for high-performance vectorized backtesting.
    """

    def __init__(self, config: Config):
        self.config = config
        self.fetcher = HistoricalFetcher()
        self.results: Optional[BacktestResult] = None

    async def close(self):
        """Close resources"""
        await self.fetcher.close()

    async def run_backtest(
        self,
        market_id: str,
        strategy: BaseStrategy,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        initial_capital: float = 10000,
    ) -> BacktestResult:
        """
        Run backtest for a single market.

        Args:
            market_id: Market ID to backtest
            strategy: Strategy to test
            start_date: Start of backtest period
            end_date: End of backtest period
            initial_capital: Starting capital

        Returns:
            BacktestResult with performance metrics
        """
        logger.info(f"Running backtest for market {market_id}")

        # Fetch historical data
        data = await self.fetcher.get_market_history(market_id, start_date, end_date)

        if not data.get("prices"):
            logger.warning("No price data available, using synthetic data")
            data["prices"] = self.fetcher.generate_synthetic_data(5)  # 5-min data

        # Convert to DataFrame
        df = self._prepare_dataframe(data)

        # Run strategy backtest
        signals = await self._generate_signals(df, strategy)

        # Calculate performance
        result = self._calculate_performance(df, signals, initial_capital)
        self.results = result

        return result

    async def run_multi_market_backtest(
        self,
        market_ids: List[str],
        strategy: BaseStrategy,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        initial_capital: float = 10000,
    ) -> Dict[str, BacktestResult]:
        """
        Run backtest across multiple markets.

        Args:
            market_ids: List of market IDs
            strategy: Strategy to test
            start_date: Start date
            end_date: End date
            initial_capital: Starting capital per market

        Returns:
            Dict mapping market_id to BacktestResult
        """
        results = {}

        for market_id in market_ids:
            try:
                result = await self.run_backtest(
                    market_id, strategy, start_date, end_date, initial_capital
                )
                results[market_id] = result
            except Exception as e:
                logger.error(f"Backtest failed for {market_id}: {e}")

        return results

    async def optimize_strategy(
        self,
        market_id: str,
        strategy_factory: Callable,
        param_grid: Dict[str, List],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Optimize strategy parameters using grid search.

        Args:
            market_id: Market to optimize on
            strategy_factory: Function that creates strategy with given params
            param_grid: Dict of parameter names to value lists
            start_date: Start date
            end_date: End date

        Returns:
            Dict with best parameters and results
        """
        data = await self.fetcher.get_market_history(market_id, start_date, end_date)
        df = self._prepare_dataframe(data)

        best_result = None
        best_params = None
        best_sharpe = -float('inf')

        # Generate parameter combinations
        import itertools
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())

        for values in itertools.product(*param_values):
            params = dict(zip(param_names, values))

            try:
                strategy = strategy_factory(params)
                signals = await self._generate_signals(df, strategy)
                result = self._calculate_performance(df, signals, 10000)

                if result.sharpe_ratio > best_sharpe:
                    best_sharpe = result.sharpe_ratio
                    best_result = result
                    best_params = params

            except Exception as e:
                logger.error(f"Optimization failed for {params}: {e}")

        return {
            "best_params": best_params,
            "best_result": best_result,
            "sharpe_ratio": best_sharpe,
        }

    def _prepare_dataframe(self, data: Dict[str, Any]) -> pd.DataFrame:
        """Convert market data to DataFrame for analysis"""
        prices = data.get("prices", [])

        if not prices:
            # Generate synthetic data
            prices = self.fetcher.generate_synthetic_data(5)

        df = pd.DataFrame(prices)

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)

        if "price" in df.columns:
            df.rename(columns={"price": "close"}, inplace=True)
            # Generate OHLC from close
            df["open"] = df["close"]
            df["high"] = df["close"] * 1.001
            df["low"] = df["close"] * 0.999

        if "volume" not in df.columns:
            df["volume"] = 1000  # Default volume

        return df

    async def _generate_signals(
        self,
        df: pd.DataFrame,
        strategy: BaseStrategy,
    ) -> pd.DataFrame:
        """Generate trading signals from strategy"""
        signals = []

        # Prepare market dict for strategy
        market = {
            "prices": df.to_dict("records"),
            "volume": df["volume"].sum() if "volume" in df.columns else 0,
        }

        # Add price columns
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                market[col] = df[col].tolist()

        # Generate signals for each row
        for i, row in df.iterrows():
            # Update market with current data point
            current_market = market.copy()
            current_market["current_price"] = row.get("close", 0.5)
            current_market["previous_price"] = df.iloc[max(0, i-1)].get("close", 0.5) if i > 0 else 0.5

            try:
                signal = await strategy.analyze(current_market)

                if signal:
                    signals.append({
                        "index": i,
                        "signal": signal.signal_type.value,
                        "confidence": signal.confidence,
                        "price": signal.price or row.get("close", 0.5),
                    })
                else:
                    signals.append({
                        "index": i,
                        "signal": "HOLD",
                        "confidence": 0,
                        "price": row.get("close", 0.5),
                    })

            except Exception as e:
                logger.error(f"Signal generation failed: {e}")
                signals.append({
                    "index": i,
                    "signal": "HOLD",
                    "confidence": 0,
                    "price": row.get("close", 0.5),
                })

        signal_df = pd.DataFrame(signals)
        signal_df.set_index("index", inplace=True)

        return signal_df

    def _calculate_performance(
        self,
        price_df: pd.DataFrame,
        signal_df: pd.DataFrame,
        initial_capital: float,
    ) -> BacktestResult:
        """Calculate backtest performance metrics using VectorBT"""
        # Merge price and signal data
        df = price_df.join(signal_df, how="left")

        # Generate entry/exit signals
        entries = df["signal"] == "BUY"
        exits = df["signal"] == "SELL"

        if "close" not in df.columns:
            df["close"] = 0.5

        # Use VectorBT for portfolio simulation
        try:
            pf = vbt.Portfolio.from_signals(
                df["close"],
                entries=entries,
                exits=exits,
                init_cash=initial_capital,
                fees=0.01,  # 1% fee
                slippage=0.001,  # 0.1% slippage
            )

            # Extract trades
            trades = pf.trades.record()
            trade_list = []
            for _, trade in trades.iterrows():
                trade_list.append({
                    "entry_index": trade.get("entry_index"),
                    "exit_index": trade.get("exit_index"),
                    "pnl": trade.get("pnl", 0),
                    "return": trade.get("return", 0),
                    "duration": trade.get("duration", 0),
                })

            # Calculate metrics
            returns = pf.returns()
            total_return = (pf.final_value() - initial_capital) / initial_capital
            win_rate = len([t for t in trade_list if t["pnl"] > 0]) / max(len(trade_list), 1)
            sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
            max_dd = pf.max_drawdown()

            # Equity curve
            equity = pf.value()

            return BacktestResult(
                total_trades=len(trade_list),
                winning_trades=len([t for t in trade_list if t["pnl"] > 0]),
                losing_trades=len([t for t in trade_list if t["pnl"] <= 0]),
                win_rate=win_rate,
                total_return=total_return,
                sharpe_ratio=sharpe,
                max_drawdown=max_dd,
                avg_trade_return=returns.mean() if len(trade_list) > 0 else 0,
                avg_trade_duration=None,  # VectorBT doesn't directly provide this
                trades=trade_list,
                equity_curve=equity.tolist(),
            )

        except Exception as e:
            logger.error(f"Performance calculation failed: {e}")
            return BacktestResult(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0,
                total_return=0,
                sharpe_ratio=0,
                max_drawdown=0,
                avg_trade_return=0,
                avg_trade_duration=None,
                trades=[],
                equity_curve=[],
            )

    def plot_results(self, result: BacktestResult) -> Any:
        """Generate plots for backtest results"""
        try:
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(3, 1, figsize=(12, 10))

            # Equity curve
            axes[0].plot(result.equity_curve)
            axes[0].set_title("Equity Curve")
            axes[0].set_xlabel("Trade")
            axes[0].set_ylabel("Portfolio Value ($)")
            axes[0].grid(True)

            # Trade returns
            if result.trades:
                returns = [t["return"] for t in result.trades]
                axes[1].bar(range(len(returns)), returns)
                axes[1].set_title("Trade Returns")
                axes[1].set_xlabel("Trade")
                axes[1].set_ylabel("Return")
                axes[1].axhline(y=0, color="r", linestyle="--")
                axes[1].grid(True)

            # Drawdown
            equity = np.array(result.equity_curve)
            running_max = np.maximum.accumulate(equity)
            drawdown = (equity - running_max) / running_max
            axes[2].fill_between(range(len(drawdown)), drawdown, 0, alpha=0.3)
            axes[2].set_title("Drawdown")
            axes[2].set_xlabel("Trade")
            axes[2].set_ylabel("Drawdown")
            axes[2].grid(True)

            plt.tight_layout()
            return fig

        except Exception as e:
            logger.error(f"Plot generation failed: {e}")
            return None