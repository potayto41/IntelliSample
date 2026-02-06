#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Direct app startup script for PostgreSQL testing.
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

print(f"USE_POSTGRES: {os.getenv('USE_POSTGRES')}")
print(f"Database URL available: {bool(os.getenv('DATABASE_URL'))}")

try:
    from app.main import app
except Exception as e:
    print(f"App import failed: {e}")
    sys.exit(1)

try:
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        log_level="info"
    )
except Exception as e:
    print(f"Uvicorn startup failed: {e}")
    sys.exit(1)