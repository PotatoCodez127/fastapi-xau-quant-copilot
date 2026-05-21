import os
import json
import requests
from dotenv import load_dotenv

class Color:
    GREEN, CYAN, YELLOW, RED, MAGENTA, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[95m', '\033[0m'

def evaluate_trade_setup(market_state, rag_context, graph_context):
    """
    Feeds the multi-dimensional context to the LLM and forces a strict JSON response.
    """
    load_dotenv()
    
    # Mirroring the API setup exactly as it exists in autoresearch.py
    raw_keys = os.environ.get("OLLAMA_API_KEYS", "").replace('"', '').replace("'", "")
    api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    
    # Defaulting to the model you just used in the terminal log, or falling back
    model = os.environ.get("OLLAMA_MODEL", "minimax-m2.5:cloud").replace('"', '').replace("'", "")
    
    if not api_keys:
        print(f"{Color.RED}❌ No API Keys found in .env{Color.RESET}")
        return None

    print(f"{Color.CYAN}⚖️ Submitting Setup to AI Judge ({model})...{Color.RESET}")

    system_prompt = """You are an elite quantitative AI judge for XAUUSD (Gold). 
    Your job is to analyze the current market state, the historical vector precedents (RAG), and the topological parameter graph to rate a potential trade setup.

    CRITICAL RULES:
    1. The Graph provides multiple Stop Loss options. You must IGNORE 'DANGER NODES' and actively SELECT a 'SAFEPATH' or 'NEUTRAL PATH' if one exists.
    2. REGIME BAN 1: If the Session is 'Asian_Consolidation' OR 'Dead_Zone', output "PASS". These lack volume.
    3. REGIME BAN 2: If the Day of Week is 'Monday', output "PASS".
    4. REGIME BAN 3: If the Session is 'London_Open' AND Strategy is 'Trend_Following', output "PASS". HOWEVER, 'London_Open' + 'Breakout' is highly profitable and MUST NOT be banned.
    5. MACRO ALIGNMENT: Gold is inversely correlated with DXY. If DXY is rising and 1H Trend is Bearish, you MUST NOT go LONG, but you SHOULD actively look to go SHORT. If DXY is falling and 1H Trend is Bullish, you MUST NOT go SHORT, but you SHOULD actively look to go LONG.
    6. THE EXECUTION MANDATE (RAG OVERRIDE): If the Graph shows a SAFEPATH, you MUST attempt to output "EXECUTE". If the RAG context warns of "chop" or "mixed outcomes", DO NOT pass. Instead, output "EXECUTE" but reduce the Recommended_Risk_Pct to 0.5 or lower. ONLY output "PASS" if the RAG history shows overwhelming, verified strong reversals against your chosen direction.
    7. You MUST output your final answer as a raw JSON object. Do not wrap it in markdown.

    REQUIRED JSON SCHEMA:
    {
        "Decision": "EXECUTE" or "PASS",
        "Direction": "LONG" or "SHORT",
        "Confidence_Score": <integer between 0 and 100>,
        "Recommended_Risk_Pct": <float between 0.1 and 2.0>,
        "Selected_SL_Type": "Wide_SL" or "Medium_SL" or "Tight_SL",
        "Primary_Reasoning": "<A one sentence explanation>"
    }"""

    user_prompt = f"""
=========================================
CURRENT MARKET STATE (Limb 1)
=========================================
{market_state}

=========================================
HISTORICAL PRECEDENTS (Limb 2 - Vector DB)
=========================================
{rag_context}

=========================================
TOPOLOGICAL SAFETY (Limb 3 - Graph DB)
=========================================
{graph_context}
"""

    active_key = api_keys[0] # Using the first key as standard

    payload = {
        "model": model, 
        "prompt": system_prompt + "\n" + user_prompt,
        "stream": False,
        "temperature": 0.2, 
        "format": "json"    
    }

    try:
        # Using string concatenation to prevent markdown hyperlink bugs
        api_url = "https://" + "ollama.com/api/generate"
        
        response = requests.post(
            api_url, 
            headers={"Authorization": f"Bearer {active_key}"},
            json=payload,
            timeout=180
        )
        
        if response.status_code != 200:
            print(f"{Color.RED}❌ API Error {response.status_code}: {response.text}{Color.RESET}")
            return None
            
        raw_output = response.json().get('response', '').strip()
        
        # Clean up in case the LLM ignored instructions and wrapped it in markdown
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:-3].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output[3:-3].strip()
            
        return json.loads(raw_output)

    except requests.exceptions.RequestException as e:
        print(f"{Color.RED}❌ Network/API Connection Error: {e}{Color.RESET}")
        return None
    except json.JSONDecodeError:
        print(f"{Color.RED}❌ LLM Failed to output valid JSON. Raw output:\n{raw_output}{Color.RESET}")
        return None

if __name__ == "__main__":
    # MOCK DATA 
    mock_market_state = """
    Time: 08:15 UTC
    Session: London_Open
    Setup Triggered: Mean_Reversion (Price swept Daily S1 Pivot)
    Gold 1H Trend: Bearish (-8.5 pts)
    DXY Momentum: Rising (+0.15)
    Volatility: 6.2 pts
    """
    
    mock_rag_context = """
    --- MATCH #1 (Distance: 0.0051) ---
    PAST TAPE: Session: London_Open | 1H Trend: Bearish (-9.1 pts) | DXY Rising
    ACTUAL OUTCOME: CHOP / CONSOLIDATION
    
    --- MATCH #2 (Distance: 0.0068) ---
    PAST TAPE: Session: London_Open | 1H Trend: Bearish (-7.5 pts) | DXY Rising
    ACTUAL OUTCOME: STRONG BEARISH CONTINUATION (Mean Reversion Failed)
    """
    
    mock_graph_context = """
    🧭 Querying Graph Topology for: [London_Open -> Mean_Reversion]
    🔴 DANGER NODE: London_Open | Mean_Reversion | Tight_SL (10.5% Win Rate | 4W - 34L)
    ⚪ NEUTRAL PATH: London_Open | Mean_Reversion | Medium_SL (51.9% Win Rate)
    """

    print(f"{Color.YELLOW}Simulating a live market trigger during the London Open...{Color.RESET}\n")
    
    decision_json = evaluate_trade_setup(mock_market_state, mock_rag_context, mock_graph_context)
    
    if decision_json:
        print(f"\n{Color.GREEN}✅ Valid JSON Received from AI Judge:{Color.RESET}")
        print(json.dumps(decision_json, indent=4))
        
        if decision_json.get("Decision") == "EXECUTE":
            print(f"\n{Color.MAGENTA}⚡ AI recommends taking the trade with {decision_json.get('Recommended_Risk_Pct')}% risk.{Color.RESET}")
        else:
            print(f"\n{Color.RED}🛑 AI vetoed the trade setup.{Color.RESET}")