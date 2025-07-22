#!/bin/bash

# Function to handle the selection
handle_selection() {
    if [[ $1 =~ ^node[0-9]+$ ]]; then
        NODE_SELECTION="$1"
    else
        echo "Invalid selection: $1. Please select a valid node in the format nodeX, where X is a number."
        exit 1 # Indicates invalid selection
    fi
}


# Check if the correct number of arguments are provided
if [ $# -ne 2 ]; then
    echo "Usage: $0 <current_signer_node> <new_signer_node>"
    exit 1
fi

# Assign arguments to variables
CURRENT_SIGNER_NODE=$1
NEW_SIGNER_NODE=$2

# Handle selections
handle_selection "$CURRENT_SIGNER_NODE"
handle_selection "$NEW_SIGNER_NODE"

# Source the environment variables from the corresponding .env files, suppressing errors
source "./../config/dlt/${CURRENT_SIGNER_NODE}.env" 2>/dev/null
source "./../config/dlt/${NEW_SIGNER_NODE}.env" 2>/dev/null

# Extract the ID from the node names
CURRENT_SIGNER_ID=${CURRENT_SIGNER_NODE: -1}
NEW_SIGNER_ID=${NEW_SIGNER_NODE: -1}

# Extract the environment variables for the current signer node
ETHERBASE_CURRENT_VAR="ETHERBASE_NODE_${CURRENT_SIGNER_ID}"
IP_CURRENT_VAR="IP_NODE_${CURRENT_SIGNER_ID}"
WS_PORT_CURRENT_VAR="WS_PORT_NODE_${CURRENT_SIGNER_ID}"

ETHERBASE_CURRENT=${!ETHERBASE_CURRENT_VAR}
IP_CURRENT=${!IP_CURRENT_VAR}
WS_PORT_CURRENT=${!WS_PORT_CURRENT_VAR}

# Extract the etherbase of the new signer node
ETHERBASE_NEW_VAR="ETHERBASE_NODE_${NEW_SIGNER_ID}"
ETHERBASE_NEW=${!ETHERBASE_NEW_VAR}

# Debug: Print the retrieved environment variables
echo "Current signer node: $CURRENT_SIGNER_NODE"
echo "ETHERBASE_CURRENT: $ETHERBASE_CURRENT"
# echo "IP_CURRENT: $IP_CURRENT"
# echo "WS_PORT_CURRENT: $WS_PORT_CURRENT"

echo "New signer node: $NEW_SIGNER_NODE"
echo "ETHERBASE_NEW: $ETHERBASE_NEW"

# Check if environment variables were retrieved successfully
if [ -z "$ETHERBASE_CURRENT" ] || [ -z "$IP_CURRENT" ] || [ -z "$WS_PORT_CURRENT" ] || [ -z "$ETHERBASE_NEW" ]; then
    echo "Error: Could not retrieve necessary environment variables."
    exit 1
fi

# Construct the Geth command to add the new signer
GETH_CMD_ADD_SIGNER="geth --exec \"clique.propose('${ETHERBASE_NEW}',true)\" attach ws://${IP_CURRENT}:${WS_PORT_CURRENT}"

# Construct the Docker command to add the new signer
DOCKER_CMD_ADD_SIGNER="docker exec -it ${CURRENT_SIGNER_NODE} $GETH_CMD_ADD_SIGNER"

# Execute the Docker command to add the new signer
echo "Executing command to add new signer: $DOCKER_CMD_ADD_SIGNER"
eval "$DOCKER_CMD_ADD_SIGNER"

# # Construct the Geth command to get the list of signers
# GETH_CMD_GET_SIGNERS="geth --exec 'clique.getSigners()' attach ws://${IP_CURRENT}:${WS_PORT_CURRENT}"

# # Construct the Docker command to get the list of signers
# DOCKER_CMD_GET_SIGNERS="docker exec -it ${CURRENT_SIGNER_NODE} $GETH_CMD_GET_SIGNERS"

# # Execute the Docker command to get the list of signers
# echo "Executing command to get list of signers: $DOCKER_CMD_GET_SIGNERS"
# eval "$DOCKER_CMD_GET_SIGNERS"

echo "Signer ${ETHERBASE_NEW} added to the DLT network."
