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

import utility_functions as utils

# Define FastAPI app and OpenAPI metadata
tags_metadata = [
    {"name": "Default DLT federation functions", "description": "Functions for consumer and provider domains."},
    {"name": "Consumer DLT federation functions", "description": "Functions for consumer domains."},
    {"name": "Provider DLT federation functions", "description": "Functions for provider domains."}
]

class FederationEvents(str, Enum):
    OPERATOR_REGISTERED = "OperatorRegistered"
    OPERATOR_REMOVED = "OperatorRemoved"
    SERVICE_ANNOUNCEMENT = "ServiceAnnouncement"
    NEW_BID = "NewBid"
    SERVICE_ANNOUNCEMENT_CLOSED = "ServiceAnnouncementClosed"
    SERVICE_DEPLOYED_EVENT = "ServiceDeployedEvent"

app = FastAPI(
    title="DLT Service Federation API",
    description="This API provides endpoints for interacting with the DLT (Blockchain + Federation Smart Contract)",
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
        logger.info(f"Loaded environment variables from: {file}")
    else:
        raise EnvironmentError(f"Environment variable {env_file} is not set.")

# Configuration from environment variables
try:
    domain = os.getenv('DOMAIN_FUNCTION', '').strip().lower()
    dlt_node_id = os.getenv('DLT_NODE_ID')
    eth_node_url = os.getenv('WS_URL')
    ip_address = os.getenv('NODE_IP')


except Exception as e:
    logger.error(f"Error loading configuration: {e}")
    raise

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
    private_key = os.getenv('PRIVATE_KEY')
    block_address = os.getenv('ETHERBASE')
    # Number used to ensure the order of transactions (and prevent transaction replay attacks)
    nonce = web3.eth.getTransactionCount(block_address)

except Exception as e:
    logger.error(f"Error initializing Web3: {e}")

# Initialize global variables
service_id = ''
domain_registered = False

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
    service_type: Optional[str] = "k8s_deployment"
    bandwidth_gbps: Optional[float] = None 
    rtt_latency_ms: Optional[int] = None 
    compute_cpus: Optional[int] = None 
    compute_ram_gb: Optional[int] = None 
    
class UpdateEndpointRequest(BaseModel):
    service_id: str
    topology_db: str
    ns_id: str 
    service_catalog_db: Optional[str] = None
    nsd_id: Optional[str] = None

class PlaceBidRequest(BaseModel):
    service_id: str
    service_price: int

class ChooseProviderRequest(BaseModel):
    bid_index: int
    service_id: str

class ServiceDeployedRequest(BaseModel):
    service_id: str
    federated_host: str

class ConsumerFederationProcessRequest(BaseModel):
    # Flag to indicate whether results should be exported to a CSV file
    export_to_csv: Optional[bool] = False
    csv_path: Optional[str] = None

    # Minimum number of service providers required before making a selection
    service_providers: Optional[int] = 1

    # Endpoint info
    topology_db: str
    ns_id: str 
    service_catalog_db: Optional[str] = None
    nsd_id: Optional[str] = None

    # Service requirements
    service_type: Optional[str] = "k8s_deployment"
    bandwidth_gbps: Optional[float] = None 
    rtt_latency_ms: Optional[int] = None 
    compute_cpus: Optional[int] = None 
    compute_ram_gb: Optional[int] = None 

class ProviderFederationProcessRequest(BaseModel):
    # Flag to indicate whether results should be exported to a CSV file
    export_to_csv: Optional[bool] = False
    csv_path: Optional[str] = None

    offered_service: Optional[str] = "k8s_deployment"
    
    # Endpoint info
    topology_db: Optional[str] = None
    ns_id: Optional[str] = None 
    
    # The price of the service offered by the provider
    service_price: Optional[int] = 10


# Function to format service requirements in key=value; format with all fields included
def format_service_requirements(request: ServiceAnnouncementRequest) -> str:
    fields = []
    
    # Ensure all fields are included, even if the value is None
    fields.append(f"service_type={request.service_type or 'None'}")
    fields.append(f"bandwidth_gbps={request.bandwidth_gbps if request.bandwidth_gbps is not None else 'None'}")
    fields.append(f"rtt_latency_ms={request.rtt_latency_ms if request.rtt_latency_ms is not None else 'None'}")
    fields.append(f"compute_cpus={request.compute_cpus if request.compute_cpus is not None else 'None'}")
    fields.append(f"compute_ram_gb={request.compute_ram_gb if request.compute_ram_gb is not None else 'None'}")
    
    # Join all fields with a semicolon separator
    return "; ".join(fields)

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
                                 
def AnnounceService(blockchain_address: str, service_requirements: str,
                    endpoint_service_catalog_db: str, endpoint_topology_db:str,
                    endpoint_nsd_id: str, endpoint_ns_id:str) -> str:
    global service_id, nonce, Federation_contract
    try:
        service_id = 'service' + str(int(time.time()))
        announce_transaction = Federation_contract.functions.AnnounceService(
            _requirements=web3.toBytes(text=service_requirements),
            _id=web3.toBytes(text=service_id),
            endpoint_service_catalog_db=web3.toBytes(text=endpoint_service_catalog_db),
            endpoint_topology_db=web3.toBytes(text=endpoint_topology_db),
            endpoint_nsd_id=web3.toBytes(text=endpoint_nsd_id),
            endpoint_ns_id=web3.toBytes(text=endpoint_ns_id)
        ).buildTransaction({
            'from': blockchain_address,
            'nonce': nonce
        })
        tx_hash = send_signed_transaction(announce_transaction)
        return tx_hash
    except Exception as e:
        logger.error(f"Failed to announce service: {str(e)}")
        raise Exception("Service announcement failed.")

def UpdateEndpoint(service_id: str, domain: str, blockchain_address: str, 
                   endpoint_service_catalog_db: str, endpoint_topology_db:str,
                   endpoint_nsd_id: str, endpoint_ns_id:str) -> str:
    global nonce, Federation_contract
    try:
        provider_flag = (domain == "provider")
        update_endpoint_transaction = Federation_contract.functions.UpdateEndpoint(
            provider=provider_flag, 
            _id=web3.toBytes(text=service_id),
            endpoint_service_catalog_db=web3.toBytes(text=endpoint_service_catalog_db),
            endpoint_topology_db=web3.toBytes(text=endpoint_topology_db),
            endpoint_nsd_id=web3.toBytes(text=endpoint_nsd_id),
            endpoint_ns_id=web3.toBytes(text=endpoint_ns_id)
        ).buildTransaction({
            'from': blockchain_address,
            'nonce': nonce
        })
        tx_hash = send_signed_transaction(update_endpoint_transaction)
        return tx_hash
    except Exception as e:
        logger.error(f"Failed to update endpoint: {str(e)}")
        raise Exception("Service update failed.")

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

def GetServiceInfo(service_id: str, domain: str, blockchain_address: str) -> tuple:
    global Federation_contract
    try:
        service_id_bytes = web3.toBytes(text=service_id)
        provider_flag = (domain == "provider")
        
        service_id, federated_host, endpoint_service_catalog_db, endpoint_topology_db, endpoint_nsd_id, endpoint_ns_id = Federation_contract.functions.GetServiceInfo(
            _id=service_id_bytes, provider=provider_flag, call_address=blockchain_address).call()

        return (
            federated_host.rstrip(b'\x00').decode('utf-8'),
            endpoint_service_catalog_db.rstrip(b'\x00').decode('utf-8'),
            endpoint_topology_db.rstrip(b'\x00').decode('utf-8'),
            endpoint_nsd_id.rstrip(b'\x00').decode('utf-8'),
            endpoint_ns_id.rstrip(b'\x00').decode('utf-8')
        )
    except Exception as e:
        logger.error(f"Failed to retrieve deployed info for service_id {service_id} and domain {domain}: {str(e)}")
        raise Exception(f"Error occurred while retrieving deployed info for service_id {service_id} and domain {domain}.")

def PlaceBid(service_id: str, service_price: int, blockchain_address: str,
            endpoint_service_catalog_db: str, endpoint_topology_db:str,
            endpoint_nsd_id: str, endpoint_ns_id:str) -> str:
    global nonce, Federation_contract
    try:
        place_bid_transaction = Federation_contract.functions.PlaceBid(
            _id=web3.toBytes(text=service_id),
            _price=service_price,
            endpoint_service_catalog_db=web3.toBytes(text=endpoint_service_catalog_db),
            endpoint_topology_db=web3.toBytes(text=endpoint_topology_db),
            endpoint_nsd_id=web3.toBytes(text=endpoint_nsd_id),
            endpoint_ns_id=web3.toBytes(text=endpoint_ns_id)
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
@app.get("/web3_info", summary="Get Web3 info", tags=["Default DLT federation functions"])
async def web3_info_endpoint():
    """
    Retrieve Web3 connection details.

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
        request (DomainRegistrationRequest): A Pydantic model containing the following fields:
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
        None

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
        request (ServiceAnnouncementRequest): A Pydantic model containing the following fields:
            - service_type (str, optional): The type of the service (default: "K8s App Deployment").
            - bandwidth_gbps (float, optional): The required bandwidth in Gbps (default: None).
            - rtt_latency_ms (int, optional): The required round-trip latency in ms (default: None).
            - compute_cpus (int, optional): The required number of CPUs for the service (default: None).
            - compute_ram_gb (int, optional): The required amount of RAM in GB (default: None).

    Returns:
        JSONResponse: A JSON object containing:
            - tx_hash (str): The transaction hash of the service announcement.
            - service_id (str): The unique identifier for the service.

    Raises:
        HTTPException:
            - 500: If there is an error during the service announcement process.
    """
    global service_id, block_address
    try:
        formatted_requirements = format_service_requirements(request)
        tx_hash = AnnounceService(block_address, formatted_requirements, "None", "None", "None", "None") 
        return JSONResponse(content={"tx_hash": tx_hash, "service_id": service_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/service_state", summary="Get service state", tags=["Default DLT federation functions"])
async def check_service_state_endpoint(service_id: str = Query(..., description="The service ID to check the state of")):
    """
    Returns the current state of a service by its service ID.
    
    Args:
        - service_id (str): The unique identifier of the service whose state is being queried.

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

@app.get("/service_info", summary="Get service info", tags=["Default DLT federation functions"])
async def check_deployed_info_endpoint(service_id: str = Query(..., description="The service ID to get the deployed info for the federated service")):
    """
    Retrieves deployment information for a federated service.

    Args:
        - service_id (str): The unique identifier of the deployed service.

    Returns:
        JSONResponse: A JSON object containing:
            - federated_host (str): The external IP address of the deployed service.
            - endpoint_provider or endpoint_consumer (dict): Contains:
                - service_catalog_db (str)
                - topology_db (str)
                - nsd_id (str)
                - ns_id (str)
    Raises:
        HTTPException:
            - 500: If there is an error retrieving the deployment information.
    """   
    global domain, block_address
    try:
        federated_host, service_catalog_db, topology_db, nsd_id, ns_id = GetServiceInfo(service_id, domain, block_address)
        
        response_data = {}
        
        if domain == "provider":
            response_data = {
                "federated_host": federated_host,
                "endpoint_provider": {
                    "service_catalog_db": service_catalog_db,
                    "topology_db": topology_db,
                    "nsd_id": nsd_id,
                    "ns_id": ns_id
                }
            }
        else:
            response_data = {
                "federated_host": federated_host,
                "endpoint_consumer": {
                    "service_catalog_db": service_catalog_db,
                    "topology_db": topology_db,
                    "nsd_id": nsd_id,
                    "ns_id": ns_id
                }
            }      
        return JSONResponse(content=response_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/service_announcements", summary="Check service federation announcements", tags=["Provider DLT federation functions"])
async def check_service_announcements_endpoint():
    """
    Check for new service announcements in the last 20 blocks.

    Returns:
        JSONResponse: A JSON object containing a list of service announcements, where each announcement includes:
            - service_id (str): The unique identifier of the announced federated service.
            - service_requirements (dict): Parsed requirements for the requested federated service.
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
            formatted_requirements = web3.toText(event['args']['requirements']).rstrip('\x00')
            requirements = utils.extract_service_requirements(formatted_requirements) # Convert to dict
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

    Returns:
        JSONResponse: A JSON object containing:
            - tx_hash (str): The transaction hash of the submitted bid.

    Raises:
        HTTPException: 
            - 400: If the provided endpoint format is invalid.
            - 500: If there is an internal server error during bid submission.
    """ 
    global block_address
    try:
        tx_hash = PlaceBid(request.service_id, request.service_price, block_address, "None", "None", "None", "None")
        return JSONResponse(content={"tx_hash": tx_hash})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/bids", summary="Check bids", tags=["Consumer DLT federation functions"]) 
async def check_bids_endpoint(service_id: str = Query(..., description="The service ID to check bids for")):
    """
    Check for bids placed on a specific service.

    Args:
        - service_id (str): The unique identifier of the service to check for bids.

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

@app.post("/send_endpoint_info", summary="Send endpoint information for federated service deployment", tags=["Default DLT federation functions"])
def send_endpoint_info(request: UpdateEndpointRequest):
    """
    
    Args:
        request (UpdateEndpointRequest): A Pydantic model containing the following fields:
            - service_id (str): The unique identifier of the service.
            - topology_db (str): URL or endpoint of the topology database.
            - ns_id (str): Network Service ID.
            - service_catalog_db (str, optional): URL or endpoint of the service catalog database (default: None).
            - nsd_id (str, optional): Network Service Descriptor ID (default: None).

    Returns:
        JSONResponse: A JSON object containing:
            - tx_hash (str): The transaction hash of the sent transaction for choosing the provider.

    Raises:
        HTTPException: 
            - 500: If there is an internal server error during the process of sending the endpoint information.
    """    
    global block_address
    try:            
        service_catalog_db = request.service_catalog_db if request.service_catalog_db is not None else "None"
        nsd_id = request.nsd_id if request.nsd_id is not None else "None"

        tx_hash = UpdateEndpoint(request.service_id, domain, block_address,
                                 service_catalog_db, request.topology_db,
                                 nsd_id, request.ns_id)
        return JSONResponse(content={"tx_hash": tx_hash})    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/winner_status", summary="Check if a winner has been chosen", tags=["Provider DLT federation functions"])
async def check_winner_status_endpoint(service_id: str = Query(..., description="The service ID to check if there is a winner provider in the federation")):
    """
    Check if a winner has been chosen for a specific service in the federation.

    Args:
        - service_id (str): The unique identifier of the service for which the winner is being checked.

    Returns:
        JSONResponse: A JSON object containing:
            - winner (str): 'yes' if a winner has been selected, otherwise 'no'.

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
                return JSONResponse(content={"winner": "yes"})   
        return JSONResponse(content={"winner": "no"})  
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/is_winner", summary="Check if the calling provider is the winner", tags=["Provider DLT federation functions"])
async def check_if_I_am_Winner_endpoint(service_id: str = Query(..., description="The service ID to check if I am the winner provider in the federation")):
    """
    Check if the calling provider is the winner for a specific service.

    Args:
        - service_id (str): The unique identifier of the service for which the provider's winner status is being checked.

    Returns:
        JSONResponse: A JSON object containing:
            - is_winner (str): 'yes' if the calling provider is the winner, otherwise 'no'.

    Raises:
        HTTPException:
            - 500: If there is an internal server error while checking the winner status.
    """
    global block_address
    try:
        if CheckWinner(service_id, block_address):
           return JSONResponse(content={"is_winner": "yes"})
        else:
           return JSONResponse(content={"is_winner": "no"})
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


###---###
@app.post("/simulate_consumer_federation_process", tags=["Consumer DLT federation functions"])
def simulate_consumer_federation_process(request: ConsumerFederationProcessRequest):
    global block_address, domain, service_id
    try:
        # List to store the timestamps of each federation step
        federation_step_times = []  
        header = ['step', 'timestamp']
        data = []

        formatted_requirements = format_service_requirements(request)

        if domain == 'consumer':
            
            # Start time of the process
            process_start_time = time.time()
                        
            # Send service announcement (federation request)
            t_service_announced = time.time() - process_start_time
            data.append(['service_announced', t_service_announced])

            service_catalog_db = request.service_catalog_db if request.service_catalog_db is not None else "None"
            topology_db = request.topology_db if request.topology_db is not None else "None"
            nsd_id = request.nsd_id if request.nsd_id is not None else "None"
            ns_id = request.ns_id if request.ns_id is not None else "None"

            tx_hash = AnnounceService(block_address, formatted_requirements, service_catalog_db, topology_db, nsd_id, ns_id) 
            logger.info(f"📢 Service announcement sent - Service ID: {service_id}")

            # Wait for provider bids
            bids_event = create_event_filter(FederationEvents.NEW_BID)
            bidderArrived = False
            logger.info("⏳ Waiting for bids...")
            while not bidderArrived:
                new_events = bids_event.get_all_entries()
                for event in new_events:
                    event_id = str(web3.toText(event['args']['_id']))
                    received_bids = int(event['args']['max_bid_index'])
                    
                    if received_bids >= request.service_providers:
                        t_bid_offer_received = time.time() - process_start_time
                        data.append(['bid_offer_received', t_bid_offer_received])
                        logger.info(f"📨 {received_bids} bid(s) received:")
                        bidderArrived = True 
                        break
            
            # Received bids
            lowest_price = None
            best_bid_index = None

            # Loop through all bid indices and print their information
            for i in range(received_bids):
                bid_info = GetBidInfo(service_id, i, block_address)
                provider_addr = bid_info[0]
                bid_price = int(bid_info[1])
                bid_index = int(bid_info[2])
                print(
                    f"{'-'*40}\n"
                    f"Bid index     : {bid_index}\n"
                    f"Bid price     : {bid_price} €/hour\n"
                    f"Provider  : {provider_addr}\n"
                    f"{'-'*40}"
                )
                if lowest_price is None or bid_price < lowest_price:
                    lowest_price = bid_price
                    best_bid_index = bid_index
                    # logger.info(f"New lowest price: {lowest_price} with bid index: {best_bid_index}")
                            
            # Choose winner provider
            t_winner_choosen = time.time() - process_start_time
            data.append(['winner_choosen', t_winner_choosen])
            tx_hash = ChooseProvider(service_id, best_bid_index, block_address)
            logger.info(f"🏆 Provider selected - Bid index: {best_bid_index}")

            logger.info("Endpoint information for application migration and inter-domain connectivity shared.")

            # Wait for provider confirmation
            serviceDeployed = False 
            logger.info(f"⏳ Waiting for provider to complete deployment...")
            while serviceDeployed == False:
                serviceDeployed = True if GetServiceState(service_id) == 2 else False
                        
            # Confirmation received
            t_confirm_deployment_received = time.time() - process_start_time
            data.append(['confirm_deployment_received', t_confirm_deployment_received])
            logger.info("✅ Deployment confirmation received.")
            # DisplayServiceState(service_id)

            # Federated service info
            federated_host, endpoint_provider_service_catalog_db, endpoint_provider_topology_db, endpoint_provider_nsd_id, endpoint_provider_ns_id = GetServiceInfo(service_id, domain, block_address)

            logger.info(
                "📡 Federated service info\n"
                f"{'-'*40}\n"
                f"{'Federated instance':<22}: {federated_host}\n"
                f"{'Network config':<22}:\n"
                f"  └ {'protocol':<18}: vxlan\n"
                f"  └ {'vni':<18}: 49\n"
                f"  └ {'local_ip':<18}: X\n"
                f"  └ {'remote_ip':<18}: Y\n"
                f"  └ {'local_port':<18}: 4789\n"
                f"  └ {'udp_port':<18}: 4789\n"
                f"{'-'*40}"
            )

            # Establish connection with the provider 
            t_establish_connection_with_provider_start = time.time() - process_start_time
            data.append(['establish_connection_with_provider_start', t_establish_connection_with_provider_start])
            
            logger.info("🔗 Setting up network connectivity with the provider...")
            API_URL = "http://10.5.15.16:9999"
            
            t_establish_connection_with_provider_finished = time.time() - process_start_time
            data.append(['establish_connection_with_provider_finished', t_establish_connection_with_provider_finished])
           
            total_duration = time.time() - process_start_time

            logger.info(f"Testing connectivity with federated instance...")

            logger.info(f"✅ Federation process successfully completed in {total_duration:.2f} seconds.")

            response = {
                "status": "success",
                "message": "Federation completed successfully.",
                "federation_duration_seconds": round(total_duration, 2),
                "federated_instance": federated_host
            }

            if request.export_to_csv:
                utils.create_csv_file(request.csv_path, header, data)
            
            return JSONResponse(content=response)
    except Exception as e:
        logger.error(f"Federation process failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))    

@app.post("/simulate_provider_federation_process", tags=["Provider DLT federation functions"])
def simulate_provider_federation_process(request: ProviderFederationProcessRequest):
    """
    """  
    global block_address, domain
    try:
        # List to store the timestamps of each federation step
        federation_step_times = []  
        header = ['step', 'timestamp']
        data = []

        if domain == 'provider':
            
            # Start time of the process
            process_start_time = time.time()
            
            service_id = ''
            newService = False
            open_services = []
            topology_db = request.topology_db if request.topology_db is not None else "None"
            ns_id = request.ns_id if request.ns_id is not None else "None"

            # Wait for service announcements
            new_service_event = create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT)
            logger.info("⏳ Waiting for federation events...")

            while newService == False:
                new_events = new_service_event.get_all_entries()
                for event in new_events:
                    service_id = web3.toText(event['args']['id'])
                    formatted_requirements = web3.toText(event['args']['requirements'])
                    requirements = utils.extract_service_requirements(formatted_requirements) 

                    # Check if this provider can offer the requested service
                    is_match = request.offered_service.strip().lower() == requirements["service_type"].strip().lower()

                    filtered_requirements = {
                        k: v for k, v in requirements.items()
                        if v is not None and str(v).lower() != "none"
                    }


                    if GetServiceState(service_id) == 0 and is_match:
                        open_services.append(service_id)
                        logger.info(
                            "📨 New service announcement:\n"
                            f"{'-'*40}\n"
                            f"{'Service ID':<22}: {service_id}\n"
                            f"{'Service state':<22}: Open\n"
                            f"{'Provider can fulfill':<22}: {is_match}\n"
                            f"{'Requirements':<22}:\n" +
                            "".join([f"  └ {k:<20}: {v}\n" for k, v in filtered_requirements.items()]) +
                            f"{'-'*40}"
                        )

                
                if len(open_services) > 0:
                    # Announcement received
                    t_announce_received = time.time() - process_start_time
                    data.append(['announce_received', t_announce_received])
                    # logger.info(f"Offers received: {len(open_services)}")
                    newService = True
                
            service_id = open_services[-1]
            # DisplayServiceState(service_id)

            # Place a bid offer
            t_bid_offer_sent = time.time() - process_start_time
            data.append(['bid_offer_sent', t_bid_offer_sent])
            tx_hash = PlaceBid(service_id, request.service_price, block_address, "None", "None", "None", "None")
            
            logger.info(f"💰 Bid offer sent - Service ID: {service_id}, Price: {request.service_price} €/hour")

            logger.info("⏳ Waiting for a winner to be selected...")

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
                    logger.info(f"🏆 Selected as the winner for service ID: {service_id}.")
                    # Start the deployment of the requested federated service
                    t_deployment_start = time.time() - process_start_time
                    data.append(['deployment_start', t_deployment_start])
                    break
                else:
                    logger.info(f"Not selected as the winner for service ID: {service_id}. Another provider has been chosen.")
                    t_other_provider_choosen = time.time() - process_start_time
                    data.append(['other_provider_choosen', t_other_provider_choosen])
                    if request.export_to_csv:
                        utils.create_csv_file(domain, header, data)
                        return JSONResponse(content={"message": f"Another provider was chosen for service ID: {service_id}."})

                    
            # Federated service info
            federated_host, endpoint_consumer_service_catalog_db, endpoint_consumer_topology_db, endpoint_consumer_nsd_id, endpoint_consumer_ns_id = GetServiceInfo(service_id, domain, block_address)
            
            logger.info(
                "📡 Federated service info\n"
                f"{'-'*40}\n"
                f"{'App descriptor':<22}: {endpoint_consumer_nsd_id}\n"
                f"{'Network config':<22}:\n"
                f"  └ {'protocol':<20}: vxlan\n"
                f"  └ {'vni':<20}: 49\n"
                f"  └ {'local_ip':<20}: X\n"
                f"  └ {'remote_ip':<20}: Y\n"
                f"  └ {'local_port':<20}: 4789\n"
                f"  └ {'udp_port':<20}: 4789\n"
                f"{'-'*40}"
            )

            # Deploy federated service (VXLAN tunnel + containers deployment)
            federated_host = "192.168.70.10"

            logger.info("🚀 Starting deployment of ROS-based application...")
            time.sleep(1)

            logger.info("🔗 Setting up network connectivity with the consumer...")
            API_URL = "http://10.5.98.105:9999"

            # Deployment finished
            t_deployment_finished = time.time() - process_start_time
            data.append(['deployment_finished', t_deployment_finished])
                
            # Send deployment confirmation
            t_confirm_deployment_sent = time.time() - process_start_time
            data.append(['confirm_deployment_sent', t_confirm_deployment_sent])

            tx_hash = UpdateEndpoint(service_id, domain, block_address,
                                 "None", topology_db,
                                 "None", ns_id)

            ServiceDeployed(service_id, federated_host, block_address)
            
            total_duration = time.time() - process_start_time

            logger.info("Endpoint information for inter-domain connectivity shared.")
            logger.info(f"✅ Service Deployed - Federated Instance (ROS_IP): {federated_host}")

            response = {
                "status": "success",
                "message": "Federation process completed successfully.",
                "federation_duration_seconds": round(total_duration, 2),
                "federated_instance": federated_host
            }
                
            if request.export_to_csv:
                utils.create_csv_file(request.csv_path, header, data)

            return JSONResponse(content=response)
        else:
            logger.error(f"Federation process failed: {str(e)}")
            raise HTTPException(status_code=500, detail="You must be provider to run this code")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  
###---###

# # # @app.post("/simulate_consumer_federation_process", tags=["Consumer DLT federation functions"])
# # # def simulate_consumer_federation_process(request: ConsumerFederationProcessRequest):
# # #     """
# # #     Simulates the consumer-side service federation process, including the following steps:
    
# # #     - Announcing the service federation request.
# # #     - Waiting for bids from providers.
# # #     - Evaluating and selecting the best bid.
# # #     - Waiting for provider confirmation and service deployment.
# # #     - Establishing a VXLAN connection with the provider.

# # #     This function performs the entire consumer-side process, from service announcement to deployment confirmation,
# # #     and establishes the required VXLAN tunnel for communication between the consumer and provider.

# # #     Args:
# # #     - request (ConsumerFederationProcessRequest).

# # #     Returns:
# # #     - JSONResponse: A JSON object with the following keys:
# # #         - message (str): A message confirming the successful completion of the federation process.
# # #         - federated_host (str): The IP address of the federated host.
    
# # #     Raises:
# # #     - HTTPException:
# # #         - 400: If the provided 'requirements' or 'endpoint' format is invalid.
# # #         - 500: If any error occurs during the federation process.
# # #     """
# # #     global block_address, domain, service_id
# # #     try:
# # #         # List to store the timestamps of each federation step
# # #         federation_step_times = []  
# # #         header = ['step', 'timestamp']
# # #         data = []

# # #         formatted_requirements = format_service_requirements(request)

# # #         if domain == 'consumer':
            
# # #             # Start time of the process
# # #             process_start_time = time.time()
                        
# # #             # Send service announcement (federation request)
# # #             t_service_announced = time.time() - process_start_time
# # #             data.append(['service_announced', t_service_announced])

# # #             service_catalog_db = request.service_catalog_db if request.service_catalog_db is not None else "None"
# # #             topology_db = request.topology_db if request.topology_db is not None else "None"
# # #             nsd_id = request.nsd_id if request.nsd_id is not None else "None"
# # #             ns_id = request.ns_id if request.ns_id is not None else "None"

# # #             tx_hash = AnnounceService(block_address, formatted_requirements, service_catalog_db, topology_db, nsd_id, ns_id) 
# # #             logger.info(f"Service announcement sent - Service ID: {service_id}")

# # #             # Wait for provider bids
# # #             bids_event = create_event_filter(FederationEvents.NEW_BID)
# # #             bidderArrived = False
# # #             logger.info("⏳ Waiting for bids...")
# # #             while not bidderArrived:
# # #                 new_events = bids_event.get_all_entries()
# # #                 for event in new_events:
# # #                     event_id = str(web3.toText(event['args']['_id']))
# # #                     received_bids = int(event['args']['max_bid_index'])
                    
# # #                     if received_bids >= request.service_providers:
# # #                         t_bid_offer_received = time.time() - process_start_time
# # #                         data.append(['bid_offer_received', t_bid_offer_received])
# # #                         logger.info(f"{received_bids} offer(s) received:")
# # #                         bidderArrived = True 
# # #                         break
            
# # #             # Received bids
# # #             lowest_price = None
# # #             best_bid_index = None

# # #             # Loop through all bid indices and print their information
# # #             for i in range(received_bids):
# # #                 bid_info = GetBidInfo(service_id, i, block_address)
# # #                 logger.info(f"Bid {i}: {bid_info}")
# # #                 bid_price = int(bid_info[1]) 
# # #                 if lowest_price is None or bid_price < lowest_price:
# # #                     lowest_price = bid_price
# # #                     best_bid_index = int(bid_info[2])
# # #                     # logger.info(f"New lowest price: {lowest_price} with bid index: {best_bid_index}")
                            
# # #             # Choose winner provider
# # #             t_winner_choosen = time.time() - process_start_time
# # #             data.append(['winner_choosen', t_winner_choosen])
# # #             tx_hash = ChooseProvider(service_id, best_bid_index, block_address)
# # #             logger.info(f"Provider choosen - Bid index: {best_bid_index}")

# # #             logger.info("Endpoint information for application and inter-domain connectivity shared.")

# # #             # Wait for provider confirmation
# # #             serviceDeployed = False 
# # #             logger.info(f"⏳ Waiting for provider to complete deployment...")
# # #             while serviceDeployed == False:
# # #                 serviceDeployed = True if GetServiceState(service_id) == 2 else False
                        
# # #             # Confirmation received
# # #             t_confirm_deployment_received = time.time() - process_start_time
# # #             data.append(['confirm_deployment_received', t_confirm_deployment_received])
# # #             logger.info("Deployment confirmation received.")
# # #             DisplayServiceState(service_id)

# # #             # Federated service info
# # #             federated_host, endpoint_provider_service_catalog_db, endpoint_provider_topology_db, endpoint_provider_nsd_id, endpoint_provider_ns_id = GetServiceInfo(service_id, domain, block_address)
# # #             logger.info("Federated service info:\n")

# # #             print("=== Federated Host (ROS_IP) ===")
# # #             print(federated_host)
# # #             print()

# # #             print("=== Federated Network Configuration ===")
# # #             topology_data_consumer = utils.fetch_topology_info(url=f'{topology_db}/{ns_id}', provider=False)
# # #             topology_data_provider = utils.fetch_topology_info(url=f'{endpoint_provider_topology_db}/{endpoint_provider_ns_id}', provider=True)
# # #             protocol = topology_data_consumer.get("protocol")
# # #             vxlan_id = topology_data_consumer.get("vxlan_id")
# # #             udp_port = topology_data_consumer.get("udp_port")
# # #             consumer_tunnel_endpoint = topology_data_consumer.get("consumer_tunnel_endpoint")
# # #             provider_tunnel_endpoint = topology_data_consumer.get("provider_tunnel_endpoint")
# # #             consumer_router_endpoint = topology_data_consumer.get("consumer_router_endpoint")

# # #             provider_subnet = topology_data_provider.get("provider_subnet")
# # #             provider_router_endpoint = topology_data_provider.get("provider_router_endpoint")

# # #             # Print extracted values
# # #             print("Protocol:", protocol)
# # #             print("VXLAN ID:", vxlan_id)
# # #             print("UDP Port:", udp_port)
# # #             print("Consumer Tunnel Endpoint:", consumer_tunnel_endpoint)
# # #             print("Provider Tunnel Endpoint:", provider_tunnel_endpoint)
# # #             print("Provider Subnet:", provider_subnet)
# # #             print("Provider Router Endpoint:", provider_router_endpoint)
# # #             print()

# # #             # Establish connection with the provider 
# # #             t_establish_connection_with_provider_start = time.time() - process_start_time
# # #             data.append(['establish_connection_with_provider_start', t_establish_connection_with_provider_start])
            
# # #             logger.info(f"Establishing connectivity with the provider...")
# # #             API_URL = "http://10.5.15.16:9999"
# # #             response = utils.configure_router(API_URL, "netcom;", consumer_router_endpoint, provider_router_endpoint, "eno1", vxlan_id, udp_port, provider_subnet, "172.28.0.1/30", "172.28.0.2")
# # #             # print(response)
            
# # #             t_establish_connection_with_provider_finished = time.time() - process_start_time
# # #             data.append(['establish_connection_with_provider_finished', t_establish_connection_with_provider_finished])
           
# # #             total_duration = time.time() - process_start_time

# # #             logger.info(f"Testing connectivity with remote host...")
# # #             response = utils.test_connectivity(API_URL, federated_host)
# # #             print(response)

# # #             logger.info(f"Federation process successfully completed in {total_duration:.2f} seconds.")

# # #             response = {
# # #                 "status": "success",
# # #                 "message": "Federation process completed successfully.",
# # #                 "federation_duration_seconds": round(total_duration, 2),
# # #                 "federated_host": federated_host
# # #             }

# # #             if request.export_to_csv:
# # #                 utils.create_csv_file(domain, header, data)
            
# # #             return JSONResponse(content=response)
# # #     except Exception as e:
# # #         logger.error(f"Federation process failed: {str(e)}")
# # #         raise HTTPException(status_code=500, detail=str(e))    

# # # @app.post("/simulate_provider_federation_process", tags=["Provider DLT federation functions"])
# # # def simulate_provider_federation_process(request: ProviderFederationProcessRequest):
# # #     """
# # #     Simulates the provider-side service federation process, including the following steps:

# # #     - Waiting for service announcements.
# # #     - Submitting a bid offer for the service.
# # #     - Waiting for the consumer to choose a winner.
# # #     - Deploying the federated service if selected as the winner.

# # #     Args:
# # #     - request (ProviderFederationProcessRequest)

# # #     Returns:
# # #     - JSONResponse: A message confirming the successful completion of the federation process, or an error if the provider was not chosen.

# # #     Steps:
# # #     1. **Service Announcement**: The provider subscribes to the service announcement events and waits for a new service to be announced.
# # #     2. **Bid Placement**: The provider places a bid for the service.
# # #     3. **Bid Evaluation**: The provider waits for the consumer to evaluate bids and select a winner.
# # #     4. **Service Deployment**: If the provider wins, the service is deployed.
# # #     5. **Deployment Confirmation**: The provider confirms the deployment on the blockchain and the process ends.

# # #     Raises:
# # #     - HTTPException: 
# # #         - 500: If an error occurs during any step of the federation process or if the provider is not selected.
# # #     """  
# # #     global block_address, domain
# # #     try:
# # #         # List to store the timestamps of each federation step
# # #         federation_step_times = []  
# # #         header = ['step', 'timestamp']
# # #         data = []

# # #         if domain == 'provider':
            
# # #             # Start time of the process
# # #             process_start_time = time.time()
            
# # #             service_id = ''
# # #             newService = False
# # #             open_services = []
# # #             topology_db = request.topology_db if request.topology_db is not None else "None"
# # #             ns_id = request.ns_id if request.ns_id is not None else "provider-net.yaml"

# # #             # Wait for service announcements
# # #             new_service_event = create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT)
# # #             logger.info("Subscribed to federation events. Waiting for service announcements...")

# # #             while newService == False:
# # #                 new_events = new_service_event.get_all_entries()
# # #                 for event in new_events:
# # #                     service_id = web3.toText(event['args']['id'])
# # #                     formatted_requirements = web3.toText(event['args']['requirements'])
# # #                     requirements = utils.extract_service_requirements(formatted_requirements) 
                    
# # #                     if GetServiceState(service_id) == 0:
# # #                         open_services.append(service_id)
                
# # #                 if len(open_services) > 0:
# # #                     # Announcement received
# # #                     t_announce_received = time.time() - process_start_time
# # #                     data.append(['announce_received', t_announce_received])
# # #                     logger.info(f"New service announcement received:\n" +
# # #                         f"  Service ID: {service_id}\n" +
# # #                         f"  Requirements: {requirements}\n")
# # #                     newService = True
                
# # #             service_id = open_services[-1]
# # #             DisplayServiceState(service_id)

# # #             # Place a bid offer
# # #             t_bid_offer_sent = time.time() - process_start_time
# # #             data.append(['bid_offer_sent', t_bid_offer_sent])
# # #             tx_hash = PlaceBid(service_id, request.service_price, block_address, "None", "None", "None", "None")
# # #             logger.info(f"Bid offer sent - Service ID: {service_id}, Price: {request.service_price} €")

# # #             logger.info("⏳ Waiting for a winner to be selected...")
# # #             winner_chosen_event = create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT_CLOSED)
# # #             winnerChosen = False
# # #             while winnerChosen == False:
# # #                 new_events = winner_chosen_event.get_all_entries()
# # #                 for event in new_events:
# # #                     event_serviceid = web3.toText(event['args']['_id'])
                    
# # #                     if event_serviceid == service_id:    
# # #                         # Winner choosen received
# # #                         t_winner_received = time.time() - process_start_time
# # #                         data.append(['winner_received', t_winner_received])
# # #                         winnerChosen = True
# # #                         break
            
# # #             am_i_winner = False
# # #             while am_i_winner == False:
# # #                 # Check if I am the winner
# # #                 am_i_winner = CheckWinner(service_id, block_address)
# # #                 if am_i_winner == True:
# # #                     logger.info(f"Selected as the winner for service ID: {service_id}. Proceeding with deployment...")
# # #                     # Start the deployment of the requested federated service
# # #                     t_deployment_start = time.time() - process_start_time
# # #                     data.append(['deployment_start', t_deployment_start])
# # #                     break
# # #                 else:
# # #                     logger.info(f"Not selected as the winner for service ID: {service_id}. Another provider has been chosen.")
# # #                     t_other_provider_choosen = time.time() - process_start_time
# # #                     data.append(['other_provider_choosen', t_other_provider_choosen])
# # #                     if request.export_to_csv:
# # #                         utils.create_csv_file(domain, header, data)
# # #                         return JSONResponse(content={"message": f"Another provider was chosen for service ID: {service_id}."})

                    
# # #             # Federated service info
# # #             federated_host, endpoint_consumer_service_catalog_db, endpoint_consumer_topology_db, endpoint_consumer_nsd_id, endpoint_consumer_ns_id = GetServiceInfo(service_id, domain, block_address)
# # #             logger.info("Federated service info:\n")

# # #             print("=== Application Descriptor ===")
# # #             utils.fetch_raw_yaml(url=f'{endpoint_consumer_service_catalog_db}/{endpoint_consumer_nsd_id}')
# # #             print()

# # #             print("=== Federated Network Configuration ===")
# # #             topology_data_provider = utils.fetch_topology_info(url=f'{topology_db}/{ns_id}', provider=True)
# # #             topology_data_consumer = utils.fetch_topology_info(url=f'{endpoint_consumer_topology_db}/{endpoint_consumer_ns_id}', provider=False)
# # #             provider_router_endpoint = topology_data_provider.get("provider_router_endpoint")

# # #             protocol = topology_data_consumer.get("protocol")
# # #             vxlan_id = topology_data_consumer.get("vxlan_id")
# # #             udp_port = topology_data_consumer.get("udp_port")
# # #             consumer_tunnel_endpoint = topology_data_consumer.get("consumer_tunnel_endpoint")
# # #             provider_tunnel_endpoint = topology_data_consumer.get("provider_tunnel_endpoint")
# # #             consumer_subnet = topology_data_consumer.get("consumer_subnet")
# # #             consumer_router_endpoint = topology_data_consumer.get("consumer_router_endpoint")

# # #             # Print extracted values
# # #             print("Protocol:", protocol)
# # #             print("VXLAN ID:", vxlan_id)
# # #             print("UDP Port:", udp_port)
# # #             print("Consumer Tunnel Endpoint:", consumer_tunnel_endpoint)
# # #             print("Provider Tunnel Endpoint:", provider_tunnel_endpoint)
# # #             print("Consumer Subnet:", consumer_subnet)
# # #             print("Consumer Router Endpoint:", consumer_router_endpoint)
# # #             print()

# # #             # Deploy federated service (VXLAN tunnel + containers deployment)
# # #             federated_host = "192.168.70.10"

# # #             logger.info("Initializing deployment of ROS-based container application...")
# # #             time.sleep(1)

# # #             logger.info("Configuring network and establishing connectivity with the consumer...")
# # #             API_URL = "http://10.5.98.105:9999"
# # #             response = utils.configure_router(API_URL, "netcom;", provider_router_endpoint, consumer_router_endpoint, "enp7s0", vxlan_id, udp_port, consumer_subnet, "172.28.0.2/30", "172.28.0.1")
# # #             # print(response)

# # #             # Deployment finished
# # #             t_deployment_finished = time.time() - process_start_time
# # #             data.append(['deployment_finished', t_deployment_finished])
                
# # #             # Send deployment confirmation
# # #             t_confirm_deployment_sent = time.time() - process_start_time
# # #             data.append(['confirm_deployment_sent', t_confirm_deployment_sent])

# # #             tx_hash = UpdateEndpoint(service_id, domain, block_address,
# # #                                  "None", topology_db,
# # #                                  "None", ns_id)

# # #             ServiceDeployed(service_id, federated_host, block_address)
# # #             logger.info(f"Service Deployed - Federated Host (ROS_IP): {federated_host}")
            
# # #             total_duration = time.time() - process_start_time

# # #             logger.info("Endpoint information for inter-domain connectivity shared.")


# # #             response = {
# # #                 "status": "success",
# # #                 "message": "Federation process completed successfully.",
# # #                 "federation_duration_seconds": round(total_duration, 2),
# # #                 "federated_host": federated_host
# # #             }
                
# # #             if request.export_to_csv:
# # #                 utils.create_csv_file(domain, header, data)

# # #             return JSONResponse(content=response)
# # #         else:
# # #             logger.error(f"Federation process failed: {str(e)}")
# # #             raise HTTPException(status_code=500, detail="You must be provider to run this code")
# # #     except Exception as e:
# # #         raise HTTPException(status_code=500, detail=str(e))  