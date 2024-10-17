import docker
import logging

# Initialize logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_docker_connection():
    """
    Verifies the connection to the Docker daemon and logs the Docker version.
    Returns the Docker client if the connection is successful.
    """
    try:
        client = docker.from_env()
        version_info = client.version()
        logger.info(f"Docker daemon connected - Version: {version_info['Version']}")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Docker daemon: {e}")
        return None

# Call the function to verify Docker connection
docker_client = verify_docker_connection()

# Check if the connection was successful
if docker_client:
    print("Docker connection successful.")
else:
    print("Docker connection failed.")