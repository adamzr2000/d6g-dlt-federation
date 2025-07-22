#!/bin/bash

# Ensure the correct argument is provided
if [[ "$1" != "--node" || -z "$2" ]]; then
    echo "Usage: $0 --node <node>"
    exit 1
fi

# Assign argument to variable
NODE="$2"

# Source the environment variables from the corresponding .env file
ENV_FILE="./../config/dlt/${NODE}.env"
# ENV_FILE="./../config/dlt-local/${NODE}.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: Environment file $ENV_FILE not found."
    exit 1
fi
source "$ENV_FILE"

# Ensure WS_URL is set
if [[ -z "$WS_URL" ]]; then
    echo "Error: WS_URL is not set in $ENV_FILE"
    exit 1
fi

# Construct the Geth command to get the number of peers
GETH_CMD="geth --exec 'net.peerCount' attach $WS_URL"

# Construct the Docker command to execute the Geth command inside the container
DOCKER_CMD="docker exec -it ${NODE} sh -c \"$GETH_CMD\""

# Execute the Docker command
echo "Executing command to get number of peers: $DOCKER_CMD"
eval "$DOCKER_CMD"
