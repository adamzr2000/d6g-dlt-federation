import os
import uuid
import logging
import threading
from datetime import datetime
from typing import Dict, List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi_utils.tasks import repeat_every
from web3 import Web3

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
    DemoProviderRequest,
)
from demo import run_consumer_federation_demo, run_provider_federation_demo

# ----------------------------- App setup -----------------------------
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

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def get_app_state():
    return app.state

# ------------------------ Lifecycle hooks ------------------------
@app.on_event("startup")
async def _init_state():
    # Read env
    domain           = os.getenv("DOMAIN_FUNCTION", "").strip().lower()
    eth_address      = os.getenv("ETH_ADDRESS")
    eth_private_key  = os.getenv("ETH_PRIVATE_KEY")
    eth_node_url     = os.getenv("ETH_NODE_URL")
    contract_addr_raw= os.getenv("CONTRACT_ADDRESS")

    # Guard checks
    required = {
        "DOMAIN_FUNCTION": domain,
        "ETH_ADDRESS":      eth_address,
        "ETH_PRIVATE_KEY":  eth_private_key,
        "ETH_NODE_URL":     eth_node_url,
        "CONTRACT_ADDRESS": contract_addr_raw,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError("ERROR: missing environment variables: " + ", ".join(missing))

    try:
        contract_address = Web3.toChecksumAddress(contract_addr_raw)
    except Exception:
        raise RuntimeError("ERROR: CONTRACT_ADDRESS '{}' is not a valid Ethereum address".format(contract_addr_raw))

    if domain not in ("provider", "consumer"):
        raise RuntimeError("ERROR: DOMAIN_FUNCTION must be 'provider' or 'consumer', got '{}'".format(domain))

    # Build blockchain client
    blockchain = BlockchainInterface(
        eth_address=eth_address,
        private_key=eth_private_key,
        eth_node_url=eth_node_url,
        abi_path="/smart-contracts/build/contracts/Federation.json",
        contract_address=contract_address
    )

    # Initialize app state
    s = get_app_state()
    s.eth_node_url = eth_node_url
    s.eth_address = eth_address
    s.contract_address = contract_address
    s.blockchain = blockchain
    s.shutdown_event = threading.Event()
    s.domain = domain
    s.provider_flag = (domain == "provider")
    s.subscriptions = {}  # type: Dict[str, Dict]
    # Reused HTTP client for notifier callbacks
    s.httpx_client = httpx.AsyncClient(timeout=5.0)

@app.on_event("shutdown")
async def _shutdown():
    # Ensure graceful cleanup
    try:
        s = get_app_state()
        s.shutdown_event.set()
        if hasattr(s, "httpx_client"):
            await s.httpx_client.aclose()
    except Exception:
        pass

# ---------------------- Background notifier loop ----------------------
@app.on_event("startup")
@repeat_every(seconds=1, wait_first=True)
async def notifier_loop() -> None:
    s = get_app_state()
    if not hasattr(s, "subscriptions"):
        return  # defensive

    client = getattr(s, "httpx_client", None)
    created_temp_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=5.0)
        created_temp_client = True

    try:
        MAX_EVENTS_PER_TICK = 1000
        for sub_id, info in list(s.subscriptions.items()):
            req = info["request"]
            flt = info["filter"]
            count = 0
            for entry in flt.get_new_entries():
                if count >= MAX_EVENTS_PER_TICK:
                    break
                decoded_args = {}  # type: Dict[str, str]
                for k, v in entry.get("args", {}).items():
                    try:
                        text = Web3.toText(v).rstrip("\x00")
                    except (TypeError, ValueError):
                        text = v
                    decoded_args[k] = text

                payload = {
                    "subscription_id": sub_id,
                    "event": entry.get("event"),
                    "tx_hash": entry.get("transactionHash").hex(),
                    "block_number": entry.get("blockNumber"),
                    "args": decoded_args,
                }
                try:
                    await client.post(req.callback_url, json=payload)
                except httpx.HTTPError as e:
                    logger.error("Failed to notify {}: {}".format(req.callback_url, e))
                count += 1
    finally:
        if created_temp_client:
            await client.aclose()

# ----------------------------- Endpoints ------------------------------
@app.get("/health")
def health():
    return {"ok": True}

# ---- Subscriptions ----
@app.post("/subscriptions", response_model=SubscriptionResponse, status_code=201)
def create_subscription(req: SubscriptionRequest):
    s = get_app_state()
    try:
        event_filter = s.blockchain.create_event_filter(req.event_name, last_n_blocks=req.last_n_blocks)
    except ValueError:
        raise HTTPException(400, f"Unknown event '{req.event_name}'")
    sub_id = uuid.uuid4().hex
    s.subscriptions[sub_id] = {"request": req, "filter": event_filter}
    return SubscriptionResponse(subscription_id=sub_id, **req.dict())

