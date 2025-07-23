#!/bin/bash

# Default value
COMPOSE_FILE="local-geth-network.yml"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --file) COMPOSE_FILE="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

echo "Starting geth network using $COMPOSE_FILE..."

docker compose -f "$COMPOSE_FILE" up -d