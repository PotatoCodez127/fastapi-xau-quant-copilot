# src/core/engine.py
import asyncio
import httpx
import pandas as pd
import yfinance as yf
from typing import Optional
from config import settings


class Color:
    GREEN, CYAN, YELLOW, RED, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[0m'


async def fetch_twelvedata_async(
    client: httpx.AsyncClient,
    symbol: str = "XAU/USD",
    interval: str = "5min",
    outputsize: int = 2500,
) -> pd.DataFrame:
    """Asynchronously fetches real-time spot gold data from TwelveData using central configurations."""
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={settings.TWELVEDATA_API_KEY}"
    try:
        res = await client.get(url, timeout=15.0)
        if res.status_code != 200:
            return pd.DataFrame()

        data = res.json()
        if "status" in data and data["status"] == "error":
            return pd.DataFrame()

        if "values" not in data:
            return pd.DataFrame()

        df = pd.DataFrame(data["values"])
        df["timestamp"] = pd.to_datetime(df["datetime"])
        df.set_index("timestamp", inplace=True)
        df = df.sort_index(ascending=True)

        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)

        df["volume"] = 0.0
        df.index = (
            df.index.tz_localize("UTC")
            if df.index.tz is None
            else df.index.tz_convert("UTC")
        )
        return df[["open", "high", "low", "close", "volume"]]
    except Exception:
        return pd.DataFrame()


async def build_macro_matrix_async(
    client: httpx.AsyncClient, daysback: int = 7
) -> pd.DataFrame:
    """Combines real-time Spot Gold and DXY data into a macro-synchronized matrix."""
    candles_needed = daysback * 288
    loop = asyncio.get_running_loop()
    dxy_future = loop.run_in_executor(
        None,
        lambda: yf.Ticker("DX-Y.NYB").history(period=f"{daysback}d", interval="5m"),
    )

    gold_df, dxy_df = await asyncio.gather(
        fetch_twelvedata_async(client, symbol="XAU/USD", outputsize=candles_needed),
        dxy_future,
    )

    if gold_df.empty:
        return pd.DataFrame()

    master_df = gold_df.copy()
    if not dxy_df.empty:
        dxy_df = dxy_df.rename(columns={"Close": "dxy_close"})
        dxy_df.index = (
            dxy_df.index.tz_localize("UTC")
            if dxy_df.index.tz is None
            else dxy_df.index.tz_convert("UTC")
        )
        master_df = master_df.join(dxy_df["dxy_close"], how="left").ffill()
    else:
        master_df["dxy_close"] = 104.0

    master_df["dxy_close"] = master_df["dxy_close"].ffill().bfill()
    return master_df[["open", "high", "low", "close", "volume", "dxy_close"]]


def engineer_xau_features(df: pd.DataFrame) -> pd.DataFrame:
    """Tags sessions and calculates technical momentum filters."""
    if df.empty:
        return df

    def assign_session(hour):
        if 0 <= hour < 6:
            return "Asian_Consolidation"
        elif 7 <= hour < 12:
            return "London_Open"
        elif 13 <= hour < 17:
            return "NY_London_Overlap"
        else:
            return "Dead_Zone"

    df["session"] = df.index.hour.map(assign_session)
    lookback = 12
    df["gold_1h_trend"] = df["close"] - df["close"].shift(lookback)

    if "dxy_close" in df.columns and len(df) > lookback:
        df["dxy_1h_momentum"] = df["dxy_close"] - df["dxy_close"].shift(lookback)

    df["hl_range"] = df["high"] - df["low"]
    df["rolling_volatility"] = df["hl_range"].rolling(lookback).mean()
    return df.dropna()


async def fetch_live_candle_async(client: httpx.AsyncClient) -> Optional[pd.Series]:
    """Asynchronously pulls latest active candle structures."""
    try:
        loop = asyncio.get_running_loop()
        dxy_future = loop.run_in_executor(
            None, lambda: yf.Ticker("DX-Y.NYB").history(period="1d", interval="5m")
        )

        gold, dxy = await asyncio.gather(
            fetch_twelvedata_async(client, symbol="XAU/USD", outputsize=30), dxy_future
        )

        if not gold.empty:
            dxy = dxy.rename(columns={"Close": "dxy_close"})
            if not dxy.empty:
                dxy.index = (
                    dxy.index.tz_localize("UTC")
                    if dxy.index.tz is None
                    else dxy.index.tz_convert("UTC")
                )
                matrix = gold.join(dxy["dxy_close"], how="left")
            else:
                matrix = gold
                matrix["dxy_close"] = 104.0

            matrix["dxy_close"] = matrix["dxy_close"].fillna(104.0)
            live_features = engineer_xau_features(matrix)
            if live_features.empty:
                return None
            return live_features.iloc[-2]
        return None
    except Exception:
        return None
