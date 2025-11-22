#!/usr/bin/env bash
set -euo pipefail

# Defaults
port="8000"
container_name="blockchain-manager"
config=""
domain_function=""
jsonrpc_port="8545"

usage() {
  cat <<EOF
Usage: $0 --config <path/to/domain.env> --domain-function <provider|consumer> [--port <port>] [--container-name <name>]

  --config            Path to your domain .env file (required)
  --domain-function   "provider" or "consumer" (required)
  --port              Host port to bind container's 8000 (default: 8000)
  --container-name    Docker container name/hostname (default: blockchain-manager)
EOF
  exit 1
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      config="$2"
      shift 2
      ;;
    --domain-function)
      domain_function="$(echo "$2" | tr '[:upper:]' '[:lower:]')"
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
    -*|--*)
      echo "Unknown option: $1"
      usage
      ;;
    *)
      break
      ;;
  esac
done

# Validate required flags
if [[ -z "$config" || -z "$domain_function" ]]; then
  echo "ERROR: --config and --domain-function are required."
  usage
fi

if [[ "$domain_function" != "provider" && "$domain_function" != "consumer" ]]; then
  echo "ERROR: --domain-function must be 'provider' or 'consumer'."
  exit 1
fi

# Ensure the domain .env exists
if [[ ! -f "$config" ]]; then
  echo "ERROR: Config file '$config' not found."
  exit 1
fi

# Source the domain-specific .env
set -o allexport
# shellcheck disable=SC1090
source "$config"
set +o allexport

# Load contract address from smart-contracts/smart-contract.env
sc_env="$(pwd)/smart-contracts/smart-contract.env"
if [[ ! -f "$sc_env" ]]; then
  echo "ERROR: smart-contract.env not found at $sc_env"
  exit 1
fi
set -o allexport
# shellcheck disable=SC1090
source "$sc_env"
set +o allexport

# Validate required variables
: "${ETHERBASE:?Missing ETHERBASE in $config}"
: "${PRIVATE_KEY:?Missing PRIVATE_KEY in $config}"
: "${JSONRPC_TRANSPORT:?Missing JSONRPC_TRANSPORT in $config}"
: "${NAT_EXTIP:?Missing NAT_EXTIP in $config}"
: "${CONTRACT_ADDRESS:?Missing CONTRACT_ADDRESS in smart-contract.env}"

# Build the Web3 node URL
eth_node_url="${JSONRPC_TRANSPORT}://${NAT_EXTIP}:$jsonrpc_port"

cat <<INFO
Launching '$container_name':
  Domain function  : $domain_function
  ETH_ADDRESS      : $ETHERBASE
  ETH_PRIVATE_KEY  : [hidden]
  ETH_NODE_URL     : $eth_node_url
  CONTRACT_ADDRESS : $CONTRACT_ADDRESS
  Host port        : $port
INFO

# Run the container
docker run \
  --rm -it \
  --name "$container_name" \
  --hostname "$container_name" \
  -p "${port}:8000" \
  --env ETH_ADDRESS="$ETHERBASE" \
  --env ETH_PRIVATE_KEY="$PRIVATE_KEY" \
  --env ETH_NODE_URL="$eth_node_url" \
  --env CONTRACT_ADDRESS="$CONTRACT_ADDRESS" \
  --env DOMAIN_FUNCTION="$domain_function" \
  --env PYTHONUNBUFFERED=1 \
  -v "$(pwd)/smart-contracts":/smart-contracts \
  -v "$(pwd)/experiments":/experiments \
  -v "$(pwd)/dockerfiles/blockchain-manager/app":/app \
  -v "$(pwd)/utils/demo/ipfs-deploy-info":/ipfs-deploy-info \
  blockchain-manager:latest
