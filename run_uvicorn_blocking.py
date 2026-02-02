#!/usr/bin/env python
# Programmatic uvicorn server runner to avoid multiprocess reloader behavior
import os
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.DEBUG)

print('Starting programmatic uvicorn server (blocking)')
from app.main import app

import uvicorn
config = uvicorn.Config(app=app, host='127.0.0.1', port=8080, log_level='debug', lifespan='on')
server = uvicorn.Server(config)

try:
    server.run()
except Exception as e:
    print('Server exception:', e)
