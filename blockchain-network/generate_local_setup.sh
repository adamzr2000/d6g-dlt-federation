#!/bin/bash

# Check if the number of nodes is passed as an argument, if not, prompt the user
if [ -z "$1" ]; then
  read -p "Please enter the number of nodes for local testing: " NUM_NODES
else
  NUM_NODES=$1
fi

# Set the local environment directory variable
LOCAL_ENV_DIR="../config/dlt-local"

# Define base IP for nodes and bootnode
BASE_IP="172.18.0"
LOCAL_BOOTNODE_IP="${BASE_IP}.4"
LOCAL_INFLUXDB_IP="${BASE_IP}.2"

# Create a directory for local environment files
mkdir -p "$LOCAL_ENV_DIR"

# Path to original config directory
ORIGINAL_CONFIG_PATH="../config/dlt"

# Generate a local .env file for bootnode
echo "Generating local environment file for bootnode..."
sed -e "s/BOOTNODE_IP=.*/BOOTNODE_IP=${LOCAL_BOOTNODE_IP}/" \
    "${ORIGINAL_CONFIG_PATH}/bootnode.env" > "$LOCAL_ENV_DIR/bootnode.env"

# Loop to generate local .env files for each node
for (( i=1; i<=NUM_NODES; i++ ))
do
  NODE_IP="${BASE_IP}.$((4 + i))"
  echo "Generating local environment file for node$i with IP ${NODE_IP}..."

  sed -e "s/NODE_IP=.*/NODE_IP=${NODE_IP}/" \
      -e "s/BOOTNODE_IP=.*/BOOTNODE_IP=${LOCAL_BOOTNODE_IP}/" \
      -e "s/INFLUXDB_IP=.*/INFLUXDB_IP=${LOCAL_INFLUXDB_IP}/" \
      "${ORIGINAL_CONFIG_PATH}/node${i}.env" > "$LOCAL_ENV_DIR/node${i}.env"
done

echo "Local environment files generated successfully in $LOCAL_ENV_DIR directory."

# Automatically call the Docker Compose generation script
python3 generate_local_docker_compose.py "$NUM_NODES"
