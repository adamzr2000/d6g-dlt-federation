#!/bin/bash

docker run \
        -it \
        --name node1 \
        --rm \
        --net host \
        -v ./scripts/genesis.json:/dlt-network/genesis.json \
        -v ./scripts/password.txt:/dlt-network/password.txt \
        -v ./scripts/node1_start.sh:/dlt-network/node1_start.sh \
        -v ./../../config/dlt/node1.env:/dlt-network/node1.env \
        dlt-node:latest


