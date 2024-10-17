#!/bin/bash

# Assemble docker image. 
echo 'Building test-app docker image.'

docker build -t test-app .

