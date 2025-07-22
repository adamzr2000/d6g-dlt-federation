#!/bin/bash

# Assemble docker image. 
echo 'Starting DLT network'

docker compose -f local-docker-compose.yml up -d

