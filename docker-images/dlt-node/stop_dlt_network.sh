#!/bin/bash

# Stop and remove the DLT network
echo 'Stopping DLT network'

# Source the environment variables
set -o allexport
source docker-compose.env
set +o allexport

# Bring down the Docker Compose setup
docker compose down

echo 'DLT network stopped'
