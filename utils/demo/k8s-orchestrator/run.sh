#!/bin/bash

container_image="k8s-orchestrator"

docker run \
    -d \
    --rm \
    --name $container_image \
    --privileged \
    -v "$(pwd)/app":/app \
    $container_image:latest
