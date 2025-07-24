# utils.py

import re
import logging
import csv
import ipaddress
import requests
import yaml
from pathlib import Path

# Get the logger defined in main.py
logger = logging.getLogger(__name__)

def extract_service_requirements(formatted_requirements: str) -> dict:
    requirements_dict = {}
    
    # Split the string by ';' and process each key-value pair
    for entry in formatted_requirements.split(";"):
        entry = entry.strip()
        if "=" in entry:  # Ensure valid key-value pairs
            key, value = entry.split("=", 1)
            key = key.strip()
            value = value.strip()
            
            # Convert numeric values from string to appropriate type
            if value.isdigit():
                value = int(value)
            elif value.replace(".", "", 1).isdigit():  # Handle float values
                value = float(value)
            elif value.lower() == "none":  # Convert 'None' string to Python None
                value = None
            
            requirements_dict[key] = value
    
    return requirements_dict


def extract_service_endpoint(endpoint):
    match = re.match(r'ip_address=(.*?);vxlan_id=(.*?);vxlan_port=(.*?);federation_net=(.*)', endpoint)

    if match:
        ip_address = match.group(1)
        vxlan_id = match.group(2)
        vxlan_port = match.group(3)
        federation_net = match.group(4)
        return ip_address, vxlan_id, vxlan_port, federation_net
    else:
        logger.error(f"Invalid endpoint format: {endpoint}")
        return None, None, None, None

# Function to fetch and parse the topology information
def fetch_topology_info(url, provider):
    """
    Fetch and parse topology information from a given URL.
    """
    try:
        # Send GET request to the specified URL
        response = requests.get(url)
        
        # Check if the request was successful
        if response.status_code == 200:
            # Parse the YAML response
            network_info = yaml.safe_load(response.text)
            
            # Extract relevant information
            if 'network_info' in network_info:
                network_data = network_info['network_info']
                
                # Prepare result dictionary
                result = {
                    "protocol": network_data.get("protocol"),
                    "vxlan_id": network_data.get("vxlan_id"),
                    "udp_port": network_data.get("udp_port"),
                    "consumer_tunnel_endpoint": network_data.get("consumer_tunnel_endpoint"),
                    "provider_tunnel_endpoint": network_data.get("provider_tunnel_endpoint"),
                }
                
                # Conditional fields based on the provider flag
                if provider:
                    result["provider_subnet"] = network_data.get("provider_subnet")
                    result["provider_router_endpoint"] = network_data.get("provider_router_endpoint")
                else:
                    result["consumer_subnet"] = network_data.get("consumer_subnet")
                    result["consumer_router_endpoint"] = network_data.get("consumer_router_endpoint")
                
                return result
            else:
                return {"error": "Network information not found in the response."}
        else:
            return {"error": "Unable to fetch data from the URL.", "status_code": response.status_code}
    
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


# Function to fetch and print the raw YAML response
def fetch_raw_yaml(url):
    try:
        # Send GET request to the specified URL
        response = requests.get(url)
        
        # Check if the request was successful
        if response.status_code == 200:
            # Print the entire raw YAML content
            print(response.text)
        else:
            print(f"Error: Unable to fetch data from the URL. Status code: {response.status_code}")
    
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

def create_csv_file(file_path, header, data):
    base_dir = Path(file_path)
    base_dir.mkdir(parents=True, exist_ok=True)

    # Detect next test index based on existing files
    existing_files = list(base_dir.glob("federation_events_test_*.csv"))
    indices = [
        int(f.stem.split('_')[-1]) for f in existing_files
        if f.stem.split('_')[-1].isdigit()
    ]
    next_index = max(indices) + 1 if indices else 1

    file_name = base_dir / f"federation_events_test_{next_index}.csv"

    with open(file_name, 'w', encoding='UTF8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data)

def extract_ip_from_url(url) -> str:
    pattern = r'http://(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+'
    match = re.match(pattern, url)
    
    if match:
        return match.group(1)
    else:
        return None

def create_smaller_subnet(original_cidr, identifier, prefix_length=24) -> str:
    ip, _ = original_cidr.split('/')
    octets = ip.split('.')
    octets[2] = identifier  # Modify the third octet with the identifier
    new_ip = '.'.join(octets)
    new_cidr = f"{new_ip}/{prefix_length}"
    return new_cidr

def get_ip_range_from_subnet(subnet: str) -> str:
    try:
        # Parse the subnet
        network = ipaddress.ip_network(subnet)

        # Get the first and last IP address in the range
        first_ip = str(network.network_address + 1)  # Skip the network address
        last_ip = str(network.broadcast_address - 1)  # Skip the broadcast address

        # Return the range in "first_ip-last_ip" format
        return f"{first_ip}-{last_ip}"
    
    except ValueError as e:
        return f"Invalid subnet: {e}"

def validate_endpoint(endpoint: str) -> bool:
    """
    Validates the 'endpoint' string.
    Expected format: 'ip_address=<ip_address>;vxlan_id=<vxlan_id>;vxlan_port=<vxlan_port>;federation_net=<federation_net>'
    """
    pattern = r'^ip_address=\d{1,3}(\.\d{1,3}){3};vxlan_id=\d+;vxlan_port=\d+;federation_net=\d{1,3}(\.\d{1,3}){3}/\d+$'
    if re.match(pattern, endpoint):
        return True
    return False

def configure_router(api_url, sudo_password, local_ip, remote_ip, interface, vni, dst_port, destination_network, tunnel_ip, gateway_ip):
    payload = {
        "sudo_password": sudo_password,
        "local_ip": local_ip,
        "remote_ip": remote_ip,
        "interface": interface,
        "vni": vni,
        "dst_port": dst_port,
        "destination_network": destination_network,
        "tunnel_ip": tunnel_ip,
        "gateway_ip": gateway_ip
    }
    response = requests.post(f"{api_url}/configure_router", json=payload)
    return response.json()

def remove_vxlan(api_url, sudo_password, vni, destination_network):
    payload = {
        "sudo_password": sudo_password,
        "vni": vni,
        "destination_network": destination_network
    }
    response = requests.post(f"{api_url}/remove_vxlan", json=payload)
    return response.json()

def test_connectivity(api_url, target):
    payload = {"target": target}
    response = requests.post(f"{api_url}/test_connectivity", json=payload)
    return response.json()
