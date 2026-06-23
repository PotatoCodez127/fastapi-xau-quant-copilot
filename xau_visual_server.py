from flask import Flask, render_template, request
from flask_socketio import SocketIO
import random

# Import the Limbs
from src.core.engine import build_macro_matrix, engineer_xau_features, fetch_live_candle
from src.memory.rag import setup_chroma_db, generate_semantic_tape, populate_memory
from src.memory.graph import generate_mock_trade_history, build_knowledge_graph
from src.api.judge import evaluate_trade_setup
from src.core.tracker import TradeTracker


class Color:
    GREEN, CYAN, YELLOW, RED, MAGENTA, RESET = (
        "\033[92m",
        "\033[96m",
        "\033[93m",
        "\033[91m",
        "\033[95m",
        "\033[0m",
    )


app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25)

market_history_cache = []


@socketio.on("connect")
def handle_connect():
    """Instantly pushes the historical cache to the newly connected browser."""
    global market_history_cache
    if market_history_cache:
        socketio.emit("init_history", market_history_cache, to=request.sid)


def get_rag_context_string(collection, current_tape):
    """Queries ChromaDB and formats the result as a string for the LLM."""
    results = collection.query(query_texts=[current_tape], n_results=2)
    if not results["documents"][0]:
        return "No historical matches found."

    context = ""
    for i in range(len(results["documents"][0])):
        context += (
            f"--- MATCH #{i+1} (Distance: {results['distances'][0][i]:.4f}) ---\n"
        )
        context += f"PAST TAPE: {results['documents'][0][i]}\n"
        context += f"ACTUAL OUTCOME: {results['metadatas'][0][i]['outcome']}\n\n"
    return context.strip()


def get_graph_context_string(G, current_session, current_strat):
    """Queries NetworkX and formats the result as a string for the LLM."""
    insights = []
    for node, attr in G.nodes(data=True):
        if (
            attr.get("type") == "parameter_combo"
            and attr.get("session") == current_session
            and attr.get("strat") == current_strat
        ):
            wins = (
                G[node].get("WIN", {}).get("weight", 0)
                if G.has_edge(node, "WIN")
                else 0
            )
            losses = (
                G[node].get("LOSS", {}).get("weight", 0)
                if G.has_edge(node, "LOSS")
                else 0
            )
            total = wins + losses
            if total == 0:
                continue

            win_rate = (wins / total) * 100
            if win_rate >= 60:
                insights.append(
                    f"🟢 SAFEPATH DETECTED: {node} ({win_rate:.1f}% Win Rate)"
                )
            elif win_rate <= 40:
                insights.append(f"🔴 DANGER NODE: {node} ({win_rate:.1f}% Win Rate)")
            else:
                insights.append(f"⚪ NEUTRAL PATH: {node} ({win_rate:.1f}% Win Rate)")

    if not insights:
        return "No historical graph data for this exact combination."
    return "\n".join(sorted(insights))


