#!/bin/bash

# === Read from environment variables ===
node_ip="${NODE_IP:-}"
port="${PORT:-}"
protocol="${PROTOCOL:-ws}"  # default to WebSocket

# === Validate required inputs ===
if [[ -z "$node_ip" || -z "$port" ]]; then
  echo "❌ Error: NODE_IP and PORT must be set as environment variables."
  echo "Example:"
  echo "  export NODE_IP=10.0.0.1"
  echo "  export PORT=3334"
  echo "  export PROTOCOL=ws"
  exit 1
fi

# === Display selected config ===
if [[ "$protocol" == "http" ]]; then
  echo "🔗 Deploying via HTTP to http://$node_ip:$port"
  output=$(truffle migrate --network geth_network_http)
elif [[ "$protocol" == "ws" ]]; then
  echo "🔗 Deploying via WebSocket to ws://$node_ip:$port"
  output=$(truffle migrate --network geth_network_ws)
else
  echo "❌ Invalid protocol: $protocol (must be 'ws' or 'http')"
  exit 1
fi

# === Print output and extract contract address ===
echo "$output"
contract_address=$(echo "$output" | grep "contract address:" | awk '{print $4}')

# === Export result ===
echo "CONTRACT_ADDRESS=$contract_address" > ./smart-contract.env
echo "✅ Contract deployed at: $contract_address"
echo "📄 Written to smart-contract.env"
