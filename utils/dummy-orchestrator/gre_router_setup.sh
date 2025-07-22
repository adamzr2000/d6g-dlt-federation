#!/bin/sh

# Function to display usage information
usage() {
    echo "Usage: $0 -l <local_ip> -r <remote_ip> -i <dev_interface> -a <tunnel_ip> -n <destination_network>"
    echo "  -l <local_ip>            Local IP address"
    echo "  -r <remote_ip>           Remote IP address"
    echo "  -i <dev_interface>       Physical device interface (e.g., eth0)"
    echo "  -a <tunnel_ip>           IP address for the GRE tunnel interface (must include CIDR, e.g., 172.16.0.1/30)"
    echo "  -n <destination_network> Network to route through the GRE tunnel in CIDR format (e.g., 192.168.2.0/24)"
    exit 1
}

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
while getopts "l:r:i:a:n:" opt; do
    case ${opt} in
        l ) local_ip=$OPTARG ;;
        r ) remote_ip=$OPTARG ;;
        i ) dev_interface=$OPTARG ;;
        a ) tunnel_ip=$OPTARG ;;
        n ) destination_network=$OPTARG ;;
        * ) usage ;;
    esac
done

# Check if all required arguments are provided
if [ -z "$local_ip" ] || [ -z "$remote_ip" ] || [ -z "$dev_interface" ] || [ -z "$tunnel_ip" ] || [ -z "$destination_network" ]; then
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

# Default GRE interface name
gre_interface="gre1"

# Create a GRE tunnel interface
echo -e "\nCreating GRE tunnel interface '$gre_interface' with parameters:"
echo "  Local IP: $local_ip"
echo "  Remote IP: $remote_ip"
echo "  Device Interface: $dev_interface"
echo "  Tunnel IP: $tunnel_ip"

# Enable IP forwarding and load required kernel modules
echo 1 > /proc/sys/net/ipv4/ip_forward
echo "Enabling IP forwarding..."

ip tunnel add $gre_interface mode gre remote $remote_ip local $local_ip ttl 255

# Assign the provided IP address to the GRE interface
echo -e "\nAssigning IP address '$tunnel_ip' to GRE interface '$gre_interface'..."
ip addr add $tunnel_ip dev $gre_interface

# Enable the GRE tunnel interface
echo -e "\nEnabling the GRE interface '$gre_interface'..."
ip link set $gre_interface up

# Add the specified route through the GRE interface
echo -e "\nAdding route '$destination_network' through GRE interface '$gre_interface'..."
ip route add $destination_network dev $gre_interface

# Add iptables rules to allow GRE traffic
echo -e "\nConfiguring iptables to allow GRE traffic..."
iptables -A INPUT -p gre -j ACCEPT
iptables -A OUTPUT -p gre -j ACCEPT

# Verify the GRE interface and route
echo -e "\nChecking the GRE interface and routes:"
ip a show dev $gre_interface
ip route show | grep $destination_network
