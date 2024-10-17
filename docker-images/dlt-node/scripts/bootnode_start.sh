#!/bin/bash

# Read environment variables from bootnode specific .env file
source bootnode.env

# Start the bootnode service.
bootnode -nodekey ./bootnode/boot.key -verbosity 9 -addr $BOOTNODE_IP:$BOOTNODE_PORT
