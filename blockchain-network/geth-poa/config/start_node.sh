#!/usr/bin/env bash
set -euo pipefail

#------------------------------------------------------------------------
# MODE SWITCH:
#   To start a bootnode, set:
#     export IDENTITY=bootnode
#     export BOOTNODE_IP=<ip>
#     export BOOTNODE_PORT=<port>
#
#   To start a Geth node, set:
#     export IDENTITY=nodeX             # node1, node2, etc.
#     export ETHERBASE=<0x...>          # miner account
#     export BOOTNODE_IP=<ip>
#     export BOOTNODE_PORT=<port>
#     export NETWORK_ID=<int>
#     export ETH_NETSTATS_SECRET=<string>
#     export ETH_NETSTATS_IP=<ip>
#     export ETH_NETSTATS_PORT=<port>
#
# Optional:
#   JSONRPC_TRANSPORT=ws|http (default ws)
#   JSONRPC_ADDR=0.0.0.0 (default 0.0.0.0)
#   JSONRPC_PORT=8545     (default 8545)
#   P2P_PORT=30303        (default 30303)
#   DISC_PORT=30303       (default = P2P_PORT)
#   SAVE_LOGS=Y           (default: no)
#------------------------------------------------------------------------

: "${IDENTITY:?set IDENTITY (nodeX or bootnode)}"

# --------- Bootnode mode ---------
if [[ "${IDENTITY,,}" == "bootnode" ]]; then
  : "${BOOTNODE_IP:?}" "${BOOTNODE_PORT:?}"
  echo "🚀 Starting bootnode on ${BOOTNODE_IP}:${BOOTNODE_PORT}"
  exec bootnode -nodekey ./bootnode/boot.key -verbosity 9 -addr "${BOOTNODE_IP}:${BOOTNODE_PORT}"
fi

# --------- Node mode ---------
: "${ETHERBASE:?}" "${BOOTNODE_IP:?}" "${BOOTNODE_PORT:?}" "${NETWORK_ID:?}" "${ETH_NETSTATS_SECRET:?}" "${ETH_NETSTATS_IP:?}" "${ETH_NETSTATS_PORT:?}"

JSONRPC_TRANSPORT="${JSONRPC_TRANSPORT:-ws}"
JSONRPC_ADDR="${JSONRPC_ADDR:-0.0.0.0}"
JSONRPC_PORT="${JSONRPC_PORT:-8545}"
DATADIR="$IDENTITY"
GENESIS_FILE="${GENESIS_FILE:-genesis.json}"
P2P_PORT="${P2P_PORT:-30303}"
DISC_PORT="${DISC_PORT:-30303}"

echo "🔧 Initializing $DATADIR with $GENESIS_FILE"
geth init --datadir "$DATADIR" "$GENESIS_FILE"

# construct the bootnode enode URL from the key + IP/port
BOOTNODE_ENODE_ID=$(bootnode -writeaddress -nodekey ./bootnode/boot.key)
BOOTNODE_URL="enode://${BOOTNODE_ENODE_ID}@${BOOTNODE_IP}:${BOOTNODE_PORT}"

# Base command
cmd=(
  geth
  --identity "$IDENTITY"
  --syncmode full
  --datadir "$DATADIR"
  --bootnodes "$BOOTNODE_URL"
  --networkid "$NETWORK_ID"
  --port "$P2P_PORT"
  --discovery.port "$DISC_PORT"
  --nat any
  --allow-insecure-unlock
  --ipcdisable
  --unlock "$ETHERBASE"
  --password password.txt
  --mine
  --snapshot=false
  --miner.etherbase "$ETHERBASE"
  --ethstats "$IDENTITY:$ETH_NETSTATS_SECRET@$ETH_NETSTATS_IP:$ETH_NETSTATS_PORT"
)

if [[ "$JSONRPC_TRANSPORT" == "http" ]]; then
  echo "🌐 Enabling HTTP JSON-RPC on ${JSONRPC_ADDR}:${JSONRPC_PORT}"
  cmd+=(--http --http.addr "$JSONRPC_ADDR" --http.port "$JSONRPC_PORT" --http.api "eth,net,web3,personal,miner,admin,clique" --http.corsdomain "*")
else
  echo "🌐 Enabling WebSocket JSON-RPC on ${JSONRPC_ADDR}:${JSONRPC_PORT}"
  cmd+=(--ws --ws.addr "$JSONRPC_ADDR" --ws.port "$JSONRPC_PORT" --ws.api "eth,net,web3,personal,miner,admin,clique")
fi

# echo "[INFO] Executing command: ${cmd[*]}"

echo "------------------------------------------------------------------"
echo "Node:          $IDENTITY"
echo "NetworkID:     $NETWORK_ID"
echo "P2P port:      $P2P_PORT (disc: $DISC_PORT)"
echo "Bootnode:      $BOOTNODE_URL"
echo "RPC:           $JSONRPC_TRANSPORT://${JSONRPC_ADDR}:${JSONRPC_PORT}"
echo "Datadir:       $DATADIR"
echo "Etherbase:     $ETHERBASE"
echo "EthStats:      $ETH_NETSTATS_IP:$ETH_NETSTATS_PORT (secret set)"
echo "------------------------------------------------------------------"

if [[ "${SAVE_LOGS:-n}" =~ ^[Yy]$ ]]; then
  mkdir -p logs
  cmd+=(--verbosity 3)
  echo "📝 Logging to logs/${IDENTITY}.log"
  "${cmd[@]}" >> "logs/${IDENTITY}.log" 2>&1
else
  "${cmd[@]}"
fi