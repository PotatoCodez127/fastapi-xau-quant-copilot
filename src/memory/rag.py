# src/memory/rag.py
import os
import pandas as pd
import chromadb
from typing import Any
from config import settings


def generate_semantic_tape(row: pd.Series) -> str:
    """Translates raw quantitative features into a text narrative for the LLM."""
    time_str = row.name.strftime("%H:%M UTC")
    session = row["session"].replace("_", " ")
    trend = (
        f"Bullish (+{row['gold_1h_trend']:.2f} pts)"
        if row["gold_1h_trend"] > 0
        else f"Bearish ({row['gold_1h_trend']:.2f} pts)"
    )

    dxy_context = ""
    if "dxy_1h_momentum" in row and row["dxy_1h_momentum"] != 0.0:
        dxy_dir = "Rising" if row["dxy_1h_momentum"] > 0 else "Falling"
        dxy_context = f" | DXY is {dxy_dir}"

    return f"[{time_str}] Session: {session} | 1H Trend: {trend}{dxy_context} | Volatility: {row['rolling_volatility']:.2f} pts"


def generate_future_outcome(
    df: pd.DataFrame, current_idx: Any, forward_look: int = 12
) -> str:
    """Looks forward in history to determine if a setup resulted in a win or a loss."""
    try:
        current_price = df.loc[current_idx, "close"]
        future_idx = df.index.get_loc(current_idx) + forward_look
        if future_idx >= len(df):
            return "Unknown (End of Data)"

        future_price = df.iloc[future_idx]["close"]
        pnl = future_price - current_price

        if pnl > 5.0:
            return f"STRONG BULLISH CONTINUATION (+{pnl:.2f} pts)"
        elif pnl < -5.0:
            return f"STRONG BEARISH REVERSAL ({pnl:.2f} pts)"
        return "CHOP / CONSOLIDATION"
    except Exception:
        return "Unknown"


def setup_chroma_db() -> chromadb.Collection:
    """Configures persistent vectors using standardized configuration boundaries."""
    os.makedirs(settings.DATABASE_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=settings.DATABASE_PATH)
    return client.get_or_create_collection(
        name="xau_memory_bank", metadata={"hnsw:space": "cosine"}
    )


def populate_memory(df: pd.DataFrame, collection: chromadb.Collection):
    """Encodes historical market regimes into the vector space database."""
    documents, metadatas, ids = [], [], []
    sample_df = df.iloc[::12].copy()

    for idx, row in sample_df.iterrows():
        tape = generate_semantic_tape(row)
        outcome = generate_future_outcome(df, idx)
        if "Unknown" in outcome:
            continue

        doc_id = f"mem_{idx.strftime('%Y%m%d_%H%M')}"
        documents.append(tape)
        metadatas.append(
            {"timestamp": str(idx), "outcome": outcome, "session": row["session"]}
        )
        ids.append(doc_id)

    if documents:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
