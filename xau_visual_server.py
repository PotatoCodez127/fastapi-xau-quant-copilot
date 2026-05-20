from flask import Flask, render_template
from flask_socketio import SocketIO
import random
import os

# Import the Limbs
from xau_massive_engine import build_macro_matrix, engineer_xau_features
from xau_rag_memory import setup_chroma_db, generate_semantic_tape, populate_memory
from xau_graph_evaluator import generate_mock_trade_history, build_knowledge_graph
from xau_ai_judge import evaluate_trade_setup
from xau_trade_tracker import TradeTracker

class Color:
    GREEN, CYAN, YELLOW, RED, MAGENTA, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[95m', '\033[0m'

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25)

def backtest_simulation_loop():
    print(f"\n{Color.CYAN}===================================================={Color.RESET}")
    print(f"{Color.CYAN}🚀 INITIALIZING XAUUSD OMNI-AGENT BACKTESTER{Color.RESET}")
    print(f"{Color.CYAN}===================================================={Color.RESET}\n")
    
    # --- BOOTSTRAP ALL LIMBS ---
    matrix = build_macro_matrix(daysback=7)
    if matrix is None or matrix.empty: return
    df = engineer_xau_features(matrix)
    
    rag_collection = setup_chroma_db()
    populate_memory(df, rag_collection)
    
    trades_df = generate_mock_trade_history(num_trades=2000)
    knowledge_graph = build_knowledge_graph(trades_df)
    
    # Initialize the new Trade Tracker
    tracker = TradeTracker()
    
    print(f"{Color.GREEN}✅ System Fully Armed. Waiting for UI connection...{Color.RESET}")
    socketio.sleep(3.0) 
    
    # --- PREPARE UI HISTORY ---
    history = []
    initial_load = df.iloc[:100]
    for idx, row in initial_load.iterrows():
        history.append({
            'time': int(idx.timestamp()),
            'open': float(row['open']), 'high': float(row['high']),
            'low': float(row['low']), 'close': float(row['close'])
        })

    socketio.emit('init_history', history)
    
    # --- WALK-FORWARD REPLAY ---
    remaining_data = df.iloc[100:]
    
    for idx, row in remaining_data.iterrows():
        socketio.sleep(0.5) 
        
        candle = {
            'time': int(idx.timestamp()),
            'open': float(row['open']), 'high': float(row['high']),
            'low': float(row['low']), 'close': float(row['close'])
        }
        
        socketio.emit('new_candle', candle)
        
        # --- PHASE 1: RESOLVE OPEN TRADES ---
        closed_trade = tracker.update(candle)
        if closed_trade:
            # Tell the UI the trade closed (we will build the UI listener later)
            socketio.emit('trade_closed', closed_trade)
        
        # --- PHASE 2: LOOK FOR NEW SETUPS ---
        trend_strength = abs(row.get('gold_1h_trend', 0))
        
        # Only allow the AI to evaluate if we are NOT currently in a trade
        if trend_strength > 4.5 and random.random() < 0.20 and tracker.active_trade is None: 
            
            print(f"\n{Color.YELLOW}⚡ MOMENTUM SETUP TRIGGERED AT {idx.strftime('%H:%M UTC')}{Color.RESET}")
            
            current_tape = generate_semantic_tape(row)
            current_session = row.get('session', 'Unknown')
            current_strat = "Trend_Following" if row.get('gold_1h_trend', 0) > 0 else "Breakout"
            
            rag_context = get_rag_context_string(rag_collection, current_tape)
            graph_context = get_graph_context_string(knowledge_graph, current_session, current_strat)
            market_state = f"Time: {idx.strftime('%H:%M UTC')}\nSession: {current_session}\nStrategy: {current_strat}\nTape: {current_tape}"
            
            decision_json = evaluate_trade_setup(market_state, rag_context, graph_context)
            
            if decision_json:
                decision = decision_json.get("Decision", "PASS")
                direction = decision_json.get("Direction", "LONG")
                reasoning = decision_json.get("Primary_Reasoning", "No reasoning provided.")
                confidence = decision_json.get("Confidence_Score", 0)
                
                # Update UI Telemetry
                ai_payload = {
                    "timestamp": int(idx.timestamp()), "price": candle['close'],
                    "decision": decision, "confidence": confidence,
                    "reasoning": reasoning, "rag_distance": "Verified"
                }
                socketio.emit('ai_decision', ai_payload)
                
                if decision == "EXECUTE":
                    entry_price = candle['close']
                    sl_distance, tp_distance = 3.00, 6.00
                    
                    sl = entry_price - sl_distance if direction == "LONG" else entry_price + sl_distance
                    tp = entry_price + tp_distance if direction == "LONG" else entry_price - tp_distance
                    
                    # LOG TO LEDGER
                    tracker.open_trade(
                        timestamp=int(idx.timestamp()), direction=direction, 
                        entry_price=entry_price, sl=sl, tp=tp, 
                        confidence=confidence, reasoning=reasoning, 
                        rag_ctx=rag_context, graph_ctx=graph_context
                    )
                    
                    signal_payload = {
                        "asset": "XAUUSD", "direction": direction,
                        "entry": round(entry_price, 2), "sl": round(sl, 2), "tp": round(tp, 2),
                        "risk": decision_json.get("Recommended_Risk_Pct", 1.0),
                        "reasoning": reasoning
                    }
                    socketio.emit('trade_signal', signal_payload)

def get_rag_context_string(collection, current_tape):
    """Queries ChromaDB and formats the result as a string for the LLM."""
    results = collection.query(query_texts=[current_tape], n_results=2)
    if not results['documents'][0]: return "No historical matches found."
    
    context = ""
    for i in range(len(results['documents'][0])):
        context += f"--- MATCH #{i+1} (Distance: {results['distances'][0][i]:.4f}) ---\n"
        context += f"PAST TAPE: {results['documents'][0][i]}\n"
        context += f"ACTUAL OUTCOME: {results['metadatas'][0][i]['outcome']}\n\n"
    return context.strip()

def get_graph_context_string(G, current_session, current_strat):
    """Queries NetworkX and formats the result as a string for the LLM."""
    insights = []
    for node, attr in G.nodes(data=True):
        if attr.get('type') == 'parameter_combo' and attr.get('session') == current_session and attr.get('strat') == current_strat:
            wins = G[node].get("WIN", {}).get("weight", 0) if G.has_edge(node, "WIN") else 0
            losses = G[node].get("LOSS", {}).get("weight", 0) if G.has_edge(node, "LOSS") else 0
            total = wins + losses
            if total == 0: continue
            
            win_rate = (wins / total) * 100
            if win_rate >= 60: insights.append(f"🟢 SAFEPATH DETECTED: {node} ({win_rate:.1f}% Win Rate)")
            elif win_rate <= 40: insights.append(f"🔴 DANGER NODE: {node} ({win_rate:.1f}% Win Rate)")
            else: insights.append(f"⚪ NEUTRAL PATH: {node} ({win_rate:.1f}% Win Rate)")
            
    if not insights: return "No historical graph data for this exact combination."
    return "\n".join(sorted(insights))

def backtest_simulation_loop():
    print(f"\n{Color.CYAN}===================================================={Color.RESET}")
    print(f"{Color.CYAN}🚀 INITIALIZING XAUUSD OMNI-AGENT BACKTESTER{Color.RESET}")
    print(f"{Color.CYAN}===================================================={Color.RESET}\n")
    
    # --- BOOTSTRAP ALL LIMBS ---
    print(f"{Color.YELLOW}Bootstrapping Limbs 1-3 (Data, Vector DB, Graph DB)...{Color.RESET}")
    
    # 1. Data Engine
    matrix = build_macro_matrix(daysback=7)
    if matrix is None or matrix.empty: return
    df = engineer_xau_features(matrix)
    
    # 2. Vector Historian
    rag_collection = setup_chroma_db()
    populate_memory(df, rag_collection)
    
    # 3. Topological Graph
    trades_df = generate_mock_trade_history(num_trades=2000)
    knowledge_graph = build_knowledge_graph(trades_df)
    
    print(f"{Color.GREEN}✅ System Fully Armed. Waiting for UI connection...{Color.RESET}")
    socketio.sleep(3.0) 
    
    # --- PREPARE UI HISTORY ---
    history = []
    initial_load = df.iloc[:100]
    for idx, row in initial_load.iterrows():
        history.append({
            'time': int(idx.timestamp()),
            'open': float(row['open']), 'high': float(row['high']),
            'low': float(row['low']), 'close': float(row['close'])
        })

    print(f"{Color.GREEN}📤 Pushing initial history batch to UI...{Color.RESET}")
    socketio.emit('init_history', history)
    
    # --- WALK-FORWARD REPLAY ---
    remaining_data = df.iloc[100:]
    
    for idx, row in remaining_data.iterrows():
        socketio.sleep(0.5) # 2 candles per second
        
        candle = {
            'time': int(idx.timestamp()),
            'open': float(row['open']), 'high': float(row['high']),
            'low': float(row['low']), 'close': float(row['close'])
        }
        
        socketio.emit('new_candle', candle)
        
        # Trigger Condition: Let's simulate a setup triggering when 1H trend is very strong
        trend_strength = abs(row.get('gold_1h_trend', 0))
        if trend_strength > 4.5 and random.random() < 0.20: # Limit triggers so we don't spam the API
            
            print(f"\n{Color.YELLOW}⚡ MOMENTUM SETUP TRIGGERED AT {idx.strftime('%H:%M UTC')}{Color.RESET}")
            print(f"{Color.MAGENTA}⏸️ Pausing chart simulation. Consulting Omni-Agent Brain...{Color.RESET}")
            
            # 1. Generate State
            current_tape = generate_semantic_tape(row)
            current_session = row.get('session', 'Unknown')
            current_strat = "Trend_Following" if row.get('gold_1h_trend', 0) > 0 else "Breakout"
            
            # 2. Fetch Contexts
            rag_context = get_rag_context_string(rag_collection, current_tape)
            graph_context = get_graph_context_string(knowledge_graph, current_session, current_strat)
            market_state = f"Time: {idx.strftime('%H:%M UTC')}\nSession: {current_session}\nStrategy: {current_strat}\nTape: {current_tape}"
            
            # 3. Request Verdict from LLM (This will block execution while it thinks)
            decision_json = evaluate_trade_setup(market_state, rag_context, graph_context)
            
            if decision_json:
                print(f"{Color.GREEN}✅ Verdict Received. Resuming playback.{Color.RESET}")
                
                decision = decision_json.get("Decision", "PASS")
                direction = decision_json.get("Direction", "LONG")
                
                ai_payload = {
                    "timestamp": int(idx.timestamp()),
                    "price": candle['close'],
                    "decision": decision,
                    "confidence": decision_json.get("Confidence_Score", 0),
                    "reasoning": decision_json.get("Primary_Reasoning", "No reasoning provided."),
                    "rag_distance": "Verified"
                }
                socketio.emit('ai_decision', ai_payload)
                
                # --- NEW: LIVE SIGNAL GENERATION ---
                if decision == "EXECUTE":
                    entry_price = candle['close']
                    
                    # Define standard XAUUSD distances (e.g., $3.00 SL, $6.00 TP for a 1:2 R:R)
                    sl_distance = 3.00
                    tp_distance = 6.00
                    
                    if direction == "LONG":
                        sl = entry_price - sl_distance
                        tp = entry_price + tp_distance
                    else:
                        sl = entry_price + sl_distance
                        tp = entry_price - tp_distance
                        
                    signal_payload = {
                        "asset": "XAUUSD",
                        "direction": direction,
                        "entry": round(entry_price, 2),
                        "sl": round(sl, 2),
                        "tp": round(tp, 2),
                        "risk": decision_json.get("Recommended_Risk_Pct", 1.0),
                        "reasoning": decision_json.get("Primary_Reasoning", "")
                    }
                    
                    print(f"{Color.MAGENTA}🔔 PUSHING LIVE SIGNAL TO UI: {direction} @ {entry_price}{Color.RESET}")
                    socketio.emit('trade_signal', signal_payload)
                    
            else:
                print(f"{Color.RED}⚠️ AI failed to respond properly. Skipping setup.{Color.RESET}")

    print(f"\n{Color.CYAN}🛑 Backtest Complete. Reached the end of historical data.{Color.RESET}")

@app.route('/')
def index(): return render_template('dashboard.html')

if __name__ == '__main__':
    socketio.start_background_task(backtest_simulation_loop)
    socketio.run(app, debug=True, use_reloader=False)