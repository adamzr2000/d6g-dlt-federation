#!/bin/bash

# Usage: ./node_start.sh

# Load environment variables from the global .env file
if [ ! -f ".env" ]; then
  echo "Error: .env file not found. Please create a .env file with the necessary variables."
  exit 1
fi

source .env

# Validate that all required environment variables are set
if [ -z "$DATADIR" ] || [ -z "$NODE_ID" ] || [ -z "$NODE_IP" ] || [ -z "$WS_PORT" ] || [ -z "$ETH_PORT" ] || \
   [ -z "$RPC_PORT" ] || [ -z "$ETHERBASE" ] || [ -z "$INFLUXDB_IP" ] || \
   [ -z "$INFLUXDB_PORT" ] || [ -z "$INFLUXDB_USERNAME" ] || [ -z "$INFLUXDB_PASSWORD" ] || \
   [ -z "$INFLUXDB_DB" ] || [ -z "$BOOTNODE_URL" ] || [ -z "$NETWORK_ID" ]; then
  echo "Error: Missing required environment variables. Please check your .env file."
  exit 1
fi

# Execute the geth init command to initialize the data directory with genesis.json
output=$(geth init --datadir "$DATADIR" genesis.json)
echo "$output"

# Define the command to start the Geth node in a single line
command="geth --identity '$NODE_ID' --syncmode 'full' --ws --ws.addr $NODE_IP --ws.port $WS_PORT --datadir '$DATADIR' --port $ETH_PORT --bootnodes $BOOTNODE_URL --ws.api 'eth,net,web3,personal,miner,admin,clique' --networkid $NETWORK_ID --nat 'any' --allow-insecure-unlock --authrpc.port $RPC_PORT --ipcdisable --unlock $ETHERBASE --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE --metrics --metrics.influxdb --metrics.influxdb.endpoint 'http://$INFLUXDB_IP:$INFLUXDB_PORT' --metrics.influxdb.username '$INFLUXDB_USERNAME' --metrics.influxdb.password '$INFLUXDB_PASSWORD' --metrics.influxdb.database '$INFLUXDB_DB' --metrics.expensive"

# Add verbosity option to the command if logs need to be saved
if [ "$SAVE_LOGS" == "y" ] || [ "$SAVE_LOGS" == "Y" ]; then
  command="$command --verbosity 3 >> ./logs/node.log 2>&1"
fi

echo "Executing command: $command ..."

# Execute the command
eval $command
