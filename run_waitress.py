# run_waitress.py

import sys
import os

# Ensure the project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from waitress import serve
from app.main import app

print("🚀 Starting Waitress server on http://0.0.0.0:8000 ...")

if __name__ == "__main__":
    serve(my_app, host="0.0.0.0", port=8000)
    print("✅ Server started successfully!")