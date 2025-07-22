#!/bin/bash

# Assemble docker image. 
echo 'Deleting DLT network'

docker compose -f local-docker-compose.yml down

