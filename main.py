import os
from dotenv import load_dotenv
from xau_visual_server import app, socketio, backtest_simulation_loop

class Color:
    GREEN, CYAN, YELLOW, RED, MAGENTA, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[95m', '\033[0m'

def print_banner():
    """Displays the system boot banner."""
    banner = f"""{Color.MAGENTA}
    ========================================================
         XAUUSD OMNI-AGENT : QUANTITATIVE TRADING ENGINE      
    ========================================================{Color.RESET}
    """
    print(banner)

def check_environment():
    """Ensures all necessary folders and API keys exist before booting."""
    print(f"{Color.CYAN}⚙️ Running pre-flight system checks...{Color.RESET}")
    
    # Load environment variables
    load_dotenv()
    
    # 1. Check API Keys
    if not os.getenv("MASSIVE_API_KEY"):
        print(f"{Color.RED}❌ FATAL ERROR: MASSIVE_API_KEY missing from .env file.{Color.RESET}")
        print(f"{Color.YELLOW}Please add it before running the engine.{Color.RESET}")
        return False
        
    if not os.getenv("OLLAMA_API_KEYS"):
        print(f"{Color.YELLOW}⚠️ WARNING: OLLAMA_API_KEYS missing. The AI Judge will fail to connect.{Color.RESET}")
        
    # 2. Ensure data directories exist for ChromaDB and the Omni-Ledger
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/xau_rag_db", exist_ok=True)
    
    print(f"{Color.GREEN}✅ Environment checks passed.{Color.RESET}\n")
    return True

if __name__ == '__main__':
    print_banner()
    
    if check_environment():
        print(f"{Color.CYAN}🚀 Booting up the Omni-Agent Server & AI Modules...{Color.RESET}")
        
        # Start the background backtesting, tracker, and AI loop
        socketio.start_background_task(backtest_simulation_loop)
        
        # Launch the Flask / WebSocket server
        print(f"{Color.GREEN}🌐 UI Server running at http://127.0.0.1:5000{Color.RESET}")
        
        # Suppress standard werkzeug logs to keep your terminal clean for AI telemetry
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        socketio.run(app, debug=True, use_reloader=False, port=5000)