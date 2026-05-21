import pandas as pd
import numpy as np
import re
import os

class Color:
    CYAN, RED, YELLOW, GREEN, MAGENTA, RESET = '\033[96m', '\033[91m', '\033[93m', '\033[92m', '\033[95m', '\033[0m'

def extract_node_info(graph_text):
    """Safely extracts the Session | Strategy | SL_Type from the graph context."""
    matches = re.findall(r'([A-Za-z_]+ \| [A-Za-z_]+ \| [A-Za-z_]+)', str(graph_text))
    if matches:
        return matches[0]
    return "Unknown_Session | Unknown_Strategy | Unknown_SL"

def run_deep_diagnostics(ledger_path="data/omni_ledger.csv"):
    if not os.path.exists(ledger_path):
        print(f"{Color.RED}❌ Ledger not found at {ledger_path}{Color.RESET}")
        return

    print(f"{Color.CYAN}🔍 INITIATING DEEP QUANTITATIVE AUDIT...{Color.RESET}\n")
    
    df = pd.read_csv(ledger_path)
    if len(df) == 0:
        print("Ledger is empty.")
        return
        
    # Standardize column names
    loss_col = 'Pips' if 'Pips' in df.columns else 'PnL'
    df['Pips'] = df[loss_col]
    
    # Feature Engineering for Analytics
    df['Entry_Time'] = pd.to_datetime(df['Entry_Time'])
    df['Day_of_Week'] = df['Entry_Time'].dt.day_name()
    
    # Extract topology directly from the LLM's graph context
    df['Node'] = df['Graph_Context'].apply(extract_node_info)
    
    # Safely split the node into 3 parts, handling errors if the format is weird
    try:
        df[['Session', 'Strategy', 'SL_Type']] = df['Node'].str.split(' \| ', n=2, expand=True)
    except:
        df['Session'] = "Unknown"
        df['Strategy'] = "Unknown"
        df['SL_Type'] = "Unknown"

    # --- 1. OVERALL METRICS ---
    total_trades = len(df)
    total_pnl = df['Pips'].sum()
    win_rate = (len(df[df['Result'] == 'WIN']) / total_trades) * 100
    
    print(f"{Color.MAGENTA}=== OVERALL SYSTEM METRICS ==={Color.RESET}")
    print(f"Total Trades: {total_trades}")
    print(f"Net PnL: {total_pnl:.1f} Pips")
    print(f"Win Rate: {win_rate:.1f}%\n")

    # --- HELPER FUNCTION FOR CATEGORICAL ANALYSIS ---
    def print_group_stats(group_name, column):
        print(f"{Color.YELLOW}--- PERFORMANCE BY {group_name.upper()} ---{Color.RESET}")
        
        # Calculate EV, Win Rate, and Net PnL per category
        stats = df.groupby(column).agg(
            Trades=('Result', 'count'),
            Win_Rate=('Result', lambda x: (x == 'WIN').mean() * 100),
            Net_Pips=('Pips', 'sum')
        ).sort_values(by='Net_Pips', ascending=False)
        
        for index, row in stats.iterrows():
            pnl_color = Color.GREEN if row['Net_Pips'] > 0 else Color.RED
            # Format the output cleanly
            print(f"{str(index):.<22} Trades: {row['Trades']:<4} | Win Rate: {row['Win_Rate']:>5.1f}% | Net PnL: {pnl_color}{row['Net_Pips']:>7.1f}{Color.RESET}")
        print()

    # --- 2. CATEGORICAL BREAKDOWNS ---
    print_group_stats("Day of Week", "Day_of_Week")
    print_group_stats("Trading Session", "Session")
    print_group_stats("Strategy Type", "Strategy")
    print_group_stats("Trade Direction", "Direction")

    # --- 3. DRAWDOWN & STREAK ANALYSIS ---
    df['Loss_Int'] = (df['Result'] == 'LOSS').astype(int)
    max_loss_streak = (df['Loss_Int'].groupby((df['Loss_Int'] != df['Loss_Int'].shift()).cumsum()).cumsum()).max()
    
    cumulative_pnl = df['Pips'].cumsum()
    running_max = np.maximum.accumulate(cumulative_pnl)
    drawdown = running_max - cumulative_pnl
    max_dd = drawdown.max()

    print(f"{Color.YELLOW}--- RISK & DRAWDOWN ---{Color.RESET}")
    print(f"Max Consecutive Losses: {int(max_loss_streak)}")
    print(f"Maximum PnL Drawdown:   {max_dd:.1f} Pips\n")

    # --- 4. NODE ANALYSIS (Alpha vs Toxic) ---
    print(f"{Color.YELLOW}--- 🕸️ TOPOLOGICAL NODE EXTREMES ---{Color.RESET}")
    node_stats = df.groupby('Node').agg(Net_Pips=('Pips', 'sum'), Trades=('Result', 'count')).sort_values(by='Net_Pips')
    
    print(f"{Color.GREEN}🏆 TOP 3 ALPHA NODES (Most Profitable){Color.RESET}")
    for node, row in node_stats.sort_values(by='Net_Pips', ascending=False).head(3).iterrows():
        if row['Net_Pips'] > 0:
            print(f"  + {node}: {row['Trades']} Trades | {row['Net_Pips']} Pips")
            
    print(f"\n{Color.RED}☠️ TOP 3 TOXIC NODES (Largest Bleed){Color.RESET}")
    for node, row in node_stats.head(3).iterrows():
        if row['Net_Pips'] < 0:
            print(f"  - {node}: {row['Trades']} Trades | {row['Net_Pips']} Pips")

if __name__ == "__main__":
    run_deep_diagnostics()