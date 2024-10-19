import os
import json
import time
from pathlib import Path
import logging
from dotenv import load_dotenv
from web3 import Web3, WebsocketProvider
from web3.middleware import geth_poa_middleware
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

import docker_functions as docker_utils
import kubernetes_functions as k8s_utils
import utility_functions as utils

# Define FastAPI app and OpenAPI metadata
tags_metadata = [
    {"name": "Default DLT federation functions", "description": "Functions for consumer and provider domains."},
    {"name": "Consumer DLT federation functions", "description": "Functions for consumer domains."},
    {"name": "Provider DLT federation functions", "description": "Functions for provider domains."},
    {"name": "Docker Functions", "description": "Manage and deploy services in Docker."},
    {"name": "Kubernetes Functions", "description": "Manage and deploy services in Kubernetes."},
]

# Directory containing example Kubernetes YAML descriptors
K8S_EXAMPLE_DESCRIPTORS_DIR = "./descriptors/examples/"

class VIMOptions(str, Enum):
    DOCKER = "docker"
    KUBERNETES = "kubernetes"

class FederationEvents(str, Enum):
    OPERATOR_REGISTERED = "OperatorRegistered"
    OPERATOR_REMOVED = "OperatorRemoved"
    SERVICE_ANNOUNCEMENT = "ServiceAnnouncement"
    NEW_BID = "NewBid"
    SERVICE_ANNOUNCEMENT_CLOSED = "ServiceAnnouncementClosed"
    SERVICE_DEPLOYED_EVENT = "ServiceDeployedEvent"

app = FastAPI(
    title="DLT Service Federation API",
    description="This API provides endpoints for interacting with the DLT (Permissioned Blockchain Network + Federation Smart Contract) and functions as a custom-built orchestrator that interacts with the virtual infrastructure on Docker/Kubernetes.",
    version="1.0.0",
    openapi_tags=tags_metadata
)

# Initialize logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
env_files = ['FEDERATION_ENV_FILE', 'DLT_NODE_ENV_FILE', 'SMART_CONTRACT_ENV_FILE']
for env_file in env_files:
    file = os.getenv(env_file)
    if file:
        load_dotenv(file, override=True)
    else:
        raise EnvironmentError(f"Environment variable {env_file} is not set.")

# Configuration from environment variables
domain = os.getenv('DOMAIN_FUNCTION').strip().lower()
dlt_node_id = os.getenv('DLT_NODE_ID')
interface_name = os.getenv('INTERFACE_NAME')
sudo_password = os.getenv('SUDO_PASSWORD') 
eth_node_url = os.getenv('WS_URL')
ip_address = os.getenv('NODE_IP')

# Web3 and Federation SC setup
try:
    web3 = Web3(WebsocketProvider(eth_node_url))
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    if web3.isConnected():
        geth_version = web3.clientVersion
        logger.info(f"Successfully connected to Ethereum node {eth_node_url} - Version: {geth_version}")
    else:
        raise ConnectionError(f"Failed to connect to Ethereum node {eth_node_url}")
    
    contract_abi = json.load(open("smart-contracts/build/contracts/Federation.json"))["abi"]
    contract_address = web3.toChecksumAddress(os.getenv('CONTRACT_ADDRESS'))
    Federation_contract = web3.eth.contract(abi=contract_abi, address=contract_address)
   
    private_key = os.getenv(f'PRIVATE_KEY_NODE_{dlt_node_id}')
    block_address = os.getenv(f'ETHERBASE_NODE_{dlt_node_id}')
    # Number used to ensure the order of transactions (and prevent transaction replay attacks)
    nonce = web3.eth.getTransactionCount(block_address)

except Exception as e:
    logger.error(f"Error initializing Web3: {e}")

# Initialize global variables
service_id = ''
domain_registered = False
vxlan_id = '200'
vxlan_port = '4789'
federation_net = '10.0.0.0/16'
service_requirements_docker = "service=alpine;replicas=1"
service_requirements_kubernetes = "service=alpine-pod-federation.yaml;replicas=1"
service_endpoint_consumer = f'ip_address={ip_address};vxlan_id={vxlan_id};vxlan_port={vxlan_port};federation_net={federation_net}'
service_endpoint_provider = f'ip_address={ip_address};vxlan_id={vxlan_id};vxlan_port={vxlan_port};federation_net={federation_net}'

# Pydantic Models
class TransactionReceiptResponse(BaseModel):
    blockHash: str
    blockNumber: int
    transactionHash: str
    gasUsed: int
    cumulativeGasUsed: int
    status: int
    from_address: str
    to_address: str
    logs: list
    logsBloom: str
    effectiveGasPrice: int

class DomainRegistrationRequest(BaseModel):
    name: str

class ServiceAnnouncementRequest(BaseModel):
    requirements: str
    endpoint_consumer: str

class PlaceBidRequest(BaseModel):
    service_id: str
    service_price: int
    endpoint_provider: str

class ChooseProviderRequest(BaseModel):
    bid_index: int
    service_id: str

class ServiceDeployedRequest(BaseModel):
    service_id: str
    federated_host: str

class ConsumerFederationProcessRequest(BaseModel):
    vim: VIMOptions
    export_to_csv: Optional[bool] = False
    service_providers: Optional[int] = 1
    endpoint_consumer: Optional[str] = service_endpoint_consumer
    requirements: Optional[str] = service_requirements_docker

class ProviderFederationProcessRequest(BaseModel):
    vim: VIMOptions
    export_to_csv: Optional[bool] = False
    service_price: Optional[int] = 10
    endpoint_provider: Optional[str] = service_endpoint_provider

class DockerNetworkConfigRequest(BaseModel):
    local_ip: str
    remote_ip: str
    interface_name: str
    vxlan_id: Optional[str] = vxlan_id
    dst_port: Optional[str] = vxlan_port
    subnet: Optional[str] = federation_net
    ip_range: Optional[str] = '10.0.1.0/24'
    net_name: Optional[str] = 'federation-net'

class KubernetesNetworkConfigRequest(BaseModel):
    local_ip: str
    remote_ip: str
    interface_name: str
    vxlan_id: Optional[str] = vxlan_id
    dst_port: Optional[str] = vxlan_port
    subnet: Optional[str] = federation_net
    ip_range: Optional[str] = '10.0.1.1-10.0.1.255'
    net_name: Optional[str] = 'federation-net'
    

class ContainerCommandRequest(BaseModel):
    name: str
    command: str
    namespace: str = "default"
    kubeconfig_path: str = "/etc/rancher/k3s/k3s.yaml"

