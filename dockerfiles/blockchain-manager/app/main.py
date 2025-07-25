import os
import time
import logging
import uuid
import httpx
from web3 import Web3
from fastapi import FastAPI, HTTPException, Query
from fastapi_utils.tasks import repeat_every
from typing import List, Dict

import utils
from blockchain_interface import BlockchainInterface, FederationEvents
from models import (
    SubscriptionRequest, 
    SubscriptionResponse,
    TransactionReceiptResponse,
    DomainRegistrationRequest,
    ServiceAnnouncementRequest,
    UpdateEndpointRequest,
    PlaceBidRequest,
    ChooseProviderRequest,
    ServiceDeployedRequest,
    ConsumerFederationProcessRequest,
    ProviderFederationProcessRequest,
)

# In-memory subscription store: sub_id → {'request': SubscriptionRequest, 'filter': Filter}
subscriptions: Dict[str, Dict] = {}

# Define FastAPI app and OpenAPI metadata
tags_metadata = [
    {"name": "General federation functions", "description": "General functions."},
    {"name": "Consumer functions", "description": "Functions for consumer domains."},
    {"name": "Provider functions", "description": "Functions for provider domains."}
]

app = FastAPI(
    title="DLT Federation - Blockchain Manager API",
    description="This API provides endpoints for interacting with the Federation Smart Contract",
    version="1.0.0",
    openapi_tags=tags_metadata
)

domain           = os.getenv("DOMAIN_FUNCTION", "").strip().lower()
eth_address      = os.getenv("ETH_ADDRESS")
eth_private_key  = os.getenv("ETH_PRIVATE_KEY")
eth_node_url     = os.getenv("ETH_NODE_URL")
contract_addr_raw= os.getenv("CONTRACT_ADDRESS")

# -- guard against missing configurations --
required = {
    "DOMAIN_FUNCTION": domain,
    "ETH_ADDRESS":      eth_address,
    "ETH_PRIVATE_KEY":  eth_private_key,
    "ETH_NODE_URL":     eth_node_url,
    "CONTRACT_ADDRESS": contract_addr_raw,
}
missing = [k for k,v in required.items() if not v]
if missing:
    raise RuntimeError(f"ERROR: missing environment variables: {', '.join(missing)}")

# -- validate & normalize the contract address --
try:
    contract_address = Web3.toChecksumAddress(contract_addr_raw)
except Exception:
    raise RuntimeError(f"ERROR: CONTRACT_ADDRESS '{contract_addr_raw}' is not a valid Ethereum address")

# -- validate domain --
if domain not in ("provider", "consumer"):
    raise RuntimeError(f"ERROR: DOMAIN_FUNCTION must be 'provider' or 'consumer', got '{domain}'")

# Initialize logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize blockchain interface
blockchain = BlockchainInterface(
    eth_address=eth_address,
    private_key=eth_private_key,
    eth_node_url=eth_node_url,
    abi_path="/smart-contracts/build/contracts/Federation.json",
    contract_address=contract_address
)


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

# Background notifier using repeat_every
@app.on_event("startup")
@repeat_every(seconds=2)
async def notifier_loop() -> None:
    async with httpx.AsyncClient() as client:
        for sub_id, info in list(subscriptions.items()):
            req = info["request"]
            flt = info["filter"]
            for entry in flt.get_new_entries():
                # Decode event arguments using Web3.toText for clean UTF-8 strings
                decoded_args: Dict[str, str] = {}
                for k, v in entry.get("args", {}).items():
                    try:
                        text = Web3.toText(v).rstrip('\x00')
                    except (TypeError, ValueError):
                        text = v  # fallback to raw
                    decoded_args[k] = text

                payload = {
                    "subscription_id": sub_id,
                    "event": entry.get("event"),
                    "tx_hash": entry.get("transactionHash").hex(),
                    "block_number": entry.get("blockNumber"),
                    "args": decoded_args
                }
                try:
                    await client.post(req.callback_url, json=payload, timeout=5.0)
                except httpx.HTTPError as e:
                    logger.error(f"Failed to notify {req.callback_url}: {e}")

