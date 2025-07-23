#!/bin/bash

set -e

ENV_FILE=".env"
BASE_COMPOSE_TEMPLATE="local-geth-network.yml"
CONFIG_DIR="config"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: $ENV_FILE not found."
  exit 1
fi

# Parse number of nodes from .env
num_nodes=$(grep -oE '^# Node [0-9]+' "$ENV_FILE" | wc -l)
echo "Detected $num_nodes nodes from local geth network configuration."

# Read global parameters
source <(grep -v '^#' "$ENV_FILE" | grep -E '^(NETWORK_ID|WS_SECRET|ETH_NETSATS_PORT|BOOTNODE_PORT|BOOTNODE_KEY|RPC_PROTOCOL)=')

echo "Please enter the IP ADDRESS of bootnode:"
read -r BOOTNODE_IP

# Generate bootnode.env
cat <<EOF > "bootnode.env"
IDENTITY=bootnode
BOOTNODE_IP=$BOOTNODE_IP
BOOTNODE_PORT=$BOOTNODE_PORT
BOOTNODE_KEY=$BOOTNODE_KEY
BOOTNODE_URL=enode://\$BOOTNODE_KEY@\$BOOTNODE_IP:\$BOOTNODE_PORT
EOF

# Loop over each node
for (( i=1; i<=num_nodes; i++ )); do
  domain_env="domain${i}.env"
  compose_file="domain${i}-geth-network.yml"

  echo "Generating $domain_env..."
  cat <<EOF > "$domain_env"
IDENTITY=node${i}
NETWORK_ID=$NETWORK_ID
WS_SECRET=$WS_SECRET
ETH_NETSATS_IP=$BOOTNODE_IP
ETH_NETSATS_PORT=$ETH_NETSATS_PORT
BOOTNODE_IP=$BOOTNODE_IP
BOOTNODE_PORT=$BOOTNODE_PORT
RPC_PROTOCOL=$RPC_PROTOCOL
BOOTNODE_KEY=$BOOTNODE_KEY
BOOTNODE_URL=enode://\$BOOTNODE_KEY@\$BOOTNODE_IP:\$BOOTNODE_PORT
EOF

  # Use generic variable names in env file
  grep "^ETHERBASE_NODE_${i}=" "$ENV_FILE" | sed "s/ETHERBASE_NODE_${i}/ETHERBASE/" >> "$domain_env"
  grep "^WS_PORT_NODE_${i}=" "$ENV_FILE" | sed "s/WS_PORT_NODE_${i}/WS_PORT/" >> "$domain_env"
  grep "^RPC_PORT_NODE_${i}=" "$ENV_FILE" | sed "s/RPC_PORT_NODE_${i}/RPC_PORT/" >> "$domain_env"
  grep "^ETH_PORT_NODE_${i}=" "$ENV_FILE" | sed "s/ETH_PORT_NODE_${i}/ETH_PORT/" >> "$domain_env"
  grep "^PRIVATE_KEY_NODE_${i}=" "$ENV_FILE" | sed "s/PRIVATE_KEY_NODE_${i}/PRIVATE_KEY/" >> "$domain_env"
  grep "^WS_NODE_${i}_URL=" "$ENV_FILE" | sed "s/WS_NODE_${i}_URL/WS_NODE_URL/" >> "$domain_env"

  while true; do
    echo "Please enter the IP ADDRESS of domain$i:"
    read -r IP_ADDR
    if [[ $IP_ADDR =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "IP_ADDR=$IP_ADDR" >> "$domain_env"
      break
    else
      echo "Invalid IP address format. Try again."
    fi
  done

  echo "Generating $compose_file..."
  cat <<EOF > "$compose_file"
# version: '3'
x-common-commands:
  node_entrypoint: &node_entrypoint >
    bash -c "
    ./start_node.sh
    "
services:
EOF

  if [[ $i -eq 1 ]]; then
    cat <<EOF >> "$compose_file"
  bootnode:
    image: blockchain-node:geth-poa
    container_name: bootnode
    env_file:
      - bootnode.env
    command: *node_entrypoint
    volumes:
      - "./$CONFIG_DIR:/src/"
    network_mode: host
    restart: always
EOF
  fi

  cat <<EOF >> "$compose_file"

  node${i}:
    image: blockchain-node:geth-poa
    container_name: node${i}
    env_file:
      - $domain_env
    command: *node_entrypoint
    volumes:
      - "./$CONFIG_DIR:/src/"
    network_mode: host
    restart: always
EOF

  if [[ $i -eq 1 ]]; then
    cat <<EOF >> "$compose_file"

  eth-netstats:
    image: eth-netstats
    container_name: eth-netstats
    depends_on:
      - node1
    network_mode: host
    restart: always
EOF
  fi

done

echo "Setup completed."