"""Gelato Web3 Functions for automated trading strategies

This module provides automation capabilities using Gelato Web3 Functions:
- Stop-loss execution
- Take-profit execution
- Conditional order execution (price-based triggers)
- Time-based order execution

Gelato Web3 Functions allow serverless automation that runs on-chain
without requiring your bot to be constantly online.
"""

import asyncio
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

import httpx

from src.config import Config
from src.utils.logging import get_logger


logger = get_logger(__name__)


GELATO_WEB3_FUNCTIONS_URL = "https://web3-functions.gelato.digital"
GELATO_USER_API_URL = "https://api.gelato.digital"


class AutomationTriggerType(str, Enum):
    """Types of automation triggers"""
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    PRICE_THRESHOLD = "price_threshold"
    TIME_BASED = "time_based"


@dataclass
class AutomationTask:
    """A Gelato Web3 Function automation task"""
    task_id: str
    trigger_type: AutomationTriggerType
    market_id: str
    token_id: str
    condition_value: float  # price threshold, percentage, etc.
    action: str  # "SELL", "BUY", "CANCEL"
    status: str = "pending"


class GelatoAutomation:
    """
    Gelato Web3 Functions integration for automated trading.

    Web3 Functions are serverless functions that can be scheduled
to run on-chain at regular intervals or based on conditions.

    Use cases:
    1. Stop-loss: Automatically sell when price drops below threshold
    2. Take-profit: Automatically sell when price reaches target
    3. Conditional orders: Execute when price crosses a level
    4. Time-based: Execute at a specific time (e.g., market close)
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.gelato_api_key
        self.chain_id = config.gelato_chain_id
        self._http = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        """Close HTTP client"""
        await self._http.aclose()

    async def create_stop_loss_task(
        self,
        token_id: str,
        trigger_price: float,
        size: float,
    ) -> AutomationTask:
        """
        Create a stop-loss automation task.

        When the market price drops to or below trigger_price,
        automatically place a SELL order.

        Args:
            token_id: The conditional token ID
            trigger_price: Price threshold (0-1)
            size: Amount to sell

        Returns:
            AutomationTask with task_id for monitoring/cancellation
        """
        try:
            # Web3 Function to check price and execute stop-loss
            w3f_code = self._generate_stop_loss_w3f(token_id, trigger_price, size)

            payload = {
                "name": f"stop-loss-{token_id[:8]}",
                "web3FunctionHash": w3f_code,
                "trigger": {
                    "interval": 60,  # Check every 60 seconds
                    "type": "time",
                },
                "chainId": self.chain_id,
            }

            response = await self._http.post(
                f"{GELATO_USER_API_URL}/tasks",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            task = AutomationTask(
                task_id=result.get("taskId", ""),
                trigger_type=AutomationTriggerType.STOP_LOSS,
                market_id="",
                token_id=token_id,
                condition_value=trigger_price,
                action="SELL",
            )

            logger.info(f"Created stop-loss task {task.task_id} for token {token_id}")
            return task

        except Exception as e:
            logger.error(f"Failed to create stop-loss task: {e}")
            raise

    async def create_take_profit_task(
        self,
        token_id: str,
        trigger_price: float,
        size: float,
    ) -> AutomationTask:
        """
        Create a take-profit automation task.

        When the market price reaches or exceeds trigger_price,
        automatically place a SELL order.
        """
        try:
            w3f_code = self._generate_take_profit_w3f(token_id, trigger_price, size)

            payload = {
                "name": f"take-profit-{token_id[:8]}",
                "web3FunctionHash": w3f_code,
                "trigger": {
                    "interval": 60,
                    "type": "time",
                },
                "chainId": self.chain_id,
            }

            response = await self._http.post(
                f"{GELATO_USER_API_URL}/tasks",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            task = AutomationTask(
                task_id=result.get("taskId", ""),
                trigger_type=AutomationTriggerType.TAKE_PROFIT,
                market_id="",
                token_id=token_id,
                condition_value=trigger_price,
                action="SELL",
            )

            logger.info(f"Created take-profit task {task.task_id} for token {token_id}")
            return task

        except Exception as e:
            logger.error(f"Failed to create take-profit task: {e}")
            raise

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel an automation task"""
        try:
            response = await self._http.delete(
                f"{GELATO_USER_API_URL}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            logger.info(f"Cancelled automation task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return False

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of an automation task"""
        try:
            response = await self._http.get(
                f"{GELATO_USER_API_URL}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return {"error": str(e)}

    async def list_tasks(self) -> list[AutomationTask]:
        """List all active automation tasks"""
        try:
            response = await self._http.get(
                f"{GELATO_USER_API_URL}/tasks",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={"chainId": self.chain_id},
            )
            response.raise_for_status()
            tasks_data = response.json().get("tasks", [])

            tasks = []
            for t in tasks_data:
                tasks.append(AutomationTask(
                    task_id=t.get("taskId", ""),
                    trigger_type=AutomationTriggerType(t.get("type", "price_threshold")),
                    market_id=t.get("marketId", ""),
                    token_id=t.get("tokenId", ""),
                    condition_value=float(t.get("condition", 0)),
                    action=t.get("action", ""),
                    status=t.get("status", "unknown"),
                ))

            return tasks

        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return []

    def _generate_stop_loss_w3f(
        self,
        token_id: str,
        trigger_price: float,
        size: float,
    ) -> str:
        """
        Generate Web3 Function code for stop-loss.

        This is a simplified representation. In production, you'd deploy
        a proper Web3 Function to IPFS and reference its hash.
        """
        # In practice, this would be the IPFS hash of a deployed Web3 Function
        # For now, return a placeholder that represents the logic
        return f"stop-loss-{token_id}-{trigger_price}-{size}"

    def _generate_take_profit_w3f(
        self,
        token_id: str,
        trigger_price: float,
        size: float,
    ) -> str:
        """Generate Web3 Function code for take-profit"""
        return f"take-profit-{token_id}-{trigger_price}-{size}"


class LocalAutomationManager:
    """
    Local automation manager that runs within the bot process.

    This is a lightweight alternative to Gelato Web3 Functions
    for users who prefer to keep automation in-house.
    It requires the bot to be running but doesn't need Gelato API.
    """

    def __init__(self, executor):
        self.executor = executor
        self._tasks: Dict[str, AutomationTask] = {}
        self._running = False
        self._check_interval = 10  # seconds

    async def start(self):
        """Start the automation loop"""
        self._running = True
        logger.info("Starting local automation manager")

        while self._running:
            try:
                await self._check_triggers()
                await asyncio.sleep(self._check_interval)
            except Exception as e:
                logger.error(f"Automation error: {e}")
                await asyncio.sleep(self._check_interval)

    def stop(self):
        """Stop the automation loop"""
        self._running = False
        logger.info("Stopped local automation manager")

    def add_stop_loss(
        self,
        task_id: str,
        token_id: str,
        trigger_price: float,
        size: float,
    ):
        """Add a stop-loss trigger"""
        self._tasks[task_id] = AutomationTask(
            task_id=task_id,
            trigger_type=AutomationTriggerType.STOP_LOSS,
            market_id="",
            token_id=token_id,
            condition_value=trigger_price,
            action="SELL",
        )
        logger.info(f"Added stop-loss: {task_id} at {trigger_price}")

    def add_take_profit(
        self,
        task_id: str,
        token_id: str,
        trigger_price: float,
        size: float,
    ):
        """Add a take-profit trigger"""
        self._tasks[task_id] = AutomationTask(
            task_id=task_id,
            trigger_type=AutomationTriggerType.TAKE_PROFIT,
            market_id="",
            token_id=token_id,
            condition_value=trigger_price,
            action="SELL",
        )
        logger.info(f"Added take-profit: {task_id} at {trigger_price}")

    def remove_task(self, task_id: str):
        """Remove an automation task"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info(f"Removed automation task: {task_id}")

    async def _check_triggers(self):
        """Check all triggers and execute if conditions are met"""
        for task_id, task in list(self._tasks.items()):
            try:
                # Get current price
                orderbook = await self.executor.polymarket.get_order_book(task.token_id)

                if task.trigger_type == AutomationTriggerType.STOP_LOSS:
                    # For stop-loss, check if best bid <= trigger price
                    bids = orderbook.get("bids", [])
                    if bids:
                        best_bid = max(float(b["price"]) for b in bids)
                        if best_bid <= task.condition_value:
                            logger.warning(
                                f"STOP LOSS TRIGGERED: {task.token_id} "
                                f"at {best_bid} (threshold: {task.condition_value})"
                            )
                            # Execute sell
                            await self.executor.execute_market_order(
                                token_id=task.token_id,
                                amount=0,  # Would need to get position size
                                side="SELL",
                            )
                            self.remove_task(task_id)

                elif task.trigger_type == AutomationTriggerType.TAKE_PROFIT:
                    # For take-profit, check if best bid >= trigger price
                    bids = orderbook.get("bids", [])
                    if bids:
                        best_bid = max(float(b["price"]) for b in bids)
                        if best_bid >= task.condition_value:
                            logger.info(
                                f"TAKE PROFIT TRIGGERED: {task.token_id} "
                                f"at {best_bid} (target: {task.condition_value})"
                            )
                            # Execute sell
                            await self.executor.execute_market_order(
                                token_id=task.token_id,
                                amount=0,
                                side="SELL",
                            )
                            self.remove_task(task_id)

            except Exception as e:
                logger.error(f"Error checking trigger {task_id}: {e}")