# DLT federation functions
def send_signed_transaction(build_transaction):
    """
    Sends a signed transaction to the blockchain network using the private key.
    
    Args:
        build_transaction (dict): The transaction data to be sent.
    
    Returns:
        str: The transaction hash of the sent transaction.
    """
    global nonce
    # Sign the transaction
    signed_txn = web3.eth.account.signTransaction(build_transaction, private_key)
    # Send the signed transaction
    tx_hash = web3.eth.sendRawTransaction(signed_txn.rawTransaction)
    # Increment the nonce
    nonce += 1
    return tx_hash.hex()
        
def create_event_filter(event_name: FederationEvents, last_n_blocks: Optional[int] = None):
    """
    Creates a filter to catch the specified event emitted by the smart contract.
    This function can be used to monitor events in real-time or from a certain number of past blocks.

    Args:
    - event_name (FederationEvents): The name of the smart contract event to create a filter for.
    - last_n_blocks (int, optional): If provided, specifies the number of blocks to look back from the latest block.
                                       If not provided, it listens from the latest block onward.

    Returns:
    - Filter: A filter for catching the specified event.
    """
    global Federation_contract
    try:
        block = web3.eth.getBlock('latest')
        block_number = block['number']
        
        # If last_n_blocks is provided, look back, otherwise start from the latest block
        from_block = max(0, block_number - last_n_blocks) if last_n_blocks else block_number
        
        event_filter = getattr(Federation_contract.events, event_name.value).createFilter(fromBlock=web3.toHex(from_block))
        return event_filter
    except AttributeError:
        raise ValueError(f"Event '{event_name}' does not exist in the contract.")
    except Exception as e:
        raise Exception(f"An error occurred while creating the filter for event '{event_name}': {str(e)}")

def RegisterDomain(domain_name: str, blockchain_address: str) -> str:
    global nonce, Federation_contract
    try:
        add_operator_transaction = Federation_contract.functions.addOperator(
            web3.toBytes(text=domain_name)
        ).buildTransaction({
            'from': blockchain_address,
            'nonce': nonce,
        })
        tx_hash = send_signed_transaction(add_operator_transaction)
        return tx_hash
    except Exception as e:
        logger.error(f"Failed to register domain: {str(e)}")
        raise Exception("Domain registration failed.")


def UnregisterDomain(blockchain_address: str) -> str:
    global nonce, Federation_contract
    try:
        del_operator_transaction = Federation_contract.functions.removeOperator().buildTransaction({
            'from': blockchain_address,
            'nonce': nonce,
        })
        tx_hash = send_signed_transaction(del_operator_transaction)
        return tx_hash
    except Exception as e:
        logger.error(f"Failed to unregister domain: {str(e)}")
        raise Exception("Domain unregistration failed.")

def AnnounceService(blockchain_address: str, service_requirements: str, service_endpoint: str) -> str:
    global service_id, nonce, Federation_contract
    try:
        service_id = 'service' + str(int(time.time()))
        announce_transaction = Federation_contract.functions.AnnounceService(
            _requirements=web3.toBytes(text=service_requirements),
            _endpoint_consumer=web3.toBytes(text=service_endpoint),
            _id=web3.toBytes(text=service_id)
        ).buildTransaction({
            'from': blockchain_address,
            'nonce': nonce
        })
        tx_hash = send_signed_transaction(announce_transaction)
        return tx_hash
    except Exception as e:
        logger.error(f"Failed to announce service: {str(e)}")
        raise Exception("Service announcement failed.")

def GetBidInfo(service_id: str, bid_index: int, blockchain_address: str) -> tuple:
    global Federation_contract
    try:
        bid_info = Federation_contract.functions.GetBid(
            _id=web3.toBytes(text=service_id),
            bider_index=bid_index,
            _creator=blockchain_address
        ).call()
        return bid_info
    except Exception as e:
        logger.error(f"Failed to retrieve bid info for service_id {service_id} and bid_index {bid_index}: {str(e)}")
        raise Exception("Error occurred while retrieving bid information.")

def ChooseProvider(service_id: str, bid_index: int, blockchain_address) -> str:
    global nonce, Federation_contract
    try:
        choose_transaction = Federation_contract.functions.ChooseProvider(
            _id=web3.toBytes(text=service_id),
            bider_index=bid_index
        ).buildTransaction({
            'from': blockchain_address,
            'nonce': nonce
        })
        tx_hash = send_signed_transaction(choose_transaction)
        return tx_hash
    except Exception as e:
        logger.error(f"Failed to choose provider for service_id {service_id} and bid_index {bid_index}: {str(e)}")
        raise Exception("Error occurred while choosing the provider.")

def GetServiceState(service_id: str) -> int:  
    global Federation_contract
    try:
        service_state = Federation_contract.functions.GetServiceState(_id=web3.toBytes(text=service_id)).call()
        return service_state
    except Exception as e:
        logger.error(f"Failed to retrieve service state for service_id {service_id}: {str(e)}")
        raise Exception(f"Error occurred while retrieving the service state for service_id {service_id}.")

def GetDeployedInfo(service_id: str, domain: str, blockchain_address: str) -> tuple:
    global Federation_contract
    try:
        service_id_bytes = web3.toBytes(text=service_id)
        provider_flag = (domain == "provider")
        
        service_id, service_endpoint, federated_host = Federation_contract.functions.GetServiceInfo(
            _id=service_id_bytes, provider=provider_flag, call_address=blockchain_address).call()

        return (
            federated_host.rstrip(b'\x00').decode('utf-8') if not provider_flag else "",
            service_endpoint.rstrip(b'\x00').decode('utf-8')
        )
    except Exception as e:
        logger.error(f"Failed to retrieve deployed info for service_id {service_id} and domain {domain}: {str(e)}")
        raise Exception(f"Error occurred while retrieving deployed info for service_id {service_id} and domain {domain}.")

def PlaceBid(service_id: str, service_price: int, service_endpoint: str, blockchain_address: str) -> str:
    global nonce, Federation_contract
    try:
        place_bid_transaction = Federation_contract.functions.PlaceBid(
            _id=web3.toBytes(text=service_id),
            _price=service_price,
            _endpoint=web3.toBytes(text=service_endpoint)
        ).buildTransaction({
            'from': blockchain_address,
            'nonce': nonce
        })
        tx_hash = send_signed_transaction(place_bid_transaction)
        return tx_hash

    except Exception as e:
        logger.error(f"Failed to place bid for service_id {service_id}: {str(e)}")
        raise Exception(f"Error occurred while placing bid for service_id {service_id}.")

