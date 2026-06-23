# xau_ai_judge.py
import json
import httpx
from typing import Optional, Dict, Any
from config import settings


class Color:
    GREEN, CYAN, YELLOW, RED, MAGENTA, RESET = (
        "\033[92m",
        "\033[96m",
        "\033[93m",
        "\033[91m",
        "\033[95m",
        "\033[0m",
    )


async def evaluate_trade_setup_async(
    client: httpx.AsyncClient, market_state: str, rag_context: str, graph_context: str
) -> Optional[Dict[str, Any]]:
    """Feeds multi-dimensional quant context to the LLM asynchronously with forced JSON schema constraints."""
    api_keys = settings.OLLAMA_API_KEYS
    model = settings.OLLAMA_MODEL

    if not api_keys:
        print(
            f"{Color.RED}❌ No API Keys resolved from valid settings matrix.{Color.RESET}"
        )
        return None

    print(
        f"{Color.CYAN}⚖️ Submitting Setup to Async AI Judge ({model})...{Color.RESET}"
    )

    system_prompt = """You are an elite quantitative AI judge for XAUUSD (Gold). 
    Your job is to analyze the current market state, historical vector precedents (RAG), and the topological parameter graph to rate a potential trade setup.

    CRITICAL RULES:
    1. The Graph provides multiple Stop Loss options. You must IGNORE 'DANGER NODES' and actively SELECT a 'SAFEPATH' or 'NEUTRAL PATH' if one exists.
    2. Only output a Decision of "PASS" if ALL graph paths are Danger Nodes, OR if the RAG history overwhelmingly shows strong reversals against your intended direction.
    3. REGIME BAN 1: If the Session is 'Asian_Consolidation' AND the Strategy is 'Breakout', you MUST output "PASS".
    4. REGIME BAN 2: If the Session is 'Dead_Zone' AND the Strategy is 'Trend_Following', you MUST output "PASS".
    5. SURGICAL BAN 1: If the Day of Week is 'Monday', you MUST output "PASS".
    6. SURGICAL BAN 2: If the Session is 'London_Open', you MUST output "PASS".
    7. RAG OVERRIDE: If the Topological Graph shows a high-win-rate SAFEPATH, but the RAG context warns of "chop" or "consolidation", you must either "PASS" or reduce Recommended_Risk_Pct to a maximum of 0.2.
    8. You MUST output your final answer as a raw JSON object. Do not wrap it in markdown block annotations.

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

    payload = {
        "model": model,
        "prompt": f"{system_prompt}\n{user_prompt}",
        "stream": False,
        "temperature": 0.2,
        "format": "json",
    }

    try:
        api_url = "https://ollama.com/api/generate"
        response = await client.post(
            api_url,
            headers={"Authorization": f"Bearer {api_keys[0]}"},
            json=payload,
            timeout=120.0,
        )

        if response.status_code != 200:
            print(
                f"{Color.RED}❌ Async API Error {response.status_code}: {response.text}{Color.RESET}"
            )
            return None

        raw_output = response.json().get("response", "").strip()
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:-3].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output[3:-3].strip()

        return json.loads(raw_output)
    except Exception as e:
        print(f"{Color.RED}❌ Evaluator Async Exception: {e}{Color.RESET}")
        return None