def backtest_simulation_loop():
    print(
        f"\n{Color.CYAN}===================================================={Color.RESET}"
    )
    print(f"{Color.CYAN}🚀 INITIALIZING XAUUSD OMNI-AGENT BACKTESTER{Color.RESET}")
    print(
        f"{Color.CYAN}===================================================={Color.RESET}\n"
    )

    # --- BOOTSTRAP ALL LIMBS ---
    matrix = build_macro_matrix(daysback=30)
    if matrix is None or matrix.empty:
        return
    df = engineer_xau_features(matrix)

    rag_collection = setup_chroma_db()
    populate_memory(df, rag_collection)

    trades_df = generate_mock_trade_history(num_trades=2000)
    knowledge_graph = build_knowledge_graph(trades_df)

    # INITIALIZE THE TRACKER
    tracker = TradeTracker()

    print(
        f"{Color.GREEN}✅ System Fully Armed. Waiting for UI connection...{Color.RESET}"
    )
    socketio.sleep(3.0)

    # --- PREPARE UI HISTORY ---
    history = []
    initial_load = df.iloc[:100]
    for idx, row in initial_load.iterrows():
        history.append(
            {
                "time": int(idx.timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )

    socketio.emit("init_history", history)

    # --- WALK-FORWARD REPLAY ---
    remaining_data = df.iloc[100:]

    for idx, row in remaining_data.iterrows():
        socketio.sleep(0.5)

        candle = {
            "time": int(idx.timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }

        socketio.emit("new_candle", candle)

        # --- PHASE 1: CHECK IF ACTIVE TRADE HIT SL OR TP ---
        closed_trade = tracker.update(candle)
        if closed_trade:
            socketio.emit("trade_closed", closed_trade)

        # --- PHASE 2: LOOK FOR NEW SETUPS (Only if no trade is active) ---
        trend_strength = abs(row.get("gold_1h_trend", 0))

        if (
            trend_strength > 4.5
            and random.random() < 0.20
            and tracker.active_trade is None
        ):

            print(
                f"\n{Color.YELLOW}⚡ MOMENTUM SETUP TRIGGERED AT {idx.strftime('%H:%M UTC')}{Color.RESET}"
            )

            current_tape = generate_semantic_tape(row)
            current_session = row.get("session", "Unknown")
            current_strat = (
                "Trend_Following" if row.get("gold_1h_trend", 0) > 0 else "Breakout"
            )

            # --- NEW: Extract Day of Week and pass it to the AI ---
            day_of_week = idx.strftime("%A")

            rag_context = get_rag_context_string(rag_collection, current_tape)
            graph_context = get_graph_context_string(
                knowledge_graph, current_session, current_strat
            )

            # Update the market state string to include the day
            market_state = f"Time: {idx.strftime('%H:%M UTC')} ({day_of_week})\nSession: {current_session}\nStrategy: {current_strat}\nTape: {current_tape}"

            decision_json = evaluate_trade_setup(
                market_state, rag_context, graph_context
            )

            if decision_json:
                decision = decision_json.get("Decision", "PASS")
                direction = decision_json.get("Direction", "LONG")
                reasoning = decision_json.get(
                    "Primary_Reasoning", "No reasoning provided."
                )
                confidence = decision_json.get("Confidence_Score", 0)
                sl_type = decision_json.get("Selected_SL_Type", "Medium_SL")

                ai_payload = {
                    "timestamp": int(idx.timestamp()),
                    "price": candle["close"],
                    "decision": decision,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "rag_distance": "Verified",
                }
                socketio.emit("ai_decision", ai_payload)

                if decision == "EXECUTE":
                    entry_price = candle_data["close"]
                    sl_type = decision_json.get("Selected_SL_Type", "Medium_SL")

                    # 🎯 BROKER CALIBRATED PIP DISTANCES (1 Pip = $0.10)
                    if sl_type == "Wide_SL":
                        sl_distance, tp_distance = 6.00, 12.00
                    elif sl_type == "Tight_SL":
                        sl_distance, tp_distance = 2.00, 4.00
                    else:
                        sl_distance, tp_distance = 4.00, 8.00

                    if direction == "LONG":
                        sl = entry_price - sl_distance
                        tp = entry_price + tp_distance
                    else:
                        sl = entry_price + sl_distance
                        tp = entry_price - tp_distance

                    # OPEN THE LIVE PAPER TRADE IN THE ACCOUNTING LEDGER
                    tracker.open_trade(
                        timestamp=int(current_time.timestamp()),
                        direction=direction,
                        entry_price=entry_price,
                        sl=sl,
                        tp=tp,
                        confidence=decision_json.get("Confidence_Score", 0),
                        reasoning=reasoning,
                        rag_ctx=rag_context,
                        graph_ctx=graph_context,
                    )

                    signal_payload = {
                        "asset": "XAUUSD",
                        "direction": direction,
                        "entry": round(entry_price, 2),
                        "sl": round(sl, 2),
                        "tp": round(tp, 2),
                        "risk": decision_json.get("Recommended_Risk_Pct", 1.0),
                        "reasoning": f"[{sl_type}] {reasoning}",
                    }
                    socketio.emit("trade_signal", signal_payload)

    print(f"\n{Color.CYAN}🛑 Historical Data Replay Complete.{Color.RESET}")
    print(f"{Color.YELLOW}📊 Generating Final Performance Tearsheet...{Color.RESET}")

    # Fetch the final metrics and push them to the UI
    final_metrics = tracker.generate_tearsheet()
    socketio.emit("backtest_complete", final_metrics)

    print(f"{Color.GREEN}✅ Tearsheet published. Run concluded.{Color.RESET}")


def live_execution_loop():
    print(
        f"\n{Color.CYAN}===================================================={Color.RESET}"
    )
    print(
        f"{Color.CYAN}🟢 INITIALIZING XAUUSD LIVE FORWARD-TESTING ENGINE{Color.RESET}"
    )
    print(
        f"{Color.CYAN}===================================================={Color.RESET}\n"
    )

    # --- BOOTSTRAP HISTORY (For Charting Context) ---
    print(f"{Color.YELLOW}Loading historical context...{Color.RESET}")
    matrix = build_macro_matrix(daysback=7)
    if matrix is None or matrix.empty:
        return
    df = engineer_xau_features(matrix)

    rag_collection = setup_chroma_db()
    populate_memory(df, rag_collection)

    trades_df = generate_mock_trade_history(num_trades=2000)
    knowledge_graph = build_knowledge_graph(trades_df)
    tracker = TradeTracker(
        ledger_path="data/live_omni_ledger.csv"
    )  # Separate ledger for live trades

    socketio.sleep(3.0)

    # --- FIX: Save history to the global cache ---
    global market_history_cache
    market_history_cache = []
    for idx, row in df.iterrows():
        market_history_cache.append(
            {
                "time": int(idx.timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )

    socketio.emit("init_history", market_history_cache)

    print(
        f"{Color.GREEN}✅ System Fully Armed. Connecting to Live API Feed...{Color.RESET}"
    )

    # --- 📡 THE LIVE POLLING LOOP ---
    last_processed_time = df.index[-1]  # The timestamp of the last known candle

    while True:
        # 1. Ask the Massive Engine for the current live state
        latest_candle = fetch_live_candle()

        if latest_candle is None:
            print(
                f"{Color.RED}⚠️ TwelveData API returned no data. Retrying in 60s...{Color.RESET}"
            )
            socketio.sleep(60)
            continue

        current_time = latest_candle.name

        print(
            f"📡 [HEARTBEAT] Live Time: {current_time} | Waiting for > {last_processed_time}"
        )

        # 2. Check if a NEW candle has closed
        if current_time > last_processed_time:
            print(f"{Color.GREEN}✨ NEW CANDLE CLOSED! Pushing to UI...{Color.RESET}")
            last_processed_time = current_time

            candle_data = {
                "time": int(current_time.timestamp()),
                "open": float(latest_candle["open"]),
                "high": float(latest_candle["high"]),
                "low": float(latest_candle["low"]),
                "close": float(latest_candle["close"]),
            }
            market_history_cache.append(candle_data)

            # Push the live tick to the frontend chart
            socketio.emit("new_candle", candle_data)

            # --- PHASE 1: MANAGE ACTIVE LIVE TRADE ---
            closed_trade = tracker.update(candle_data)
            if closed_trade:
                socketio.emit("trade_closed", closed_trade)

            # --- PHASE 2: LOOK FOR NEW LIVE SETUPS ---
            trend_strength = abs(latest_candle.get("gold_1h_trend", 0))

            if trend_strength > 4.5 and tracker.active_trade is None:
                print(
                    f"\n{Color.YELLOW}⚡ LIVE MOMENTUM TRIGGER DETECTED! EVALUATING...{Color.RESET}"
                )

                current_tape = generate_semantic_tape(latest_candle)
                current_session = latest_candle.get("session", "Unknown")
                current_strat = (
                    "Trend_Following"
                    if latest_candle.get("gold_1h_trend", 0) > 0
                    else "Breakout"
                )
                day_of_week = current_time.strftime("%A")

                rag_context = get_rag_context_string(rag_collection, current_tape)
                graph_context = get_graph_context_string(
                    knowledge_graph, current_session, current_strat
                )
                market_state = f"Time: {current_time.strftime('%H:%M UTC')} ({day_of_week})\nSession: {current_session}\nStrategy: {current_strat}\nTape: {current_tape}"

                decision_json = evaluate_trade_setup(
                    market_state, rag_context, graph_context
                )

                if decision_json:
                    decision = decision_json.get("Decision", "PASS")
                    direction = decision_json.get("Direction", "LONG")
                    reasoning = decision_json.get(
                        "Primary_Reasoning", "No reasoning provided."
                    )

                    ai_payload = {
                        "timestamp": int(current_time.timestamp()),
                        "price": candle_data["close"],
                        "decision": decision,
                        "confidence": decision_json.get("Confidence_Score", 0),
                        "reasoning": reasoning,
                        "rag_distance": "Verified",
                    }
                    socketio.emit("ai_decision", ai_payload)

                    if decision == "EXECUTE":
                        entry_price = candle_data["close"]
                        sl_type = decision_json.get("Selected_SL_Type", "Medium_SL")

                        # 🎯 BROKER CALIBRATED PIP DISTANCES (1 Pip = $0.10)
                        if sl_type == "Wide_SL":
                            sl_distance, tp_distance = 6.00, 12.00
                        elif sl_type == "Tight_SL":
                            sl_distance, tp_distance = 2.00, 4.00
                        else:
                            sl_distance, tp_distance = 4.00, 8.00

                        if direction == "LONG":
                            sl = entry_price - sl_distance
                            tp = entry_price + tp_distance
                        else:
                            sl = entry_price + sl_distance
                            tp = entry_price - tp_distance

                        # OPEN THE LIVE PAPER TRADE IN THE ACCOUNTING LEDGER
                        tracker.open_trade(
                            timestamp=int(current_time.timestamp()),
                            direction=direction,
                            entry_price=entry_price,
                            sl=sl,
                            tp=tp,
                            confidence=decision_json.get("Confidence_Score", 0),
                            reasoning=reasoning,
                            rag_ctx=rag_context,
                            graph_ctx=graph_context,
                        )

                        signal_payload = {
                            "asset": "XAUUSD",
                            "direction": direction,
                            "entry": round(entry_price, 2),
                            "sl": round(sl, 2),
                            "tp": round(tp, 2),
                            "risk": decision_json.get("Recommended_Risk_Pct", 1.0),
                            "reasoning": f"[{sl_type}] {reasoning}",
                        }
                        socketio.emit("trade_signal", signal_payload)

        # Wait 10 seconds before polling the API again to avoid rate-limits
        socketio.sleep(60)


@app.route("/")
def index():
    return render_template("dashboard.html")


if __name__ == "__main__":
    # socketio.start_background_task(backtest_simulation_loop)
    socketio.start_background_task(live_execution_loop)
    socketio.run(app, debug=True, use_reloader=False)