def CheckWinner(service_id: str, blockchain_address: str) -> bool:
    global Federation_contract
    try:
        state = GetServiceState(service_id)
        if state == 1:
            result = Federation_contract.functions.isWinner(
                _id=web3.toBytes(text=service_id), 
                _winner=blockchain_address
            ).call()
            return result
        else:
            return False
    except Exception as e:
        logger.error(f"Failed to check winner for service_id {service_id}: {str(e)}")
        raise Exception(f"Error occurred while checking the winner for service_id {service_id}.")

def ServiceDeployed(service_id: str, federated_host: str, blockchain_address: str) -> str:
    global nonce, Federation_contract
    try:
        service_deployed_transaction = Federation_contract.functions.ServiceDeployed(
            info=web3.toBytes(text=federated_host),
            _id=web3.toBytes(text=service_id)
        ).buildTransaction({
            'from': blockchain_address,
            'nonce': nonce
        })
        tx_hash = send_signed_transaction(service_deployed_transaction)
        return tx_hash
    except Exception as e:
        logger.error(f"Failed to confirm deployment for service_id {service_id}: {str(e)}")
        raise Exception(f"Failed to confirm deployment for service_id {service_id}.")

def DisplayServiceState(service_id: str):  
    current_service_state = GetServiceState(service_id)
    if current_service_state == 0:
        logger.info("Service state: Open")
    elif current_service_state == 1:
        logger.info("Service state: Closed")
    elif current_service_state == 2:
        logger.info("Service state: Deployed")
    else:
        logger.error(f"Error: state for service {service_id} is {current_service_state}")


# DLT-related API Endpoints
@app.get("/web3_info", summary="Get Web3 and Ethereum node info", tags=["Default DLT federation functions"])
async def web3_info_endpoint():
    """
    Retrieve Ethereum node and Web3 connection details.

    Returns:
        JSONResponse: A JSON object containing:
            - ethereum_node_url (str): The URL of the connected Ethereum node.
            - ethereum_address (str): The Ethereum address associated with the connected node.
            - contract_address (str): The address of the deployed Federation Smart Contract (SC).

    Raises:
        HTTPException:
            - 500: If there is an issue retrieving the Ethereum node or Web3 connection information.
    """
    global eth_node_url, block_address, contract_address
    try:
        web3_info = {
            "ethereum_node_url": eth_node_url,
            "ethereum_address": block_address,
            "contract_address": contract_address
        }
        return JSONResponse(content={"web3_info": web3_info})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tx_receipt", summary="Get transaction receipt", tags=["Default DLT federation functions"], response_model=TransactionReceiptResponse)
async def tx_receipt_endpoint(tx_hash: str = Query(..., description="The transaction hash to retrieve the receipt")):
    """
    Retrieves the transaction receipt details for a specified transaction hash.

    Args:
        - tx_hash (str): The transaction hash for which the receipt is requested.

    Returns:
        JSONResponse: A JSON object containing:
            - blockHash (str): The hash of the block containing the transaction.
            - blockNumber (int): The block number in which the transaction was included.
            - transactionHash (str): The transaction hash.
            - gasUsed (int): The amount of gas used for the transaction.
            - cumulativeGasUsed (int): The cumulative gas used by all transactions in the block up to and including this one.
            - status (int): Transaction status (`1` for success, `0` for failure).
            - from_address (str): The sender’s address.
            - to_address (str): The recipient’s address.
            - logs (list): A list of event logs generated during the transaction.
            - logsBloom (str): A bloom filter for quick searching of logs.
            - effectiveGasPrice (int): The actual gas price paid for the transaction.

    Raises:
        HTTPException:
            - 500: If there is an issue retrieving the transaction receipt from the blockchain.
    """
    try:
        # Get the transaction receipt
        receipt = web3.eth.get_transaction_receipt(tx_hash)
        if receipt:
            # Convert HexBytes to strings for JSON serialization
            receipt_dict = dict(receipt)
            receipt_dict['blockHash'] = receipt_dict['blockHash'].hex()
            receipt_dict['transactionHash'] = receipt_dict['transactionHash'].hex()
            receipt_dict['logsBloom'] = receipt_dict['logsBloom'].hex()
            receipt_dict['logs'] = [dict(log) for log in receipt_dict['logs']]

            # Rename fields to match the expected response model
            receipt_dict['from_address'] = receipt_dict.pop('from')
            receipt_dict['to_address'] = receipt_dict.pop('to')

            for log in receipt_dict['logs']:
                log['blockHash'] = log['blockHash'].hex()
                log['transactionHash'] = log['transactionHash'].hex()
                log['topics'] = [topic.hex() for topic in log['topics']]
            return JSONResponse(content={"tx_receipt": receipt_dict})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/register_domain", summary="Register a new domain (operator)", tags=["Default DLT federation functions"])
def register_domain_endpoint(request: DomainRegistrationRequest):
    """
    Registers a new domain (operator) in the federation.

     Args:
        - name (str): The name of the domain to register as an operator.

    Returns:
        JSONResponse: A JSON object containing:
            - tx_hash (str): The transaction hash of the sent registration transaction.

    Raises:
        HTTPException:
            - 500: If the domain is already registered or if there is an error during the registration process.
    """
    global domain_registered, block_address
    try:
        if not domain_registered:
            tx_hash = RegisterDomain(request.name, block_address)
            domain_registered = True
            return JSONResponse(content={"tx_hash": tx_hash})
        else:
            raise HTTPException(status_code=500, detail=f"Domain {request.name} is already registered.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/unregister_domain", summary="Unregisters an existing domain (operator)", tags=["Default DLT federation functions"])
def unregister_domain_endpoint():
    """
    Unregisters an existing domain (operator) from the federation.

    Args:
        - None

    Returns:
        JSONResponse: A JSON object containing:
            - tx_hash (str): The transaction hash of the sent unregistration transaction.

    Raises:
        HTTPException:
            - 500: If the domain is not registered or if there is an error during the unregistration process.
    """
    global domain_registered, block_address
    try:
        if domain_registered:
            tx_hash = UnregisterDomain(block_address)
            domain_registered = False
            return JSONResponse(content={"tx_hash": tx_hash})
        else:
            raise HTTPException(status_code=500, detail="Domain is not registered in the SC")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/create_service_announcement", summary="Create service federation announcement", tags=["Consumer DLT federation functions"])
