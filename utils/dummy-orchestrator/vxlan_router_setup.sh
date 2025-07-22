#!/bin/sh

# Function to display usage information
usage() {
    echo "Usage: $0 -l <local_ip> -r <remote_ip> -i <interface_name> -v <vni> -p <dst_port> -n <destination_network> -a <tunnel_ip> -g <gateway_ip>"
    echo "  -l <local_ip>           Local IP address"
    echo "  -r <remote_ip>          Remote IP address"
    echo "  -i <interface_name>     Physical interface name (e.g., enp0s3)"
    echo "  -v <vni>                VXLAN Network Identifier (VNI)"
    echo "  -p <dst_port>           VXLAN UDP destination port"
    echo "  -n <destination_network> Network to route through the VXLAN tunnel in CIDR format (e.g., 192.168.2.0/24)"
    echo "  -a <tunnel_ip>          IP address for the VXLAN tunnel interface (must include CIDR, e.g., 172.16.0.1/30)"
    echo "  -g <gateway_ip>         Gateway IP address for the route"
    exit 1
}

# Function to validate IP address format
validate_ip() {
    local ip=$1
    local valid_ip_regex="^[0-9]{1,3}(\.[0-9]{1,3}){3}$"
    if echo "$ip" | grep -Eq "$valid_ip_regex"; then
        for octet in $(echo "$ip" | tr '.' ' '); do
            if [ "$octet" -lt 0 ] || [ "$octet" -gt 255 ]; then
                return 1
            fi
        done
        return 0
    else
        return 1
    fi
}

# Parse input arguments
while getopts "l:r:i:v:p:n:a:g:" opt; do
    case ${opt} in
        l ) local_ip=$OPTARG ;;
        r ) remote_ip=$OPTARG ;;
        i ) dev_interface=$OPTARG ;;
        v ) vni=$OPTARG ;;
        p ) dst_port=$OPTARG ;;
        n ) destination_network=$OPTARG ;;
        a ) tunnel_ip=$OPTARG ;;
        g ) gateway_ip=$OPTARG ;;
        * ) usage ;;
    esac
done

# Check if all required arguments are provided
if [ -z "$local_ip" ] || [ -z "$remote_ip" ] || [ -z "$dev_interface" ] || \
   [ -z "$vni" ] || [ -z "$destination_network" ] || [ -z "$tunnel_ip" ] || [ -z "$gateway_ip" ]; then
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

if ! validate_ip $gateway_ip; then
    echo "Invalid gateway IP address format: $gateway_ip"
    exit 1
fi

# Enable IP forwarding and load required kernel modules
echo 1 > /proc/sys/net/ipv4/ip_forward
echo "Enabling IP forwarding..."
# modprobe vxlan
# modprobe br_netfilter

# Create the VXLAN network interface
vxlan_iface="vxlan$vni"
echo -e "\nCreating VXLAN network interface '$vxlan_iface' with parameters:"
echo "  VNI: $vni"
echo "  Local IP: $local_ip"
echo "  Remote IP: $remote_ip"
echo "  Destination Port: $dst_port"
echo "  Device Interface: $dev_interface"
echo "  Tunnel IP: $tunnel_ip"

ip link add $vxlan_iface type vxlan id $vni local $local_ip remote $remote_ip dstport $dst_port dev $dev_interface

# Assign the provided IP address to the VXLAN interface
echo -e "\nAssigning IP address '$tunnel_ip' to VXLAN interface '$vxlan_iface'..."
ip addr add $tunnel_ip dev $vxlan_iface

# Enable the VXLAN network interface
echo -e "\nEnabling the VXLAN interface '$vxlan_iface'..."
ip link set $vxlan_iface up

# Add the specified route through the VXLAN interface
echo -e "\nAdding route '$destination_network' through VXLAN interface '$vxlan_iface' with gateway '$gateway_ip'..."
ip route add $destination_network dev $vxlan_iface via $gateway_ip

# Verify the VXLAN interface setup
echo -e "\nVerifying VXLAN interface configuration:"
ip a show dev $vxlan_iface
ip route show | grep $destination_network

echo -e "\nVXLAN and bridge setup complete."
