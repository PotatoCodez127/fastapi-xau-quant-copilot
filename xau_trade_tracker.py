import csv
import os
from datetime import datetime

class Color:
    GREEN, RED, YELLOW, RESET = '\033[92m', '\033[91m', '\033[93m', '\033[0m'

class TradeTracker:
    def __init__(self, ledger_path="data/omni_ledger.csv"):
        self.ledger_path = ledger_path
        self.active_trade = None 
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
        
        # Create CSV with headers if it doesn't exist
        if not os.path.exists(ledger_path):
            with open(ledger_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Entry_Time", "Exit_Time", "Direction", "Entry_Price", 
                    "Exit_Price", "SL", "TP", "PnL", "Result", 
                    "Confidence", "AI_Reasoning", "RAG_Context", "Graph_Context"
                ])

    def open_trade(self, timestamp, direction, entry_price, sl, tp, confidence, reasoning, rag_ctx, graph_ctx):
        """Registers a new trade in the system."""
        if self.active_trade is not None:
            return False # Enforce one trade at a time
            
        self.active_trade = {
            "entry_time": timestamp,
            "direction": direction,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
            "confidence": confidence,
            "reasoning": reasoning,
            "rag_ctx": rag_ctx,
            "graph_ctx": graph_ctx
        }
        return True

    def update(self, candle):
        """Checks the current candle against the active trade's SL/TP levels."""
        if not self.active_trade:
            return None 
            
        t = self.active_trade
        high = candle['high']
        low = candle['low']
        close_time = candle['time']
        
        exit_price = None
        result = None
        
        if t['direction'] == 'LONG':
            # Conservative backtesting: Assume Stop Loss is hit first if both are breached in the same candle
            if low <= t['sl']:
                exit_price = t['sl']
                result = "LOSS"
            elif high >= t['tp']:
                exit_price = t['tp']
                result = "WIN"
        else: # SHORT
            if high >= t['sl']:
                exit_price = t['sl']
                result = "LOSS"
            elif low <= t['tp']:
                exit_price = t['tp']
                result = "WIN"
                
        if result:
            return self._close_trade(exit_price, result, close_time)
        
        return None

    def _close_trade(self, exit_price, result, exit_time):
        """Calculates PnL, writes the audit to the ledger, and clears the active trade."""
        t = self.active_trade
        
        # Calculate PnL (Points)
        if t['direction'] == 'LONG':
            pnl = exit_price - t['entry_price']
        else:
            pnl = t['entry_price'] - exit_price
            
        # Clean formatting for the CSV
        entry_str = datetime.utcfromtimestamp(t['entry_time']).strftime('%Y-%m-%d %H:%M:%S')
        exit_str = datetime.utcfromtimestamp(exit_time).strftime('%Y-%m-%d %H:%M:%S')
        flat_rag = t['rag_ctx'].replace('\n', ' | ')
        flat_graph = t['graph_ctx'].replace('\n', ' | ')
        
        row = [
            entry_str, exit_str, t['direction'], round(t['entry_price'], 2), 
            round(exit_price, 2), round(t['sl'], 2), round(t['tp'], 2), 
            round(pnl, 2), result, t['confidence'], t['reasoning'], 
            flat_rag, flat_graph
        ]
        
        with open(self.ledger_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row)
            
        color = Color.GREEN if result == "WIN" else Color.RED
        print(f"\n{color}💰 TRADE CLOSED: {result} | PnL: {pnl:.2f} pts | Ledger Updated.{Color.RESET}")
        
        self.active_trade = None
        
        # Return the full trade details for the live UI
        return {
            "entry_time": entry_str,
            "exit_time": exit_str,
            "direction": t['direction'],
            "entry": round(t['entry_price'], 2),
            "exit": round(exit_price, 2),
            "pnl": round(pnl, 2),
            "result": result,
            "reasoning": t['reasoning']
        }