@app.get("/subscriptions", response_model=List[SubscriptionResponse])
def list_subscriptions():
    s = get_app_state()
    return [
        SubscriptionResponse(subscription_id=sub_id, **info["request"].dict())
        for sub_id, info in s.subscriptions.items()
    ]

@app.delete("/subscriptions/{sub_id}", status_code=204)
def delete_subscription(sub_id: str):
    s = get_app_state()
    s.subscriptions.pop(sub_id, None)
    return

# ---- General federation functions ----
@app.get("/web3_info", summary="Get Web3 info", tags=["General federation functions"])
def web3_info_endpoint():
    s = get_app_state()
    try:
        return {
            "ethereum_node_url": s.eth_node_url,
            "ethereum_address": str(s.eth_address),
            "contract_address": str(s.contract_address),
        }
    except Exception as e:
        logger.exception("web3_info_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get(
    "/tx_receipt/{tx_hash}",
    summary="Get transaction receipt",
    tags=["General federation functions"],
    response_model=TransactionReceiptResponse,
)
def tx_receipt_endpoint(tx_hash: str):
    s = get_app_state()
    try:
        return s.blockchain.get_transaction_receipt(tx_hash)
    except Exception as e:
        logger.exception("tx_receipt_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/register_domain/{name}", summary="Register a new domain (operator)", tags=["General federation functions"])
def register_domain_endpoint(name: str):
    s = get_app_state()
    try:
        tx_hash = s.blockchain.register_domain(name, wait=True, timeout=120)
        return {"tx_hash": tx_hash}
    except Exception as e:
        logger.exception("register_domain_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/unregister_domain", summary="Unregisters an existing domain (operator)", tags=["General federation functions"])
def unregister_domain_endpoint():
    s = get_app_state()
    try:
        tx_hash = s.blockchain.unregister_domain(wait=True, timeout=120)
        return {"tx_hash": tx_hash}
    except Exception as e:
        logger.exception("unregister_domain_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/announce_service", summary="Create service federation announcement", tags=["Consumer functions"])
