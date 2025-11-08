from pydantic import BaseModel, HttpUrl
from typing import Optional
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
    deployment_manifest_ipfs_cid: Optional[str] = None

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

class DemoConsumerRequest(BaseModel):
    service1_description: Optional[str] = "detnet_transport"
    service1_availability: Optional[int] = 0 
    service1_max_latency_ms: Optional[int] = 0
    service1_max_jitter_ms: Optional[int] = 0
    service1_min_bandwidth_Mbps: Optional[int] = 0
    service1_compute_cpu_mcores: Optional[int] = 0 
    service1_compute_ram_MB: Optional[int] = 0
    service1_deployment_manifest_cid: Optional[str] = None

    service2_description: Optional[str] = "ros_app_k8s_deployment"
    service2_availability: Optional[int] = 0 
    service2_max_latency_ms: Optional[int] = 0
    service2_max_jitter_ms: Optional[int] = 0 
    service2_min_bandwidth_Mbps: Optional[int] = 0
    service2_compute_cpu_mcores: Optional[int] = 0 
    service2_compute_ram_MB: Optional[int] = 0
    service2_deployment_manifest_cid: Optional[str] = None

    expected_hours: Optional[int] = 1
    offers_to_wait: Optional[int] = 1
    export_to_csv: Optional[bool] = False
    deployment_manifest_ipfs_cid: Optional[str] = None
    csv_path: Optional[str] = "federation_demo_consumer.csv"

class DemoProviderRequest(BaseModel):
    price_wei_per_hour: Optional[int] = 10000
    location: Optional[str] = "5TONIC @ Madrid, Spain"
    description_filter: Optional[str] = None 
    export_to_csv: Optional[bool] = False
    csv_path: Optional[str] = "federation_demo_provider.csv"