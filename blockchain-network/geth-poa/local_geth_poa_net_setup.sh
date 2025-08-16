#!/bin/bash

# Define variables for better scalability
CONFIG_DIR="config"
ENV_FILE=".env"
DOCKER_COMPOSE_FILE="local-geth-network.yml"

# Handle Ctrl+C
trap on_interrupt SIGINT

on_interrupt() {
  echo -e "\n❌ Setup interrupted by user (Ctrl+C). Exiting..."
  exit 1
}

# Function to prompt the user for input and validate it
prompt_and_validate_input() {
  local prompt_message="$1"
  local variable_name="$2"
  local validation_pattern="$3"

  while true; do
    echo "$prompt_message"
    read -r $variable_name
    if [[ ! ${!variable_name} =~ $validation_pattern ]]; then
      echo "Invalid input. Please try again."
    else
      break
    fi
  done
}

# Prompt for the number of geth nodes (>0)
prompt_and_validate_input "Please enter the number of geth nodes for the network [>0]:" numNodes '^[1-9][0-9]*$'
# Prompt for period value (>=0)
prompt_and_validate_input "Please enter the 'period' value (average time(s) interval for adding new blocks to the blockchain) [>=0]:" period '^[0-9]+$|^0$'
# Prompt for chainID value (>0)
prompt_and_validate_input "Please enter the 'chainID' value for genesis.json [>0]:" chainID '^[1-9][0-9]*$'
# Prompt for log saving option (y/n)
prompt_and_validate_input "Do you want to save logs in a .log file? (y/n):" saveLogs '^[ynYN]$'

echo "Number of nodes: $numNodes"
echo "Block period: $period seconds"
echo "Chain ID: $chainID"
echo "Save logs: $saveLogs"

# Initialize the .env file
touch $ENV_FILE

# Write global environment variables to the .env file
cat << EOF > $ENV_FILE
# Global configuration
NETWORK_ID=$chainID
BLOCKCHAIN_SUBNET=10.0.0.0/24
ETH_NETSTATS_SECRET=mysecret
ETH_NETSTATS_IP=10.0.0.2
ETH_NETSTATS_PORT=3000
BOOTNODE_IP=10.0.0.3
BOOTNODE_PORT=30301
SAVE_LOGS=$saveLogs
JSONRPC_TRANSPORT=http
BLOCKSCOUT_IP=10.0.0.4
BLOCKSCOUT_POSTGRES_IP=10.0.0.5
EOF

# Generate node addresses and update the .env file
declare -a addresses
alloc=""
extraData="0x0000000000000000000000000000000000000000000000000000000000000000"

for (( i=1; i<=$numNodes; i++ )); do
  mkdir -p "$CONFIG_DIR/node$i"
  
  # Generate a new account
  addr=$(geth --datadir "$CONFIG_DIR/node$i" account new --password "$CONFIG_DIR/password.txt" 2>&1 | grep "Public address of the key" | awk '{print $NF}')
  addresses+=("$addr")
  
  # Append node configuration to the .env file
  cat << EOF >> $ENV_FILE
# Node $i configuration
ETHERBASE_NODE_$i=$addr
IP_NODE_$i=10.0.0.$((5 + $i))
EOF

  # Append address to extraData and alloc sections
  extraData+="${addr#'0x'}"
  alloc+='"'$addr'": { "balance": "100000000000000000000" },'

  echo "node$i created and configured."
done

# Remove trailing comma from alloc
alloc=${alloc::-1}

# Add 65 zero bytes at the end of extraData
extraData+="0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"

# Create genesis.json file
cat << EOF > "$CONFIG_DIR/genesis.json"
{
  "config": {
    "chainId": $chainID,
    "homesteadBlock": 0,
    "eip150Block": 0,
    "eip155Block": 0,
    "eip158Block": 0,
    "byzantiumBlock": 0,
    "constantinopleBlock": 0,
    "petersburgBlock": 0,
    "istanbulBlock": 0,
    "muirGlacierBlock": 0,
    "berlinBlock": 0,
    "londonBlock": 0,
    "arrowGlacierBlock": 0,
    "grayGlacierBlock": 0,
    "clique": {
      "period": $period,
      "epoch": 30000
    }
  },
  "difficulty": "1",
  "gasLimit": "8000000",
  "extraData": "$extraData",
  "alloc": {
    $alloc
  }
}
EOF

# Create bootnode
mkdir -p "$CONFIG_DIR/bootnode" && bootnode -genkey "$CONFIG_DIR/bootnode/boot.key"
bootnode_key=$(bootnode -writeaddress -nodekey "$CONFIG_DIR/bootnode/boot.key")