def create_service_announcement_endpoint(request: ServiceAnnouncementRequest):
    """
    Consumer announces the need for service federation. 

    Args:
        requirements (str): The specific requirements for the requested service, formatted as:
            'service=<docker_image/k8s_descriptor>;replicas=<container_replicas>'
        endpoint_consumer (str): The consumer's network endpoint for establishing VXLAN connectivity, formatted as:
            'ip_address=<ip_address>;vxlan_id=<vxlan_id>;vxlan_port=<vxlan_port>;federation_net=<federation_net>'

    Returns:
        JSONResponse: A JSON object containing:
            - tx_hash (str): The transaction hash of the service announcement.
            - service_id (str): The unique identifier for the service.

    Raises:
        HTTPException:
            - 400: If the 'requirements' or 'endpoint_consumer' formats are invalid.
            - 500: If there is an error during the service announcement process.
    """
    # Validate requirements format
    if request.requirements and not utils.validate_requirements(request.requirements):
        raise HTTPException(status_code=400, detail="Invalid 'requirements' format. Expected format: 'service=<docker_image>;replicas=<container_replicas>'")

    # Validate endpoint format
    if request.endpoint_consumer and not utils.validate_endpoint(request.endpoint_consumer):
        raise HTTPException(status_code=400, detail="Invalid 'endpoint' format. Expected format: 'ip_address=<ip_address>;vxlan_id=<vxlan_id>;vxlan_port=<vxlan_port>;federation_net=<federation_net>'")

    global service_id, block_address
    try:
        tx_hash = AnnounceService(block_address, request.requirements, request.endpoint_consumer)
        return JSONResponse(content={"tx_hash": tx_hash, "service_id": service_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check_service_state", summary="Get service state", tags=["Default DLT federation functions"])
async def check_service_state_endpoint(service_id: str = Query(..., description="The service ID to check the state of")):
    """
    Returns the current state of a service by its service ID.
    
    Args:
        service_id (str): The unique identifier of the service whose state is being queried.

    Returns:
        JSONResponse: A JSON object containing:
            - service_state (str): The current state of the service, which can be:
                - 'open' (0)
                - 'closed' (1)
                - 'deployed' (2)
                - 'unknown' if the state is unrecognized.

    Raises:
        HTTPException:
            - 500: If there is an error retrieving the service state.
    """     
    try:
        current_service_state = GetServiceState(service_id)
        state_mapping = {0: "open", 1: "closed", 2: "deployed"}
        state = state_mapping.get(current_service_state, "unknown")  # Use 'unknown' if the state is not recognized
        return JSONResponse(content={"service_state": state})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check_deployed_info", summary="Get deployed info", tags=["Default DLT federation functions"])
async def check_deployed_info_endpoint(service_id: str = Query(..., description="The service ID to get the deployed info for the federated service")):
    """
    Retrieves deployment information for a federated service.

    Args:
        service_id (str): The unique identifier of the deployed service.

    Returns:
        JSONResponse: A JSON object containing:
            - federated_host (str): The external IP address of the deployed service.
            - service_endpoint (str): The service endpoint where the consumer can access the deployed service.

    Raises:
        HTTPException:
            - 500: If there is an error retrieving the deployment information.
    """   
    global domain, block_address
    try:
        federated_host, service_endpoint = GetDeployedInfo(service_id, domain, block_address)  
        return JSONResponse(content={"service_endpoint": service_endpoint, "federated_host": federated_host})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check_service_announcements", summary="Check service federation announcements", tags=["Provider DLT federation functions"])
async def check_service_announcements_endpoint():
    """
    Check for new service announcements in the last 20 blocks.

    Returns:
        JSONResponse: A JSON object containing a list of service announcements, where each announcement includes:
            - service_id (str): The unique identifier of the announced federated service.
            - service_requirements (str): The requirements for the requested federated service.
            - tx_hash (str): The transaction hash of the service announcement event.
            - block_number (str): The block number where the service announcement was recorded.

    Raises:
        HTTPException:
            - 404: If no new service announcements are found within the last 20 blocks.
            - 500: If an error occurs while processing the request or fetching the announcements.
    """ 
    try:
        new_service_event = create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT, last_n_blocks=20)
        new_events = new_service_event.get_all_entries()
        open_services = []
        announcements_received = []

        for event in new_events:
            service_id = web3.toText(event['args']['id']).rstrip('\x00')
            requirements = web3.toText(event['args']['requirements']).rstrip('\x00')
            tx_hash = web3.toHex(event['transactionHash'])
            block_number = event['blockNumber']
            event_name = event['event']
            if GetServiceState(service_id) == 0:  # Open services
                open_services.append(service_id)
                announcements_received.append({
                    "service_id": service_id,
                    "service_requirements": requirements,
                    "tx_hash": tx_hash,
                    "block_number": block_number
                })

        if announcements_received:
            return JSONResponse(content={"announcements": announcements_received})
        else:
            raise HTTPException(status_code=404, detail="No new services announced in the last 20 blocks.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/place_bid", summary="Place a bid", tags=["Provider DLT federation functions"])
def place_bid_endpoint(request: PlaceBidRequest):
    """
    Place a bid for a service announcement.

    Args:
        request (PlaceBidRequest): A Pydantic model containing the following fields:
            - service_id (str): The unique identifier of the service being bid on.
            - service_price (int): The price the provider is offering for the service.
            - endpoint_provider (str): The provider's VXLAN endpoint, in the format:
                'ip_address=<ip_address>;vxlan_id=<vxlan_id>;vxlan_port=<vxlan_port>;federation_net=<federation_net>'.

    Returns:
        JSONResponse: A JSON object containing:
            - tx_hash (str): The transaction hash of the submitted bid.

    Raises:
        HTTPException: 
            - 400: If the provided endpoint format is invalid.
            - 500: If there is an internal server error during bid submission.
    """ 
    global block_address

    # Validate endpoint format
    if request.endpoint_provider and not utils.validate_endpoint(request.endpoint_provider):
        raise HTTPException(status_code=400, detail="Invalid 'endpoint' format. Expected format: 'ip_address=<ip_address>;vxlan_id=<vxlan_id>;vxlan_port=<vxlan_port>;federation_net=<federation_net>'")

    try:
        tx_hash = PlaceBid(request.service_id, request.service_price, request.endpoint_provider, block_address)
        return JSONResponse(content={"tx_hash": tx_hash})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check_bids", summary="Check bids", tags=["Consumer DLT federation functions"]) 
async def check_bids_endpoint(service_id: str = Query(..., description="The service ID to check bids for")):
    """
    Check for bids placed on a specific service.

    Args:
        service_id (str): The unique identifier of the service to check for bids.

    Returns:
        dict: A JSON response containing:
            - bid_index (str): The index of the highest bid.
            - provider_address (str): The blockchain address of the bidding provider.
            - service_price (str): The price offered for the service.

    Raises:
        HTTPException: If no bids are found or if there is an internal server error.
    """    
    global block_address
    try:
        bids_event = create_event_filter(FederationEvents.NEW_BID, last_n_blocks=20)
        new_events = bids_event.get_all_entries()
        bids_received = []
        for event in new_events:
            received_bids = int(event['args']['max_bid_index'])
            if received_bids >= 1:
                bid_info = GetBidInfo(service_id, received_bids-1, block_address)
                bids_received.append({
                    "bid_index": bid_info[2],
                    "provider_address": bid_info[0],
                    "service_price": bid_info[1]
                })
        if bids_received:
            return JSONResponse(content={"bids": bids_received})
        else:
            raise HTTPException(status_code=404, detail="No new bids in the last 20 blocks.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/choose_provider", summary="Choose provider", tags=["Consumer DLT federation functions"])
def choose_provider_endpoint(request: ChooseProviderRequest):
    """
    Choose a provider from the bids received for a federated service.

    Args:
        request (ChooseProviderRequest): A Pydantic model containing the following fields:
            - service_id (str): The unique identifier of the service for which the provider is being selected.
            - bid_index (int): The index of the bid representing the chosen provider.

    Returns:
        JSONResponse: A JSON object containing:
            - tx_hash (str): The transaction hash of the sent transaction for choosing the provider.

    Raises:
        HTTPException: 
            - 500: If there is an internal server error during the provider selection process.
    """    
    global block_address
    try:
        tx_hash = ChooseProvider(request.service_id, request.bid_index, block_address)
        return JSONResponse(content={"tx_hash": tx_hash})    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check_winner", summary="Check for winner", tags=["Provider DLT federation functions"])
async def check_winner_endpoint(service_id: str = Query(..., description="The service ID to check if there is a winner provider in the federation")):
    """
    Check if a winner has been chosen for a specific service in the federation.

    Args:
        service_id (str): The unique identifier of the service for which the winner is being checked.

    Returns:
        JSONResponse: A JSON object containing:
            - winner-chosen (str): 'yes' if a winner has been selected, otherwise 'no'.

    Raises:
        HTTPException:
            - 500: If there is an internal server error while checking for the winner.
    """    
    try:
        winner_chosen_event = create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT_CLOSED, last_n_blocks=20)
        new_events = winner_chosen_event.get_all_entries()
        for event in new_events:
            event_service_id = web3.toText(event['args']['_id']).rstrip('\x00')
            if event_service_id == service_id:
                return JSONResponse(content={"winner-chosen": "yes"})   
        return JSONResponse(content={"winner-chosen": "no"})  
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check_if_i_am_winner", summary="Check if I am winner", tags=["Provider DLT federation functions"])
async def check_if_I_am_Winner_endpoint(service_id: str = Query(..., description="The service ID to check if I am the winner provider in the federation")):
    """
    Check if the calling provider is the winner for a specific service.

    Args:
        service_id (str): The unique identifier of the service for which the provider's winner status is being checked.

    Returns:
        JSONResponse: A JSON object containing:
            - am-i-winner (str): 'yes' if the calling provider is the winner of the service, otherwise 'no'.

    Raises:
        HTTPException:
            - 500: If there is an internal server error while checking the winner status.
    """
    global block_address
    try:
        if CheckWinner(service_id, block_address):
           return JSONResponse(content={"am-i-winner": "yes"})
        else:
           return JSONResponse(content={"am-i-winner": "no"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/service_deployed", summary="Confirm service deployment", tags=["Provider DLT federation functions"])
def service_deployed_endpoint(request: ServiceDeployedRequest):
    """
    Confirm the successful deployment of a service by the provider.

    Args:
        request (ServiceDeployedRequest): The request object containing:
            - service_id (str): The unique identifier of the deployed service.
            - federated_host (str): The external IP address where the service is hosted.

    Returns:
        JSONResponse: A JSON object containing:
            - tx_hash (str): The transaction hash of the confirmation sent to the blockchain.

    Raises:
        HTTPException:
            - 404: If the calling provider is not the winner of the service.
            - 500: If there is an internal server error during the confirmation process.
    """   
    global block_address
    try:
        if CheckWinner(request.service_id, block_address):
            tx_hash = ServiceDeployed(request.service_id, request.federated_host, block_address)
            return JSONResponse(content={"tx_hash": tx_hash})
        else:
            raise HTTPException(status_code=404, detail="You are not the winner.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))    

@app.post("/simulate_consumer_federation_process", tags=["Consumer DLT federation functions"])
def simulate_consumer_federation_process(request: ConsumerFederationProcessRequest):
    """
    Simulates the consumer-side service federation process, including the following steps:
    
    - Announcing the service federation request.
    - Waiting for bids from providers.
    - Evaluating and selecting the best bid.
    - Waiting for provider confirmation and service deployment.
    - Establishing a VXLAN connection with the provider.

    This function performs the entire consumer-side process, from service announcement to deployment confirmation,
    and establishes the required VXLAN tunnel for communication between the consumer and provider.

    Args:
    - request (ConsumerFederationProcessRequest): Contains the service requirements, consumer endpoint, and other optional parameters such as VIM (Docker or Kubernetes) and number of service providers.

    Returns:
    - JSONResponse: A JSON object with the following keys:
        - message (str): A message confirming the successful completion of the federation process.
        - federated_host (str): The IP address of the federated host.
    
    Raises:
    - HTTPException:
        - 400: If the provided 'requirements' or 'endpoint' format is invalid.
        - 500: If any error occurs during the federation process.
    """
    # Validate requirements format
    if request.requirements and not utils.validate_requirements(request.requirements):
        raise HTTPException(status_code=400, detail="Invalid 'requirements' format. Expected format: 'service=<docker_image>;replicas=<container_replicas>'")

    # Validate endpoint format
    if request.endpoint_consumer and not utils.validate_endpoint(request.endpoint_consumer):
        raise HTTPException(status_code=400, detail="Invalid 'endpoint' format. Expected format: 'ip_address=<ip_address>;vxlan_id=<vxlan_id>;vxlan_port=<vxlan_port>;federation_net=<federation_net>'")

    global block_address, domain, service_id
    try:
        # List to store the timestamps of each federation step
        federation_step_times = []  
        header = ['step', 'timestamp']
        data = []

        consumer_endpoint_ip, consumer_endpoint_vxlan_id, consumer_endpoint_vxlan_port, consumer_endpoint_federation_net = utils.extract_service_endpoint(request.endpoint_consumer)

        if domain == 'consumer':
            
            # Start time of the process
            process_start_time = time.time()
                        
            # Send service announcement (federation request)
            t_service_announced = time.time() - process_start_time
            data.append(['service_announced', t_service_announced])
            tx_hash = AnnounceService(block_address, request.requirements, request.endpoint_consumer)
            logger.info(f"Service Announcement sent to the SC - Service ID: {service_id}")

            # Wait for provider bids
            bids_event = create_event_filter(FederationEvents.NEW_BID)
            bidderArrived = False
            logger.info("Waiting for bids...")
            while not bidderArrived:
                new_events = bids_event.get_all_entries()
                for event in new_events:
                    event_id = str(web3.toText(event['args']['_id']))
                    received_bids = int(event['args']['max_bid_index'])
                    
                    if received_bids >= request.service_providers:
                        t_bid_offer_received = time.time() - process_start_time
                        data.append(['bid_offer_received', t_bid_offer_received])
                        logger.info(f"{received_bids} bid offers received")
                        bidderArrived = True 
                        break
            
            # Received bids
            lowest_price = None
            best_bid_index = None

            # Loop through all bid indices and print their information
            for i in range(received_bids):
                bid_info = GetBidInfo(service_id, i, block_address)
                logger.info(f"Bid {i}: {bid_info}")
                bid_price = int(bid_info[1]) 
                if lowest_price is None or bid_price < lowest_price:
                    lowest_price = bid_price
                    best_bid_index = int(bid_info[2])
                    # logger.info(f"New lowest price: {lowest_price} with bid index: {best_bid_index}")
                            
            # Choose winner provider
            t_winner_choosen = time.time() - process_start_time
            data.append(['winner_choosen', t_winner_choosen])
            tx_hash = ChooseProvider(service_id, best_bid_index, block_address)
            logger.info(f"Provider Choosen - Bid Index: {best_bid_index}")

            # Service closed (state 1)
            DisplayServiceState(service_id)

            # Wait for provider confirmation
            serviceDeployed = False 
            while serviceDeployed == False:
                serviceDeployed = True if GetServiceState(service_id) == 2 else False
            
            # Confirmation received
            t_confirm_deployment_received = time.time() - process_start_time
            data.append(['confirm_deployment_received', t_confirm_deployment_received])

            # Federated service info
            federated_host, service_endpoint_provider = GetDeployedInfo(service_id, domain, block_address)
            provider_endpoint_ip, provider_endpoint_vxlan_id, provider_endpoint_vxlan_port, provider_endpoint_federation_net = utils.extract_service_endpoint(service_endpoint_provider)
            logger.info(f"Federated Service Info - Service Endpoint Provider: {service_endpoint_provider}, Federated Host: {federated_host}")
            
            # Establish VXLAN connection with the provider 
            t_establish_vxlan_connection_with_provider_start = time.time() - process_start_time
            data.append(['establish_vxlan_connection_with_provider_start', t_establish_vxlan_connection_with_provider_start])
            consumer_docker_ip_range = utils.create_smaller_subnet(provider_endpoint_federation_net, dlt_node_id)
            consumer_kubernetes_ip_range = utils.get_ip_range_from_subnet(consumer_docker_ip_range)
            if request.vim == VIMOptions.DOCKER:
                docker_utils.configure_docker_network_and_vxlan(consumer_endpoint_ip, provider_endpoint_ip, interface_name, consumer_endpoint_vxlan_id, consumer_endpoint_vxlan_port, provider_endpoint_federation_net, consumer_docker_ip_range)
                # docker_utils.attach_docker_container_to_network("alpine_1", "federation-net")
            elif request.vim == VIMOptions.KUBERNETES:
                k8s_utils.configure_kubernetes_network_and_vxlan(consumer_endpoint_ip, provider_endpoint_ip, interface_name, consumer_endpoint_vxlan_id, consumer_endpoint_vxlan_port, provider_endpoint_federation_net, consumer_kubernetes_ip_range)
                # k8s_utils.recreate_pod_with_network("alpine_pod", "federation-net")

            t_establish_vxlan_connection_with_provider_finished = time.time() - process_start_time
            data.append(['establish_vxlan_connection_with_provider_finished', t_establish_vxlan_connection_with_provider_finished])
           
            total_duration = time.time() - process_start_time

            logger.info(f"Federation process completed in {total_duration:.2f} seconds")


            # logger.info(f"Monitoring connection with federated host ({federated_host})")
            # monitor_connection_command = f"ping -c 10 {federated_host}"
            # if request.vim == VIMOptions.DOCKER:
            #     docker_utils.execute_command_in_docker_container("alpine_1", monitor_connection_command)
            # elif request.vim == VIMOptions.KUBERNETES:
            #     k8s_utils.execute_command_in_kubernetes_pod("alpine_pod", monitor_connection_command)

            if request.export_to_csv:
                utils.create_csv_file(domain, header, data)
            return JSONResponse(content={"message": f"Federation process completed in {total_duration:.2f} seconds", "federated_host": federated_host})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))    

@app.post("/simulate_provider_federation_process", tags=["Provider DLT federation functions"])
def simulate_provider_federation_process(request: ProviderFederationProcessRequest):
    """
    Simulates the provider-side service federation process, including the following steps:

    - Waiting for service announcements.
    - Submitting a bid offer for the service.
    - Waiting for the consumer to choose a winner.
    - Deploying the federated service if selected as the winner.

    Args:
    - request (ProviderFederationProcessRequest): Contains details such as the service price, endpoint, and VIM options (Docker or Kubernetes).

    Returns:
    - JSONResponse: A message confirming the successful completion of the federation process, or an error if the provider was not chosen.

    Steps:
    1. **Service Announcement**: The provider subscribes to the service announcement events and waits for a new service to be announced.
    2. **Bid Placement**: The provider places a bid for the service, offering a price and providing its VXLAN endpoint details.
    3. **Bid Evaluation**: The provider waits for the consumer to evaluate bids and select a winner.
    4. **Service Deployment**: If the provider wins, the service is deployed, either via Docker or Kubernetes.
    5. **Deployment Confirmation**: The provider confirms the deployment on the blockchain and the process ends.

    Raises:
    - HTTPException: 
        - 500: If an error occurs during any step of the federation process or if the provider is not selected.
    """  
    global block_address, domain
    try:
        # List to store the timestamps of each federation step
        federation_step_times = []  
        header = ['step', 'timestamp']
        data = []

        provider_endpoint_ip, provider_endpoint_vxlan_id, provider_endpoint_vxlan_port, provider_endpoint_federation_net = utils.extract_service_endpoint(request.endpoint_provider)

        if domain == 'provider':
            
            # Start time of the process
            process_start_time = time.time()
            
            service_id = ''
            # requested_service = ''
            # requested_replicas = ''
            newService = False
            open_services = []

            # Wait for service announcements
            new_service_event = create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT)
            logger.info("Subscribed to federation events...")
            while newService == False:
                new_events = new_service_event.get_all_entries()
                for event in new_events:
                    service_id = web3.toText(event['args']['id'])
                    requirements = web3.toText(event['args']['requirements'])
                    requested_service, requested_replicas = utils.extract_service_requirements(requirements.rstrip('\x00'))
                    
                    if GetServiceState(service_id) == 0:
                        open_services.append(service_id)
                
                if len(open_services) > 0:
                    # Announcement received
                    t_announce_received = time.time() - process_start_time
                    data.append(['announce_received', t_announce_received])
                    logger.info(f"Announcement Received - Service ID: {service_id}, Requested Service: {repr(requested_service)}, Requested Replicas: {repr(requested_replicas)}")
                    newService = True
                
            service_id = open_services[-1]

            # Place a bid offer
            t_bid_offer_sent = time.time() - process_start_time
            data.append(['bid_offer_sent', t_bid_offer_sent])
            tx_hash = PlaceBid(service_id, request.service_price, request.endpoint_provider, block_address)
            logger.info(f"Bid Offer sent to the SC - Service ID: {service_id}, Price: {request.service_price} €")

            # Wait for a winner to be selected 
            winner_chosen_event = create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT_CLOSED)
            winnerChosen = False
            while winnerChosen == False:
                new_events = winner_chosen_event.get_all_entries()
                for event in new_events:
                    event_serviceid = web3.toText(event['args']['_id'])
                    
                    if event_serviceid == service_id:    
                        # Winner choosen received
                        t_winner_received = time.time() - process_start_time
                        data.append(['winner_received', t_winner_received])
                        winnerChosen = True
                        break
            
            am_i_winner = False
            while am_i_winner == False:
                # Check if I am the winner
                am_i_winner = CheckWinner(service_id, block_address)
                if am_i_winner == True:
                    logger.info(f"I am the winner for {service_id}")
                    # Start the deployment of the requested federated service
                    logger.info("Start deployment of the requested federated service...")
                    t_deployment_start = time.time() - process_start_time
                    data.append(['deployment_start', t_deployment_start])
                    break
                else:
                    logger.info(f"I am not the winner for {service_id}")
                    t_other_provider_choosen = time.time() - process_start_time
                    data.append(['other_provider_choosen', t_other_provider_choosen])
                    if export_to_csv:
                        utils.create_csv_file(domain, header, data)
                        return JSONResponse(content={"message": f"Other provider chosen for {service_id}"})

            # Retrieve consumer service endpoint
            federated_host, service_endpoint_consumer = GetDeployedInfo(service_id, domain, block_address)
            consumer_endpoint_ip, consumer_endpoint_vxlan_id, consumer_endpoint_vxlan_port, consumer_endpoint_federation_net = utils.extract_service_endpoint(service_endpoint_consumer)
            provider_docker_ip_range = utils.create_smaller_subnet(consumer_endpoint_federation_net, dlt_node_id)
            provider_kubernetes_ip_range = utils.get_ip_range_from_subnet(provider_docker_ip_range)
            logger.info(f"Service Endpoint Consumer: {service_endpoint_consumer}")

            # Deploy federated service (VXLAN tunnel + containers deployment)
            if request.vim == VIMOptions.DOCKER:
                docker_utils.configure_docker_network_and_vxlan(provider_endpoint_ip, consumer_endpoint_ip, interface_name, consumer_endpoint_vxlan_id, consumer_endpoint_vxlan_port, consumer_endpoint_federation_net, provider_docker_ip_range)
                env_vars = {"SERVER_ID": "test_app"}
                docker_utils.deploy_docker_service(
                    image=requested_service,
                    service_name="federated-service",
                    network="federation-net",
                    replicas=int(requested_replicas),
                    env_vars=env_vars,
                    container_port=5000,
                    start_host_port=5000,
                    command='sh -c "trap : TERM INT; sleep infinity & wait"'
                )          

                container_ips = docker_utils.get_docker_container_ips("federated-service")
                if container_ips:
                    first_container_name = next(iter(container_ips))
                    federated_host = container_ips[first_container_name]
                

            elif request.vim == VIMOptions.KUBERNETES:
                k8s_utils.configure_kubernetes_network_and_vxlan(ip_address, consumer_endpoint_ip, interface_name, consumer_endpoint_vxlan_id, consumer_endpoint_vxlan_port, consumer_endpoint_federation_net, provider_kubernetes_ip_range)
                yaml_file_path = os.path.join(K8S_EXAMPLE_DESCRIPTORS_DIR, requested_service)
                created_resources = k8s_utils.create_kubernetes_resource_from_yaml(yaml_file_path)[0]
                logger.info(f"K8s resources created: {created_resources}")

                # Retrieve the Multus CNI IP address from the pod's annotations
                federated_host = k8s_utils.get_multus_network_ip(pod_name=created_resources, multus_network="federation-net")
                # federated_host = "0.0.0.0"

            # Deployment finished
            t_deployment_finished = time.time() - process_start_time
            data.append(['deployment_finished', t_deployment_finished])
                
            # Send deployment confirmation
            t_confirm_deployment_sent = time.time() - process_start_time
            data.append(['confirm_deployment_sent', t_confirm_deployment_sent])
            ServiceDeployed(service_id, federated_host, block_address)
            logger.info(f"Service Deployed - Federated Host: {federated_host}")
            DisplayServiceState(service_id)

            total_duration = time.time() - process_start_time
                
            if request.export_to_csv:
                utils.create_csv_file(domain, header, data)

            return {"message": f"Federation process completed successfully."}
        else:
            raise HTTPException(status_code=500, detail="You must be provider to run this code")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  


