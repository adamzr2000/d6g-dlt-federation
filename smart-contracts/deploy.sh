#!/bin/bash

# Path to the node1 environment file
NODE_ENV_FILE="../config/dlt/node1.env"

# Function to load environment variables from node1.env
load_env_vars() {
  if [ -f "$NODE_ENV_FILE" ]; then
    echo "Loading environment variables from $NODE_ENV_FILE"
    source "$NODE_ENV_FILE"  # Load the environment file to access variables directly
  else
    echo "Environment file $NODE_ENV_FILE not found!"
    exit 1
  fi
}

# Load the environment variables
load_env_vars

# Construct the start command for deploying the smart contract
START_CMD="./deploy_smart_contract.sh"

# Start a Docker container with the specified configurations
docker run \
  -it \
  --rm \
  --name truffle \
  --hostname truffle \
  --network host \
  -v "$(pwd)/.":/smart-contracts \
  -e NODE_IP="$NODE_IP" \
  -e WS_PORT="$WS_PORT" \
  truffle:latest \
  $START_CMD
