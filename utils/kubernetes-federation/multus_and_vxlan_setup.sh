#!/bin/bash

# Function to display usage information
usage() {
    echo "Usage: $0 -l <local_ip> -r <remote_ip> -i <interface_name> -v <vxlan_id> -p <dst_port> -s <subnet> -d <ip_range> [-n <network_name>]"
    echo "  -l <local_ip>        Local IP address"
    echo "  -r <remote_ip>       Remote IP address"
    echo "  -i <interface_name>  Interface name (e.g., ens3)"
    echo "  -v <vxlan_id>        VXLAN ID"
    echo "  -p <dst_port>        Destination port"
    echo "  -s <subnet>          Subnet for Kubernetes pods (e.g., 10.0.0.0/16)"
    echo "  -d <ip_range>        IP range in format startRange-endRange (e.g., 10.0.1.2-10.0.1.50)"
    echo "  -n <network_name>    Name of the Multus network (default: federation-net)"
    exit 1
}

# Function to validate IP address format
validate_ip() {
    local ip=$1
    local valid_ip_regex="^([0-9]{1,3}\.){3}[0-9]{1,3}$"
    if [[ $ip =~ $valid_ip_regex ]]; then
        IFS='.' read -r -a octets <<< "$ip"
        for octet in "${octets[@]}"; do
            if (( octet < 0 || octet > 255 )); then
                return 1
            fi
        done
        return 0
    else
        return 1
    fi
}

# Parse input arguments
network_name="federation-net"
while getopts "l:r:i:v:p:s:d:n:" opt; do
    case ${opt} in
        l ) local_ip=$OPTARG ;;
        r ) remote_ip=$OPTARG ;;
        i ) dev_interface=$OPTARG ;;
        v ) vxlan_id=$OPTARG ;;
        p ) dst_port=$OPTARG ;;
        s ) subnet=$OPTARG ;;
        d ) ip_range=$OPTARG ;;
        n ) network_name=$OPTARG ;;
        * ) usage ;;
    esac
done

# Validate input
if [ -z "$local_ip" ] || [ -z "$remote_ip" ] || [ -z "$dev_interface" ] || [ -z "$vxlan_id" ] || [ -z "$dst_port" ] || [ -z "$subnet" ] || [ -z "$ip_range" ]; then
    usage
fi

# Extract rangeStart and rangeEnd from ip_range
IFS='-' read -r rangeStart rangeEnd <<< "$ip_range"

# Validate IP address format
if ! validate_ip $local_ip || ! validate_ip $remote_ip || ! validate_ip $rangeStart || ! validate_ip $rangeEnd; then
    echo "Invalid IP address format in input arguments"
    exit 1
fi


# This script sets up a Kubernetes network with Multus CNI and a VXLAN network interface.

# Step 1: Create a VXLAN network interface.
vxlan_iface="vxlan$vxlan_id"
echo -e "\nCreating VXLAN network interface '$vxlan_iface' with parameters - VXLAN ID: $vxlan_id, Local IP: $local_ip, Remote IP: $remote_ip, Destination Port: $dst_port, Device Interface: $dev_interface"
sudo ip link add $vxlan_iface type vxlan id $vxlan_id local $local_ip remote $remote_ip dstport $dst_port dev $dev_interface

# Step 2: Enable the VXLAN network interface.
# echo -e "\nEnabling the VXLAN interface '$vxlan_iface'..."
sudo ip link set $vxlan_iface up

# Step 3: Verify that the VXLAN interface is correctly configured.
# echo -e "\nChecking the list of interfaces for '$vxlan_iface'..."
# ip a | grep vxlan

# Step 4: Create the NetworkAttachmentDefinition for Multus
cat <<EOF | kubectl apply -f -
apiVersion: "k8s.cni.cncf.io/v1"
kind: NetworkAttachmentDefinition
metadata:
  name: $network_name
spec:
  config: '{
    "cniVersion": "0.3.1",
    "type": "macvlan",
    "master": "$vxlan_iface", 
    "mode": "bridge",
    "ipam": {
      "type": "host-local",
      "subnet": "$subnet", 
      "rangeStart": "$rangeStart", 
      "rangeEnd": "$rangeEnd" 
    }
  }'
EOF

echo -e "\nFederation completed successfully."