# Docker-related API Endpoints
@app.post("/deploy_docker_service", tags=["Docker Functions"], summary="Deploy docker service")
def deploy_docker_service_endpoint(image: str, name: str, network: str = "bridge", replicas: int = 1, env_vars: str = None, container_port: int = None, host_port: int = None, command: str = 'sh -c "trap : TERM INT; sleep infinity & wait"'):
    try:
        containers = docker_utils.deploy_docker_service(image, name, network, replicas, env_vars, container_port, host_port, command)
        if not containers:
            raise HTTPException(status_code=500, detail="Failed to deploy Docker service")
        container_ips = docker_utils.get_docker_container_ips(name)
        container_info = [{"container_name": cname, "ip_address": ip} for cname, ip in container_ips.items()]
        return JSONResponse(content={"message": "Service deployed", "service_info": container_info})
    except HTTPException as e:
        raise e  
    except Exception as e:
        logger.error(f"Error occurred while deploying Docker service: {e}")
        raise HTTPException(status_code=500, detail="An error occurred during the Docker service deployment")

@app.delete("/delete_docker_service", tags=["Docker Functions"], summary="Delete docker service")
def delete_docker_service_endpoint(name: str):
    try:
        deleted_containers = docker_utils.delete_docker_service(name)
        if not deleted_containers:
            raise HTTPException(status_code=404, detail=f"No containers found with name '{name}'.")
        return JSONResponse(content={"message": "Service deleted"})
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error while deleting Docker containers: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while deleting the Docker service.")

