#!/bin/bash

# Define image name
IMAGE_NAME="blockchain-manager"

# Assemble Docker image
echo "Building $IMAGE_NAME Docker image."

docker build -t "$IMAGE_NAME" .