#!/bin/bash

# Check if the correct number of arguments are provided
if [ $# -ne 1 ]; then
    echo "Usage: $0 <node>"
    exit 1
fi

# Assign argument to variable
NODE=$1

# Source the environment variables from the corresponding .env file
source "./../config/dlt/${NODE}.env" 2>/dev/null

# Construct the Geth command to get the number of peers
GETH_CMD="geth --exec 'net.peerCount' attach $WS_URL"

# Construct the Docker command to get the number of peers
DOCKER_CMD="docker exec -it ${NODE} sh -c \"$GETH_CMD\""

# Execute the Docker command
echo "Executing command to get number of peers: $DOCKER_CMD"
eval "$DOCKER_CMD"
