#!/bin/bash

# Load environment variables from .env file if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Check if necessary environment variables are set
if [ -z "$ETH_NODE_URL" ]; then
  echo "Error: ETH_NODE_URL is not set. Please set it in the environment or .env file."
  exit 1
fi

if [ -z "$CONTRACT_ADDRESS" ]; then
  echo "Error: CONTRACT_ADDRESS is not set. Please set it in the environment or .env file."
  exit 1
fi

# Execute the Python script with the environment variables as arguments
python3 dlt_txs_monitoring.py --eth_node_url "$ETH_NODE_URL" --contract_address "$CONTRACT_ADDRESS"
