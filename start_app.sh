#!/bin/bash

# Default values
ENV_FILE=""

# Function to display usage
usage() {
  echo "Usage: $0 --env-file <path_to_env_file>"
  exit 1
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --env-file)
      ENV_FILE="$2"
      shift
      ;;
    *)
      echo "Unknown parameter passed: $1"
      usage
      ;;
  esac
  shift
done

# Check if the environment file was provided
if [ -z "$ENV_FILE" ]; then
  echo "Error: --env-file option is required."
  usage
fi

# Load environment variables from the specified file
FEDERATION_ENV_FILE=$ENV_FILE
source $FEDERATION_ENV_FILE

# Define a screen session name
SCREEN_SESSION_NAME="dlt-federation"

# Start a new screen session and run the command
screen -dmS $SCREEN_SESSION_NAME bash -c "FEDERATION_ENV_FILE=$FEDERATION_ENV_FILE python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 --env-file $FEDERATION_ENV_FILE"

echo "Server started in screen session: $SCREEN_SESSION_NAME"
echo "You can attach to it using: screen -r $SCREEN_SESSION_NAME"
echo "You can kill it using: screen -XS $SCREEN_SESSION_NAME quit"
