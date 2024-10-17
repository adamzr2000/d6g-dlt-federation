#!/bin/bash

# Function to load specific environment variables from a file
load_specific_env_vars() {
  local env_file="$1"
  local node_index="$2"
  
  if [ -f "$env_file" ]; then
    echo "Loading specific environment variables from $env_file"
    eval $(grep "^IP_NODE_${node_index}=" "$env_file" | xargs)
    eval $(grep "^WS_PORT_NODE_${node_index}=" "$env_file" | xargs)
  else
    echo "Environment file $env_file not found!"
    exit 1
  fi
}

# Array of node environment files
node_env_files=(
  "../config/dlt/node1.env"
  "../config/dlt/node2.env"
  "../config/dlt/node3.env"
  "../config/dlt/node4.env"
)

# Load specific environment variables for each node and construct docker_env_args
docker_env_args=""
for env_file in "${node_env_files[@]}"; do
  # Extract the node index (e.g., 1 from node1.env)
  node_index=$(basename "$env_file" | grep -o '[0-9]\+')
  load_specific_env_vars "$env_file" "$node_index"
  docker_env_args+=" -e IP_NODE_${node_index}=$(eval echo \$IP_NODE_${node_index})"
  docker_env_args+=" -e WS_PORT_NODE_${node_index}=$(eval echo \$WS_PORT_NODE_${node_index})"
done

# Construct the start command based on the selection
START_CMD="./deploy_smart_contract.sh"

# Start a Docker container with the specified configurations
docker run \
  -it \
  --rm \
  --name truffle \
  --hostname truffle \
  --network host \
  -v $(pwd)/.:/smart-contracts \
  $docker_env_args \
  truffle:latest \
  $START_CMD
