from pydantic import BaseModel
from typing import Optional

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