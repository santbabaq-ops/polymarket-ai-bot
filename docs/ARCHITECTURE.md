# Architecture Documentation

## Overview

The Polymarket AI Trading Bot is designed with a modular architecture separating concerns into distinct layers:

1. **Strategy Layer**: AI/ML/custom strategies for signal generation
2. **Backtesting Layer**: Historical validation using VectorBT
3. **Execution Layer**: Order execution via Polymarket CLOB + Gelato

## Component Diagrams

### Trading Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Market Scan  │────▶│ Strategy     │────▶│ Signal Gen   │────▶│ Executor     │
│ (5min/15min) │     │ (AI/ML)      │     │              │     │ (Gelato)     │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Backtest Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Historical   │────▶│ Data Prep    │────▶│ Strategy     │────▶│ Performance  │
│ Data Fetch   │     │ (VectorBT)   │     │ Simulation   │     │ Analysis     │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

## Key Modules

### Trading Module

| File | Purpose |
|------|---------|
| `polymarket_client.py` | Polymarket CLOB API integration |
| `gelato_relay.py` | Gelato Turbo Relayer for gasless tx |
| `order_executor.py` | Order execution orchestration |

### Strategy Module

| File | Purpose |
|------|---------|
| `base.py` | Abstract base class for strategies |
| `ai_strategist.py` | Claude API-powered analysis |
| `ml_strategist.py` | Local ML model predictions |
| `signal_generator.py` | Multi-indicator consensus |
| `position_sizer.py` | Kelly criterion sizing |

### Backtest Module

| File | Purpose |
|------|---------|
| `backtest_engine.py` | VectorBT-powered backtesting |
| `historical_fetcher.py` | Data fetching/caching |
| `performance_analyzer.py` | Metrics calculation |

## API Integrations

### Polymarket CLOB API

- Endpoint: `https://clob.polymarket.com`
- Order matching on Polygon
- Low latency execution

### Gelato Turbo Relayer

- Gasless transactions on Polygon
- Sponsored transaction mode
- WebSocket status updates

### Claude API

- Market analysis prompts
- Signal generation
- Strategy refinement

## Data Flow

### Real-time Trading

1. Market scanner finds 5min/15min markets
2. Strategy analyzes market data
3. Signal generator produces actionable signal
4. Position sizer calculates optimal size
5. Order executor sends via Gelato (gasless)
6. Status updates via WebSocket

### Backtesting

1. Historical fetcher retrieves market data
2. Data prepared as OHLCV DataFrame
3. Strategy generates signals on historical data
4. VectorBT simulates portfolio
5. Performance analyzer computes metrics
6. Results cached for comparison

## Configuration

Configuration is loaded from:
1. `config.yaml` (if exists)
2. Environment variables
3. Default values

See `config.py` for all options.

## Extension Points

### Custom Strategy

Implement `BaseStrategy`:
```python
class MyStrategy(BaseStrategy):
    async def analyze(self, market):
        # Custom logic
        return Signal(...)
```

### Custom Indicator

Add to `SignalGenerator`:
```python
def my_indicator(market):
    return {'signal': 'BUY', 'confidence': 0.7}
```

## Error Handling

- Retry logic for API failures
- Circuit breaker for repeated failures
- Graceful degradation
- Detailed logging

## Security

- Private keys in environment variables
- No secrets in code
- API key rotation support
- Transaction signing separation
