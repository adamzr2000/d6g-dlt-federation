#!/bin/bash

# Load contract address from the smart-contract.env file
source ../../smart-contracts/smart-contract.env

# Check if the contract address was loaded successfully
if [ -z "$CONTRACT_ADDRESS" ]; then
  echo "Error: CONTRACT_ADDRESS could not be loaded from ../../smart-contracts/smart-contract.env"
  exit 1
fi

eth_node_url="ws://10.5.30.10:3334"

echo "ETH_NODE_URL: $eth_node_url"
echo "CONTRACT_ADDRESS: $CONTRACT_ADDRESS"

echo 'Running dlt-txs-monitoring image.'

docker run \
    -d \
    --name dlt-txs-monitoring \
    --rm \
    --net host \
    -e ETH_NODE_URL="$eth_node_url" \
    -e CONTRACT_ADDRESS="$CONTRACT_ADDRESS" \
    -v "$(pwd)/data":/app/data \
    -v "$(pwd)/../../smart-contracts":/app/smart-contracts \
    dlt-txs-monitoring:latest
