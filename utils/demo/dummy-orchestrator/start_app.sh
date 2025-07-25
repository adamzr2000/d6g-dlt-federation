#!/bin/bash

# Default port
PORT=9999

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --port) PORT="$2"; shift ;;
        *) echo "Unknown argument: $1"; exit 1 ;;  # Handle unknown arguments
    esac
    shift
done

# # Ensure Flask is installed
# if ! command -v flask &> /dev/null; then
#     echo "Flask is not installed. Please install Flask to run the application."
#     exit 1
# fi

# Define a screen session name
SCREEN_SESSION_NAME="dummy-orchestrator"

# Set Flask environment variables
export FLASK_APP="app.py"
export FLASK_ENV="development"

# Start the Flask app in a detached screen session
screen -dmS "$SCREEN_SESSION_NAME" flask run --host=0.0.0.0 --port="$PORT"
# sudo -u $(whoami) screen -dmS "$SCREEN_SESSION_NAME" flask run --host=0.0.0.0 --port="$PORT"

# Provide user feedback
echo "Server started in screen session: $SCREEN_SESSION_NAME"
echo "You can attach to it using: screen -r $SCREEN_SESSION_NAME"
echo "You can kill it using: screen -XS $SCREEN_SESSION_NAME quit"