@app.post("/configure_docker_network_resources", tags=["Docker Functions"], summary="Configure Docker network and VXLAN")
def configure_docker_network_and_vxlan_endpoint(request: DockerNetworkConfigRequest):
    global sudo_password
    try:
        docker_utils.configure_docker_network_and_vxlan(
            request.local_ip, 
            request.remote_ip, 
            request.interface_name, 
            request.vxlan_id, 
            request.dst_port, 
            request.subnet, 
            request.ip_range, 
            sudo_password, 
            request.net_name
        )
        return JSONResponse(content={"message": "Federated Docker network and VXLAN connection created successfully"})
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/delete_docker_network_resources", tags=["Docker Functions"], summary="Delete Docker network and VXLAN")
def delete_docker_network_and_vxlan_endpoint(vxlan_id: str='200', net_name: str='federation-net'):
    global sudo_password
    try:
        docker_utils.delete_docker_network_and_vxlan(sudo_password, vxlan_id, net_name)
        return JSONResponse(content={"message": "Federated Docker network and VXLAN connection deleted successfully"})
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")

@app.post("/execute_command_in_docker_container", tags=["Docker Functions"], summary="Execute a command in a Docker Container")
def execute_command_in_docker_container_endpoint(request: ContainerCommandRequest):
    try:        
         # Split the command string into a list
        command_list = request.command.split()
        
        # Call the function and get the response
        response = docker_utils.execute_command_in_docker_container(request.name, command_list)
        
        if response is None:
            raise HTTPException(status_code=500, detail="Failed to execute command in the Docker container.")

        # Debugging: print response for troubleshooting
        logger.info(f"Command execution response: {response}")

        # Format the output as a list of lines
        response_lines = response.strip().split("\n")
        
        # Return the response in JSON format
        return JSONResponse(content={"message": "Command executed successfully", "response": response_lines})
    
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# K8s-related API Endpoints
@app.post("/deploy_kubernetes_service", tags=["Kubernetes Functions"], summary="Create k8s resource from available YAML files")
def deploy_kubernetes_service_endpoint(descriptor: str, kubeconfig_path: str = "/etc/rancher/k3s/k3s.yaml"):
    yaml_file_path = os.path.join(K8S_EXAMPLE_DESCRIPTORS_DIR, descriptor)

    # Check if the file exists
    if not os.path.exists(yaml_file_path):
        raise HTTPException(status_code=404, detail=f"YAML file '{descriptor}' not found in {K8S_EXAMPLE_DESCRIPTORS_DIR}")

    try:
        k8s_utils.create_kubernetes_resource_from_yaml(yaml_file_path, kubeconfig_path)
        return JSONResponse(content={"message": f"Kubernetes resource {descriptor} created successfully"})
    except Exception as e:
        logger.error(f"Error occurred while deploying Kubernetes service: {e}")
        raise HTTPException(status_code=500, detail="An error occurred during the Kubernetes service deployment")

