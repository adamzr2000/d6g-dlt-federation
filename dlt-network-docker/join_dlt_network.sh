#!/bin/bash

# Function to handle the selection
handle_selection() {
    if [[ $1 =~ ^node[0-9]+$ ]]; then
        NODE_SELECTION="$1"
    else
        echo "Invalid selection: $1. Please select a valid node in the format nodeX, where X is a number."
        exit 1 # Indicates invalid selection
    fi
}

# Function to handle validators parameter
handle_validators() {
    if [[ $1 =~ ^[0-9]+$ ]] && [ $1 -ge 2 ]; then
        VALIDATORS="$1"
    else
        echo "Invalid validators value: $1. It must be a number greater than or equal to 2."
        exit 1 # Indicates invalid validators value
    fi
}

# Check if at least two arguments are provided
if [ $# -lt 2 ]; then
    echo "Usage: $0 <node_selection> <validators>"
    echo "Example: $0 node2 3"
    exit 1
else
    handle_selection "$1"
    handle_validators "$2"
fi

# Set the genesis file based on validators parameter
GENESIS_FILE="genesis_${VALIDATORS}_validators.json"

# Proceed with the operation
START_CMD="./node_start.sh"

DOCKER_CMD="docker run -d --name $NODE_SELECTION --hostname $NODE_SELECTION --network host --rm \
-v $(pwd)/../config/dlt/$NODE_SELECTION.env:/dlt-network/.env \
-v $(pwd)/../config/dlt/genesis/$GENESIS_FILE:/dlt-network/genesis.json \
dlt-node $START_CMD"

echo "Starting $NODE_SELECTION with $GENESIS_FILE and command $START_CMD..."
eval "$DOCKER_CMD"

echo "$NODE_SELECTION started successfully."
