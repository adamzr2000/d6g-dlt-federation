from pydantic import BaseModel, HttpUrl
from typing import Optional
from enum import Enum
from blockchain_interface import FederationEvents

class SubscriptionRequest(BaseModel):
    event_name: FederationEvents         # e.g. FederationEvents.NEW_BID
    callback_url: HttpUrl                # where we POST notifications
    last_n_blocks: Optional[int] = 0     # replay history on first connect

class SubscriptionResponse(SubscriptionRequest):
    subscription_id: str

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

class ServiceAnnouncementRequest(BaseModel):
    description: Optional[str] = "k8s_deployment"
    availability: Optional[int] = None 
    max_latency_ms: Optional[int] = None
    max_jitter_ms: Optional[int] = None 
    min_bandwidth_Mbps: Optional[int] = None 
    compute_cpu_mcores: Optional[int] = None 
    compute_ram_MB: Optional[int] = None 
    
class UpdateEndpointRequest(BaseModel):
    service_id: str
    topology: Optional[str] = None
    ns_id: Optional[str] = None
    catalog: Optional[str] = None
    nsd_id: Optional[str] = None

class PlaceBidRequest(BaseModel):
    service_id: str
    price_wei_hour: int
    location: Optional[str] = "Madrid, Spain"

class ChooseProviderRequest(BaseModel):
    service_id: str
    bider_index: int
    expected_hours: int
    payment_wei: int

class ServiceDeployedRequest(BaseModel):
    service_id: str