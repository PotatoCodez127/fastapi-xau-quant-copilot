# test_ai_judge.py
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from xau_ai_judge import evaluate_trade_setup_async

@pytest.mark.asyncio
async def test_evaluate_trade_setup_async_success(monkeypatch):
    """Validates full execution path handling for successful JSON outputs from the LLM endpoint."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    # Standard schema matched payload response
    mock_response.json.return_value = {
        "response": '{"Decision": "EXECUTE", "Direction": "LONG", "Confidence_Score": 85, "Recommended_Risk_Pct": 1.0, "Selected_SL_Type": "Medium_SL", "Primary_Reasoning": "Strong momentum setup."}'
    }
    mock_client.post.return_value = mock_response

    # Force inject settings variables during environment execution testing
    monkeypatch.setenv("OLLAMA_API_KEYS", "mock_key_alpha")
    monkeypatch.setenv("OLLAMA_MODEL", "test-quant-model")

    market_state = "Time: 14:00 UTC\nSession: NY_London_Overlap"
    rag_ctx = "Historical Match Data"
    graph_ctx = "Topological Insights"

    decision = await evaluate_trade_setup_async(mock_client, market_state, rag_ctx, graph_ctx)
    
    assert decision is not None
    assert decision["Decision"] == "EXECUTE"
    assert decision["Confidence_Score"] == 85
    assert decision["Selected_SL_Type"] == "Medium_SL"

@pytest.mark.asyncio
async def test_evaluate_trade_setup_async_malformed_json(monkeypatch):
    """Ensures execution blocks gracefully degrade to None if the LLM drops corrupted strings."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "response": "Corrupted non-JSON string payload output."
    }
    mock_client.post.return_value = mock_response

    monkeypatch.setenv("OLLAMA_API_KEYS", "mock_key_alpha")

    decision = await evaluate_trade_setup_async(mock_client, "State", "RAG", "Graph")
    assert decision is None