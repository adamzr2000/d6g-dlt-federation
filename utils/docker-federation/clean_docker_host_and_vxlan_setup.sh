#!/bin/bash

# Function to display usage information
usage() {
    echo "Usage: $0 [-n <network_name>] [-v <vxlan_id>]"
    echo "  -n <network_name>    Docker network name (default: federation-net)"
    echo "  -v <vxlan_id>        VXLAN ID (default: 200)"
    exit 1
}

# Parse input arguments
network_name="federation-net"
vxlan_id="200"
while getopts "n:v:" opt; do
    case ${opt} in
        n ) network_name=$OPTARG ;;
        v ) vxlan_id=$OPTARG ;;
        * ) usage ;;
    esac
done

# Step 1: Remove the Docker network.
echo -e "\nRemoving Docker network '$network_name'..."
sudo docker network rm $network_name

# Step 2: Remove the VXLAN network interface.
vxlan_iface="vxlan$vxlan_id"
echo -e "\nRemoving VXLAN network interface '$vxlan_iface'..."
sudo ip link set $vxlan_iface down
sudo ip link del $vxlan_iface

echo -e "\nCleanup completed successfully."