# Subscription endpoints
@app.post("/subscriptions", response_model=SubscriptionResponse, status_code=201)
def create_subscription(req: SubscriptionRequest):
    try:
        # ensure valid event
        _ = BlockchainInterface  # for type access
        event_filter = blockchain.create_event_filter(req.event_name, last_n_blocks=req.last_n_blocks)
    except ValueError:
        raise HTTPException(400, f"Unknown event '{req.event_name}'")
    sub_id = uuid.uuid4().hex
    subscriptions[sub_id] = {"request": req, "filter": event_filter}
    return SubscriptionResponse(subscription_id=sub_id, **req.dict())

@app.get("/subscriptions", response_model=List[SubscriptionResponse])
def list_subscriptions():
    return [SubscriptionResponse(subscription_id=sub_id, **info["request"].dict())
            for sub_id, info in subscriptions.items()]

@app.delete("/subscriptions/{sub_id}", status_code=204)
def delete_subscription(sub_id: str):
    subscriptions.pop(sub_id, None)
    return


@app.get("/web3_info", summary="Get Web3 info", tags=["General federation functions"])
def web3_info_endpoint():
    try:
        return {"ethereum_node_url": eth_node_url,
                "ethereum_address": eth_address,
                "contract_address": contract_address}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tx_receipt", summary="Get transaction receipt", tags=["General federation functions"], response_model=TransactionReceiptResponse)
def tx_receipt_endpoint(tx_hash: str = Query(..., description="The transaction hash to retrieve the receipt")):
    try:
        return blockchain.get_transaction_receipt(tx_hash)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/register_domain", summary="Register a new domain (operator)", tags=["General federation functions"])
