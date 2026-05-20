import networkx as nx
import pandas as pd
import random

class Color:
    GREEN, CYAN, YELLOW, RED, MAGENTA, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[95m', '\033[0m'

def generate_mock_trade_history(num_trades=1000):
    """
    Generates a synthetic log of past trades to simulate months of backtesting data.
    We intentionally inject a 'winning path' (Trend Following during NY Overlap with Wide SL)
    and a 'danger node' (Mean Reversion during London Open with Tight SL).
    """
    print(f"{Color.CYAN}📊 Generating Synthetic Trade History ({num_trades} trades)...{Color.RESET}")
    sessions = ["Asian_Consolidation", "London_Open", "NY_London_Overlap", "Dead_Zone"]
    strategies = ["Trend_Following", "Mean_Reversion", "Breakout"]
    sl_distances = ["Tight_SL", "Medium_SL", "Wide_SL"]
    
    trades = []
    for _ in range(num_trades):
        session = random.choice(sessions)
        strat = random.choice(strategies)
        sl = random.choice(sl_distances)
        
        # Inject realistic market logic biases to test the graph
        win_prob = 0.50
        
        # Gold breakouts in the NY Overlap with Wide SLs usually win
        if session == "NY_London_Overlap" and strat == "Breakout" and sl == "Wide_SL":
            win_prob = 0.85
            
        # Mean Reversion during London Open with Tight SL gets swept (Loss)
        if session == "London_Open" and strat == "Mean_Reversion" and sl == "Tight_SL":
            win_prob = 0.15
            
        outcome = "WIN" if random.random() < win_prob else "LOSS"
        
        trades.append({"Session": session, "Strategy": strat, "SL_Distance": sl, "Outcome": outcome})
        
    return pd.DataFrame(trades)

def build_knowledge_graph(df):
    """Builds a NetworkX topological graph mapping parameter combinations to outcomes."""
    print(f"{Color.YELLOW}🕸️ Building Topological Parameter Graph...{Color.RESET}")
    G = nx.Graph()
    
    G.add_node("WIN", type="outcome")
    G.add_node("LOSS", type="outcome")
    
    for _, row in df.iterrows():
        # Create a combined parameter node (e.g., "NY_London_Overlap | Breakout | Wide_SL")
        param_node = f"{row['Session']} | {row['Strategy']} | {row['SL_Distance']}"
        outcome = row['Outcome']
        
        G.add_node(param_node, type="parameter_combo", session=row['Session'], strat=row['Strategy'])
        
        if G.has_edge(param_node, outcome):
            G[param_node][outcome]['weight'] += 1
        else:
            G.add_edge(param_node, outcome, weight=1)
            
    print(f"{Color.GREEN}✅ Graph Built: {G.number_of_nodes()} Nodes, {G.number_of_edges()} Edges.{Color.RESET}\n")
    return G

def evaluate_topology(G, current_session, current_strat):
    """
    Traverses the graph to find the historical win/loss ratios of parameters 
    for the exact session and strategy currently being considered.
    """
    print(f"{Color.MAGENTA}🧭 Querying Graph Topology for: [{current_session} -> {current_strat}]{Color.RESET}")
    print("-" * 50)
    
    insights = []
    
    # Iterate through all nodes looking for parameter combos that match our current market state
    for node, attr in G.nodes(data=True):
        if attr.get('type') == 'parameter_combo' and attr.get('session') == current_session and attr.get('strat') == current_strat:
            wins = G[node].get("WIN", {}).get("weight", 0) if G.has_edge(node, "WIN") else 0
            losses = G[node].get("LOSS", {}).get("weight", 0) if G.has_edge(node, "LOSS") else 0
            
            total = wins + losses
            if total == 0: continue
                
            win_rate = (wins / total) * 100
            
            if win_rate >= 60:
                insights.append(f"🟢 SAFEPATH DETECTED: {node} ({win_rate:.1f}% Win Rate | {wins}W - {losses}L)")
            elif win_rate <= 40:
                insights.append(f"🔴 DANGER NODE: {node} ({win_rate:.1f}% Win Rate | {wins}W - {losses}L)")
            else:
                insights.append(f"⚪ NEUTRAL PATH: {node} ({win_rate:.1f}% Win Rate | {wins}W - {losses}L)")
                
    # Sort insights so Danger Nodes and Safepaths are grouped
    for insight in sorted(insights):
        print(insight)
        
    if not insights:
        print("No historical graph data for this exact combination.")
    print("-" * 50)

if __name__ == "__main__":
    # 1. Generate Fake Trade Data (Will be replaced by real CSV logs later)
    trades_df = generate_mock_trade_history(num_trades=2000)
    
    # 2. Build the NetworkX Graph
    knowledge_graph = build_knowledge_graph(trades_df)
    
    # 3. Simulate the AI asking the Graph for advice during two different market environments
    
    # Scenario A: The AI wants to trade a Breakout during the NY Overlap
    evaluate_topology(knowledge_graph, current_session="NY_London_Overlap", current_strat="Breakout")
    
    print("\n")
    
    # Scenario B: The AI wants to trade Mean Reversion during the London Open
    evaluate_topology(knowledge_graph, current_session="London_Open", current_strat="Mean_Reversion")