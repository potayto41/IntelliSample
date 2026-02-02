#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Direct app startup script for PostgreSQL testing.
"""
import os
import sys

# Load env vars
from dotenv import load_dotenv
load_dotenv()

print(f"PostgreSQL: {os.getenv('USE_POSTGRES')}")
print(f"Database URL available: {bool(os.getenv('DATABASE_URL'))}")

# Import and run
try:
    print("Importing app...")
    from app.main import app
    print("[OK] App imported successfully")
    
    print("Starting server on 127.0.0.1:8080...")
    import uvicorn
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8080,
        log_level="info"
    )
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)