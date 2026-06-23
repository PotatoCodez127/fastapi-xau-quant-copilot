# test_quant_core.py
import pytest
import pandas as pd
import numpy as np
from datetime import timezone
import httpx
from unittest.mock import AsyncMock, MagicMock

from src.api.state import QuantitativeGuard
from src.core.engine import engineer_xau_features, fetch_twelvedata_async


@pytest.fixture
def sample_market_data() -> pd.DataFrame:
    """Generates an isolated historical DataFrame structure to test technical parameters."""
    timestamps = pd.date_range(
        start="2026-01-01 00:00:00", periods=20, freq="5min", tz="UTC"
    )
    data = {
        "open": np.linspace(2030.0, 2040.0, 20),
        "high": np.linspace(2032.0, 2042.0, 20),
        "low": np.linspace(2028.0, 2038.0, 20),
        "close": np.linspace(2031.0, 2041.0, 20),
        "volume": [0.0] * 20,
        "dxy_close": np.linspace(104.0, 104.5, 20),
    }
    df = pd.DataFrame(data, index=timestamps)
    return df


def test_quantitative_guard_thresholds():
    """Validates that the QuantitativeGuard accurately enforces regime filtration limits."""
    # Test case 1: Setup below trend threshold
    invalid_candle = {"gold_1h_trend": 2.1, "rolling_volatility": 5.0}
    assert QuantitativeGuard.verify_execution_threshold(invalid_candle) is False

    # Test case 2: Setup meeting execution parameters
    valid_candle = {"gold_1h_trend": 5.2, "rolling_volatility": 6.1}
    assert QuantitativeGuard.verify_execution_threshold(valid_candle) is True

    # Test case 3: Setup missing volatility profile
    dead_candle = {"gold_1h_trend": 6.0, "rolling_volatility": 0.0}
    assert QuantitativeGuard.verify_execution_threshold(dead_candle) is False


def test_engineer_xau_features(sample_market_data):
    """Verifies calculated column parsing, session mapping, and rolling calculations."""
    engineered_df = engineer_xau_features(sample_market_data)

    assert not engineered_df.empty
    assert "session" in engineered_df.columns
    assert "gold_1h_trend" in engineered_df.columns
    assert "rolling_volatility" in engineered_df.columns

    # Confirm timezone attributes remain preserved as UTC
    assert engineered_df.index.tz == timezone.utc


@pytest.mark.asyncio
async def test_fetch_twelvedata_async_error_handling():
    """Ensures network failures or error responses from TwelveData cleanly fallback to an empty DataFrame."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # Simulate a non-200 connection drop
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_client.get.return_value = mock_response

    result_df = await fetch_twelvedata_async(
        mock_client, symbol="XAU/USD", outputsize=10
    )
    assert result_df.empty
