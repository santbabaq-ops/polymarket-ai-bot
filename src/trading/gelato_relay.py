"""Gelato Turbo Relayer for gasless transactions"""

import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass

import httpx

from src.config import Config
from src.utils.logging import get_logger


logger = get_logger(__name__)


GELATO_API_URL = "https://relay.gelato.digital"
GELATO_TURBO_URL = "https://api.gelato.com"


@dataclass
class RelayRequest:
    """Request for gasless transaction"""
    chain_id: int
    target: str
    data: str
    user: str


@dataclass
class RelayReceipt:
    """Receipt from gasless transaction"""
    task_id: str
    transaction_hash: Optional[str] = None
    status: str = "pending"


class GelatoRelay:
    """
    Gelato Turbo Relayer integration for gasless transactions on Polygon.

    Uses Gelato's sponsored transaction API to execute trades without paying gas fees.
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.gelato_api_key
        self.chain_id = config.gelato_chain_id  # 137 for Polygon

        # Polygon RPC
        self.rpc_url = config.polygon_rpc_url

        # HTTP client
        self._http = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        """Close HTTP client"""
        await self._http.aclose()

    async def get_balance(self) -> Dict[str, Any]:
        """
        Get Gelato Gas Tank balance.
        The Gas Tank is where you fund your sponsored transactions.
        """
        try:
            response = await self._http.get(
                f"{GELATO_API_URL}/balance",
                headers={"x-gelato-api-key": self.api_key},
                params={"chainId": self.chain_id}
            )
            response.raise_for_status()
            data = response.json()
            return {
                "balance": data.get("balance", "0"),
                "decimals": data.get("decimals", 18),
                "unit": data.get("unit", "USDC"),
            }
        except Exception as e:
            logger.error(f"Failed to get Gelato balance: {e}")
            return {"balance": "0", "decimals": 18, "unit": "USDC"}

    async def get_supported_tokens(self) -> list[Dict[str, str]]:
        """Get list of tokens accepted for gas payment"""
        try:
            response = await self._http.get(
                f"{GELATO_API_URL}/tokens",
                params={"chainId": self.chain_id}
            )
            response.raise_for_status()
            return response.json().get("tokens", [])
        except Exception as e:
            logger.error(f"Failed to get supported tokens: {e}")
            return []

    async def send_transaction_sync(
        self,
        target: str,
        data: str,
        value: int = 0,
    ) -> RelayReceipt:
        """
        Send a transaction synchronously (returns when mined or timeout).

        This is the main method for gasless trading.
        """
        try:
            payload = {
                "chainId": self.chain_id,
                "target": target,
                "data": data,
                "user": self._get_user_address(),
                "value": hex(value),
            }

            response = await self._http.post(
                f"{GELATO_API_URL}/relay/sponsored/sync",
                headers={
                    "x-gelato-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            return RelayReceipt(
                task_id=result.get("taskId", ""),
                transaction_hash=result.get("txHash"),
                status="submitted",
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Gelato API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to send gasless transaction: {e}")
            raise

    async def send_transaction(
        self,
        target: str,
        data: str,
        value: int = 0,
    ) -> str:
        """
        Send a transaction asynchronously (returns task ID immediately).

        Use this for non-blocking transaction submission.
        """
        try:
            payload = {
                "chainId": self.chain_id,
                "target": target,
                "data": data,
                "user": self._get_user_address(),
                "value": hex(value),
            }

            response = await self._http.post(
                f"{GELATO_API_URL}/relay/sponsored",
                headers={
                    "x-gelato-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            return result.get("taskId", "")

        except Exception as e:
            logger.error(f"Failed to submit transaction: {e}")
            raise

    async def wait_for_receipt(
        self,
        task_id: str,
        timeout: int = 120,
    ) -> RelayReceipt:
        """Wait for a transaction to be confirmed"""
        start_time = asyncio.get_event_loop().time()
        poll_interval = 2

        while True:
            try:
                response = await self._http.get(
                    f"{GELATO_API_URL}/relay/status/{task_id}",
                    headers={"x-gelato-api-key": self.api_key},
                )
                response.raise_for_status()
                status = response.json()

                state = status.get("taskState", "")

                if state == "ExecSuccess":
                    return RelayReceipt(
                        task_id=task_id,
                        transaction_hash=status.get("transactionHash"),
                        status="success",
                    )
                elif state in ("ExecReverted", "Blacklisted", "Cancelled"):
                    return RelayReceipt(
                        task_id=task_id,
                        status=state.lower(),
                    )

                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    return RelayReceipt(task_id=task_id, status="timeout")

                await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Error checking status: {e}")
                await asyncio.sleep(poll_interval)

    async def simulate_transaction(
        self,
        target: str,
        data: str,
    ) -> Dict[str, Any]:
        """
        Simulate a transaction to check if it will succeed.

        Use this before actually sending to catch errors early.
        """
        try:
            payload = {
                "chainId": self.chain_id,
                "target": target,
                "data": data,
                "user": self._get_user_address(),
            }

            response = await self._http.post(
                f"{GELATO_API_URL}/relay/simulate",
                headers={
                    "x-gelato-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                return {"success": False, "error": e.response.json()}
            raise
        except Exception as e:
            logger.error(f"Simulation failed: {e}")
            return {"success": False, "error": str(e)}

    def _get_user_address(self) -> str:
        """Get the user's wallet address from private key"""
        from web3 import Web3
        account = Web3().eth.account.from_key(self.config.wallet_private_key)
        return account.address

    async def estimate_gas(self, target: str, data: str) -> int:
        """Estimate gas for a transaction"""
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(self.rpc_url))

            payload = {
                "from": self._get_user_address(),
                "to": target,
                "data": data,
            }

            gas = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: w3.eth.estimate_gas(payload)
            )
            return gas

        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            return 200000  # Default gas limit


class GelatoWebSocket:
    """WebSocket subscription for real-time transaction status"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ws_url = "wss://ws.gelato.digital"
        self._ws = None

    async def subscribe(self, task_id: str) -> Any:
        """Subscribe to transaction status updates"""
        import websockets

        try:
            self._ws = await websockets.connect(self.ws_url)
            await self._ws.send({
                "type": "subscribe",
                "taskId": task_id,
                "apiKey": self.api_key,
            })
            return self._ws
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            raise

    async def unsubscribe(self):
        """Unsubscribe from updates"""
        if self._ws:
            await self._ws.close()