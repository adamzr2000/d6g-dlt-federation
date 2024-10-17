#!/bin/bash

# Check if container name and network name arguments are provided
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 <container_name> <network_name>"
  exit 1
fi

CONTAINER_NAME=$1
NETWORK_NAME=$2

# Attach the container to the specified Docker network
sudo docker network connect $NETWORK_NAME $CONTAINER_NAME

# Check if the operation was successful
if [ $? -eq 0 ]; then
  echo "Successfully attached container '$CONTAINER_NAME' to network '$NETWORK_NAME'."
else
  echo "Failed to attach container '$CONTAINER_NAME' to network '$NETWORK_NAME'."
fi
