# kubernetes_functions.py
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
import json
import logging
import yaml
import subprocess
import time

# Get the logger defined in main.py
logger = logging.getLogger(__name__)

def verify_kubernetes_connection(kubeconfig_path="/etc/rancher/k3s/k3s.yaml"):
    """
    Verifies the connection to the Kubernetes cluster using the specified kubeconfig file.

    Args:
        kubeconfig_path (str): Path to the kubeconfig file (default is "/etc/rancher/k3s/k3s.yaml").

    Returns:
        Kubernetes API client if the connection is successful, None otherwise.
    """
    try:
        config.load_kube_config(config_file=kubeconfig_path)
        # logger.info(f"Loaded kubeconfig from {kubeconfig_path}")
        v1 = client.VersionApi()
        version_info = v1.get_code()
        # logger.info(f"Kubernetes cluster connected - Version: {version_info.git_version}")
        return client.ApiClient()
    except ApiException as e:
        logger.error(f"Failed to connect to Kubernetes cluster: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return None

def get_kubernetes_pod_ip(pod_name, namespace="default", kubeconfig_path="/etc/rancher/k3s/k3s.yaml"):
    """
    Retrieves the IP address of a single Kubernetes Pod based on the pod name.

    Args:
        pod_name (str): The name of the Pod.
        namespace (str): The namespace where the Pod is running (default is "default").
        kubeconfig_path (str): Path to the kubeconfig file (default is "/etc/rancher/k3s/k3s.yaml").

    Returns:
        str: The IP address of the Pod, or None if the Pod is not found.
    """
    k8s_client = verify_kubernetes_connection(kubeconfig_path)
    if k8s_client is None:
        logger.error("Failed to connect to the Kubernetes cluster.")
        return None

    try:
        v1 = client.CoreV1Api()
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        pod_ip = pod.status.pod_ip
        if pod_ip:
            logger.info(f"Pod '{pod_name}' has IP: {pod_ip}")
            return pod_ip
        else:
            logger.error(f"Pod '{pod_name}' has no IP assigned.")
            return None

    except ApiException as e:
        logger.error(f"Failed to retrieve IP for Pod '{pod_name}': {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while retrieving Pod IP: {e}")
        return None


def execute_command_in_kubernetes_pod(pod_name, command, namespace="default", kubeconfig_path="/etc/rancher/k3s/k3s.yaml"):
    """
    Executes a command inside a specified Kubernetes Pod and returns the response.

    Args:
        pod_name (str): The name of the Pod.
        command (list): The command to execute (as a list of arguments).
        namespace (str): The namespace of the Pod.
        kubeconfig_path (str): Path to the kubeconfig file (default is "/etc/rancher/k3s/k3s.yaml").

    Returns:
        str: The response from the command executed inside the Pod.
    """
    k8s_client = verify_kubernetes_connection(kubeconfig_path)
    if k8s_client is None:
        logger.error("Failed to connect to the Kubernetes cluster.")
        return

    try:
        v1 = client.CoreV1Api()
        exec_command = command
        resp = stream(v1.connect_get_namespaced_pod_exec,
                             pod_name,
                             namespace,
                             command=exec_command,
                             stderr=True,
                             stdin=False,
                             stdout=True,
                             tty=False)

        return resp
    except ApiException as e:
        logger.error(f"Error executing command '{command}' in Pod '{pod_name}': {e}")
    except Exception as e:
        logger.error(f"Unexpected error while executing command in Pod '{pod_name}': {e}")


def wait_for_pod_ready(api_instance, namespace, pod_name, timeout=300):
    """
    Waits for the specified Pod to be ready within a given timeout.

    Args:
        api_instance: The CoreV1Api instance.
        namespace (str): The namespace of the Pod.
        pod_name (str): The name of the Pod.
        timeout (int): The timeout in seconds.

    Returns:
        bool: True if the Pod is ready, False otherwise.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        pod = api_instance.read_namespaced_pod(name=pod_name, namespace=namespace)
        if pod.status.phase == "Running":
            logger.info(f"Pod '{pod_name}' is ready.")
            return True
        logger.info(f"Waiting for Pod '{pod_name}' to be ready...")
        time.sleep(1)
    logger.error(f"Timeout waiting for Pod '{pod_name}' to be ready.")
    return False

def create_kubernetes_resource_from_yaml(yaml_file_path, kubeconfig_path="/etc/rancher/k3s/k3s.yaml") -> list:
    """
    Creates a Kubernetes resource (Pod, Service, Deployment) from a specified YAML file and returns
    the name of each created resource.

    Args:
        yaml_file_path (str): Path to the YAML file containing the resource configuration.
        kubeconfig_path (str): Path to the kubeconfig file (default is "/etc/rancher/k3s/k3s.yaml").

    Returns:
        list: A list of resource names that were created.
    """
    k8s_client = verify_kubernetes_connection(kubeconfig_path)
    if k8s_client is None:
        logger.error("Failed to connect to the Kubernetes cluster. Aborting resource creation.")
        return []

    created_resources = []

    try:
        with open(yaml_file_path, 'r') as file:
            resources = yaml.safe_load_all(file)
            for resource in resources:
                kind = resource.get("kind")
                namespace = resource.get("metadata", {}).get("namespace", "default")
                name = resource.get("metadata", {}).get("name")

                if kind not in ["Pod", "Service", "Deployment"]:
                    raise ValueError(f"Unsupported resource kind: {kind}")

                # Dynamic dispatch based on the kind of the resource
                if kind == "Pod":
                    resp = client.CoreV1Api().create_namespaced_pod(body=resource, namespace=namespace)
                    logger.info(f"Pod '{name}' created in namespace '{namespace}'.")

                    # Wait for the Pod to be ready
                    if not wait_for_pod_ready(client.CoreV1Api(), namespace, name):
                        raise Exception(f"Pod '{name}' creation timed out.")
                
                elif kind == "Service":
                    resp = client.CoreV1Api().create_namespaced_service(body=resource, namespace=namespace)
                    logger.info(f"Service '{name}' created in namespace '{namespace}'.")
                
                elif kind == "Deployment":
                    resp = client.AppsV1Api().create_namespaced_deployment(body=resource, namespace=namespace)
                    logger.info(f"Deployment '{name}' created in namespace '{namespace}'.")

                    # Wait for the Deployment to scale up and pods to become ready
                    if not wait_for_pod_ready(client.CoreV1Api(), namespace, name):
                        raise Exception(f"Deployment '{name}' creation timed out.")
                
                # Append the name of the created resource to the list
                created_resources.append(name)

    except ApiException as e:
        logger.error(f"API Exception when creating Kubernetes resource: {e}")
        raise
    except ValueError as e:
        logger.error(f"Value Error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during resource creation: {e}")
        raise

    # Return the list of created resource names
    return created_resources


def wait_for_pod_deletion(api_instance, namespace, pod_name, timeout=300):
    """
    Waits for the specified Pod to be deleted within a given timeout.

    Args:
        api_instance: The CoreV1Api instance.
        namespace (str): The namespace of the Pod.
        pod_name (str): The name of the Pod.
        timeout (int): The timeout in seconds.

    Returns:
        bool: True if the Pod is deleted, False if it times out.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            api_instance.read_namespaced_pod(name=pod_name, namespace=namespace)
            logger.info(f"Waiting for Pod '{pod_name}' to be deleted...")
        except ApiException as e:
            if e.status == 404:  # Pod is not found, hence deleted
                logger.info(f"Pod '{pod_name}' deleted successfully.")
                return True
        time.sleep(1)
    logger.error(f"Timeout waiting for Pod '{pod_name}' to be deleted.")
    return False

def delete_kubernetes_resource_from_yaml(yaml_file_path, kubeconfig_path="/etc/rancher/k3s/k3s.yaml"):
    """
    Deletes a Kubernetes resource (Pod, Service, Deployment) specified in a YAML file.

    Args:
        yaml_file_path (str): Path to the YAML file containing the resource configuration.
        kubeconfig_path (str): Path to the kubeconfig file (default is "/etc/rancher/k3s/k3s.yaml").
    """
    k8s_client = verify_kubernetes_connection(kubeconfig_path)
    if k8s_client is None:
        logger.error("Failed to connect to the Kubernetes cluster. Aborting resource deletion.")
        return

    try:
        with open(yaml_file_path, 'r') as file:
            resources = yaml.safe_load_all(file)
            for resource in resources:
                kind = resource.get("kind")
                metadata = resource.get("metadata", {})
                namespace = metadata.get("namespace", "default")
                name = metadata.get("name")

                if kind not in ["Pod", "Service", "Deployment"]:
                    raise ValueError(f"Unsupported resource kind for deletion: {kind}")

                # Dynamic dispatch based on the kind of the resource
                if kind == "Pod":
                    client.CoreV1Api().delete_namespaced_pod(name=name, namespace=namespace)
                    logger.info(f"Pod '{name}' deletion initiated in namespace '{namespace}'.")
                    
                    # Wait for the Pod to be deleted
                    if not wait_for_pod_deletion(client.CoreV1Api(), namespace, name):
                        raise Exception(f"Pod '{name}' deletion timed out.")

                elif kind == "Service":
                    client.CoreV1Api().delete_namespaced_service(name=name, namespace=namespace)
                    logger.info(f"Service '{name}' deleted from namespace '{namespace}'.")

                elif kind == "Deployment":
                    client.AppsV1Api().delete_namespaced_deployment(name=name, namespace=namespace)
                    logger.info(f"Deployment '{name}' deleted from namespace '{namespace}'.")
                    
                    # Wait for all associated Pods to be deleted
                    pod_selector = f'app={name}'  # Assuming the app label is used for Pods
                    pods_deleted = True
                    pod_list = client.CoreV1Api().list_namespaced_pod(namespace=namespace, label_selector=pod_selector)
                    for pod in pod_list.items:
                        if not wait_for_pod_deletion(client.CoreV1Api(), namespace, pod.metadata.name):
                            pods_deleted = False
                    if not pods_deleted:
                        raise Exception(f"Pods associated with Deployment '{name}' deletion timed out.")
    except ApiException as e:
        logger.error(f"API Exception when deleting Kubernetes resource: {e}")
        raise
    except ValueError as e:
        logger.error(f"Value Error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during resource deletion: {e}")
        raise

def configure_kubernetes_network_and_vxlan(local_ip, remote_ip, interface_name, vxlan_id, dst_port, subnet, ip_range, sudo_password='netcom;', k8s_net_name='federation-net'):
    """
    Configures K8s network with Multus and VXLAN on the host machine.

    Args:
        local_ip (str): The local IP address.
        remote_ip (str): The remote IP address.
        interface_name (str): The network interface name.
        vxlan_id (str): The VXLAN ID. 
        dst_port (str): The VXLAN destination port.
        subnet (str): The K8s subnet.
        ip_range (str): The IP range for the K8s network (e.g., 10.0.1.1-10.0.1.10).
        sudo_password (str): The sudo password for executing commands. 
        k8s_net_name (str): The name of the K8s network. 

    Returns:
        None
    """
    script_path = './utils/kubernetes-federation/multus_and_vxlan_setup.sh'
    command = [
        'sudo', '-S', 'bash', script_path,
        '-l', local_ip,
        '-r', remote_ip,
        '-i', interface_name,
        '-v', vxlan_id,
        '-p', dst_port,
        '-s', subnet,
        '-d', ip_range,
        '-n', k8s_net_name
    ]
    
    try:
        # Run the command with sudo and password
        result = subprocess.run(command, input=sudo_password.encode() + b'\n', check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(result.stdout.decode())
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error occurred while running the script: {e.stderr.decode()}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")

def delete_kubernetes_network_and_vxlan(sudo_password='netcom;', vxlan_id='200', k8s_net_name='federation-net'):
    """
    Deletes K8s network and VXLAN configuration from the host machine.

    Args:
        sudo_password (str, optional): The sudo password for executing commands. 
        vxlan_id (str, optional): The VXLAN ID. Defaults to '200'.
        k8s_net_name (str, optional): The name of the K8s network. Defaults to 'federation-net'.

    Returns:
        None
    """    
    script_path = './utils/kubernetes-federation/clean_multus_and_vxlan_setup.sh'
    command = [
        'sudo', '-S', 'bash', script_path,
        '-n', k8s_net_name,
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

def recreate_pod_with_network(pod_name, network_name="federation-net", namespace="default"):
    """
    Recreate a Kubernetes pod with a new network annotation using the Kubernetes Python client.

    Args:
        pod_name (str): The name of the pod to recreate.
        network_name (str): The name of the network to attach to the pod.
        namespace (str): The Kubernetes namespace of the pod (default: "default").

    Returns:
        str: Message indicating the success or failure of the operation.
    """
    try:
        # Load kubeconfig and initialize Kubernetes API clients
        config.load_kube_config()
        v1 = client.CoreV1Api()

        # Fetch the current pod configuration
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)

        # Extract the image of the first container
        image = pod.spec.containers[0].image

        # Delete the existing pod
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        logger.info(f"Deleted pod '{pod_name}'.")

        # Define the new pod configuration with network annotation
        pod_metadata = client.V1ObjectMeta(
            name=pod_name,
            annotations={"k8s.v1.cni.cncf.io/networks": network_name}
        )
        
        pod_spec = client.V1PodSpec(
            containers=[client.V1Container(name=pod_name, image=image)],
            restart_policy="Never"
        )

        # Create a new pod object with the updated configuration
        new_pod = client.V1Pod(metadata=pod_metadata, spec=pod_spec)

        # Recreate the pod with the new configuration
        v1.create_namespaced_pod(namespace=namespace, body=new_pod)
        logger.info(f"Successfully recreated pod '{pod_name}' with network '{network_name}'.")

    except ApiException as e:
        logger.error(f"Error: {e.reason}")
        return f"Error: {e.reason}"
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return f"Unexpected error: {str(e)}"


def get_multus_network_ip(pod_name, namespace="default", multus_network="federation-net"):
    """
    Retrieve the IP address of the Multus CNI network attached to the specified Kubernetes Pod.

    Args:
        pod_name (str): The name of the Pod.
        namespace (str): The namespace where the Pod is running.
        multus_network (str): The name of the Multus network to look for.

    Returns:
        str: The IP address of the specified Multus CNI network, or None if not found.
    """
    k8s_client = verify_kubernetes_connection()

    if k8s_client is None:
        print("Failed to connect to the Kubernetes cluster.")
        return None

    try:
        v1 = client.CoreV1Api()
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)

        # Extract the pod annotations
        annotations = pod.metadata.annotations

        if annotations:
            multus_network_status = annotations.get("k8s.v1.cni.cncf.io/network-status")
            if multus_network_status:
                # Parse the network status annotation (it is in JSON format)
                network_status = json.loads(multus_network_status)

                # Look for the specific Multus network in the network status
                for network in network_status:
                    if multus_network in network.get("name", ""):
                        # Return the IP address associated with this network
                        return network.get("ips", [None])[0]

        logger.warning(f"Multus network '{multus_network}' not found in pod annotations.")
        return None

    except ApiException as e:
        logger.error(f"Error retrieving pod details: {e}")
        return None