import os
import time
import logging
import uuid
import httpx
from web3 import Web3
from fastapi import FastAPI, HTTPException, Query
from fastapi_utils.tasks import repeat_every
from prettytable import PrettyTable

from typing import List, Dict
from datetime import datetime
import sys
import threading
import signal

import utils
from blockchain_interface import BlockchainInterface, FederationEvents
from models import (
    SubscriptionRequest, 
    SubscriptionResponse,
    TransactionReceiptResponse,
    ServiceAnnouncementRequest,
    UpdateEndpointRequest,
    PlaceBidRequest,
    ChooseProviderRequest,
    ServiceDeployedRequest,
    DemoConsumerRequest,
    DemoProviderRequest
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

shutdown_event = threading.Event()

# Graceful shutdown handler
def handle_sigint(sig, frame):
    print("🔌 SIGINT received. Cleaning up...")
    shutdown_event.set()
    # Do custom cleanup here (close files, stop threads, etc.)
    sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

domain           = os.getenv("DOMAIN_FUNCTION", "").strip().lower()
eth_address      = os.getenv("ETH_ADDRESS")
eth_private_key  = os.getenv("ETH_PRIVATE_KEY")
eth_node_url     = os.getenv("ETH_NODE_URL")
contract_addr_raw= os.getenv("CONTRACT_ADDRESS")
provider_flag = (domain == "provider")

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

# Background notifier using repeat_every
@app.on_event("startup")
@repeat_every(seconds=1)
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

@app.get("/tx_receipt/{tx_hash}", summary="Get transaction receipt", tags=["General federation functions"], response_model=TransactionReceiptResponse)
def tx_receipt_endpoint(tx_hash: str):
    try:
        return blockchain.get_transaction_receipt(tx_hash)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/register_domain/{name}", summary="Register a new domain (operator)", tags=["General federation functions"])
def register_domain_endpoint(name: str):
    try:
        tx_hash = blockchain.register_domain(name)
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


@app.post("/announce_service", summary="Create service federation announcement", tags=["Consumer functions"])
def announce_service_endpoint(request: ServiceAnnouncementRequest):
    try:
        tx_hash, service_id = blockchain.announce_service(
            request.description if request.description is not None else 'None', 
            request.availability if request.availability is not None else 0,  
            request.max_latency_ms if request.max_latency_ms is not None else 0,  
            request.max_jitter_ms if request.max_jitter_ms is not None else 0, 
            request.min_bandwidth_Mbps if request.min_bandwidth_Mbps is not None else 0, 
            request.compute_cpu_mcores if request.compute_cpu_mcores is not None else 0, 
            request.compute_ram_MB if request.compute_ram_MB is not None else 0
        ) 
        return {"tx_hash": tx_hash, "service_id": service_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/service_state/{service_id}", summary="Get service state", tags=["General federation functions"])
def check_service_state_endpoint(service_id: str): 
    try:
        current_service_state = blockchain.get_service_state(service_id)
        state_mapping = {0: "open", 1: "closed", 2: "deployed"}
        return {"service_state": state_mapping.get(current_service_state, "unknown")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@app.get("/service_info/{service_id}", summary="Get service info", tags=["General federation functions"])
def check_service_info_endpoint(service_id: str):
    try:
        description, catalog, topology, nsd_id, ns_id = blockchain.get_service_info(service_id, provider_flag)
        
        response_data = {}
        
        if provider_flag:
            response_data = {
                "endpoint_consumer": {
                    "service_catalog_db": catalog,
                    "topology_db": topology,
                    "nsd_id": nsd_id,
                    "ns_id": ns_id
                }
            }
        else:
            response_data = {
                "endpoint_provider": {
                    "service_catalog_db": catalog,
                    "topology_db": topology,
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
        announcements_received = []

        for event in new_events:
            service_id = Web3.toText(event['args']['serviceId']).rstrip('\x00')
            description = event['args']['description']
            tx_hash = Web3.toHex(event['transactionHash'])
            block_number = event['blockNumber']

            # Fetch block to extract timestamp
            block = blockchain.web3.eth.get_block(block_number)
            timestamp = datetime.utcfromtimestamp(block['timestamp']).isoformat() + "Z"

            # Check if the service is still open
            if blockchain.get_service_state(service_id) == 0:
                req = blockchain.get_service_requirements(service_id)
                requirements = {
                    "availability": req[0],
                    "max_latency_ms": req[1],
                    "max_jitter_ms": req[2],
                    "min_bandwidth_mbps": req[3],
                    "compute_cpu_mcores": req[4],
                    "compute_ram_MB": req[5]
                }

                announcements_received.append({
                    "service_id": service_id,
                    "description": description,
                    "requirements": requirements,
                    "tx_hash": tx_hash,
                    "block_number": block_number,
                    "timestamp": timestamp
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
        tx_hash = blockchain.place_bid(
            request.service_id, 
            request.price_wei_hour, 
            request.location if request.location is not None else 'None',
        )
        return {"tx_hash": tx_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/bids/{service_id}", summary="Check bids", tags=["Consumer functions"])
def check_bids_endpoint(service_id: str):
    try:
        bid_count = blockchain.get_bid_count(service_id)
        bids_received = []

        for index in range(bid_count):
            provider_address, price_wei_hour, bider_index, location = blockchain.get_bid_info(service_id, index)

            bids_received.append({
                "bider_index": bider_index,
                "provider_address": provider_address,
                "price_wei_hour": price_wei_hour,
                "location": location
            })

        if bids_received:
            return {"bids": bids_received}
        else:
            raise HTTPException(status_code=404, detail=f"No bids found for service ID {service_id}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/choose_provider", summary="Choose provider", tags=["Consumer functions"])
def choose_provider_endpoint(request: ChooseProviderRequest): 
    try:
        tx_hash = blockchain.choose_provider(request.service_id, request.bider_index, request.expected_hours, request.payment_wei)
        return {"tx_hash": tx_hash}    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send_endpoint_info", summary="Send endpoint information for federated service deployment", tags=["General federation functions"])
def send_endpoint_info(request: UpdateEndpointRequest):
    try:            
        tx_hash = blockchain.update_endpoint(
            request.service_id,
            provider_flag, 
            request.catalog if request.catalog is not None else 'None',
            request.topology if request.topology is not None else 'None',
            request.nsd_id if request.nsd_id is not None else 'None',
            request.ns_id if request.ns_id is not None else 'None'
        )
        return {"tx_hash": tx_hash}    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/is_winner/{service_id}", summary="Check if the calling provider is the winner", tags=["Provider functions"])
def is_winner_endpoint(service_id: str):
    try:
        return {"is_winner": "yes" if blockchain.is_winner(service_id) else "no"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/service_deployed", summary="Confirm service deployment", tags=["Provider functions"])
def service_deployed_endpoint(request: ServiceDeployedRequest):
    try:
        if blockchain.is_winner(request.service_id):
            tx_hash = blockchain.service_deployed(request.service_id)
            return {"tx_hash": tx_hash}
        else:
            raise HTTPException(status_code=404, detail="You are not the winner.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))    


@app.post("/start_demo_consumer", tags=["Consumer functions"])
def start_demo_consumer(request: DemoConsumerRequest):
    try:
        if domain != 'consumer':
            raise HTTPException(status_code=403, detail="This function is restricted to consumer domains.")
        requirements = [request.availability, 
                        request.max_latency_ms, 
                        request.max_jitter_ms, 
                        request.min_bandwidth_Mbps, 
                        request.compute_cpu_mcores, 
                        request.compute_ram_MB]
        response = run_consumer_federation_demo(description=request.description, req=requirements, expected_hours=request.expected_hours, offers_to_wait=request.offers_to_wait, export_to_csv=request.export_to_csv, csv_path=request.csv_path)
        return response

    except Exception as e:
        logger.error(f"Federation process failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/start_demo_provider", tags=["Provider functions"])
def start_demo_provider(request: DemoProviderRequest):
    try:
        if domain != 'provider':
            raise HTTPException(status_code=403, detail="This function is restricted to provider domains.")

        response = run_provider_federation_demo(price_wei_per_hour=request.price_wei_per_hour, location=request.location, description_filter=request.description_filter, export_to_csv=request.export_to_csv, csv_path=request.csv_path)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def run_consumer_federation_demo(description, req, expected_hours, offers_to_wait, export_to_csv, csv_path):
    federation_step_times = []  
    header = ['step', 'timestamp']
    data = []

    process_start_time = time.time()
                
    # Send service announcement (federation request)
    t_service_announced = time.time() - process_start_time
    data.append(['service_announced', t_service_announced])

    tx_hash, service_id = blockchain.announce_service(description, req[0], req[1], req[2], req[3], req[4], req[5]) 
    logger.info(f"📢 Service announcement sent - Service ID: {service_id}")

    # Wait for provider bids
    bids_event = blockchain.create_event_filter(FederationEvents.NEW_BID)
    bidderArrived = False
    logger.info("⏳ Waiting for bids...")
    while not bidderArrived:
        new_events = bids_event.get_all_entries()
        for event in new_events:
            event_service_id = Web3.toText(event['args']['serviceId']).rstrip('\x00')
            received_bids = int(event['args']['biderIndex'])
            
            if event_service_id == service_id and received_bids >= offers_to_wait:
                t_bid_offer_received = time.time() - process_start_time
                data.append(['bid_offer_received', t_bid_offer_received])
                logger.info(f"📨 {received_bids} bid(s) received:")
                bidderArrived = True 
                break
    
    # Process bids
    lowest_price = None
    best_bid_index = None

    table = PrettyTable()
    table.field_names = ["Bid Index", "Provider Address", "Price (Wei/hour)", "Location"]

    # Loop through all bid indices and print their information
    for i in range(received_bids):
        bid_info = blockchain.get_bid_info(service_id, i)
        provider_addr = bid_info[0]
        bid_price = int(bid_info[1])
        bid_index = int(bid_info[2])
        location = bid_info[3]
        table.add_row([bid_index, provider_addr, bid_price, location])

        if lowest_price is None or bid_price < lowest_price:
            lowest_price = bid_price
            best_bid_index = bid_index
            # logger.info(f"New lowest price: {lowest_price} with bid index: {best_bid_index}")
    print(table)
    # Choose winner provider
    t_winner_choosen = time.time() - process_start_time
    data.append(['winner_choosen', t_winner_choosen])
    tx_hash = blockchain.choose_provider(service_id, best_bid_index, expected_hours, expected_hours*bid_price)
    logger.info(f"🏆 Provider selected - Bid index: {best_bid_index}")

    logger.info("Endpoint information for application migration and inter-domain connectivity shared.")

    # Wait for provider confirmation
    logger.info(f"⏳ Waiting for provider to complete deployment...")
    while blockchain.get_service_state(service_id) != 2:
        time.sleep(1)
                
    t_confirm_deployment_received = time.time() - process_start_time
    data.append(['confirm_deployment_received', t_confirm_deployment_received])
    logger.info("✅ Deployment confirmation received.")
    # blockchain.display_service_state(service_id)

    # Federated service info
    # desc, endpoint_provider_catalog, endpoint_provider_topology, endpoint_provider_nsd_id, endpoint_provider_ns_id = blockchain.get_service_info(service_id, provider_flag)
    logger.info(
        "📡 Federated service info\n"
        f"{'-'*40}\n"
        f"{'Network config':<22}:\n"
        f"  └ {'protocol':<18}: vxlan\n"
        f"  └ {'vni':<18}: 200\n"
        f"  └ {'local_ip':<18}: X\n"
        f"  └ {'remote_ip':<18}: Y\n"
        f"  └ {'udp_port':<18}: 4789\n"
        f"{'-'*40}"
    )

    # Establish connection with the provider 
    t_establish_connection_with_provider_start = time.time() - process_start_time
    data.append(['establish_connection_with_provider_start', t_establish_connection_with_provider_start])
    
    logger.info("🔗 Setting up network connectivity with the provider...")
    
    t_establish_connection_with_provider_finished = time.time() - process_start_time
    data.append(['establish_connection_with_provider_finished', t_establish_connection_with_provider_finished])
    
    total_duration = time.time() - process_start_time

    logger.info(f"Testing connectivity with federated instance...")

    logger.info(f"✅ Federation process successfully completed in {total_duration:.2f} seconds.")

    if export_to_csv:
        utils.create_csv_file(csv_path, header, data)
    
    return {
        "status": "success",
        "duration_s": round(total_duration, 2)
    }
    
def run_provider_federation_demo(price_wei_per_hour, location, description_filter, export_to_csv, csv_path):
    federation_step_times = []  
    header = ['step', 'timestamp']
    data = []

    process_start_time = time.time()
    open_services = []

    # Wait for service announcements
    new_service_event = blockchain.create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT)
    logger.info("⏳ Waiting for federation events...")

    newService = False
    while not newService:
        new_events = new_service_event.get_all_entries()
        for event in new_events:
            service_id = Web3.toText(event['args']['serviceId']).rstrip('\x00')
            description = event['args']['description']

            if blockchain.get_service_state(service_id) == 0 and (description_filter is None or description == description_filter):
                requirements = blockchain.get_service_requirements(service_id) 
                open_services.append(service_id)

                # Format and display the service announcement using a table
                table = PrettyTable()
                table.title = "📨 New Service Announcement"
                table.field_names = ["Field", "Value"]
                table.align["Field"] = "l"
                table.align["Value"] = "l"

                table.add_row(["Service ID", service_id])
                table.add_row(["Description", description])
                table.add_row(["Availability", requirements[0]])
                table.add_row(["Max Latency (ms)", requirements[1]])
                table.add_row(["Max Jitter (ms)", requirements[2]])
                table.add_row(["Min Bandwidth (Mbps)", requirements[3]])
                table.add_row(["CPU (millicores)", requirements[4]])
                table.add_row(["RAM (MB)", requirements[5]])

                print(table)

        if len(open_services) > 0:
            # Announcement received
            t_announce_received = time.time() - process_start_time
            data.append(['announce_received', t_announce_received])
            # logger.info(f"Offers received: {len(open_services)}")
            newService = True
        
    service_id = open_services[-1]  # Select the latest open service

    # Place bid
    t_bid_offer_sent = time.time() - process_start_time
    data.append(['bid_offer_sent', t_bid_offer_sent])
    blockchain.place_bid(service_id, price_wei_per_hour, location)
    logger.info(f"💰 Bid offer sent - Service ID: {service_id}, Price: {price_wei_per_hour} Wei/hour")

    logger.info("⏳ Waiting for a winner to be selected...")
    winner_chosen_event = blockchain.create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT_CLOSED)
    winnerChosen = False
    while not winnerChosen:
        new_events = winner_chosen_event.get_all_entries()
        for event in new_events:
            event_service_id = Web3.toText(event['args']['serviceId']).rstrip('\x00')
            if event_service_id == service_id:    
                # Winner choosen received
                t_winner_received = time.time() - process_start_time
                data.append(['winner_received', t_winner_received])
                winnerChosen = True
                break
    
    # Check if this provider is the winner
    if blockchain.is_winner(service_id):
        logger.info(f"🏆 Selected as the winner for service ID: {service_id}.")
        t_deployment_start = time.time() - process_start_time
        data.append(['deployment_start', t_deployment_start])
    else:
        logger.info(f"❌ Not selected as the winner for service ID: {service_id}.")
        t_other_provider_choosen = time.time() - process_start_time
        data.append(['other_provider_choosen', t_other_provider_choosen])

        if export_to_csv:
            utils.create_csv_file(csv_path, header, data)

        return {"message": f"Another provider was chosen for service ID: {service_id}."}
            
    # Federated service info
    # desc, endpoint_consumer_catalog, endpoint_consumer_topology, endpoint_consumer_nsd_id, endpoint_consumer_ns_id = blockchain.get_service_info(service_id, provider_flag)

    logger.info(
        "📡 Federated service info\n"
        f"{'-'*40}\n"
        f"{'Network config':<22}:\n"
        f"  └ {'protocol':<20}: vxlan\n"
        f"  └ {'vni':<20}: 200\n"
        f"  └ {'local_ip':<20}: X\n"
        f"  └ {'remote_ip':<20}: Y\n"
        f"  └ {'udp_port':<20}: 4789\n"
        f"{'-'*40}"
    )


    logger.info("🚀 Starting deployment of ROS-based application...")
    time.sleep(1)

    logger.info("🔗 Setting up network connectivity with the consumer...")

    t_deployment_finished = time.time() - process_start_time
    data.append(['deployment_finished', t_deployment_finished])
        
    # Confirm service deployed
    t_confirm_deployment_sent = time.time() - process_start_time
    data.append(['confirm_deployment_sent', t_confirm_deployment_sent])

    # tx_hash = blockchain.update_endpoint(
    #     request.service_id,
    #     provider_flag, 
    #     request.catalog if request.catalog is not None else 'None',
    #     request.topology if request.topology is not None else 'None',
    #     request.nsd_id if request.nsd_id is not None else 'None',
    #     request.ns_id if request.ns_id is not None else 'None'
    # )
    
    blockchain.service_deployed(service_id)
    
    total_duration = time.time() - process_start_time

    logger.info("Endpoint information for inter-domain connectivity shared.")
    # logger.info(f"✅ Service Deployed - Federated Instance (ROS_IP): {federated_host}")

    if export_to_csv:
        utils.create_csv_file(csv_path, header, data)

    return {
        "status": "success",
        "duration_s": round(total_duration, 2)
    }