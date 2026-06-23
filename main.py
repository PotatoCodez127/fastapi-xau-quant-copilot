# main.py
import asyncio
import logging
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from config import settings
from src.core.engine import (
    build_macro_matrix_async,
    engineer_xau_features,
    fetch_live_candle_async,
)
from src.core.tracker import TradeTracker
from src.api.state import state_manager, QuantitativeGuard
from src.api.judge import evaluate_trade_setup_async
from src.memory.rag import setup_chroma_db, generate_semantic_tape, populate_memory
from src.memory.graph import build_knowledge_graph, generate_mock_trade_history

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("quant.main")


class Color:
    GREEN, CYAN, YELLOW, RED, MAGENTA, RESET = (
        "\033[92m",
        "\033[96m",
        "\033[93m",
        "\033[0m",
    )


tracker = TradeTracker(ledger_path=settings.LIVE_LEDGER_PATH)


async def run_live_forward_testing_loop():
    """Asynchronous pipeline polling engine."""
    logger.info(f"{Color.CYAN}🟢 INITIALIZING ASYNC XAUUSD LIVE ENGINE...{Color.RESET}")

    async with httpx.AsyncClient() as client:
        matrix = await build_macro_matrix_async(client, daysback=7)
        if matrix.empty:
            logger.error("Failed to load background context matrix. Halting loop.")
            return

        df = engineer_xau_features(matrix)
        rag_collection = setup_chroma_db()
        populate_memory(df, rag_collection)

        trades_df = generate_mock_trade_history(num_trades=2000)
        knowledge_graph = build_knowledge_graph(trades_df)

        for idx, row in df.iterrows():
            await state_manager.append_candle(
                {
                    "time": int(idx.timestamp()),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )

        last_processed_time = df.index[-1]
        logger.info(
            f"{Color.GREEN}✅ Live Telemetry Fully Armed. Loop Initiated.{Color.RESET}"
        )

        while True:
            try:
                latest_candle = await fetch_live_candle_async(client)
                if latest_candle is None:
                    await asyncio.sleep(60.0)
                    continue

                current_time = latest_candle.name
                if current_time > last_processed_time:
                    last_processed_time = current_time

                    candle_data = {
                        "time": int(current_time.timestamp()),
                        "open": float(latest_candle["open"]),
                        "high": float(latest_candle["high"]),
                        "low": float(latest_candle["low"]),
                        "close": float(latest_candle["close"]),
                    }
                    await state_manager.append_candle(candle_data)
                    await state_manager.broadcast("new_candle", candle_data)

                    closed_trade = tracker.update(candle_data)
                    if closed_trade:
                        await state_manager.broadcast("trade_closed", closed_trade)

                    if (
                        tracker.active_trade is None
                        and QuantitativeGuard.verify_execution_threshold(latest_candle)
                    ):
                        logger.info(
                            f"{Color.YELLOW}⚡ STRAT THRESHOLD HIT! RUNNING LLM RISK ANALYSIS...{Color.RESET}"
                        )

                        current_tape = generate_semantic_tape(latest_candle)
                        current_session = latest_candle.get("session", "Unknown")
                        current_strat = (
                            "Trend_Following"
                            if latest_candle.get("gold_1h_trend", 0.0) > 0
                            else "Breakout"
                        )
                        day_of_week = current_time.strftime("%A")

                        # Leverage context string builders from our refined memory packages
                        from src.api.state import (
                            get_rag_context_string,
                            get_graph_context_string,
                        )

                        rag_context = get_rag_context_string(
                            rag_collection, current_tape
                        )
                        graph_context = get_graph_context_string(
                            knowledge_graph, current_session, current_strat
                        )

                        market_state = f"Time: {current_time.strftime('%H:%M UTC')} ({day_of_week})\nSession: {current_session}\nStrategy: {current_strat}\nTape: {current_tape}"

                        decision_json = await evaluate_trade_setup_async(
                            client, market_state, rag_context, graph_context
                        )

                        if decision_json and decision_json.get("Decision") == "EXECUTE":
                            entry_price = candle_data["close"]
                            sl_type = decision_json.get("Selected_SL_Type", "Medium_SL")

                            sl_distance, tp_distance = (
                                (6.0, 12.0)
                                if sl_type == "Wide_SL"
                                else (
                                    (2.0, 4.0) if sl_type == "Tight_SL" else (4.0, 8.0)
                                )
                            )
                            direction = decision_json.get("Direction", "LONG")

                            sl = (
                                entry_price - sl_distance
                                if direction == "LONG"
                                else entry_price + sl_distance
                            )
                            tp = (
                                entry_price + tp_distance
                                if direction == "LONG"
                                else entry_price - tp_distance
                            )

                            tracker.open_trade(
                                timestamp=int(current_time.timestamp()),
                                direction=direction,
                                entry_price=entry_price,
                                sl=sl,
                                tp=tp,
                                confidence=decision_json.get("Confidence_Score", 0),
                                reasoning=decision_json.get("Primary_Reasoning", ""),
                                rag_ctx=rag_context,
                                graph_ctx=graph_context,
                            )

                            await state_manager.broadcast(
                                "trade_signal",
                                {
                                    "asset": "XAUUSD",
                                    "direction": direction,
                                    "entry": round(entry_price, 2),
                                    "sl": round(sl, 2),
                                    "tp": round(tp, 2),
                                    "risk": decision_json.get(
                                        "Recommended_Risk_Pct", 1.0
                                    ),
                                    "reasoning": f"[{sl_type}] {decision_json.get('Primary_Reasoning')}",
                                },
                            )

                await asyncio.sleep(60.0)
            except Exception as loop_ex:
                logger.error(f"Error inside forward testing loop iteration: {loop_ex}")
                await asyncio.sleep(10.0)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    loop_task = asyncio.create_task(run_live_forward_testing_loop())
    yield
    loop_task.cancel()


app = FastAPI(title="XAUUSD Omni-Agent Quant Core", lifespan=app_lifespan)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await state_manager.register(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await state_manager.unregister(websocket)


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    with open("templates/dashboard.html", "r") as f:
        return HTMLResponse(content=f.read(), status_code=200)
