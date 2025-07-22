#!/bin/bash

# Define image name
IMAGE_NAME="eth-netstats"

# Assemble Docker image
echo "Building $IMAGE_NAME Docker image."

docker build -t "$IMAGE_NAME" .