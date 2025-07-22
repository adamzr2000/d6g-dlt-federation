#!/bin/bash

# Ensure FEDERATION_ENV_FILE is set
if [ -z "$FEDERATION_ENV_FILE" ]; then
  echo "Error: ENV_FILE environment variable is not set." >&2
  exit 1
fi

# Load environment variables
source "$FEDERATION_ENV_FILE"

# Start Uvicorn server
exec python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 --env-file "$FEDERATION_ENV_FILE"