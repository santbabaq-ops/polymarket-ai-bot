#!/usr/bin/env python3
"""Polymarket AI Trading Bot - Main CLI Entry Point"""

import click
import asyncio
import sys

from src.config import load_config, Config
from src.utils.logging import setup_logging, get_logger
from src.trading.polymarket_client import PolymarketClient
from src.trading.order_executor import OrderExecutor
from src.strategy.base import StrategyType
from src.strategy.ai_strategist import AIStrategist
from src.strategy.ml_strategist import MLStrategist
from src.strategy.custom_strategist import CustomStrategy
from src.backtest.backtest_engine import BacktestEngine
from src.utils.market_scanner import MarketScanner
from src.interactive.claude_code_interface import ClaudeCodeInterface


logger = get_logger(__name__)


def get_strategist(config: Config):
    """Factory to get the configured strategist."""
    if config.strategy_type == StrategyType.AI:
        return AIStrategist(config)
    elif config.strategy_type == StrategyType.ML:
        return MLStrategist(config)
    elif config.strategy_type == StrategyType.CUSTOM:
        return CustomStrategy(config)
    else:
        raise ValueError(f"Unknown strategy type: {config.strategy_type}")


@click.group()
@click.option('--config', type=click.Path(exists=True), help='Config file path')
@click.option('--debug', is_flag=True, help='Enable debug logging')
def cli(config, debug):
    """Polymarket AI Trading Bot - Gasless trading with AI strategies."""
    setup_logging(debug=debug)


@cli.command()
@click.option('--strategy', type=click.Choice(['ai', 'ml', 'custom']), default='ai',
              help='Strategy type to use')
@click.option('--dry-run', is_flag=True, help='Run without executing trades')
def run(strategy, dry_run):
    """Run the trading bot."""
    config = load_config()

    logger.info(f"Starting Polymarket Trading Bot (strategy={strategy}, dry_run={dry_run})")

    # Initialize components
    polymarket = PolymarketClient(config)
    executor = OrderExecutor(polymarket)
    strategist = get_strategist(config)
    scanner = MarketScanner(polymarket)

    try:
        # Main trading loop
        asyncio.run(trading_loop(scanner, strategist, executor, config, dry_run))
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        sys.exit(1)


async def trading_loop(scanner, strategist, executor, config, dry_run):
    """Main trading loop."""
    while True:
        try:
            # Scan for 5min/15min markets
            markets = await scanner.scan_time_based_markets(['5min', '15min'])

            for market in markets:
                logger.info(f"Analyzing market: {market['question']}")

                # Generate signal
                signal = await strategist.analyze(market)

                if signal and not dry_run:
                    # Execute trade
                    await executor.execute(signal)
                elif signal and dry_run:
                    logger.info(f"DRY RUN: Would execute {signal}")

            # Wait before next iteration
            await asyncio.sleep(config.scan_interval)

        except Exception as e:
            logger.error(f"Error in trading loop: {e}")
            await asyncio.sleep(60)


@cli.command()
@click.argument('market_id')
@click.option('--strategy', type=click.Choice(['ai', 'ml', 'custom']), default='ai')
def backtest(market_id, strategy):
    """Run backtest for a specific market."""
    config = load_config()

    logger.info(f"Running backtest for market {market_id} with {strategy} strategy")

    engine = BacktestEngine(config)
    strategist = get_strategist(config)

    # Run backtest
    results = asyncio.run(engine.run_backtest(market_id, strategist))

    # Display results
    click.echo("\n=== Backtest Results ===")
    click.echo(f"Total Trades: {results.get('total_trades', 0)}")
    click.echo(f"Win Rate: {results.get('win_rate', 0):.2%}")
    click.echo(f"Total Return: {results.get('total_return', 0):.2%}")
    click.echo(f"Sharpe Ratio: {results.get('sharpe_ratio', 0):.2f}")
    click.echo(f"Max Drawdown: {results.get('max_drawdown', 0):.2%}")


@cli.command()
def markets():
    """List available 5min/15min markets."""
    config = load_config()

    polymarket = PolymarketClient(config)
    scanner = MarketScanner(polymarket)

    try:
        markets = asyncio.run(scanner.scan_time_based_markets(['5min', '15min']))

        if not markets:
            click.echo("No 5min/15min markets found")
            return

        click.echo(f"\nFound {len(markets)} time-based markets:\n")
        for m in markets:
            click.echo(f"  [{m['id']}] {m['question']}")
            click.echo(f"      Volume: ${float(m.get('volume', 0)):,.2f} | "
                      f" Liquidity: ${float(m.get('liquidity', 0)):,.2f}")
            click.echo()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('task')
def status(task):
    """Check status of bot components."""
    config = load_config()

    if task == 'bot':
        click.echo("=== Bot Status ===")
        click.echo(f"Strategy: {config.strategy_type.value}")
        click.echo(f"Scan Interval: {config.scan_interval}s")
    elif task == 'wallet':
        polymarket = PolymarketClient(config)
        balance = asyncio.run(polymarket.get_usdc_balance())
        click.echo(f"=== Wallet Status ===")
        click.echo(f"USDC Balance: {balance}")


@cli.command()
@click.option('--market-id', help='Specific market to analyze')
@click.option('--interactive', '-i', is_flag=True, help='Interactive mode for Claude Code')
def claude(market_id, interactive):
    """Interactive Claude Code interface for strategy and backtesting."""
    config = load_config()

    interface = ClaudeCodeInterface(config)

    if interactive:
        asyncio.run(interface.interactive_loop())
    elif market_id:
        asyncio.run(interface.analyze_market(market_id))
    else:
        click.echo("Usage: polybot claude --market-id <id>  or  polybot claude -i")


if __name__ == '__main__':
    cli()
