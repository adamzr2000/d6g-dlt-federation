#!/bin/bash

docker run \
        -it \
        --name node1 \
        --rm \
        --net host \
        -v ./../../config/dlt/genesis/genesis_2_validators.json:/dlt-network/genesis.json \
        -v ./../../config/dlt/node1.env:/dlt-network/.env \
        dlt-node:latest


