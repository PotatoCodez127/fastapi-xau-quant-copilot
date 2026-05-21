import os
import pandas as pd
from datetime import datetime
import yfinance as yf
import time
import csv

class Color:
    GREEN, CYAN, YELLOW, RED, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[0m'

def fetch_yahoo_history(symbol, daysback=7, interval="5m"):
    """Fetches historical data from Yahoo Finance to ensure seamless live continuity."""
    print(f"📡 Fetching {daysback} days of {symbol} from Yahoo Finance...")
    try:
        df = yf.Ticker(symbol).history(period=f"{daysback}d", interval=interval)
        if df.empty:
            return pd.DataFrame()
            
        df = df.rename(columns={
            'Open': 'open', 'High': 'high', 
            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
        })
        
        # Standardize everything to UTC to match the AI Ledger
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        else:
            df.index = df.index.tz_convert('UTC')
            
        return df[['open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        print(f"{Color.RED}Yahoo API Error for {symbol}: {e}{Color.RESET}")
        return pd.DataFrame()

def build_macro_matrix(daysback=30):
    print(f"{Color.CYAN}📥 Building Macro-Synchronized Matrix (Yahoo Finance)...{Color.RESET}")
    
    # 1. Fetch Gold Futures (GC=F) - 10 Min Delayed
    gold_df = fetch_yahoo_history("GC=F", daysback=daysback)
    
    if gold_df.empty:
        print(f"{Color.RED}❌ Critical Failure: Could not fetch Gold data. Halting.{Color.RESET}")
        return None

    # 2. Fetch DXY Macro Data
    dxy_df = fetch_yahoo_history("DX-Y.NYB", daysback=daysback)
    
    master_df = gold_df.copy()
    
    if not dxy_df.empty:
        dxy_df = dxy_df.rename(columns={'close': 'dxy_close'})
        # Merge DXY onto the Gold timeline
        master_df = master_df.join(dxy_df['dxy_close'], how='left').ffill()
    else:
        master_df['dxy_close'] = 104.0
        
    master_df.dropna(inplace=True)
    return master_df[['open', 'high', 'low', 'close', 'volume', 'dxy_close']]

def engineer_xau_features(df):
    """Tags Gold-specific liquidity sessions and macro momentum."""
    # Session Logic (UTC)
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
    """Pings Yahoo Finance for GC=F (10-min delayed) and merges DXY."""
    try:
        gold = yf.Ticker("GC=F").history(period="5d", interval="5m")
        dxy = yf.Ticker("DX-Y.NYB").history(period="5d", interval="5m")
        
        if not gold.empty:
            gold = gold.rename(columns={
                'Open': 'open', 'High': 'high', 
                'Low': 'low', 'Close': 'close', 'Volume': 'volume'
            })
            dxy = dxy.rename(columns={'Close': 'dxy_close'})
            
            matrix = gold.join(dxy['dxy_close'], how='left').ffill()
            
            if matrix.index.tz is None:
                matrix.index = matrix.index.tz_localize('UTC')
            else:
                matrix.index = matrix.index.tz_convert('UTC')
                
            live_features = engineer_xau_features(matrix)
            return live_features.iloc[-1]
            
        return None
    except Exception as e:
        print(f"Live API Error: {e}")
        return None