def register_domain_endpoint(request: DomainRegistrationRequest):
    try:
        tx_hash = blockchain.register_domain(request.name)
        return {"tx_hash": tx_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/unregister_domain", summary="Unregisters an existing domain (operator)", tags=["General federation functions"])
def unregister_domain_endpoint():
    try:
        tx_hash = blockchain.unregister_domain()
        return {"tx_hash": tx_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/create_service_announcement", summary="Create service federation announcement", tags=["Consumer functions"])
def create_service_announcement_endpoint(request: ServiceAnnouncementRequest):
    try:
        formatted_requirements = format_service_requirements(request)
        tx_hash, service_id = blockchain.announce_service(formatted_requirements, "None", "None", "None", "None") 
        return {"tx_hash": tx_hash, "service_id": service_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/service_state", summary="Get service state", tags=["General federation functions"])
def check_service_state_endpoint(service_id: str = Query(..., description="The service ID to check the state of")): 
    try:
        current_service_state = blockchain.get_service_state(service_id)
        state_mapping = {0: "open", 1: "closed", 2: "deployed"}
        return {"service_state": state_mapping.get(current_service_state, "unknown")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/service_info", summary="Get service info", tags=["General federation functions"])
def check_deployed_info_endpoint(service_id: str = Query(..., description="The service ID to get the deployed info for the federated service")):
    try:
        federated_host, service_catalog_db, topology_db, nsd_id, ns_id = blockchain.get_service_info(service_id, domain)
        
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
        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/service_announcements", summary="Check service federation announcements", tags=["Provider functions"])
def check_service_announcements_endpoint():
    blocks_to_check = 20
    try:
        new_service_event = blockchain.create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT, last_n_blocks=blocks_to_check)
        new_events = new_service_event.get_all_entries()
        open_services = []
        announcements_received = []

        for event in new_events:
            service_id = Web3.toText(event['args']['id']).rstrip('\x00')
            formatted_requirements = Web3.toText(event['args']['requirements']).rstrip('\x00')
            requirements = utils.extract_service_requirements(formatted_requirements) # Convert to dict
            tx_hash = Web3.toHex(event['transactionHash'])
            block_number = event['blockNumber']
            event_name = event['event']
            if blockchain.get_service_state(service_id) == 0:  # Open services
                open_services.append(service_id)
                announcements_received.append({
                    "service_id": service_id,
                    "service_requirements": requirements,
                    "tx_hash": tx_hash,
                    "block_number": block_number
                })

        if announcements_received:
            return {"announcements": announcements_received}
        else:
            raise HTTPException(status_code=404, detail=f"No new services announced in the last {blocks_to_check} blocks.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/place_bid", summary="Place a bid", tags=["Provider functions"])
def place_bid_endpoint(request: PlaceBidRequest):
    try:
        tx_hash = blockchain.place_bid(request.service_id, request.service_price, "None", "None", "None", "None")
        return {"tx_hash": tx_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/bids", summary="Check bids", tags=["Consumer functions"]) 
def check_bids_endpoint(service_id: str = Query(..., description="The service ID to check bids for")):  
    blocks_to_check = 20
    try:
        bids_event = blockchain.create_event_filter(FederationEvents.NEW_BID, last_n_blocks=blocks_to_check)
        new_events = bids_event.get_all_entries()
        bids_received = []
        for event in new_events:
            received_bids = int(event['args']['max_bid_index'])
            if received_bids >= 1:
                bid_info = blockchain.get_bid_info(service_id, received_bids-1)
                bids_received.append({
                    "bid_index": bid_info[2],
                    "provider_address": bid_info[0],
                    "service_price": bid_info[1]
                })
        if bids_received:
            return {"bids": bids_received}
        else:
            raise HTTPException(status_code=404, detail=f"No new bids in the last {blocks_to_check} blocks.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/choose_provider", summary="Choose provider", tags=["Consumer functions"])
def choose_provider_endpoint(request: ChooseProviderRequest): 
    try:
        tx_hash = blockchain.choose_provider(request.service_id, request.bid_index)
        return {"tx_hash": tx_hash}    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send_endpoint_info", summary="Send endpoint information for federated service deployment", tags=["General federation functions"])
def send_endpoint_info(request: UpdateEndpointRequest):
    try:            
        service_catalog_db = request.service_catalog_db if request.service_catalog_db is not None else "None"
        nsd_id = request.nsd_id if request.nsd_id is not None else "None"

        tx_hash = blockchain.update_endpoint(request.service_id, domain,
                                 service_catalog_db, request.topology_db,
                                 nsd_id, request.ns_id)
        return {"tx_hash": tx_hash}    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/is_winner", summary="Check if the calling provider is the winner", tags=["Provider functions"])
def check_if_I_am_Winner_endpoint(service_id: str = Query(..., description="The service ID to check if I am the winner provider in the federation")):
    try:
        return {"is_winner": "yes" if blockchain.check_winner(service_id) else "no"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/service_deployed", summary="Confirm service deployment", tags=["Provider functions"])
def service_deployed_endpoint(request: ServiceDeployedRequest):
    try:
        if blockchain.check_winner(request.service_id):
            tx_hash = blockchain.service_deployed(request.service_id, request.federated_host)
            return {"tx_hash": tx_hash}
        else:
            raise HTTPException(status_code=404, detail="You are not the winner.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))    


###---###
@app.post("/start_demo_consumer", tags=["Consumer functions"])
def start_demo_consumer(request: ConsumerFederationProcessRequest):
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

            tx_hash, service_id = blockchain.announce_service(formatted_requirements, service_catalog_db, topology_db, nsd_id, ns_id) 
            logger.info(f"📢 Service announcement sent - Service ID: {service_id}")

            # Wait for provider bids
            bids_event = blockchain.create_event_filter(FederationEvents.NEW_BID)
            bidderArrived = False
            logger.info("⏳ Waiting for bids...")
            while not bidderArrived:
                new_events = bids_event.get_all_entries()
                for event in new_events:
                    event_id = str(Web3.toText(event['args']['_id']))
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
                bid_info = blockchain.get_bid_info(service_id, i)
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
            tx_hash = blockchain.choose_provider(service_id, best_bid_index)
            logger.info(f"🏆 Provider selected - Bid index: {best_bid_index}")

            logger.info("Endpoint information for application migration and inter-domain connectivity shared.")

            # Wait for provider confirmation
            serviceDeployed = False 
            logger.info(f"⏳ Waiting for provider to complete deployment...")
            while serviceDeployed == False:
                serviceDeployed = True if blockchain.get_service_state(service_id) == 2 else False
                        
            # Confirmation received
            t_confirm_deployment_received = time.time() - process_start_time
            data.append(['confirm_deployment_received', t_confirm_deployment_received])
            logger.info("✅ Deployment confirmation received.")
            # blockchain.display_service_state(service_id)

            # Federated service info
            federated_host, endpoint_provider_service_catalog_db, endpoint_provider_topology_db, endpoint_provider_nsd_id, endpoint_provider_ns_id = blockchain.get_service_info(service_id, domain)

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
            
            return response
    except Exception as e:
        logger.error(f"Federation process failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))    

@app.post("/start_demo_provider", tags=["Provider functions"])
def start_demo_provider(request: ProviderFederationProcessRequest):
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
            new_service_event = blockchain.create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT)
            logger.info("⏳ Waiting for federation events...")

            while newService == False:
                new_events = new_service_event.get_all_entries()
                for event in new_events:
                    service_id = Web3.toText(event['args']['id'])
                    formatted_requirements = Web3.toText(event['args']['requirements'])
                    requirements = utils.extract_service_requirements(formatted_requirements) 

                    # Check if this provider can offer the requested service
                    is_match = request.offered_service.strip().lower() == requirements["service_type"].strip().lower()

                    filtered_requirements = {
                        k: v for k, v in requirements.items()
                        if v is not None and str(v).lower() != "none"
                    }


                    if blockchain.get_service_state(service_id) == 0 and is_match:
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
            # blockchain.display_service_state(service_id)

            # Place a bid offer
            t_bid_offer_sent = time.time() - process_start_time
            data.append(['bid_offer_sent', t_bid_offer_sent])
            tx_hash = blockchain.place_bid(service_id, request.service_price, "None", "None", "None", "None")
            
            logger.info(f"💰 Bid offer sent - Service ID: {service_id}, Price: {request.service_price} €/hour")

            logger.info("⏳ Waiting for a winner to be selected...")

            winner_chosen_event = blockchain.create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT_CLOSED)
            winnerChosen = False
            while winnerChosen == False:
                new_events = winner_chosen_event.get_all_entries()
                for event in new_events:
                    event_serviceid = Web3.toText(event['args']['_id'])
                    
                    if event_serviceid == service_id:    
                        # Winner choosen received
                        t_winner_received = time.time() - process_start_time
                        data.append(['winner_received', t_winner_received])
                        winnerChosen = True
                        break
            
            am_i_winner = False
            while am_i_winner == False:
                # Check if I am the winner
                am_i_winner = blockchain.check_winner(service_id)
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
                        return{"message": f"Another provider was chosen for service ID: {service_id}."}

                    
            # Federated service info
            federated_host, endpoint_consumer_service_catalog_db, endpoint_consumer_topology_db, endpoint_consumer_nsd_id, endpoint_consumer_ns_id = blockchain.get_service_info(service_id, domain)
            
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

            tx_hash = blockchain.update_endpoint(service_id, domain,
                                 "None", topology_db,
                                 "None", ns_id)

            blockchain.service_deployed(service_id, federated_host)
            
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

            return response
        else:
            logger.error(f"Federation process failed: {str(e)}")
            raise HTTPException(status_code=500, detail="You must be provider to run this code")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  
    

###---###

# # # @app.post("/start_demo_consumer", tags=["Consumer functions"])
# # # def start_demo_consumer(request: ConsumerFederationProcessRequest):
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

# # # @app.post("/start_demo_provider", tags=["Provider functions"])
# # # def start_demo_provider(request: ProviderFederationProcessRequest):
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