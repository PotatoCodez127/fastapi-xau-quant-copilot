import pandas as pd
import re
import os

class Color:
    CYAN, RED, YELLOW, GREEN, RESET = '\033[96m', '\033[91m', '\033[93m', '\033[92m', '\033[0m'

def run_diagnostics(ledger_path="data/omni_ledger.csv"):
    if not os.path.exists(ledger_path):
        print(f"{Color.RED}❌ Ledger not found at {ledger_path}{Color.RESET}")
        return

    print(f"{Color.CYAN}🔍 ANALYZING OMNI-LEDGER FOR SYSTEMIC FAILURES...{Color.RESET}\n")
    
    # Load the ledger
    df = pd.read_csv(ledger_path)
    
    total_trades = len(df)
    losers = df[df['Result'] == 'LOSS']
    total_losses = len(losers)
    
    if total_losses == 0:
        print(f"{Color.GREEN}No losses to analyze!{Color.RESET}")
        return

    # 1. Directional Bias Failure
    long_losses = len(losers[losers['Direction'] == 'LONG'])
    short_losses = len(losers[losers['Direction'] == 'SHORT'])
    
    print(f"{Color.YELLOW}--- 📉 DIRECTIONAL BLEED ---{Color.RESET}")
    print(f"Long Trades: {long_losses} Losses ({(long_losses/total_losses)*100:.1f}%)")
    print(f"Short Trades: {short_losses} Losses ({(short_losses/total_losses)*100:.1f}%)\n")

    # 2. Extract Topological Nodes (Session | Strategy | SL)
    # The graph context looks like: "🟢 SAFEPATH DETECTED: London_Open | Mean_Reversion | Wide_SL"
    print(f"{Color.YELLOW}--- 🕸️ TOPOLOGICAL NODE FAILURES ---{Color.RESET}")
    
    node_failures = {}
    for idx, row in losers.iterrows():
        graph_text = str(row['Graph_Context'])
        # Regex to find the node pattern: Session | Strategy | SL
        matches = re.findall(r'([A-Za-z_]+ \| [A-Za-z_]+ \| [A-Za-z_]+)', graph_text)
        
        for match in set(matches): # Use set to avoid double counting if listed multiple times
            if match in node_failures:
                node_failures[match] += 1
            else:
                node_failures[match] = 1
                
    # Sort by the most frequent failures
    sorted_nodes = sorted(node_failures.items(), key=lambda x: x[1], reverse=True)
    
    for node, count in sorted_nodes[:5]: # Top 5 worst nodes
        print(f"Node '{node}': {count} Losses ({(count/total_losses)*100:.1f}% of all losses)")

    # 3. AI Reasoning Audit
    print(f"\n{Color.YELLOW}--- 🧠 AI REASONING AUDIT (Top 3 Worst Trades by Pips) ---{Color.RESET}")
    worst_trades = losers.sort_values(by='Pips', ascending=True).head(3)
    
    for idx, row in worst_trades.iterrows():
        print(f"\n[{row['Entry_Time']}] {row['Direction']} (Lost {row['Pips']} Pips)")
        print(f"AI Logic: {row['AI_Reasoning']}")

if __name__ == "__main__":
    run_diagnostics()