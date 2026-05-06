"""Tests for backtest module"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pandas as pd
import numpy as np

from src.backtest.backtest_engine import BacktestEngine, BacktestResult
from src.backtest.performance_analyzer import PerformanceAnalyzer, PerformanceMetrics


class TestBacktestEngine:
    """Tests for BacktestEngine"""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration"""
        config = MagicMock()
        config.get = MagicMock(return_value=None)
        return config

    @pytest.fixture
    def engine(self, mock_config):
        """Create backtest engine"""
        return BacktestEngine(mock_config)

    def test_prepare_dataframe(self, engine):
        """Test DataFrame preparation"""
        data = {
            "prices": [
                {"timestamp": "2024-01-01T00:00:00", "price": 0.50, "volume": 1000},
                {"timestamp": "2024-01-01T00:01:00", "price": 0.52, "volume": 1200},
                {"timestamp": "2024-01-01T00:02:00", "price": 0.51, "volume": 800},
            ]
        }

        df = engine._prepare_dataframe(data)

        assert len(df) == 3
        assert "close" in df.columns
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns

    def test_prepare_dataframe_synthetic(self, engine):
        """Test synthetic data generation fallback"""
        data = {}  # Empty data

        with patch.object(engine.fetcher, 'generate_synthetic_data') as mock_gen:
            mock_gen.return_value = [{"price": 0.5, "volume": 100}]
            df = engine._prepare_dataframe(data)

            assert len(df) > 0
            assert "close" in df.columns

    @pytest.mark.asyncio
    async def test_calculate_performance(self, engine):
        """Test performance calculation"""
        # Create sample price data
        prices = np.linspace(0.5, 0.6, 100)
        df = pd.DataFrame({
            "close": prices,
            "open": prices,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "volume": np.random.randint(100, 1000, 100)
        })

        # Create signals (buy at start, sell at end)
        signals = pd.DataFrame({
            "signal": ["BUY"] + ["HOLD"] * 48 + ["SELL"] + ["HOLD"] * 50,
            "confidence": [0.7] + [0] * 98 + [0.7],
            "price": prices
        }, index=df.index)

        result = engine._calculate_performance(df, signals, 10000)

        assert isinstance(result, BacktestResult)
        assert result.total_trades >= 0

    def test_backtest_result_dataclass(self):
        """Test BacktestResult initialization"""
        result = BacktestResult(
            total_trades=10,
            winning_trades=7,
            losing_trades=3,
            win_rate=0.7,
            total_return=0.15,
            sharpe_ratio=1.5,
            max_drawdown=0.05,
            avg_trade_return=0.015,
            avg_trade_duration=None,
            trades=[],
            equity_curve=[10000, 10100, 10200]
        )

        assert result.total_trades == 10
        assert result.win_rate == 0.7
        assert len(result.equity_curve) == 3