@app.delete("/delete_kubernetes_service", tags=["Kubernetes Functions"], summary="Delete k8s resource from available YAML files")
def delete_kubernetes_service_endpoint(descriptor: str, kubeconfig_path: str = "/etc/rancher/k3s/k3s.yaml"):
    yaml_file_path = os.path.join(K8S_EXAMPLE_DESCRIPTORS_DIR, descriptor)

    # Check if the file exists
    if not os.path.exists(yaml_file_path):
        raise HTTPException(status_code=404, detail=f"YAML file '{descriptor}' not found in {K8S_EXAMPLE_DESCRIPTORS_DIR}")

    try:
        k8s_utils.delete_kubernetes_resource_from_yaml(yaml_file_path, kubeconfig_path)
        return JSONResponse(content={"message": f"Kubernetes resource {descriptor} deleted successfully"})
    except Exception as e:
        logger.error(f"Error occurred while deleting Kubernetes resource: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while deleting the Kubernetes resource.")

@app.post("/configure_kubernetes_network_resources", tags=["Kubernetes Functions"], summary="Configure Kubernetes network and VXLAN")
def configure_kubernetes_network_and_vxlan_endpoint(request: KubernetesNetworkConfigRequest):
    global sudo_password
    try:
        k8s_utils.configure_kubernetes_network_and_vxlan(
            request.local_ip, 
            request.remote_ip, 
            request.interface_name, 
            request.vxlan_id, 
            request.dst_port, 
            request.subnet, 
            request.ip_range, 
            sudo_password, 
            request.net_name
        )
        return JSONResponse(content={"message": "Federated K8s network and VXLAN connection created successfully"})
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/delete_kubernetes_network_resources", tags=["Kubernetes Functions"], summary="Delete Kubernetes network and VXLAN")
def delete_kubernetes_network_and_vxlan_endpoint(vxlan_id: str='200', net_name: str='federation-net'):
    global sudo_password
    try:
        k8s_utils.delete_kubernetes_network_and_vxlan(sudo_password, vxlan_id, net_name)
        return JSONResponse(content={"message": "Federated K8s network and VXLAN connection deleted successfully"})
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")


@app.post("/execute_command_in_kubernetes_pod", tags=["Kubernetes Functions"], summary="Execute a command in a Kubernetes Pod")
def execute_command_in_kubernetes_pod_endpoint(request: ContainerCommandRequest):
    try:        
         # Split the command string into a list
        command_list = request.command.split()
        
        # Call the function and get the response
        response = k8s_utils.execute_command_in_kubernetes_pod(request.name, command_list, request.namespace, request.kubeconfig_path)
        
        if response is None:
            raise HTTPException(status_code=500, detail="Failed to execute command in the Kubernetes pod.")

        # Debugging: print response for troubleshooting
        logger.info(f"Command execution response: {response}")

        # Format the output as a list of lines
        response_lines = response.strip().split("\n")
        
        # Return the response in JSON format
        return JSONResponse(content={"message": "Command executed successfully", "response": response_lines})
    
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
