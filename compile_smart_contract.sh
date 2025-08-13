#!/bin/bash

# Construct the command for the container
START_CMD="./deploy.sh"

docker run \
  -it \
  --rm \
  --name truffle \
  --network host \
  -v "$(pwd)/smart-contracts":/smart-contracts \
  truffle:latest \
  sh -c "cd /smart-contracts && truffle compile"