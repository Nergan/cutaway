#!/bin/bash

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "Starting Main Site on port 7860 with native asyncio loop..."
# Force standard asyncio to bypass the uvloop SSL handshake timeout bug
exec uvicorn main:app --host 0.0.0.0 --port 7860 --loop asyncio
