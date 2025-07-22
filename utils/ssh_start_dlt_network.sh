#!/bin/bash

# Define the nodes with their respective IPs and usernames
NODE_1_IP="10.5.15.55"
NODE_1_USER="desire6g"

NODE_2_IP="10.5.99.5"
NODE_2_USER="netcom"

NODE_3_IP="10.5.99.6"
NODE_3_USER="netcom"

# Define the individual commands for each node
NODE_1_COMMAND="cd /home/${NODE_1_USER}/adam/dlt-federation-demo/dlt-network/ && ./start_dlt_network.sh"
NODE_2_COMMAND="cd /home/${NODE_2_USER}/dlt-federation-demo/dlt-network/ && ./join_dlt_network.sh --node node2 --validators 3"
NODE_3_COMMAND="cd /home/${NODE_3_USER}/dlt-federation-demo/dlt-network/ && ./join_dlt_network.sh --node node3 --validators 3"

# Function to execute SSH command with debug logging
execute_ssh_command() {
  local node_ip=$1
  local node_user=$2
  local command=$3
  echo "Executing on ${node_user}@${node_ip}: ${command}"
  ssh ${node_user}@${node_ip} "${command}"
  if [ $? -ne 0 ]; then
    echo "Error: Command failed on ${node_user}@${node_ip}"
  else
    echo "Success: Command executed on ${node_user}@${node_ip}"
  fi
}

# Start the DLT network on the first node
execute_ssh_command "$NODE_1_IP" "$NODE_1_USER" "$NODE_1_COMMAND"

sleep 5

# Join the second node to the network
execute_ssh_command "$NODE_2_IP" "$NODE_2_USER" "$NODE_2_COMMAND"

sleep 2

# Join the third node to the network
execute_ssh_command "$NODE_3_IP" "$NODE_3_USER" "$NODE_3_COMMAND"
