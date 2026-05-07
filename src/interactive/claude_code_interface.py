"""Interactive Claude Code interface for strategy and backtesting.

This module provides an interactive interface that allows Claude Code to:
1. Analyze markets in real-time
2. Develop and modify trading strategies
3. Run backtests with custom parameters
4. Execute trades (dry-run or live)
5. Monitor positions and performance

Usage from Claude Code:
    $ polybot claude -i          # Interactive mode
    $ polybot claude --market-id <id>  # Analyze specific market
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

from src.config import Config
from src.utils.logging import get_logger
from src.trading.polymarket_client import PolymarketClient
from src.trading.order_executor import OrderExecutor
from src.strategy.base import BaseStrategy, Signal, SignalType, StrategyType
from src.strategy.ai_strategist import AIStrategist
from src.strategy.ml_strategist import MLStrategist
from src.strategy.custom_strategist import CustomStrategy
from src.strategy.position_sizer import PositionSizer, RiskManager
from src.backtest.backtest_engine import BacktestEngine
from src.utils.market_scanner import MarketScanner


logger = get_logger(__name__)


@dataclass
class AnalysisResult:
    """Result of market analysis"""
    market_id: str
    question: str
    signal: Optional[Signal]
    kelly_size: Optional[float]
    confidence: float
    recommendation: str
    reasoning: str
    risks: List[str]


@dataclass
class StrategyConfig:
    """Configuration for strategy testing"""
    strategy_type: StrategyType
    parameters: Dict[str, Any]
    kelly_fraction: float = 0.25
    max_position_size: float = 100.0


class ClaudeCodeInterface:
    """
    Interactive interface for Claude Code to execute strategies and backtests.

    This class provides a programmatic API that Claude Code can use to:
    - Fetch and analyze market data
    - Run backtests with different strategies
    - Execute trades
    - Monitor performance
    """

    def __init__(self, config: Config):
        self.config = config
        self.polymarket = PolymarketClient(config)
        self.scanner = MarketScanner(self.polymarket)
        self.executor = OrderExecutor(self.polymarket)
        self.backtest_engine = BacktestEngine(config)
        self.risk_manager = RiskManager({
            "max_positions": 5,
            "stop_loss": config.stop_loss,
            "take_profit": config.take_profit,
        })

    async def interactive_loop(self):
        """
        Interactive loop for Claude Code.

        Presents a menu of actions and executes them.
        This is designed to be called from Claude Code CLI.
        """
        print("\n" + "=" * 60)
        print("  Polymarket AI Bot - Claude Code Interactive Interface")
        print("=" * 60)
        print("\nAvailable commands:")
        print("  1. scan     - Scan for 5min/15min markets")
        print("  2. analyze  - Analyze a specific market")
        print("  3. backtest - Run backtest on a market")
        print("  4. strategy - Configure and test strategies")
        print("  5. execute  - Execute a trade (dry-run or live)")
        print("  6. status   - Check bot status and positions")
        print("  7. exit     - Exit interactive mode")
        print("\n" + "=" * 60)

        while True:
            try:
                command = input("\n[claude-bot] > ").strip().lower()

                if command in ("1", "scan"):
                    await self._cmd_scan()
                elif command in ("2", "analyze"):
                    await self._cmd_analyze()
                elif command in ("3", "backtest"):
                    await self._cmd_backtest()
                elif command in ("4", "strategy"):
                    await self._cmd_strategy()
                elif command in ("5", "execute"):
                    await self._cmd_execute()
                elif command in ("6", "status"):
                    await self._cmd_status()
                elif command in ("7", "exit", "quit"):
                    print("Exiting interactive mode...")
                    break
                else:
                    print(f"Unknown command: {command}")
                    print("Type a number (1-7) or command name")

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                logger.error(f"Error in interactive loop: {e}")
                print(f"Error: {e}")

    async def analyze_market(self, market_id: str) -> AnalysisResult:
        """
        Analyze a specific market and return detailed analysis.

        Args:
            market_id: The market ID to analyze

        Returns:
            AnalysisResult with signal, sizing, and reasoning
        """
        print(f"\nAnalyzing market: {market_id}")

        # Fetch market data
        market = await self.polymarket.get_market_by_id(market_id)
        if not market:
            raise ValueError(f"Market {market_id} not found")

        # Get order book
        token_ids = self._extract_token_ids(market)
        if token_ids:
            market["order_book"] = await self.polymarket.get_order_book(token_ids[0])

        # Run AI analysis
        strategist = AIStrategist(self.config)
        signal = await strategist.analyze(market)

        # Calculate position size
        position_sizer = PositionSizer(
            kelly_fraction=self.config.kelly_fraction,
            max_position_pct=0.1,
            bankroll=1000.0,  # Default for analysis
        )

        kelly_size = None
        if signal and signal.signal_type in (SignalType.BUY, SignalType.SELL):
            current_price = float(market.get("outcomePrices", ["0.5", "0.5"])[0])
            size_result = position_sizer.calculate_size(
                price=current_price,
                win_probability=signal.confidence,
                confidence=signal.confidence,
            )
            kelly_size = size_result.size

        # Build recommendation
        recommendation = self._build_recommendation(signal, kelly_size)
        reasoning = signal.reason if signal else "No clear signal generated"
        risks = self._assess_risks(market, signal)

        result = AnalysisResult(
            market_id=market_id,
            question=market.get("question", "Unknown"),
            signal=signal,
            kelly_size=kelly_size,
            confidence=signal.confidence if signal else 0.0,
            recommendation=recommendation,
            reasoning=reasoning,
            risks=risks,
        )

        # Print analysis
        self._print_analysis(result)
        return result

    async def run_backtest(
        self,
        market_id: str,
        strategy_type: StrategyType = StrategyType.AI,
        strategy_params: Optional[Dict[str, Any]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        initial_capital: float = 10000.0,
    ) -> Dict[str, Any]:
        """
        Run a backtest with specified parameters.

        Args:
            market_id: Market to backtest
            strategy_type: Type of strategy (ai/ml/custom)
            strategy_params: Optional strategy parameters
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting capital

        Returns:
            Dict with backtest results and metrics
        """
        print(f"\nRunning backtest for market: {market_id}")
        print(f"Strategy: {strategy_type.value}")
        print(f"Initial capital: ${initial_capital:,.2f}")

        # Create strategy
        strategy = self._create_strategy(strategy_type, strategy_params or {})

        # Run backtest
        result = await self.backtest_engine.run_backtest(
            market_id=market_id,
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )

        # Print results
        self._print_backtest_results(result)

        return {
            "market_id": market_id,
            "strategy": strategy_type.value,
            "total_trades": result.total_trades,
            "win_rate": result.win_rate,
            "total_return": result.total_return,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "avg_trade_return": result.avg_trade_return,
            "trades": result.trades[:10],  # First 10 trades
            "equity_curve": result.equity_curve[:100],  # First 100 points
        }

    async def execute_signal(
        self,
        market_id: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute a trading signal.

        Args:
            market_id: Market to trade
            side: "BUY" or "SELL"
            size: Position size in USDC
            price: Limit price (None for market order)
            dry_run: If True, simulate without executing

        Returns:
            Dict with execution result
        """
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Executing trade:")
        print(f"  Market: {market_id}")
        print(f"  Side: {side}")
        print(f"  Size: ${size:.2f}")
        print(f"  Price: {'Market' if price is None else f'${price:.4f}'}")

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "market_id": market_id,
                "side": side,
                "size": size,
                "price": price,
                "message": "Dry run - no trade executed",
            }

        # Get token ID
        market = await self.polymarket.get_market_by_id(market_id)
        token_ids = self._extract_token_ids(market)
        if not token_ids:
            raise ValueError(f"No token IDs found for market {market_id}")

        token_id = token_ids[0]  # Use first outcome

        # Execute order
        if price:
            result = await self.executor.execute_limit_order(
                token_id=token_id,
                side=side,
                price=price,
                size=size,
            )
        else:
            result = await self.executor.execute_market_order(
                token_id=token_id,
                amount=size,
                side=side,
            )

        return {
            "success": result.success,
            "order_id": result.order_id,
            "market_id": market_id,
            "side": side,
            "size": size,
            "price": price,
        }

    async def get_market_summary(self) -> List[Dict[str, Any]]:
        """Get summary of available time-based markets"""
        markets = await self.scanner.scan_time_based_markets(
            durations=["5min", "15min"],
            min_volume=self.config.min_market_volume,
            min_liquidity=self.config.min_market_liquidity,
        )

        summaries = []
        for market in markets:
            summary = {
                "id": market.get("id", ""),
                "question": market.get("question", ""),
                "volume": float(market.get("volume", 0)),
                "liquidity": float(market.get("liquidity", 0)),
                "outcomes": market.get("outcomes", ["YES", "NO"]),
                "outcome_prices": market.get("outcomePrices", ["0.5", "0.5"]),
            }
            summaries.append(summary)

        return summaries

    async def compare_strategies(
        self,
        market_id: str,
        strategies: List[StrategyType],
        initial_capital: float = 10000.0,
    ) -> Dict[str, Any]:
        """
        Compare multiple strategies on the same market.

        Args:
            market_id: Market to test
            strategies: List of strategy types to compare
            initial_capital: Starting capital

        Returns:
            Dict with comparison results
        """
        print(f"\nComparing strategies on market: {market_id}")

        results = {}
        for strategy_type in strategies:
            print(f"\nTesting {strategy_type.value} strategy...")
            try:
                result = await self.run_backtest(
                    market_id=market_id,
                    strategy_type=strategy_type,
                    initial_capital=initial_capital,
                )
                results[strategy_type.value] = result
            except Exception as e:
                logger.error(f"Backtest failed for {strategy_type.value}: {e}")
                results[strategy_type.value] = {"error": str(e)}

        # Print comparison
        self._print_strategy_comparison(results)
        return results

    # --- Internal command handlers ---

    async def _cmd_scan(self):
        """Handle scan command"""
        print("\nScanning for time-based markets...")
        markets = await self.get_market_summary()

        if not markets:
            print("No markets found")
            return

        print(f"\nFound {len(markets)} markets:\n")
        for i, m in enumerate(markets[:10], 1):  # Show top 10
            print(f"  {i}. [{m['id']}] {m['question'][:80]}...")
            print(f"     Volume: ${m['volume']:,.0f} | Liquidity: ${m['liquidity']:,.0f}")
            prices = [float(p) for p in m['outcome_prices']]
            print(f"     Prices: {' | '.join(f'{p:.2%}' for p in prices)}")
            print()

    async def _cmd_analyze(self):
        """Handle analyze command"""
        market_id = input("Enter market ID: ").strip()
        if not market_id:
            print("Market ID required")
            return

        try:
            result = await self.analyze_market(market_id)
        except Exception as e:
            print(f"Analysis failed: {e}")

    async def _cmd_backtest(self):
        """Handle backtest command"""
        market_id = input("Enter market ID: ").strip()
        if not market_id:
            print("Market ID required")
            return

        strategy_input = input("Strategy (ai/ml/custom) [ai]: ").strip() or "ai"
        strategy_type = StrategyType(strategy_input)

        capital_input = input("Initial capital [10000]: ").strip()
        initial_capital = float(capital_input) if capital_input else 10000.0

        try:
            result = await self.run_backtest(
                market_id=market_id,
                strategy_type=strategy_type,
                initial_capital=initial_capital,
            )
        except Exception as e:
            print(f"Backtest failed: {e}")

    async def _cmd_strategy(self):
        """Handle strategy configuration command"""
        print("\nStrategy Configuration")
        print("=" * 40)

        print("\nAvailable strategies:")
        print("  1. AI (Claude) - Natural language market analysis")
        print("  2. ML (Local) - Machine learning predictions")
        print("  3. Custom - User-defined strategy")

        choice = input("\nSelect strategy (1-3): ").strip()

        strategies = {
            "1": StrategyType.AI,
            "2": StrategyType.ML,
            "3": StrategyType.CUSTOM,
        }

        strategy_type = strategies.get(choice, StrategyType.AI)

        # Show current config
        print(f"\nCurrent configuration for {strategy_type.value}:")
        print(f"  Kelly fraction: {self.config.kelly_fraction}")
        print(f"  Max position: ${self.config.max_position_size}")
        print(f"  Stop loss: {self.config.stop_loss:.1%}")
        print(f"  Take profit: {self.config.take_profit:.1%}")

    async def _cmd_execute(self):
        """Handle execute command"""
        print("\nTrade Execution")
        print("=" * 40)

        market_id = input("Market ID: ").strip()
        side = input("Side (BUY/SELL): ").strip().upper()
        size = float(input("Size (USDC): ").strip())

        price_input = input("Limit price (empty for market): ").strip()
        price = float(price_input) if price_input else None

        dry_run = input("Dry run? (y/n) [y]: ").strip().lower() != "n"

        try:
            result = await self.execute_signal(
                market_id=market_id,
                side=side,
                size=size,
                price=price,
                dry_run=dry_run,
            )
            print(f"\nResult: {result}")
        except Exception as e:
            print(f"Execution failed: {e}")

    async def _cmd_status(self):
        """Handle status command"""
        print("\nBot Status")
        print("=" * 40)

        # Wallet
        try:
            balance = await self.polymarket.get_usdc_balance()
            print(f"\nWallet: {self.polymarket.address}")
            print(f"USDC Balance: ${balance:,.2f}")
        except Exception as e:
            print(f"Wallet error: {e}")

        # Strategy
        print(f"\nStrategy: {self.config.strategy_type.value}")
        print(f"Scan interval: {self.config.scan_interval}s")

        # Risk settings
        print(f"\nRisk Settings:")
        print(f"  Max position: ${self.config.max_position_size}")
        print(f"  Stop loss: {self.config.stop_loss:.1%}")
        print(f"  Take profit: {self.config.take_profit:.1%}")
        print(f"  Kelly fraction: {self.config.kelly_fraction}")

    # --- Helper methods ---

    def _create_strategy(
        self,
        strategy_type: StrategyType,
        params: Dict[str, Any],
    ) -> BaseStrategy:
        """Create a strategy instance"""
        if strategy_type == StrategyType.AI:
            return AIStrategist(self.config)
        elif strategy_type == StrategyType.ML:
            return MLStrategist(self.config)
        elif strategy_type == StrategyType.CUSTOM:
            return CustomStrategy(self.config)
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")

    def _extract_token_ids(self, market: Dict[str, Any]) -> List[str]:
        """Extract token IDs from market data"""
        token_ids_raw = market.get("clob_token_ids")
        if not token_ids_raw:
            return []

        try:
            import ast
            if isinstance(token_ids_raw, str):
                return ast.literal_eval(token_ids_raw)
            return token_ids_raw
        except Exception:
            return []

    def _build_recommendation(self, signal: Optional[Signal], kelly_size: Optional[float]) -> str:
        """Build human-readable recommendation"""
        if not signal:
            return "HOLD - No clear trading opportunity"

        if signal.signal_type == SignalType.HOLD:
            return "HOLD - Wait for better opportunity"

        action = signal.signal_type.value
        confidence_pct = signal.confidence * 100

        if kelly_size and kelly_size > 0:
            return f"{action} - Confidence: {confidence_pct:.0f}%, Size: ${kelly_size:.2f}"
        else:
            return f"{action} - Confidence: {confidence_pct:.0f}%, Size: 0 (risk limit)"

    def _assess_risks(self, market: Dict[str, Any], signal: Optional[Signal]) -> List[str]:
        """Assess risks for a market"""
        risks = []

        volume = float(market.get("volume", 0))
        liquidity = float(market.get("liquidity", 0))

        if volume < 1000:
            risks.append("Low volume - potential slippage")
        if liquidity < 500:
            risks.append("Low liquidity - wide spreads")

        if signal and signal.confidence < 0.7:
            risks.append("Low confidence - consider smaller position")

        return risks

    def _print_analysis(self, result: AnalysisResult):
        """Print analysis result"""
        print("\n" + "=" * 60)
        print("  Market Analysis")
        print("=" * 60)
        print(f"\nMarket: {result.question}")
        print(f"ID: {result.market_id}")
        print(f"\nRecommendation: {result.recommendation}")
        print(f"\nReasoning:")
        print(f"  {result.reasoning}")

        if result.risks:
            print(f"\nRisks:")
            for risk in result.risks:
                print(f"  - {risk}")

        print("=" * 60)

    def _print_backtest_results(self, result):
        """Print backtest results"""
        print("\n" + "=" * 60)
        print("  Backtest Results")
        print("=" * 60)
        print(f"\nTotal Trades: {result.total_trades}")
        print(f"Win Rate: {result.win_rate:.2%}")
        print(f"Total Return: {result.total_return:.2%}")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"Max Drawdown: {result.max_drawdown:.2%}")
        print(f"Avg Trade Return: {result.avg_trade_return:.4f}")

        if result.trades:
            print(f"\nRecent Trades:")
            for trade in result.trades[:5]:
                pnl = trade.get("pnl", 0)
                symbol = "+" if pnl > 0 else ""
                print(f"  PnL: {symbol}${pnl:.2f}")

        print("=" * 60)

    def _print_strategy_comparison(self, results: Dict[str, Any]):
        """Print strategy comparison"""
        print("\n" + "=" * 80)
        print("  Strategy Comparison")
        print("=" * 80)

        print(f"\n{'Strategy':<12} {'Trades':>8} {'Win Rate':>10} {'Return':>10} {'Sharpe':>8}")
        print("-" * 80)

        for name, result in results.items():
            if "error" in result:
                print(f"{name:<12} {'ERROR':>8}")
            else:
                print(
                    f"{name:<12} "
                    f"{result['total_trades']:>8} "
                    f"{result['win_rate']:>9.1%} "
                    f"{result['total_return']:>9.1%} "
                    f"{result['sharpe_ratio']:>8.2f}"
                )

        print("=" * 80)

    async def close(self):
        """Clean up resources"""
        await self.polymarket.aclose()
        await self.backtest_engine.close()
