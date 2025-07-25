#!/bin/bash

# Define the nodes with their respective IPs and usernames
DOMAIN_1_IP="10.5.15.55"
DOMAIN_1_USER="desire6g"

DOMAIN_2_IP="10.5.99.5"
DOMAIN_2_USER="netcom"

DOMAIN_3_IP="10.5.99.6"
DOMAIN_3_USER="netcom"

# Define the individual commands for each node
DOMAIN_1_COMMAND="cd /home/${DOMAIN_1_USER}/adam/d6g-dlt-federation/blockchain-network/geth-poa/ && ./start_geth_net.sh --file domain1-geth-network.yml"
DOMAIN_2_COMMAND="cd /home/${DOMAIN_2_USER}/d6g-dlt-federation/blockchain-network/geth-poa/ && ./start_geth_net.sh --file domain2-geth-network.yml"
DOMAIN_3_COMMAND="cd /home/${DOMAIN_3_USER}/d6g-dlt-federation/blockchain-network/geth-poa/ && ./start_geth_net.sh --file domain3-geth-network.yml"

# Function to execute SSH command with debug logging
execute_ssh_command() {
  local domain_ip=$1
  local domain_user=$2
  local command=$3
  echo "Executing on ${domain_user}@${domain_ip}: ${command}"
  ssh ${domain_user}@${domain_ip} "${command}"
  if [ $? -ne 0 ]; then
    echo "Error: Command failed on ${domain_user}@${domain_ip}"
  else
    echo "Success: Command executed on ${domain_user}@${domain_ip}"
  fi
}

# Start the DLT network on the first node
execute_ssh_command "$DOMAIN_1_IP" "$DOMAIN_1_USER" "$DOMAIN_1_COMMAND"

sleep 5

# Join the second node to the network
execute_ssh_command "$DOMAIN_2_IP" "$DOMAIN_2_USER" "$DOMAIN_2_COMMAND"

sleep 2

# Join the third node to the network
execute_ssh_command "$DOMAIN_3_IP" "$DOMAIN_3_USER" "$DOMAIN_3_COMMAND"
