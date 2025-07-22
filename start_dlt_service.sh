#!/bin/bash

# Default values
env_file="/app/config/federation/consumer1.env"
port="8080"
container_name="dlt-manager"

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      env_file="$2"
      shift 2
      ;;
    --port)
      port="$2"
      shift 2
      ;;
    --container-name)
      container_name="$2"
      shift 2
      ;;      
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--env-file <path>] [--port <port>] [--container-name <container-name>]"
      exit 1
      ;;
  esac
done

echo "Running $container_name image with:"
echo " - Environment file: $env_file"
echo " - Exposed port: $port"

START_CMD="./run_server.sh"

docker run \
    -it \
    --name $container_name \
    --hostname $container_name \
    --rm \
    -p "$port":8000 \
    -v "./config":/app/config \
    -v "./smart-contracts":/app/smart-contracts \
    -v "./docker-images/dlt-manager/scripts/utility_functions.py":/app/utility_functions.py \
    -v "./docker-images/dlt-manager/scripts/main.py":/app/main.py \
    -v "./docker-images/dlt-manager/scripts/run_server.sh":/app/run_server.sh \
    -v "./experiments":/experiments \
    -e FEDERATION_ENV_FILE="$env_file" \
    dlt-manager:latest \
    $START_CMD
