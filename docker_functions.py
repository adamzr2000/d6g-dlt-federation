# docker_functions.py
import docker
import logging
import subprocess
from docker.errors import NotFound, APIError

# Get the logger defined in main.py
logger = logging.getLogger(__name__)

def verify_docker_connection():
    """
    Verifies the connection to the Docker daemon.

    Returns:
        docker.DockerClient: The Docker client object if the connection is successful, otherwise None.
    """
    try:
        client = docker.from_env()
        version_info = client.version()
        # logger.info(f"Docker daemon connected - Version: {version_info['Version']}")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Docker daemon: {e}")
        return None

def deploy_docker_service(image, service_name, network="bridge", replicas=1, env_vars=None, container_port=None, start_host_port=None, command=None):
    """
    Deploys Docker containers based on the provided parameters.

    Args:
        image (str): The Docker image to use.
        service_name (str): The base name for the containers.
        network (str, optional): The Docker network to connect the containers to. Default to "bridge".
        replicas (int, optional): The number of container replicas to deploy. Default to 1.
        env_vars (dict, optional): Environment variables to set in the containers. Default to None.
        container_port (int, optional): The port inside the container to map to the host. Default to None.
        start_host_port (int, optional): The starting port on the host to map to container ports. Default to None.
        command (str, optional): The command to execute inside the container. Default to None.

    Returns:
        list: A list of deployed container objects.
    """    
    containers = []
    client = verify_docker_connection()
    if client is None:
        return []

    try:
        for i in range(replicas):
            container_name = f"{service_name}_{i+1}"

            # Set ports only if container_port and start_host_port are provided
            ports = {}
            if container_port and start_host_port:
                ports = {f'{container_port}/tcp': start_host_port + i}

            # Run container with environment variables and command if provided
            container = client.containers.run(
                image=image,
                name=container_name,
                network=network,
                detach=True,
                auto_remove=True,
                ports=ports if ports else None,
                environment=env_vars if env_vars else None,
                command=command if command else None
            )
            containers.append(container)

        # Wait for containers to be ready
        for container in containers:
            while True:
                container.reload()
                if container.status == "running":
                    logger.info(f"Container {container_name} deployed successfully.")
                    break
                time.sleep(1)

        return containers
    except Exception as e:
        logger.error(f"Failed to deploy containers: {e}")
        return []

def delete_docker_service(service_name):
    """
    Deletes Docker containers with the specified service name.

    Args:
        service_name (str): The base name of the containers to delete.

    Returns:
        bool: True if successful, False if an error occurred.
    """
    client = verify_docker_connection()
    if client is None:
        return False  # Docker connection already failed and logged, return failure

    try:
        containers = client.containers.list(all=True, filters={"name": service_name})
        if not containers:
            logger.warning(f"No containers found with service name: {service_name}")
            return False  # No containers found to delete

        for container in containers:
            container_name = container.name
            container.remove(force=True)
            
            # Wait for the container to be removed
            while True:
                remaining_containers = client.containers.list(all=True, filters={"name": container_name})
                if not remaining_containers:
                    logger.info(f"Container {container_name} deleted successfully.")
                    break

        return True  # Successfully deleted all containers

    except Exception as e:
        logger.error(f"Failed to delete containers for service {service_name}: {e}")
        return False  # Indicate failure


def scale_docker_service(service_name, action, replicas):
    """
    Scales the number of Docker containers up or down.

    Args:
        service_name (str): The base name of the containers to scale.
        action (str): The action to perform ('up' to increase replicas, 'down' to decrease replicas).
        replicas (int): The number of replicas to add or remove.
    
    Returns:
        None
    """    
    client = verify_docker_connection()
    if client is None:
        return

    try:
        existing_containers = client.containers.list(all=True, filters={"name": service_name})
        current_replicas = len(existing_containers)
        
        if action.lower() == "up":
            new_replicas = current_replicas + replicas
            for i in range(current_replicas, new_replicas):
                container_name = f"{service_name}_{i+1}"
                container = client.containers.run(
                    image=existing_containers[0].image.tags[0],
                    name=container_name,
                    network=existing_containers[0].attrs['HostConfig']['NetworkMode'],
                    detach=True
                )
                logger.info(f"Container {container_name} deployed successfully.")
        elif action.lower() == "down":
            new_replicas = max(0, current_replicas - replicas)
            for i in range(current_replicas - 1, new_replicas - 1, -1):
                container_name = f"{service_name}_{i+1}"
                container = client.containers.get(container_name)
                container.remove(force=True)
                logger.info(f"Container {container_name} deleted successfully.")
        else:
            logger.error("Invalid action. Use 'up' or 'down'.")
            return
    except Exception as e:
        logger.error(f"Failed to scale containers: {e}")

