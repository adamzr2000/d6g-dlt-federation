#!/bin/bash

# Assemble docker image.
echo 'Starting DLT network'

# Source the environment variables
set -o allexport
source docker-compose.env
set +o allexport

# Start the Docker Compose setup
docker compose up -d
