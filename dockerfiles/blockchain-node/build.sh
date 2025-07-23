#!/bin/bash

# Default consensus algorithm
CONSENSUS="poa"

# Parse the --consensus flag
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --consensus) CONSENSUS="$2"; shift ;; # Capture the consensus type
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# Check if the consensus type is valid
if [[ "$CONSENSUS" != "poa" && "$CONSENSUS" != "pow" ]]; then
    echo "Invalid consensus type. Please specify either 'poa' or 'pow'."
    exit 1
fi

# Define image name
IMAGE_NAME="blockchain-node:geth-$CONSENSUS"

echo "Building $IMAGE_NAME Docker image."

docker build -t "$IMAGE_NAME" -f Dockerfile-geth-$CONSENSUS .