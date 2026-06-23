# xau_state_manager.py
import asyncio
import logging
from typing import List, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger("quant.state")


class QuantEngineState:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.market_history_cache: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def register(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
            # Instantly catch up newly connected browser
            if self.market_history_cache:
                await websocket.send_json(
                    {"event": "init_history", "data": self.market_history_cache}
                )

    async def unregister(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def append_candle(self, candle: Dict[str, Any]):
        async with self._lock:
            self.market_history_cache.append(candle)
            # Prevent memory leaks by bounding the cache length
            if len(self.market_history_cache) > 2000:
                self.market_history_cache.pop(0)

    async def broadcast(self, event: str, data: Any):
        async with self._lock:
            if not self.active_connections:
                return

            payload = {"event": event, "data": data}
            # Broadcast concurrently across active connections
            tasks = [self._safe_send(ws, payload) for ws in self.active_connections]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, ws: WebSocket, payload: Dict[str, Any]):
        try:
            await ws.send_json(payload)
        except Exception:
            # Stale connection will be cleaned up by the lifecycle router
            pass


class QuantitativeGuard:
    @staticmethod
    def verify_execution_threshold(latest_candle: Any) -> bool:
        """Enforces a rigorous quantitative filter before allocating LLM execution tokens."""
        trend_strength = abs(latest_candle.get("gold_1h_trend", 0.0))
        volatility = latest_candle.get("rolling_volatility", 0.0)

        # Guard Clause: Veto setups lacking macro expansion parameters
        if trend_strength < 4.5 or volatility <= 0.0:
            return False

        return True


state_manager = QuantEngineState()
