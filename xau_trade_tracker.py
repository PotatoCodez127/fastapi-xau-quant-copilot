import csv
import os
from datetime import datetime

class Color:
    GREEN, RED, YELLOW, RESET = '\033[92m', '\033[91m', '\033[93m', '\033[0m'

class TradeTracker:
    def __init__(self, ledger_path="data/omni_ledger.csv"):
        self.ledger_path = ledger_path
        self.active_trade = None 
        self.closed_trades = [] # Keep a memory of the run for the tearsheet
        
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
        
        # We now explicitly track "Pips" instead of ambiguous "Pts"
        if not os.path.exists(ledger_path):
            with open(ledger_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Entry_Time", "Exit_Time", "Direction", "Entry_Price", 
                    "Exit_Price", "SL", "TP", "Pips", "Result", 
                    "Confidence", "AI_Reasoning", "RAG_Context", "Graph_Context"
                ])

    def open_trade(self, timestamp, direction, entry_price, sl, tp, confidence, reasoning, rag_ctx, graph_ctx):
        if self.active_trade is not None: return False 
            
        self.active_trade = {
            "entry_time": timestamp, "direction": direction,
            "entry_price": entry_price, "sl": sl, "tp": tp,
            "confidence": confidence, "reasoning": reasoning,
            "rag_ctx": rag_ctx, "graph_ctx": graph_ctx
        }
        return True

    def update(self, candle):
        if not self.active_trade: return None 
            
        t = self.active_trade
        high, low, close_time = candle['high'], candle['low'], candle['time']
        exit_price, result = None, None
        
        if t['direction'] == 'LONG':
            if low <= t['sl']: exit_price, result = t['sl'], "LOSS"
            elif high >= t['tp']: exit_price, result = t['tp'], "WIN"
        else: # SHORT
            if high >= t['sl']: exit_price, result = t['sl'], "LOSS"
            elif low <= t['tp']: exit_price, result = t['tp'], "WIN"
                
        if result: return self._close_trade(exit_price, result, close_time)
        return None

    def _close_trade(self, exit_price, result, exit_time):
        t = self.active_trade
        
        # Calculate raw price move
        price_move = (exit_price - t['entry_price']) if t['direction'] == 'LONG' else (t['entry_price'] - exit_price)
        
        # XAUUSD Standardization: $1.00 move = 100 pips
        pips = round(price_move * 100, 1)
            
        entry_str = datetime.utcfromtimestamp(t['entry_time']).strftime('%Y-%m-%d %H:%M:%S')
        exit_str = datetime.utcfromtimestamp(exit_time).strftime('%Y-%m-%d %H:%M:%S')
        flat_rag, flat_graph = t['rag_ctx'].replace('\n', ' | '), t['graph_ctx'].replace('\n', ' | ')
        
        row = [
            entry_str, exit_str, t['direction'], round(t['entry_price'], 2), 
            round(exit_price, 2), round(t['sl'], 2), round(t['tp'], 2), 
            pips, result, t['confidence'], t['reasoning'], flat_rag, flat_graph
        ]
        
        with open(self.ledger_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row)
            
        color = Color.GREEN if result == "WIN" else Color.RED
        print(f"\n{color}💰 TRADE CLOSED: {result} | PnL: {pips} Pips | Ledger Updated.{Color.RESET}")
        
        ui_payload = {
            "entry_time": entry_str, "exit_time": exit_str, "direction": t['direction'],
            "entry": float(t['entry_price']), "exit": float(exit_price),
            "pnl": pips, "result": result, "reasoning": t['reasoning']
        }
        
        self.closed_trades.append(ui_payload)
        self.active_trade = None
        
        return ui_payload

    def generate_tearsheet(self):
        """Calculates the overall performance metrics for the run."""
        total_trades = len(self.closed_trades)
        if total_trades == 0:
            return {"total_trades": 0, "win_rate": 0, "net_pips": 0, "winners": 0, "losers": 0}
            
        winners = [t for t in self.closed_trades if t['result'] == "WIN"]
        losers = [t for t in self.closed_trades if t['result'] == "LOSS"]
        
        net_pips = sum([t['pnl'] for t in self.closed_trades])
        win_rate = (len(winners) / total_trades) * 100
        
        return {
            "total_trades": total_trades,
            "win_rate": round(win_rate, 2),
            "net_pips": round(net_pips, 1),
            "winners": len(winners),
            "losers": len(losers)
        }