#!/bin/bash

# Execute the geth init command to initialize the data directory with genesis.json
output=$(geth init --datadir node42 genesis.json)
echo "$output"

# Read environment variables from node specific .env file
source node42.env

# Define the command
command="geth --identity 'node42' --syncmode 'full' --ws --ws.addr $IP_NODE_42  --ws.port $WS_PORT_NODE_42 --datadir node42 --port $ETH_PORT_NODE_42 --bootnodes $BOOTNODE_URL --ws.api 'eth,net,web3,personal,miner,admin,clique' --networkid $NETWORK_ID --nat 'any' --allow-insecure-unlock --authrpc.port $RPC_PORT_NODE_42 --ipcdisable --unlock $ETHERBASE_NODE_42 --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE_NODE_42 --ethstats node42:$WS_SECRET@$ETH_NETSATS_IP:$ETH_NETSATS_PORT" 

# Add verbosity option to the command if logs need to be saved
if [ "$SAVE_LOGS" == "y" ] || [ "$SAVE_LOGS" == "Y" ]; then
  command="$command --verbosity 3 >> ./logs/node42.log 2>&1"
else
  command="$command"
fi

# Execute the command
eval $command
