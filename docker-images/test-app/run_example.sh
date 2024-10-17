#!/bin/bash

docker run -d --rm -p 5000:5000 --name test-service --env SERVER_ID="Provider domain" test-app