# Append bootnode URL to .env file
cat << EOF >> $ENV_FILE
# Private keys
EOF

python3 "$CONFIG_DIR/private_key_decrypt.py"

# Generate docker-compose.yml file
touch $DOCKER_COMPOSE_FILE

# Write the base structure of docker-compose file
cat << EOF > $DOCKER_COMPOSE_FILE
# version: '3'
x-common-commands:
  node_entrypoint: &node_entrypoint >
    bash -c "
    ./start_node.sh
    "
services:
  bootnode:
    image: blockchain-node:geth-poa
    container_name: bootnode
    hostname: bootnode
    environment:
      - IDENTITY=bootnode
      - BOOTNODE_PORT=\${BOOTNODE_PORT}
    command: *node_entrypoint
    volumes:
      - "./$CONFIG_DIR:/src/"    
    networks:
      blockchain_network:
        ipv4_address: \${BOOTNODE_IP}
    restart: always
EOF

# Add each node to the docker-compose file
for (( i=1; i<=$numNodes; i++ )); do
  cat << EOF >> $DOCKER_COMPOSE_FILE

  node$i:
    image: blockchain-node:geth-poa
    container_name: node$i
    hostname: node$i
    depends_on:
      - bootnode
    environment:
      - IDENTITY=node$i
      - ETHERBASE=\${ETHERBASE_NODE_$i}
      - JSONRPC_TRANSPORT=\${JSONRPC_TRANSPORT}
      - BOOTNODE_IP=bootnode
      - BOOTNODE_PORT=\${BOOTNODE_PORT}
      - NETWORK_ID=\${NETWORK_ID}
      - ETH_NETSTATS_SECRET=\${ETH_NETSTATS_SECRET}
      - ETH_NETSTATS_IP=eth-netstats
      - ETH_NETSTATS_PORT=\${ETH_NETSTATS_PORT}
    command: *node_entrypoint
    ports:
      - "$((8544 + $i)):8545"      # JSRONRPC_PORT
    volumes:
      - "./$CONFIG_DIR:/src/"
    networks:
      blockchain_network:
        ipv4_address: \${IP_NODE_$i}
    restart: always
EOF
done

# Add eth-netstats service
cat << EOF >> $DOCKER_COMPOSE_FILE

  eth-netstats:
    image: eth-netstats
    container_name: eth-netstats
    depends_on:
      - node1
    ports:
      - "\${ETH_NETSTATS_PORT}:\${ETH_NETSTATS_PORT}"
    networks:
      blockchain_network:
        ipv4_address: \${ETH_NETSTATS_IP}
    restart: always

  blockscoutpostgres:
    image: postgres:13-alpine
    container_name: blockscoutpostgres
    restart: on-failure
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_HOST_AUTH_METHOD: trust
    # volumes:
    #   - blockscoutpostgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 10s
      retries: 5
    networks:
      blockchain_network:
        ipv4_address: \${BLOCKSCOUT_POSTGRES_IP}

  blockscout:
    image: consensys/blockscout:v4.1.5-beta
    container_name: blockscout
    depends_on:
      - blockscoutpostgres
    environment:
      PORT: "4000"
      ECTO_USE_SSL: "false"
      DATABASE_URL: "postgresql://postgres:postgres@blockscoutpostgres:5432/postgres?ssl=false"
      POSTGRES_PASSWORD: "postgres"
      POSTGRES_USER: "postgres"

      # ---- Chain metadata ----
      NETWORK: "D6G Private Blockchain"
      SUBNETWORK: "Clique PoA"
      CHAIN_ID: "$chainID"
      COIN: "ETH"

      # ---- JSON-RPC wiring to your node1 ----
      ETHEREUM_JSONRPC_VARIANT: "geth"
      ETHEREUM_JSONRPC_TRANSPORT: "http"
      ETHEREUM_JSONRPC_HTTP_URL: "http://node1:8545"
      ETHEREUM_JSONRPC_TRACE_URL: "http://node1:8545"

    entrypoint: ["/bin/sh","-c","cd /opt/app/; echo $MIX_ENV && mix do ecto.create, ecto.migrate; mix phx.server;"]
    ports:
      - "26000:4000"
    networks:
      blockchain_network:
        ipv4_address: \${BLOCKSCOUT_IP}

networks:
  blockchain_network:
    name: blockchain_network
    ipam:
      driver: default
      config:
        - subnet: \${BLOCKCHAIN_SUBNET}
EOF

echo "Setup completed."
