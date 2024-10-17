# utility_functions.py

import re
import logging
import csv
import ipaddress

# Get the logger defined in main.py
logger = logging.getLogger(__name__)

def extract_service_requirements(requirements):
    """
    Extracts service and replicas from the requirements string.

    Args:
        requirements (str): String containing service and replicas in the format "service=A;replicas=B".

    Returns:
        tuple: A tuple containing extracted service and replicas.
    """
    match = re.match(r'service=(.*?);replicas=(.*)', requirements)

    if match:
        requested_service = match.group(1)
        replicas = match.group(2)
        return requested_service, replicas
    else:
        logger.error(f"Invalid requirements format: {requirements}")
        return None, None

def extract_service_endpoint(endpoint):
    """
    Extracts the IP address, VXLAN ID, VXLAN port, and Docker/K8s federation net from the endpoint string.

    Args:
        endpoint (str): String containing the endpoint information in the format "ip_address=A;vxlan_id=B;vxlan_port=C;federation_net=D".

    Returns:
        tuple: A tuple containing the extracted IP address, VXLAN ID, VXLAN port, and Docker/K8s subnet.
    """
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

def create_csv_file(role, header, data):
    """
    Creates a CSV file to store federation events based on the role (Consumer or Provider).

    Args:
        role (str): The role for which the file is created (e.g., 'consumer', 'provider').
        header (list): The header row for the CSV file.
        data (list): The data rows to be written to the CSV file.

    Returns:
        None        
    """
    base_dir = Path("experiments") / role
    base_dir.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists
    
    existing_files = list(base_dir.glob("federation_events_{}_test_*.csv".format(role)))
    indices = [int(f.stem.split('_')[-1]) for f in existing_files if f.stem.split('_')[-1].isdigit()]
    next_index = max(indices) + 1 if indices else 1

    file_name = base_dir / f"federation_events_{role}_test_{next_index}.csv"

    with open(file_name, 'w', encoding='UTF8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)  # Write the header
        writer.writerows(data)  # Write the data

    logger.info(f"Data saved to {file_name}")

def extract_ip_from_url(url) -> str:
    """
    Extracts the IP address from a given URL.

    Args:
        url (str): The URL containing the IP address.

    Returns:
        str: The extracted IP address, or None if not found.
    """
    pattern = r'http://(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+'
    match = re.match(pattern, url)
    
    if match:
        return match.group(1)
    else:
        return None

def create_smaller_subnet(original_cidr, identifier, prefix_length=24) -> str:
    """
    Creates a smaller subnet by modifying the third octet of the original CIDR IP address.
    
    Args:
        original_cidr (str): The original CIDR notation IP address.
        identifier (str): A generic identifier to use for the third octet of the subnet.
        prefix_length (int, optional): The prefix length for the new subnet (default is /24).
    
    Returns:
        str: The new CIDR notation IP address with the specified prefix length.
    """
    ip, _ = original_cidr.split('/')
    octets = ip.split('.')
    octets[2] = identifier  # Modify the third octet with the identifier
    new_ip = '.'.join(octets)
    new_cidr = f"{new_ip}/{prefix_length}"
    return new_cidr

def get_ip_range_from_subnet(subnet: str) -> str:
    """
    Takes a network subnet in CIDR notation and returns the IP range in the format "start_ip-end_ip".

    Args:
        subnet (str): The network subnet in CIDR notation (e.g., '10.0.0.0/24').

    Returns:
        str: The IP range in the format "start_ip-end_ip".
    """
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

def validate_requirements(requirements: str) -> bool:
    """
    Validates the 'requirements' string.
    Expected format: 'service=<docker_image>;replicas=<container_replicas>'
    """
    pattern = r'^service=[\w\.-]+;replicas=\d+$'
    if re.match(pattern, requirements):
        return True
    return False

def validate_endpoint(endpoint: str) -> bool:
    """
    Validates the 'endpoint' string.
    Expected format: 'ip_address=<ip_address>;vxlan_id=<vxlan_id>;vxlan_port=<vxlan_port>;federation_net=<federation_net>'
    """
    pattern = r'^ip_address=\d{1,3}(\.\d{1,3}){3};vxlan_id=\d+;vxlan_port=\d+;federation_net=\d{1,3}(\.\d{1,3}){3}/\d+$'
    if re.match(pattern, endpoint):
        return True
    return False