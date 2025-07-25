#!/bin/sh

# Function to display usage information
usage() {
    echo "Usage: $0 -v <vni> -n <destination_network>"
    echo "  -v <vni>                VXLAN Network Identifier (VNI)"
    echo "  -n <destination_network> Network routed through the VXLAN tunnel (e.g., 192.168.2.0/24)"
    exit 1
}

# Parse input arguments
while getopts "v:n:" opt; do
    case ${opt} in
        v ) vni=$OPTARG ;;
        n ) destination_network=$OPTARG ;;
        * ) usage ;;
    esac
done

# Check if required arguments are provided
if [ -z "$vni" ] || [ -z "$destination_network" ]; then
    usage
fi

# Define VXLAN interface name
vxlan_iface="vxlan$vni"

echo -e "\nRemoving route '$destination_network' associated with VXLAN interface '$vxlan_iface'..."
ip route del $destination_network dev $vxlan_iface

# Delete the VXLAN network interface
echo -e "\nDeleting VXLAN interface '$vxlan_iface'..."
ip link del $vxlan_iface

echo -e "\nVXLAN tunnel cleanup complete."