class TestPerformanceAnalyzer:
    """Tests for PerformanceAnalyzer"""

    @pytest.fixture
    def analyzer(self):
        """Create performance analyzer"""
        return PerformanceAnalyzer()

    def test_analyze_empty_results(self, analyzer):
        """Test analyzing empty results"""
        metrics = analyzer.analyze([])

        assert metrics.total_return == 0
        assert metrics.sharpe_ratio == 0
        assert metrics.win_rate == 0

    def test_analyze_winning_trades(self, analyzer):
        """Test analyzing winning trades"""
        results = [
            {"return": 0.05, "pnl": 50},
            {"return": 0.03, "pnl": 30},
            {"return": 0.02, "pnl": 20},
        ]

        metrics = analyzer.analyze(results)

        assert metrics.total_return == 0.10
        assert metrics.win_rate == 1.0
        assert metrics.avg_trade == pytest.approx(0.0333, rel=0.01)

    def test_analyze_mixed_trades(self, analyzer):
        """Test analyzing mixed win/loss trades"""
        results = [
            {"return": 0.10, "pnl": 100},
            {"return": -0.05, "pnl": -50},
            {"return": 0.08, "pnl": 80},
            {"return": -0.02, "pnl": -20},
        ]

        metrics = analyzer.analyze(results)

        assert metrics.total_return == 0.11
        assert metrics.win_rate == 0.5
        assert metrics.profit_factor > 1  # Profitable

    def test_profit_factor_calculation(self, analyzer):
        """Test profit factor calculation"""
        winners = [50, 30, 20]
        losers = [20, 10]

        pf = analyzer._profit_factor(winners, losers)

        assert pf == (50 + 30 + 20) / (20 + 10)  # 100/30

    def test_sharpe_ratio(self, analyzer):
        """Test Sharpe ratio calculation"""
        # Generate returns with known properties
        returns = [0.01, 0.02, -0.01, 0.03, 0.015]

        sharpe = analyzer._sharpe_ratio(returns, 0.02)

        assert isinstance(sharpe, float)
        assert not np.isnan(sharpe)

    def test_max_drawdown(self, analyzer):
        """Test max drawdown calculation"""
        pnls = [100, 50, -20, 30, -10, 80]

        dd = analyzer._max_drawdown(pnls)

        assert 0 <= dd <= 1

    def test_calmar_ratio(self, analyzer):
        """Test Calmar ratio calculation"""
        total_return = 0.5
        max_drawdown = 0.2

        calmar = analyzer._calmar_ratio(total_return, max_drawdown)

        assert calmar == 2.5

    def test_expectancy(self, analyzer):
        """Test expectancy calculation"""
        pnls = [100, 50, -30, 80, -20]

        exp = analyzer._expectancy(pnls)

        assert isinstance(exp, float)

    def test_compare_strategies(self, analyzer):
        """Test strategy comparison"""
        strategy_a = [{"return": 0.1, "pnl": 100}]
        strategy_b = [{"return": 0.05, "pnl": 50}]

        comparison = analyzer.compare_strategies({
            "Strategy A": strategy_a,
            "Strategy B": strategy_b
        })

        assert "Strategy A" in comparison
        assert "Strategy B" in comparison
        assert comparison["Strategy A"].total_return > comparison["Strategy B"].total_return

    def test_generate_report(self, analyzer):
        """Test report generation"""
        metrics = PerformanceMetrics(
            total_return=0.15,
            annualized_return=0.20,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.05,
            calmar_ratio=4.0,
            win_rate=0.65,
            profit_factor=1.8,
            avg_trade=0.015,
            median_trade=0.012,
            std_trade=0.02,
            best_trade=0.10,
            worst_trade=-0.05,
            expectancy=0.008,
            recovery_factor=3.0,
            payoff_ratio=1.5
        )

        report = analyzer.generate_report(metrics, "Test Strategy")

        assert "Test Strategy" in report
        assert "Total Return" in report
        assert "Sharpe Ratio" in report
        assert "15.00%" in report  # Total return formatted


class TestRiskMetrics:
    """Tests for risk-related calculations"""

    @pytest.fixture
    def analyzer(self):
        return PerformanceAnalyzer()

    def test_sortino_ratio(self, analyzer):
        """Test Sortino ratio (downside deviation only)"""
        # Returns with some downside
        returns = [0.02, 0.01, -0.02, 0.03, -0.01, 0.02]

        sortino = analyzer._sortino_ratio(returns, 0.02)

        assert isinstance(sortino, float)

    def test_recovery_factor(self, analyzer):
        """Test recovery factor"""
        total_return = 0.5
        max_drawdown = 0.1

        rf = analyzer._recovery_factor(total_return, max_drawdown)

        assert rf == 5.0

    def test_recovery_factor_zero_drawdown(self, analyzer):
        """Test recovery factor with zero drawdown"""
        rf = analyzer._recovery_factor(0.1, 0)

        assert rf == float('inf')
