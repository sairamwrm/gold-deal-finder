# run.py
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from config import APP_HOST, APP_PORT, APP_RELOAD, AUTO_OPEN_BROWSER

def setup_directories():
    """Create necessary directories"""
    Path("static").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    Path("templates").mkdir(exist_ok=True)
    Path("cache").mkdir(exist_ok=True)
    
    # Create sample data if no scans exist
    data_dir = Path("data")
    if len(list(data_dir.glob("*.json"))) == 0:
        print("📁 No scan data found. Creating sample data...")
        try:
            from sample_data import create_sample_scans
            create_sample_scans(5)
        except ImportError:
            print("⚠️ Could not create sample data. Run sample_data.py manually.")

def open_browser():
    """Open browser after server starts"""
    time.sleep(2)
    webbrowser.open(f"http://localhost:{APP_PORT}")

if __name__ == "__main__":
    setup_directories()
    
    print(f"""
    ╔══════════════════════════════════════════════════════════════════╗
    ║                                                                  ║
    ║        GOLD DEAL FINDER - LOCAL DASHBOARD RUNTIME               ║
    ║                                                                  ║
    ║   Latest scan view with historical drill-down                   ║
    ║   Manual scans enabled locally                                  ║
    ║   Data directory: ./data/                                       ║
    ║                                                                  ║
    ║   Server: http://localhost:{APP_PORT:<4}                                   ║
    ║   API Docs: http://localhost:{APP_PORT:<4}/docs                             ║
    ║   Auto-open browser: {'ON ' if AUTO_OPEN_BROWSER else 'OFF'}                               ║
    ║                                                                  ║
    ║   Press Ctrl+C to stop the server                              ║
    ║                                                                  ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    
    if AUTO_OPEN_BROWSER:
        threading.Thread(target=open_browser, daemon=True).start()
    
    uvicorn.run(
        "api:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=APP_RELOAD,
        log_level="info"
    )
