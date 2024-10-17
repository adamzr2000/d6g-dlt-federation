#!/bin/bash

# Function to display usage information
usage() {
    echo "Usage: $0 -l <local_ip> -r <remote_ip> -i <interface_name> -v <vxlan_id> -p <dst_port> -s <subnet> -d <ip_range> [-n <network_name>]"
    echo "  -l <local_ip>        Local IP address"
    echo "  -r <remote_ip>       Remote IP address"
    echo "  -i <interface_name>  Interface name (e.g., enp0s3)"
    echo "  -v <vxlan_id>        VXLAN ID"
    echo "  -p <dst_port>        Destination port"
    echo "  -s <subnet>          Subnet for Docker network (e.g., 10.0.0.0/16)"
    echo "  -d <ip_range>        IP range for Docker network (e.g., 10.0.1.0/24)"
    echo "  -n <network_name>    Docker network name (default: federation-net)"
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

# Validate IP address format
if ! validate_ip $local_ip; then
    echo "Invalid local IP address format: $local_ip"
    exit 1
fi

if ! validate_ip $remote_ip; then
    echo "Invalid remote IP address format: $remote_ip"
    exit 1
fi

# This script sets up a Docker network and a VXLAN network interface.

# Step 1: Create a Docker network.
echo -e "\nCreating Docker network '$network_name' with subnet $subnet and IP range $ip_range..."
network_id=$(sudo docker network create --subnet $subnet --ip-range $ip_range $network_name)

# Step 2: Verify the Docker network creation and extract the bridge name from brctl show.
sudo docker network inspect $network_id > /dev/null

# Extract the bridge name associated with the created network
bridge_name=$(sudo brctl show | grep $(echo $network_id | cut -c 1-12) | awk '{print $1}')
if [ -z "$bridge_name" ]; then
    echo "Bridge name could not be retrieved."
else
    echo -e "\nSuccessfully created Docker network '$network_name' - Network ID: $network_id, Bridge Name: $bridge_name"
fi

# Step 3: Create a VXLAN network interface.
vxlan_iface="vxlan$vxlan_id"
echo -e "\nCreating VXLAN network interface '$vxlan_iface' with parameters - VXLAN ID: $vxlan_id, Local IP: $local_ip, Remote IP: $remote_ip, Destination Port: $dst_port, Device Interface: $dev_interface"
sudo ip link add $vxlan_iface type vxlan id $vxlan_id local $local_ip remote $remote_ip dstport $dst_port dev $dev_interface

# Step 4: Enable the VXLAN network interface.
# echo -e "\nEnabling the VXLAN interface '$vxlan_iface'..."
sudo ip link set $vxlan_iface up

# Step 5: Verify that the VXLAN interface is correctly configured.
# echo -e "\nChecking the list of interfaces for '$vxlan_iface'..."
# ip a | grep vxlan

# Step 6: Display the Docker bridge names and check the connectivity.
# echo -e "\nDisplaying bridge connections..."
# sudo brctl show

# Step 7: Attach the newly created VXLAN interface to the docker bridge.
echo -e "\nAttaching VXLAN interface '$vxlan_iface' to the Docker bridge '$bridge_name'..."
sudo brctl addif $bridge_name $vxlan_iface

echo -e "\nFederation completed successfully."
