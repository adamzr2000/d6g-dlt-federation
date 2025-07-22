#!/bin/bash

# Define the paths to be cleaned
LOCAL_ENV_DIR="../config/dlt-local"
DOCKER_COMPOSE_FILE="docker-compose.yml"

# Check and remove the local environment directory
if [ -d "$LOCAL_ENV_DIR" ]; then
  echo "Removing local environment directory: $LOCAL_ENV_DIR"
  rm -rf "$LOCAL_ENV_DIR"
else
  echo "Local environment directory not found: $LOCAL_ENV_DIR"
fi

# Check and remove the Docker Compose file
if [ -f "$DOCKER_COMPOSE_FILE" ]; then
  echo "Removing Docker Compose file: $DOCKER_COMPOSE_FILE"
  rm -f "$DOCKER_COMPOSE_FILE"
else
  echo "Docker Compose file not found: $DOCKER_COMPOSE_FILE"
fi

echo "Cleanup completed."
