import os
import pandas as pd
import chromadb
from chromadb.config import Settings
from xau_massive_engine import build_macro_matrix, engineer_xau_features

class Color:
    GREEN, CYAN, YELLOW, RED, MAGENTA, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[95m', '\033[0m'

def generate_semantic_tape(row):
    """
    Translates raw quantitative features into a textual narrative for the LLM.
    """
    time_str = row.name.strftime('%H:%M UTC')
    session = row['session'].replace('_', ' ')
    trend = f"Bullish (+{row['gold_1h_trend']:.2f} pts)" if row['gold_1h_trend'] > 0 else f"Bearish ({row['gold_1h_trend']:.2f} pts)"
    
    # Handle DXY if it exists and isn't 0.0
    dxy_context = ""
    if 'dxy_1h_momentum' in row and row['dxy_1h_momentum'] != 0.0:
        dxy_dir = "Rising" if row['dxy_1h_momentum'] > 0 else "Falling"
        dxy_context = f" | DXY is {dxy_dir}"

    tape = f"[{time_str}] Session: {session} | 1H Trend: {trend}{dxy_context} | Volatility: {row['rolling_volatility']:.2f} pts"
    return tape

def generate_future_outcome(df, current_idx, forward_look=12):
    """
    Looks ahead 1 hour (12 periods of 5m) to see what actually happened.
    This is the 'Label' we store in the memory bank so the AI knows if the setup won or lost.
    """
    try:
        current_price = df.loc[current_idx, 'close']
        future_idx = df.index.get_loc(current_idx) + forward_look
        
        if future_idx >= len(df):
            return "Unknown (End of Data)"
            
        future_price = df.iloc[future_idx]['close']
        pnl = future_price - current_price
        
        if pnl > 5.0: return f"STRONG BULLISH CONTINUATION (+{pnl:.2f} pts)"
        elif pnl < -5.0: return f"STRONG BEARISH REVERSAL ({pnl:.2f} pts)"
        else: return "CHOP / CONSOLIDATION"
        
    except Exception:
        return "Unknown"

def setup_chroma_db():
    print(f"{Color.CYAN}🧠 Initializing ChromaDB Vector Store...{Color.RESET}")
    db_path = os.path.join(os.getcwd(), "data", "xau_rag_db")
    os.makedirs(db_path, exist_ok=True)
    
    client = chromadb.PersistentClient(path=db_path)
    # Using cosine similarity is usually better for semantic text matching
    collection = client.get_or_create_collection(name="xau_memory_bank", metadata={"hnsw:space": "cosine"})
    return collection

def populate_memory(df, collection):
    print(f"{Color.YELLOW}📚 Encoding Market History into Vector Space...{Color.RESET}")
    
    documents = []
    metadatas = []
    ids = []
    
    # Sample every 12th candle (1 hour) to avoid database bloat for the prototype
    sample_df = df.iloc[::12].copy()
    
    for idx, row in sample_df.iterrows():
        tape = generate_semantic_tape(row)
        outcome = generate_future_outcome(df, idx)
        
        # Only store meaningful historical outcomes
        if "Unknown" in outcome: continue
            
        doc_id = f"mem_{idx.strftime('%Y%m%d_%H%M')}"
        
        documents.append(tape)
        metadatas.append({"timestamp": str(idx), "outcome": outcome, "session": row['session']})
        ids.append(doc_id)

    if documents:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
        print(f"{Color.GREEN}✅ Saved {len(documents)} new semantic memories to ChromaDB.{Color.RESET}")

def query_similar_history(collection, current_tape):
    """Retrieves the top 3 most similar past environments."""
    print(f"\n{Color.MAGENTA}🔍 Querying RAG Memory for similar past setups...{Color.RESET}")
    print(f"Current Market State: {current_tape}\n")
    
    results = collection.query(
        query_texts=[current_tape],
        n_results=3
    )
    
    if not results['documents'][0]:
        print("No historical matches found.")
        return
        
    for i in range(len(results['documents'][0])):
        matched_tape = results['documents'][0][i]
        meta = results['metadatas'][0][i]
        distance = results['distances'][0][i] # Lower distance = higher similarity
        
        print(f"--- MATCH #{i+1} (Distance: {distance:.4f}) ---")
        print(f"PAST TAPE: {matched_tape}")
        print(f"ACTUAL OUTCOME: {Color.YELLOW}{meta['outcome']}{Color.RESET}\n")

if __name__ == "__main__":
    # 1. Fetch Data using Limb 1
    matrix = build_macro_matrix(daysback=10) # Pulling 10 days to give the memory bank depth
    if matrix is not None:
        df = engineer_xau_features(matrix)
        
        # 2. Setup Vector DB
        rag_collection = setup_chroma_db()
        
        # 3. Populate DB with history
        populate_memory(df, rag_collection)
        
        # 4. Test the Retrieval System
        # Simulate a live market event by grabbing the very last row in our dataset
        live_row = df.iloc[-1]
        live_tape = generate_semantic_tape(live_row)
        
        query_similar_history(rag_collection, live_tape)