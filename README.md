# Polymarket AI Trading Bot

An autonomous AI-powered trading bot for Polymarket 5min/15min prediction markets with gasless transactions and backtesting capabilities.

## Features

- **Gasless Trading**: Zero gas fees using Gelato Turbo Relayer
- **Multiple AI Strategies**:
  - Claude AI-powered market analysis
  - Local ML models (XGBoost, LightGBM)
  - Custom strategy interface
- **Backtesting Engine**: VectorBT-powered fast backtesting
- **Smart Position Sizing**: Kelly criterion and risk management
- **Multi-Market Support**: Focus on 5min/15min time-based markets

## Quick Start

### Prerequisites

- Python 3.11+
- Polygon wallet with USDC
- API keys (see below)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/polymarket-ai-bot.git
cd polymarket-ai-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env
```

### Configuration

Edit `.env` with your API keys:

```env
# Wallet (required)
POLYGON_WALLET_PRIVATE_KEY=0x...

# APIs (required)
ANTHROPIC_API_KEY=sk-ant-...    # For AI strategy
GELATO_API_KEY=...               # For gasless transactions
```

### Usage

```bash
# List available 5min/15min markets
polybot markets

# Run with AI strategy
polybot run --strategy ai

# Run with ML strategy
polybot run --strategy ml

# Dry run (no real trades)
polybot run --strategy ai --dry-run

# Run backtest on a market
polybot backtest <market_id> --strategy ai

# Check bot status
polybot status bot
polybot status gelato
polybot status wallet
```

## Project Structure

```
polymarket-ai-bot/
├── src/
│   ├── main.py              # CLI entry point
│   ├── config.py            # Configuration management
│   ├── trading/
│   │   ├── polymarket_client.py   # Polymarket CLOB API
│   │   ├── gelato_relay.py        # Gasless transactions
│   │   └── order_executor.py      # Order execution
│   ├── strategy/
│   │   ├── base.py               # Strategy interface
│   │   ├── ai_strategist.py      # Claude AI strategy
│   │   ├── ml_strategist.py      # ML-based strategy
│   │   ├── custom_strategist.py  # Custom strategy loader
│   │   ├── signal_generator.py   # Multi-indicator signals
│   │   └── position_sizer.py     # Kelly criterion sizing
│   ├── backtest/
│   │   ├── backtest_engine.py     # VectorBT backtesting
│   │   ├── historical_fetcher.py  # Data fetching
│   │   └── performance_analyzer.py # Metrics analysis
│   └── utils/
│       ├── logging.py
│       └── market_scanner.py     # Market discovery
└── tests/                        # Test suite
```

## Strategies

### AI Strategy (Claude)
Uses Claude API for natural language market analysis. Generates signals based on:
- Market question analysis
- Order book dynamics
- Volume trends

### ML Strategy
Local machine learning models trained on historical data:
- Feature extraction from market data
- Gradient Boosting classifier
- Online learning capability

### Custom Strategy
Load your own strategy from a Python file:
```python
from src.strategy.base import BaseStrategy, Signal

class MyStrategy(BaseStrategy):
    async def analyze(self, market):
        # Your logic here
        return Signal(...)
```

## Backtesting

```python
from src.backtest.backtest_engine import BacktestEngine
from src.strategy.ai_strategist import AIStrategist

engine = BacktestEngine(config)
strategy = AIStrategist(config)

results = await engine.run_backtest(
    market_id="...",
    strategy=strategy,
    initial_capital=10000
)

print(f"Win Rate: {results.win_rate:.2%}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI / Commands                           │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────────┐
│                    Strategy Engine                           │
│  ┌───────────┐  ┌───────────┐  ┌────────────────────────┐  │
│  │ AI        │  │ ML        │  │ Signal Generator       │  │
│  │ Strategist│  │ Strategist│  │ (Multi-indicator)      │  │
│  └───────────┘  └───────────┘  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────────┐
│                 Backtesting Engine                           │
│  - VectorBT: Fast vectorized backtesting                    │
│  - Historical Fetcher: Polymarket data                      │
│  - Performance Analyzer: Comprehensive metrics             │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────────┐
│                 Trading Execution Layer                      │
│  ┌─────────────────────────┐  ┌──────────────────────────┐  │
│  │ Gelato Turbo Relayer    │  │ Polymarket CLOB Client   │  │
│  │ (Gasless transactions)  │  │ (Order matching)         │  │
│  └─────────────────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Risk Management

- **Kelly Criterion**: Optimal position sizing based on edge
- **Stop Loss/Take Profit**: Configurable exit points
- **Max Drawdown**: Automatic trading halt on losses
- **Position Limits**: Maximum position size constraints

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_strategy.py
```

## License

MIT License - see LICENSE file for details.

## Disclaimer

This software is for educational purposes. Cryptocurrency trading involves substantial risk of loss. Past performance does not guarantee future results. Use at your own risk.