def announce_service_endpoint(request: ServiceAnnouncementRequest):
    s = get_app_state()
    try:
        tx_hash, service_id = s.blockchain.announce_service(
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
        logger.exception("announce_service_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/service_state/{service_id}", summary="Get service state", tags=["General federation functions"])
def check_service_state_endpoint(service_id: str): 
    s = get_app_state()
    try:
        current_service_state = s.blockchain.get_service_state(service_id)
        state_mapping = {0: "open", 1: "closed", 2: "deployed"}
        return {"service_state": state_mapping.get(current_service_state, "unknown")}
    except Exception as e:
        logger.exception("check_service_state_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))
        
@app.get("/service_info/{service_id}", summary="Get service info", tags=["General federation functions"])
def check_service_info_endpoint(service_id: str):
    s = get_app_state()
    try:
        description, deployment_manifest_ipfs_cid = s.blockchain.get_service_info(service_id, s.provider_flag)
        
        response_data = {}
        
        if s.provider_flag:
            response_data = {
                "description": description,
                "endpoint_consumer": {
                    "deployment_manifest_ipfs_cid": deployment_manifest_ipfs_cid,
                }
            }
        else:
            response_data = {
                "description": description,
                "endpoint_provider": {
                    "deployment_manifest_ipfs_cid": deployment_manifest_ipfs_cid,
                }
            }  
        return response_data
    except Exception as e:
        logger.exception("check_service_info_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/service_announcements", summary="Check service federation announcements", tags=["Provider functions"])
def check_service_announcements_endpoint():
    blocks_to_check = 20
    s = get_app_state()
    try:
        new_service_event = s.blockchain.create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT, last_n_blocks=blocks_to_check)
        new_events = new_service_event.get_all_entries()
        announcements_received = []

        for event in new_events:
            service_id = Web3.toText(event['args']['serviceId']).rstrip('\x00')
            description = event['args']['description']
            tx_hash = Web3.toHex(event['transactionHash'])
            block_number = event['blockNumber']

            # Fetch block to extract timestamp
            block = s.blockchain.web3.eth.get_block(block_number)
            timestamp = datetime.utcfromtimestamp(block['timestamp']).isoformat() + "Z"

            # Check if the service is still open
            if s.blockchain.get_service_state(service_id) == 0:
                req = s.blockchain.get_service_requirements(service_id)
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
        logger.exception("check_service_announcements_endpoint failed")    
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/place_bid", summary="Place a bid", tags=["Provider functions"])
def place_bid_endpoint(request: PlaceBidRequest):
    s = get_app_state()
    try:
        tx_hash = s.blockchain.place_bid(
            request.service_id, 
            request.price_wei_hour, 
            request.location if request.location is not None else 'None',
        )
        return {"tx_hash": tx_hash}
    except Exception as e:
        logger.exception("place_bid_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/bids/{service_id}", summary="Check bids", tags=["Consumer functions"])
def check_bids_endpoint(service_id: str):
    s = get_app_state()
    try:
        bid_count = s.blockchain.get_bid_count(service_id)
        bids_received = []

        for index in range(bid_count):
            provider_address, price_wei_hour, bider_index, location = s.blockchain.get_bid_info(service_id, index)

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
        logger.exception("check_bids_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/choose_provider", summary="Choose provider", tags=["Consumer functions"])
def choose_provider_endpoint(request: ChooseProviderRequest): 
    s = get_app_state()
    try:
        tx_hash = s.blockchain.choose_provider(request.service_id, request.bider_index, request.expected_hours, request.payment_wei)
        return {"tx_hash": tx_hash}    
    except Exception as e:
        logger.exception("choose_provider_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send_endpoint_info", summary="Send endpoint information for federated service deployment", tags=["General federation functions"])
def send_endpoint_info(request: UpdateEndpointRequest):
    s = get_app_state()
    try:            
        tx_hash = s.blockchain.update_endpoint(
            request.service_id,
            s.provider_flag, 
            request.deployment_manifest_ipfs_cid,
        )
        return {"tx_hash": tx_hash}    
    except Exception as e:
        logger.exception("send_endpoint_info failed")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/is_winner/{service_id}", summary="Check if the calling provider is the winner", tags=["Provider functions"])
def is_winner_endpoint(service_id: str):
    s = get_app_state()
    try:
        return {"is_winner": "yes" if s.blockchain.is_winner(service_id) else "no"}
    except Exception as e:
        logger.exception("is_winner_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/service_deployed", summary="Confirm service deployment", tags=["Provider functions"])
def service_deployed_endpoint(request: ServiceDeployedRequest):
    s = get_app_state()
    try:
        if s.blockchain.is_winner(request.service_id):
            tx_hash = s.blockchain.service_deployed(request.service_id)
            return {"tx_hash": tx_hash}
        else:
            raise HTTPException(status_code=404, detail="You are not the winner.")
    except Exception as e:
        logger.exception("service_deployed_endpoint failed")
        raise HTTPException(status_code=500, detail=str(e))    


@app.post("/start_demo_consumer", tags=["Consumer functions"])
def start_demo_consumer(request: DemoConsumerRequest):
    s = get_app_state()
    try:
        if s.domain != 'consumer':
            raise HTTPException(status_code=403, detail="This function is restricted to consumer domains.")
        
        service1_requirements = [
            request.service1_availability,
            request.service1_max_latency_ms,
            request.service1_max_jitter_ms,
            request.service1_min_bandwidth_Mbps,
            request.service1_compute_cpu_mcores,
            request.service1_compute_ram_MB,
        ]

        service2_requirements = [
            request.service1_availability,
            request.service1_max_latency_ms,
            request.service1_max_jitter_ms,
            request.service1_min_bandwidth_Mbps,
            request.service1_compute_cpu_mcores,
            request.service1_compute_ram_MB,
        ]

        services_to_announce = {
            "service1": {
                "description": request.service1_description,
                "requirements": service1_requirements,
                "deployment_manifest_cid": request.service1_deployment_manifest_cid,
            },
            "service2": {
                "description": request.service2_description,
                "requirements": service2_requirements,
                "deployment_manifest_cid": request.service2_deployment_manifest_cid,
            },
        }

        response = run_consumer_federation_demo(
            app=app,
            services_to_announce=services_to_announce,
            expected_hours=request.expected_hours,
            offers_to_wait=request.offers_to_wait,
            export_to_csv=request.export_to_csv,
            csv_path=request.csv_path,
        )

        return response

    except Exception as e:
        logger.error(f"Federation process failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/start_demo_provider", tags=["Provider functions"])
def start_demo_provider(request: DemoProviderRequest):
    s = get_app_state()
    try:
        if s.domain != 'provider':
            raise HTTPException(status_code=403, detail="This function is restricted to provider domains.")

        return run_provider_federation_demo(
            app=app,
            price_wei_per_hour=request.price_wei_per_hour,
            location=request.location,
            description_filter=request.description_filter,
            export_to_csv=request.export_to_csv,
            csv_path=request.csv_path,
        )

    except Exception as e:
        logger.error(f"Federation process failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))