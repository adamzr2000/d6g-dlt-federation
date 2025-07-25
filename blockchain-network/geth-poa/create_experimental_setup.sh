#!/bin/bash

set -e

ENV_FILE=".env"
CONFIG_DIR="config"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: $ENV_FILE not found."
  exit 1
fi

# Parse number of nodes from .env
num_nodes=$(grep -oE '^# Node [0-9]+' "$ENV_FILE" | wc -l)
echo "Detected $num_nodes nodes from local geth network configuration."

# Read global parameters
source <(grep -v '^#' "$ENV_FILE" | grep -E '^(NETWORK_ID|WS_SECRET|ETH_NETSTATS_PORT|BOOTNODE_PORT|BOOTNODE_KEY|RPC_PROTOCOL)=')

echo "Please enter the IP ADDRESS of bootnode:"
read -r BOOTNODE_IP

# Generate bootnode.env
cat <<EOF > "bootnode.env"
IDENTITY=bootnode
BOOTNODE_IP=$BOOTNODE_IP
BOOTNODE_PORT=$BOOTNODE_PORT
EOF

# Loop over each node
for (( i=1; i<=num_nodes; i++ )); do
  domain_env="domain${i}.env"
  compose_file="domain${i}-geth-network.yml"

  # Extract port values for the current node
  WS_PORT=$(grep -E "^WS_PORT_NODE_${i}=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '[:space:]')
  RPC_PORT=$(grep -E "^RPC_PORT_NODE_${i}=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '[:space:]')
  ETH_PORT=$(grep -E "^ETH_PORT_NODE_${i}=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '[:space:]')

  if [[ -z "$WS_PORT" || -z "$RPC_PORT" || -z "$ETH_PORT" ]]; then
    echo "Error: Port configuration missing for node $i."
    exit 1
  fi

  echo "Generating $domain_env..."
  cat <<EOF > "$domain_env"
IDENTITY=node${i}
NETWORK_ID=$NETWORK_ID
WS_SECRET=$WS_SECRET
ETH_NETSTATS_IP=$BOOTNODE_IP
ETH_NETSTATS_PORT=$ETH_NETSTATS_PORT
BOOTNODE_IP=$BOOTNODE_IP
BOOTNODE_PORT=$BOOTNODE_PORT
RPC_PROTOCOL=$RPC_PROTOCOL
EOF

  # Add node-specific variables to env
  grep "^ETHERBASE_NODE_${i}=" "$ENV_FILE" | sed "s/ETHERBASE_NODE_${i}/ETHERBASE/" >> "$domain_env"
  echo "WS_PORT=$WS_PORT" >> "$domain_env"
  echo "RPC_PORT=$RPC_PORT" >> "$domain_env"
  echo "ETH_PORT=$ETH_PORT" >> "$domain_env"
  grep "^PRIVATE_KEY_NODE_${i}=" "$ENV_FILE" | sed "s/PRIVATE_KEY_NODE_${i}/PRIVATE_KEY/" >> "$domain_env"

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

  # Add bootnode only for domain1
  if [[ $i -eq 1 ]]; then
    cat <<EOF >> "$compose_file"
  bootnode:
    image: blockchain-node:geth-poa
    container_name: bootnode
    hostname: bootnode
    env_file:
      - bootnode.env
    command: *node_entrypoint
    network_mode: host
    volumes:
      - "./$CONFIG_DIR:/src/"
    restart: always

EOF
  fi

  # Add node${i} service
  echo "  node${i}:" >> "$compose_file"
  echo "    image: blockchain-node:geth-poa" >> "$compose_file"
  echo "    container_name: node${i}" >> "$compose_file"
  echo "    hostname: node${i}" >> "$compose_file"
  echo "    env_file:" >> "$compose_file"
  echo "      - $domain_env" >> "$compose_file"
  echo "    command: *node_entrypoint" >> "$compose_file"
  echo "    volumes:" >> "$compose_file"
  echo "      - \"./$CONFIG_DIR:/src/\"" >> "$compose_file"
  if [[ $i -eq 1 ]]; then
    echo "    depends_on:" >> "$compose_file"
    echo "      - bootnode" >> "$compose_file"
  fi
  echo "    network_mode: host" >> "$compose_file"
  echo "    restart: always" >> "$compose_file"
  echo "" >> "$compose_file"

  # Add eth-netstats only for domain1
  if [[ $i -eq 1 ]]; then
    cat <<EOF >> "$compose_file"
  eth-netstats:
    image: eth-netstats
    container_name: eth-netstats
    network_mode: host
    depends_on:
      - node1
    restart: always
EOF
  fi

done

echo "✅ Setup completed successfully."
