#!/bin/bash

container_image="k8s-orchestrator"

echo "Building $container_image docker image."
sudo docker build . -t $container_image
