#!/bin/bash

# Function to display usage instructions
usage() {
    echo "Usage: $0 --node <node_selection> --validators <validators>"
    echo "Example: $0 --node node2 --validators 3"
    exit 1
}

# Function to validate node selection
validate_node() {
    if [[ $1 =~ ^node[0-9]+$ ]]; then
        NODE_SELECTION="$1"
    else
        echo "Error: Invalid node selection '$1'. Use format 'nodeX' (e.g., node2)."
        exit 1
    fi
}

# Function to validate the number of validators
validate_validators() {
    if [[ $1 =~ ^[0-9]+$ ]] && [[ $1 -ge 2 ]]; then
        VALIDATORS="$1"
    else
        echo "Error: Invalid validators count '$1'. Must be a number >= 2."
        exit 1
    fi
}

# Parse named arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --node)
            validate_node "$2"
            shift 2
            ;;
        --validators)
            validate_validators "$2"
            shift 2
            ;;
        *)
            echo "Error: Unknown parameter '$1'"
            usage
            ;;
    esac
done

# Ensure required arguments are set
if [[ -z "$NODE_SELECTION" || -z "$VALIDATORS" ]]; then
    echo "Error: Missing required arguments."
    usage
fi

# Set the genesis file based on the number of validators
GENESIS_FILE="genesis_${VALIDATORS}_validators.json"

# Start the container
START_CMD="./node_start.sh"

DOCKER_CMD="docker run -d --name $NODE_SELECTION --network host --rm \
-v $(pwd)/../config/dlt/$NODE_SELECTION.env:/dlt-network/.env \
-v $(pwd)/../config/dlt/genesis/$GENESIS_FILE:/dlt-network/genesis.json \
dlt-node $START_CMD"

echo "Starting $NODE_SELECTION with $GENESIS_FILE and command $START_CMD..."
eval "$DOCKER_CMD"

echo "$NODE_SELECTION started successfully."
