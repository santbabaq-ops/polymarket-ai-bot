# Polymarket AI Trading Bot - Architecture

## Overview

A minimal, gasless AI trading bot for Polymarket's 5min/15min prediction markets.

**Key insight**: Polymarket's CLOB API already supports native gasless trading via EIP-712 off-chain signing. No third-party relayer needed.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI (Click)                            │
│         Commands: run, backtest, markets, status           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Strategy Engine                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ AI (Claude) │  │ ML (Local)  │  │ Custom              │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Backtesting Engine                           │
│  - VectorBT for fast historical backtesting                 │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Trading Execution Layer                      │
│  ┌────────────────────────┐                                 │
│  │ Polymarket CLOB Client │  Native gasless via EIP-712    │
│  │ - create_order         │  Orders signed locally          │
│  │ - create_market_order  │  Polymarket relayer pays gas    │
│  │ - cancel_order         │                                 │
│  └────────────────────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

## Gasless Flow

```
Bot                         Polymarket API
│                                 │
├── 1. Build order ──────────────>│
│                                 │
├── 2. Sign (EIP-712) ──────────>│
│                                 │── 3. Relayer pays gas
│                                 │── 4. Execute on-chain
│<─ 5. Order ID ─────────────────│
```

## Project Structure

```
polymarket-ai-bot/
├── src/
│   ├── main.py                    # CLI entry point
│   ├── config.py                  # Config (wallet + API keys)
│   ├── trading/
│   │   ├── polymarket_client.py   # CLOB API wrapper
│   │   └── order_executor.py      # Order execution
│   ├── strategy/
│   │   ├── ai_strategist.py       # Claude strategy
│   │   ├── ml_strategist.py       # Local ML strategy
│   │   ├── custom_strategist.py   # User-defined strategy
│   │   └── position_sizer.py      # Kelly criterion sizing
│   ├── backtest/
│   │   ├── backtest_engine.py     # VectorBT backtesting
│   │   └── performance_analyzer.py # Metrics
│   └── utils/
│       ├── market_scanner.py      # Find 5min/15min markets
│       └── logging.py
├── tests/
│   ├── test_trading.py
│   ├── test_strategy.py
│   └── test_backtest.py
└── docs/
    ├── ARCHITECTURE.md
    └── RESEARCH.md
```

## Configuration

### Required
```
POLYGON_WALLET_PRIVATE_KEY=0x...     # For signing orders
ANTHROPIC_API_KEY=sk-ant-...         # For AI strategy (optional if using ML/Custom)
```

### Optional
```
POLYMARKET_API_KEY=...               # If API requires it
POLYGON_RPC_URL=...                  # Custom RPC endpoint
```

## Testing

```bash
pytest tests/ -v
```

## References

- [Polymarket py-clob-client](https://github.com/Polymarket/py-clob-client)
- [VectorBT](https://github.com/polakowo/vectorbt)
