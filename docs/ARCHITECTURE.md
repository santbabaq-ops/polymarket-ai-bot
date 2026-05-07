# Polymarket AI Trading Bot - Architecture

## Overview

This is a gasless AI trading bot for Polymarket's 5min/15min prediction markets. It combines:
- **Native Polymarket gasless CLOB trading** (EIP-712 off-chain signing)
- **AI-powered strategies** (Claude API)
- **Backtesting engine** (VectorBT)
- **Optional Gelato integration** for on-chain operations and automation

## Key Design Decisions

### 1. Native Gasless Trading (Primary)

**Discovery**: Polymarket's CLOB client already supports gasless trading via EIP-712 off-chain signing. Orders are signed locally and submitted to Polymarket's API, which handles gas payment through their relayer.

**Implementation**:
```python
# Standard trading - NO gas fees, NO Gelato needed
order = client.create_order(token_id, side, price, size)
client.post_order(order)  # Polymarket relayer pays gas
```

**Benefits**:
- Zero gas fees for users
- Simpler architecture
- Faster execution (no relayer round-trip)
- More reliable (single API call)

### 2. Gelato Integration (Secondary)

Gelato is reserved for specific use cases that require on-chain execution:

| Use Case | Gelato Feature | Why Needed |
|----------|---------------|------------|
| Token approvals (USDC/CTF) | SponsoredCall | On-chain ERC20 approve |
| Stop-loss automation | Web3 Functions | Serverless execution |
| Take-profit automation | Web3 Functions | Serverless execution |
| Conditional orders | Web3 Functions | Price-based triggers |

### 3. Dual Automation Approach

We provide two automation options:

**Option A: Gelato Web3 Functions** (Serverless)
- Runs on Gelato's infrastructure
- Bot can be offline
- Requires Gelato API key

**Option B: Local Automation Manager** (In-process)
- Runs within the bot process
- Requires bot to be running
- No Gelato dependency
- Good for testing/development

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI / Web UI                           │
│         (Click commands: run, backtest, markets)           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Strategy Engine                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ AI Strategist│  │ Signal Gen │  │ Kelly Sizing        │ │
│  │ (Claude)    │  │ Module     │  │ Module              │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Backtesting Engine                           │
│  - VectorBT for fast historical backtesting                 │
│  - Sliding window validation                                │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Trading Execution Layer                      │
│  ┌────────────────────────┐  ┌──────────────────────────┐  │
│  │ Polymarket CLOB Client │  │ Gelato Relay (Optional)  │  │
│  │ - Native gasless       │  │ - Token approvals        │  │
│  │ - EIP-712 signing      │  │ - Automation tasks       │  │
│  │ - Order management     │  │ - Web3 Functions         │  │
│  └────────────────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Gasless Transaction Flow

### Standard CLOB Order (Gasless)

```
User Bot                    Polymarket API              Relayer
   │                             │                         │
   │── 1. Create order ─────────>│                         │
   │                             │                         │
   │── 2. Sign (EIP-712) ───────>│                         │
   │                             │── 3. Submit to relayer ─>│
   │                             │                         │── 4. Pay gas & execute
   │                             │<─ 5. Confirmation ───────│
   │<─ 6. Order ID ──────────────│                         │
```

### On-chain Operation via Gelato

```
User Bot          Gelato API         Relayer         Blockchain
   │                 │                  │                │
   │── 1. Submit tx ->│                │                │
   │                 │── 2. Queue ────>│                │
   │                 │                │── 3. Execute ──>│
   │                 │<─ 4. Receipt ───│<─ 5. Confirm ───│
   │<─ 6. Task ID ────│                │                │
```

## Project Structure

```
polymarket-ai-bot/
├── README.md
├── pyproject.toml
├── .env.example
├── src/
│   ├── __init__.py
│   ├── main.py                    # CLI entry point
│   ├── config.py                  # Configuration management
│   ├── trading/
│   │   ├── __init__.py
│   │   ├── polymarket_client.py   # CLOB API wrapper (native gasless)
│   │   ├── gelato_relay.py        # Gelato relay for on-chain ops
│   │   ├── gelato_automation.py   # Web3 Functions + local automation
│   │   └── order_executor.py      # Order execution logic
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── base.py                # Base strategy interface
│   │   ├── ai_strategist.py       # Claude-powered strategy
│   │   ├── ml_strategist.py       # Local ML strategy
│   │   ├── custom_strategist.py   # User custom strategies
│   │   ├── signal_generator.py    # Signal generation
│   │   └── position_sizer.py      # Kelly criterion sizing
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── historical_fetcher.py  # Fetch historical data
│   │   ├── backtest_engine.py     # VectorBT backtesting
│   │   └── performance_analyzer.py # Strategy evaluation
│   └── utils/
│       ├── __init__.py
│       ├── logging.py
│       └── market_scanner.py      # Find 5min/15min markets
├── tests/
│   ├── test_trading.py
│   ├── test_strategy.py
│   └── test_backtest.py
└── docs/
    ├── ARCHITECTURE.md            # This file
    └── RESEARCH.md                # Research findings
```

## Configuration

### Required (for basic trading)
```
POLYGON_WALLET_PRIVATE_KEY=0x...
ANTHROPIC_API_KEY=sk-ant-...  # Only for AI strategy
```

### Optional (for advanced features)
```
GELATO_API_KEY=...              # For on-chain approvals/automation
POLYMARKET_API_KEY=...          # If required by API
```

## API Keys Summary

| Key | Required | Purpose |
|-----|----------|---------|
| `POLYGON_WALLET_PRIVATE_KEY` | Yes | Signing orders |
| `ANTHROPIC_API_KEY` | Yes (AI strategy) | Claude strategy generation |
| `GELATO_API_KEY` | No | On-chain ops, automation |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/test_trading.py -v
pytest tests/test_strategy.py -v
pytest tests/test_backtest.py -v
```

## Deployment

### Local Development
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m src.main run --dry-run
```

### Production
```bash
# Set environment variables
export POLYGON_WALLET_PRIVATE_KEY=...
export ANTHROPIC_API_KEY=...

# Run with AI strategy
python -m src.main run --strategy ai

# Run backtest
python -m src.main backtest MARKET_ID --strategy ai
```

## References

- [Polymarket CLOB Client](https://github.com/Polymarket/py-clob-client)
- [Polymarket CLOB Client TS](https://github.com/Polymarket/clob-client) - Shows native gasless support
- [Gelato Relay SDK](https://github.com/gelatodigital/relay-sdk)
- [Gelato Web3 Functions](https://github.com/gelatodigital/web3-functions-sdk)
- [VectorBT](https://github.com/polakowo/vectorbt)