def get_docker_container_ips(service_name):
    """
    Retrieves the IP addresses of Docker containers based on the service name.

    Args:
        service_name (str): The base name of the containers.

    Returns:
        dict: A dictionary with container names as keys and their IP addresses as values.
    """    
    client = verify_docker_connection()
    if client is None:
        return {}

    container_ips = {}
    try:
        containers = client.containers.list(all=True, filters={"name": service_name})
        if not containers:
            logger.error(f"No containers found with service name: {service_name}")
            return container_ips
        
        for container in containers:
            container.reload() 
            network_settings = container.attrs['NetworkSettings']['Networks']
            for network_name, network_data in network_settings.items():
                ip_address = network_data['IPAddress']
                container_ips[container.name] = ip_address
        return container_ips
    except Exception as e:
        logger.error(f"Failed to get IP addresses for containers: {e}")
        return {}

def attach_docker_container_to_network(container_name, network_name):
    """
    Attaches a Docker container to a specified network.

    Args:
        container_name (str): The name of the container to attach.
        network_name (str): The name of the network to attach the container to.
    Returns:
        None
    """    
    client = verify_docker_connection()
    if client is None:
        return

    try:
        container = client.containers.get(container_name)
    except docker.errors.NotFound:
        logger.error(f"Container '{container_name}' not found.")
        return

    try:
        network = client.networks.get(network_name)
    except docker.errors.NotFound:
        logger.error(f"Network '{network_name}' not found.")
        return

    try:
        network.connect(container)
        logger.info(f"Container '{container_name}' successfully attached to network '{network_name}'.")
    except Exception as e:
        logger.error(f"An error occurred while attaching container '{container_name}' to network '{network_name}': {e}")

def execute_command_in_docker_container(container_name, command):
    """
    Executes a command inside a specified Docker container and returns the response.

    Args:
        container_name (str): The name of the container.
        command (str): The command to execute.

    Returns:
        dict: The response with the output and exit code.
    """   
    client = verify_docker_connection()
    if client is None:
        return
    try:
        container = client.containers.get(container_name)
    except NotFound:
        logger.error(f"Container '{container_name}' not found.")
        return
    except APIError as e:
        logger.error(f"Error retrieving container '{container_name}': {str(e)}")
        return

    try:
        result = container.exec_run(command, tty=True)
        if result.exit_code == 0:
            output = result.output.decode('utf-8')
            return output
        else:
            logger.error(f"Failed to execute command '{command}' in container '{container_name}'.")
            print(result.output.decode('utf-8'))
    except APIError as e:
        logger.error(f"Error executing command '{command}' in container '{container_name}': {str(e)}")

def configure_docker_network_and_vxlan(local_ip, remote_ip, interface_name, vxlan_id, dst_port, subnet, ip_range, sudo_password='netcom;', docker_net_name='federation-net'):
    """
    Configures Docker network and VXLAN on the host machine.

    Args:
        local_ip (str): The local IP address.
        remote_ip (str): The remote IP address.
        interface_name (str): The network interface name.
        vxlan_id (str): The VXLAN ID. 
        dst_port (str): The VXLAN destination port.
        subnet (str): The Docker subnet.
        ip_range (str): The IP range for the Docker network.
        sudo_password (str): The sudo password for executing commands. 
        docker_net_name (str): The name of the Docker network. 

    Returns:
        None
    """
    script_path = './utils/docker-federation/docker_host_and_vxlan_setup.sh'
    command = [
        'sudo', '-S', 'bash', script_path,
        '-l', local_ip,
        '-r', remote_ip,
        '-i', interface_name,
        '-v', vxlan_id,
        '-p', dst_port,
        '-s', subnet,
        '-d', ip_range,
        '-n', docker_net_name
    ]
    
    try:
        # Run the command with sudo and password
        result = subprocess.run(command, input=sudo_password.encode() + b'\n', check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(result.stdout.decode())
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error occurred while running the script: {e.stderr.decode()}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")

def delete_docker_network_and_vxlan(sudo_password='netcom;', vxlan_id='200', docker_net_name='federation-net'):
    """
    Deletes Docker network and VXLAN configuration from the host machine.

    Args:
        sudo_password (str, optional): The sudo password for executing commands. 
        vxlan_id (str, optional): The VXLAN ID. Defaults to '200'.
        docker_net_name (str, optional): The name of the Docker network. Defaults to 'federation-net'.

    Returns:
        None
    """    
    script_path = './utils/docker-federation/clean_docker_host_and_vxlan_setup.sh'
    command = [
        'sudo', '-S', 'bash', script_path,
        '-n', docker_net_name,
        '-v', vxlan_id
    ]
    try:
        # Run the command with sudo and password
        result = subprocess.run(command, input=sudo_password.encode() + b'\n', check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(result.stdout.decode())
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error occurred while running the script: {e.stderr.decode()}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")