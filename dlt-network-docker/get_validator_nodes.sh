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

# Extract the ID from the node name
NODE_ID=${NODE: -1}

# Extract the environment variables for the node
IP_VAR="IP_NODE_${NODE_ID}"
WS_PORT_VAR="WS_PORT_NODE_${NODE_ID}"

IP=$(eval echo \$$IP_VAR)
WS_PORT=$(eval echo \$$WS_PORT_VAR)

# Construct the Geth command to get the number of peers
GETH_CMD="geth --exec 'clique.getSigners()' attach ws://${IP}:${WS_PORT}"

# Construct the Docker command to get the number of peers
DOCKER_CMD="docker exec -it ${NODE} sh -c \"$GETH_CMD\""

# Execute the Docker command
echo "Executing command to get current validators: $DOCKER_CMD"
eval "$DOCKER_CMD"
