import os
import requests
import pandas as pd
from datetime import datetime
import yfinance as yf

class Color:
    GREEN, CYAN, YELLOW, RED, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[0m'

def fetch_twelvedata(symbol="XAU/USD", interval="5min", outputsize=2500):
    """Fetches real-time, zero-delay Spot Gold from TwelveData."""
    api_key = os.getenv("TWELVEDATA_API_KEY")
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={api_key}"
    
    try:
        res = requests.get(url)
        data = res.json()
        
        if 'status' in data and data['status'] == 'error':
            print(f"{Color.RED}TwelveData Error: {data['message']}{Color.RESET}")
            return pd.DataFrame()
            
        if 'values' not in data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data['values'])
        
        # Format the TwelveData response to our internal standards
        df['timestamp'] = pd.to_datetime(df['datetime'])
        df.set_index('timestamp', inplace=True)
        
        # TwelveData returns data newest-first, we need it oldest-first
        df = df.sort_index(ascending=True)
        
        # Convert string prices to floats
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
            
        # Spot Forex usually doesn't provide real volume, create a zeroed column to prevent crashes
        df['volume'] = 0.0 
        
        # Standardize timezone to UTC
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        else:
            df.index = df.index.tz_convert('UTC')
            
        return df[['open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        print(f"{Color.RED}TwelveData API Exception: {e}{Color.RESET}")
        return pd.DataFrame()

def build_macro_matrix(daysback=7):
    print(f"{Color.CYAN}📥 Building Macro-Synchronized Matrix (TwelveData Real-Time)...{Color.RESET}")
    
    # 1. Fetch Real-Time Spot Gold (288 5-min candles per day)
    candles_needed = daysback * 288
    gold_df = fetch_twelvedata(symbol="XAU/USD", outputsize=candles_needed)
    
    if gold_df.empty:
        print(f"{Color.RED}❌ Critical Failure: Could not fetch XAU/USD. Halting.{Color.RESET}")
        return None

    # 2. Fetch DXY Macro Data (Yahoo)
    dxy_df = yf.Ticker("DX-Y.NYB").history(period=f"{daysback}d", interval="5m")
    master_df = gold_df.copy()
    
    if not dxy_df.empty:
        dxy_df = dxy_df.rename(columns={'Close': 'dxy_close'})
        if dxy_df.index.tz is None:
            dxy_df.index = dxy_df.index.tz_localize('UTC')
        else:
            dxy_df.index = dxy_df.index.tz_convert('UTC')
        master_df = master_df.join(dxy_df['dxy_close'], how='left').ffill()
    else:
        master_df['dxy_close'] = 104.0
        
    # Forward-fill any remaining NaNs in DXY
    master_df['dxy_close'] = master_df['dxy_close'].ffill().bfill()
    return master_df[['open', 'high', 'low', 'close', 'volume', 'dxy_close']]

def engineer_xau_features(df):
    """Tags Gold-specific liquidity sessions and macro momentum."""
    def assign_session(hour):
        if 0 <= hour < 6: return "Asian_Consolidation"
        elif 7 <= hour < 12: return "London_Open"
        elif 13 <= hour < 17: return "NY_London_Overlap" 
        else: return "Dead_Zone"
        
    df['session'] = df.index.hour.map(assign_session)
    
    lookback = 12 
    df['gold_1h_trend'] = df['close'] - df['close'].shift(lookback)
    
    if 'dxy_close' in df.columns and df['dxy_close'].iloc[-1] != 0:
        df['dxy_1h_momentum'] = df['dxy_close'] - df['dxy_close'].shift(lookback)
    
    df['hl_range'] = df['high'] - df['low']
    df['rolling_volatility'] = df['hl_range'].rolling(lookback).mean()

    return df.dropna()

def fetch_live_candle():
    """Pings TwelveData for zero-delay Spot Gold and merges DXY."""
    try:
        # We only need the last 5 candles to grab the most recent closed one
        gold = fetch_twelvedata(symbol="XAU/USD", outputsize=30)
        
        # We pull 1 day of DXY to ensure we have a valid reference point, even on holidays
        # We pull 1 day of DXY to ensure we have a valid reference point
        dxy = yf.Ticker("DX-Y.NYB").history(period="1d", interval="5m")
        
        if not gold.empty:
            dxy = dxy.rename(columns={'Close': 'dxy_close'})
            if not dxy.empty:
                if dxy.index.tz is None:
                    dxy.index = dxy.index.tz_localize('UTC')
                else:
                    dxy.index = dxy.index.tz_convert('UTC')
                matrix = gold.join(dxy['dxy_close'], how='left')
            else:
                matrix = gold
                matrix['dxy_close'] = 104.0
            
            # =======================================================
            # 🛡️ THE FIX: Forcefully replace all Holiday NaNs with 104.0 
            # so .dropna() doesn't wipe out the Spot Gold data!
            # =======================================================
            matrix['dxy_close'] = matrix['dxy_close'].fillna(104.0)
            
            live_features = engineer_xau_features(matrix)
            
            if live_features.empty:
                return None
                
            # Return the fully completed, closed candle
            return live_features.iloc[-2]
            
        return None
    except Exception as e:
        print(f"Live API Error: {e}")
        return None