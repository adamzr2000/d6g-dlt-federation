#!/bin/bash

# Usage: ./node_start.sh

# Load environment variables from the global .env file
if [ ! -f ".env" ]; then
  echo "Error: .env file not found. Please create a .env file with the necessary variables."
  exit 1
fi

source .env

# Log all required environment variables
echo "========== Loaded Environment Variables =========="
echo "DATADIR: $DATADIR"
echo "NODE_ID: $NODE_ID"
echo "NODE_IP: $NODE_IP"
echo "WS_PORT: $WS_PORT"
echo "ETH_PORT: $ETH_PORT"
echo "RPC_PORT: $RPC_PORT"
echo "ETHERBASE: $ETHERBASE"
echo "ETH_NETSTATS_IP: $ETH_NETSTATS_IP"
echo "ETH_NETSTATS_PORT: $ETH_NETSTATS_PORT"
echo "WS_SECRET: $WS_SECRET"
echo "BOOTNODE_URL: $BOOTNODE_URL"
echo "NETWORK_ID: $NETWORK_ID"
echo "SAVE_LOGS: $SAVE_LOGS"
echo "=============================================="

# Validate that all required environment variables are set
MISSING_VARS=false
for var in DATADIR NODE_ID NODE_IP WS_PORT ETH_PORT RPC_PORT ETHERBASE ETH_NETSTATS_IP ETH_NETSTATS_PORT WS_SECRET BOOTNODE_URL NETWORK_ID; do
  if [ -z "${!var}" ]; then
    echo "Error: Missing required environment variable: $var"
    MISSING_VARS=true
  fi
done

if [ "$MISSING_VARS" = true ]; then
  echo "Please check your .env file and ensure all required variables are set."
  exit 1
fi

# Execute the geth init command to initialize the data directory with genesis.json
output=$(geth init --datadir "$DATADIR" genesis.json)
echo "$output"

# Define the command to start the Geth node in a single line
command="geth --identity '$NODE_ID' --syncmode 'full' --ws --ws.addr $NODE_IP --ws.port $WS_PORT --datadir '$DATADIR' --port $ETH_PORT --bootnodes $BOOTNODE_URL --ws.api 'eth,net,web3,personal,miner,admin,clique' --networkid $NETWORK_ID --nat 'any' --allow-insecure-unlock --authrpc.port $RPC_PORT --ipcdisable --unlock $ETHERBASE --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE --ethstats $NODE_ID:$WS_SECRET@$ETH_NETSTATS_IP:$ETH_NETSTATS_PORT"

# Add verbosity option to the command if logs need to be saved
if [ "$SAVE_LOGS" == "y" ] || [ "$SAVE_LOGS" == "Y" ]; then
  command="$command --verbosity 3 >> ./logs/node.log 2>&1"
fi

echo "Executing command: $command ..."

# Execute the command
eval $command
