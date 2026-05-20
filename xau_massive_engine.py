import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import time

class Color:
    GREEN, CYAN, YELLOW, RED, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[0m'

def fetch_chunk(symbol, start_str, end_str, api_key):
    """Fetches a specific chunk of data from Massive with a retry mechanism."""
    endpoint_url = f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/5/minute/{start_str}/{end_str}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}
    headers = {"Authorization": f"Bearer {api_key}"}

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(endpoint_url, params=params, headers=headers, timeout=15)
            
            if response.status_code != 200:
                print(f"{Color.RED}❌ HTTP Error {response.status_code} for {symbol}: {response.text}{Color.RESET}")
                return []
                
            data = response.json()
            
            if data.get("resultsCount", 0) == 0:
                print(f"{Color.YELLOW}⚠️ API returned 0 results for {symbol} between {start_str} and {end_str}.{Color.RESET}")
                return []
                
            return data.get("results", [])
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                print(f"{Color.YELLOW}⚠️ Connection dropped for {symbol}. Retrying in 2 seconds... (Attempt {attempt + 1}/{max_retries}){Color.RESET}")
                time.sleep(2)
            else:
                print(f"{Color.RED}❌ Network/Execution Error fetching {symbol} after {max_retries} attempts: {e}{Color.RESET}")
                return []

def fetch_massive_asset(symbol, daysback=5):
    """Fetches data and maps it to a Pandas DataFrame."""
    load_dotenv()
    api_key = os.getenv("MASSIVE_API_KEY")
    
    if not api_key:
        raise ValueError("MASSIVE_API_KEY is missing from the .env file.")

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=daysback) 

    end_str = end_date.strftime('%Y-%m-%d')
    start_str = start_date.strftime('%Y-%m-%d')

    print(f"📡 Fetching {symbol} from Massive API...")
    raw_candles = fetch_chunk(symbol, start_str, end_str, api_key)

    if not raw_candles:
        return pd.DataFrame()

    df = pd.DataFrame(raw_candles)
    df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume', 't': 'timestamp'})
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC')
    
    df.drop_duplicates(subset=['timestamp'], inplace=True)
    df.sort_values('timestamp', inplace=True)
    df.set_index('timestamp', inplace=True)
    
    return df[['open', 'high', 'low', 'close', 'volume']]

def build_macro_matrix(daysback=5):
    print(f"{Color.CYAN}📥 Building Macro-Synchronized Matrix...{Color.RESET}")
    
    gold_df = fetch_massive_asset("C:XAUUSD", daysback) 
    dxy_df = fetch_massive_asset("UUP", daysback)     
    
    if gold_df.empty:
        print(f"{Color.RED}❌ Critical Failure: Could not fetch Gold data. Halting.{Color.RESET}")
        return None

    master_df = gold_df.copy()
    
    # Merge DXY onto the Gold timeline (Forward fill missing macro ticks)
    if not dxy_df.empty:
        master_df['dxy_close'] = dxy_df['close'].reindex(master_df.index).ffill()
    else:
        print(f"{Color.YELLOW}⚠️ DXY data missing. Filling with 0.0 (API might not support I:DXY){Color.RESET}")
        master_df['dxy_close'] = 0.0

    master_df.dropna(inplace=True)
    return master_df

def engineer_xau_features(df):
    """Tags Gold-specific liquidity sessions and macro momentum."""
    print(f"{Color.YELLOW}⚙️ Engineering XAUUSD AI Context Features...{Color.RESET}")
    
    # Session Logic (UTC)
    def assign_session(hour):
        if 0 <= hour < 6: return "Asian_Consolidation"
        elif 7 <= hour < 12: return "London_Open"
        elif 13 <= hour < 17: return "NY_London_Overlap" 
        else: return "Dead_Zone"
        
    df['session'] = df.index.hour.map(assign_session)
    
    # Rolling Context for the RAG Vector DB (1 hour lookback on 5m chart)
    lookback = 12 
    df['gold_1h_trend'] = df['close'] - df['close'].shift(lookback)
    
    if 'dxy_close' in df.columns and df['dxy_close'].iloc[-1] != 0:
        df['dxy_1h_momentum'] = df['dxy_close'] - df['dxy_close'].shift(lookback)
    
    df['hl_range'] = df['high'] - df['low']
    df['rolling_volatility'] = df['hl_range'].rolling(lookback).mean()

    return df.dropna()

if __name__ == "__main__":
    matrix = build_macro_matrix(daysback=7)
    if matrix is not None:
        final_df = engineer_xau_features(matrix)
        
        print(f"\n{Color.GREEN}✅ Massive Data Engine Initialized. Shape: {final_df.shape}{Color.RESET}\n")
        
        # Display the highly volatile Overlap session
        ny_sample = final_df[final_df['session'] == 'NY_London_Overlap'].tail(5)
        print("Sample Output (Ready for RAG Vectorization):")
        print(ny_sample[['close', 'session', 'dxy_close', 'gold_1h_trend']].to_string())