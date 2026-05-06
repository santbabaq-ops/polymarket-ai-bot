"""Performance analyzer for backtest results"""

from typing import Dict, Any, List
from dataclasses import dataclass
import statistics

import numpy as np


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics"""
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    avg_trade: float
    median_trade: float
    std_trade: float
    best_trade: float
    worst_trade: float
    expectancy: float
    recovery_factor: float
    payoff_ratio: float


class PerformanceAnalyzer:
    """
    Analyzes backtest results and generates performance reports.
    """

    def __init__(self):
        self.metrics: Dict[str, PerformanceMetrics] = {}

    def analyze(
        self,
        results: List[Dict],
        risk_free_rate: float = 0.02,
    ) -> PerformanceMetrics:
        """
        Analyze backtest results.

        Args:
            results: List of trade results
            risk_free_rate: Annual risk-free rate for Sharpe calculation

        Returns:
            PerformanceMetrics object
        """
        if not results:
            return self._empty_metrics()

        returns = [r.get("return", 0) for r in results]
        pnls = [r.get("pnl", 0) for r in results]

        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [abs(p) for p in pnls if p <= 0]

        total_return = sum(pnls)
        avg_trade = statistics.mean(returns) if returns else 0

        # Calculate metrics
        metrics = PerformanceMetrics(
            total_return=total_return,
            annualized_return=self._annualize(avg_trade, periods_per_year=365),
            sharpe_ratio=self._sharpe_ratio(returns, risk_free_rate),
            sortino_ratio=self._sortino_ratio(returns, risk_free_rate),
            max_drawdown=self._max_drawdown(pnls),
            calmar_ratio=self._calmar_ratio(total_return, self._max_drawdown(pnls)),
            win_rate=len(winning_trades) / len(pnls) if pnls else 0,
            profit_factor=self._profit_factor(winning_trades, losing_trades),
            avg_trade=avg_trade,
            median_trade=statistics.median(returns) if returns else 0,
            std_trade=statistics.stdev(returns) if len(returns) > 1 else 0,
            best_trade=max(returns) if returns else 0,
            worst_trade=min(returns) if returns else 0,
            expectancy=self._expectancy(pnls),
            recovery_factor=self._recovery_factor(total_return, self._max_drawdown(pnls)),
            payoff_ratio=statistics.mean(winning_trades) / statistics.mean(losing_trades) if losing_trades and winning_trades else 0,
        )

        return metrics

    def compare_strategies(
        self,
        strategy_results: Dict[str, List[Dict]],
    ) -> Dict[str, PerformanceMetrics]:
        """
        Compare multiple strategies.

        Args:
            strategy_results: Dict mapping strategy name to results list

        Returns:
            Dict mapping strategy name to PerformanceMetrics
        """
        comparison = {}

        for name, results in strategy_results.items():
            comparison[name] = self.analyze(results)

        return comparison

    def generate_report(
        self,
        metrics: PerformanceMetrics,
        strategy_name: str = "Strategy",
    ) -> str:
        """Generate a text report from metrics"""
        report = f"""
{'='*60}
{strategy_name} Performance Report
{'='*60}

Return Metrics:
  Total Return:     {metrics.total_return:>10.2%}
  Annualized:       {metrics.annualized_return:>10.2%}
  Sharpe Ratio:     {metrics.sharpe_ratio:>10.2f}
  Sortino Ratio:    {metrics.sortino_ratio:>10.2f}
  Calmar Ratio:     {metrics.calmar_ratio:>10.2f}

Risk Metrics:
  Max Drawdown:     {metrics.max_drawdown:>10.2%}
  Recovery Factor: {metrics.recovery_factor:>10.2f}

Trade Metrics:
  Win Rate:         {metrics.win_rate:>10.2%}
  Profit Factor:    {metrics.profit_factor:>10.2f}
  Payoff Ratio:     {metrics.payoff_ratio:>10.2f}
  Expectancy:       {metrics.expectancy:>10.4f}

Trade Statistics:
  Average Trade:    {metrics.avg_trade:>10.2%}
  Median Trade:    {metrics.median_trade:>10.2%}
  Std Deviation:   {metrics.std_trade:>10.2%}
  Best Trade:      {metrics.best_trade:>10.2%}
  Worst Trade:     {metrics.worst_trade:>10.2%}

{'='*60}
"""
        return report

    def _annualize(self, return_pct: float, periods_per_year: int) -> float:
        """Annualize a return"""
        return ((1 + return_pct) ** periods_per_year) - 1

    def _sharpe_ratio(self, returns: List[float], risk_free_rate: float) -> float:
        """Calculate Sharpe ratio"""
        if not returns or len(returns) < 2:
            return 0

        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)

        if std_return == 0:
            return 0

        excess_return = mean_return - (risk_free_rate / 365)
        return (excess_return / std_return) * np.sqrt(252)

    def _sortino_ratio(self, returns: List[float], risk_free_rate: float) -> float:
        """Calculate Sortino ratio (using downside deviation)"""
        if not returns:
            return 0

        mean_return = statistics.mean(returns)
        downside_returns = [r for r in returns if r < 0]

        if not downside_returns:
            return float('inf') if mean_return > 0 else 0

        downside_std = statistics.stdev(downside_returns) if len(downside_returns) > 1 else 0

        if downside_std == 0:
            return 0

        excess_return = mean_return - (risk_free_rate / 365)
        return (excess_return / downside_std) * np.sqrt(252)

    def _max_drawdown(self, pnls: List[float]) -> float:
        """Calculate maximum drawdown"""
        if not pnls:
            return 0

        cumulative = np.cumsum([0] + pnls)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / np.maximum(running_max, 1)

        return abs(drawdown.min()) if len(drawdown) > 0 else 0

    def _calmar_ratio(self, total_return: float, max_drawdown: float) -> float:
        """Calculate Calmar ratio"""
        if max_drawdown == 0:
            return 0
        return total_return / max_drawdown

    def _profit_factor(self, winners: List[float], losers: List[float]) -> float:
        """Calculate profit factor"""
        gross_profit = sum(winners) if winners else 0
        gross_loss = sum(losers) if losers else 0

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0

        return gross_profit / gross_loss

    def _expectancy(self, pnls: List[float]) -> float:
        """Calculate trade expectancy"""
        if not pnls:
            return 0

        win_rate = len([p for p in pnls if p > 0]) / len(pnls)
        avg_win = statistics.mean([p for p in pnls if p > 0]) if [p for p in pnls if p > 0] else 0
        avg_loss = abs(statistics.mean([p for p in pnls if p <= 0])) if [p for p in pnls if p <= 0] else 0

        return (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    def _recovery_factor(self, total_return: float, max_drawdown: float) -> float:
        """Calculate recovery factor"""
        if max_drawdown == 0:
            return float('inf') if total_return > 0 else 0
        return total_return / max_drawdown

    def _empty_metrics(self) -> PerformanceMetrics:
        """Return empty metrics"""
        return PerformanceMetrics(
            total_return=0,
            annualized_return=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            max_drawdown=0,
            calmar_ratio=0,
            win_rate=0,
            profit_factor=0,
            avg_trade=0,
            median_trade=0,
            std_trade=0,
            best_trade=0,
            worst_trade=0,
            expectancy=0,
            recovery_factor=0,
            payoff_ratio=0,
        )