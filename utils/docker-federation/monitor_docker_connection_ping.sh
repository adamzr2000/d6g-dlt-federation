#!/bin/bash

# Check if IP address argument is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <ip_address>"
  exit 1
fi

IP_ADDRESS=$1

# Run the Docker command
sudo docker run --name monitor-connection -it --rm --network federation-net alpine sh -c "
  echo 'Pinging IP address $IP_ADDRESS';
  ping $IP_ADDRESS
"

