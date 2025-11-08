#!/bin/bash

container_image="k8s-orchestrator"

docker run \
    -d \
    --rm \
    --name $container_image \
    --privileged \
    -p 6665:8000 \
    -v "$(pwd)/app":/app \
    -v "./config:/config" \
    $container_image:latest
