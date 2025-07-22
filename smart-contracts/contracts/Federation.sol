// SPDX-License-Identifier: MIT
pragma solidity >=0.4.21 <0.7.0;
pragma experimental ABIEncoderV2;

// Define the smart contract
contract Federation {

    // Define the possible states of a service
    enum ServiceState {Open, Closed, Deployed}

    // Define the Operator struct
    struct Operator {
        bytes32 name;
        bool registered;
    }

    struct Endpoint {
        bytes32 service_catalog_db;
        bytes32 topology_db;
        bytes32 nsd_id;
        bytes32 ns_id; 
    }

    // Define the Service struct
    struct Service {
        address creator;
        bytes32 endpoint_consumer; 
        bytes32 id;
        address provider;
        bytes32 endpoint_provider; 
        bytes req_info;
        ServiceState state;
    }

    // Define the Bid struct
    struct Bid {
        address bid_address;
        uint price;
        bytes32 endpoint_provider;
    }
    
    // Define mappings to store data
    mapping(bytes32 => uint) public bidCount;
    mapping(bytes32 => Bid[]) public bids;
    mapping(bytes32 => Service) public service;
    mapping(address => Operator) public operator;
    mapping(bytes32 => Endpoint) public endpoints;
    
    // Define events
    event OperatorRegistered(address operator, bytes32 name);
    event OperatorRemoved(address operator);
    event ServiceAnnouncement(bytes requirements, bytes32 id);
    event NewBid(bytes32 _id, uint256 max_bid_index);
    event ServiceAnnouncementClosed(bytes32 _id);
    event ServiceDeployedEvent(bytes32 _id);

    function addOperator(bytes32 name) public {
        Operator storage current_operator = operator[msg.sender];
        require(name.length > 0, "Name is not valid");
        require(current_operator.registered == false, "Operator already registered");
        current_operator.name = name;
        current_operator.registered = true;
        emit OperatorRegistered(msg.sender, name);
    }

    function removeOperator() public {
        Operator storage current_operator = operator[msg.sender];
        require(current_operator.registered == true, "Operator is not registered");
        delete operator[msg.sender];
        emit OperatorRemoved(msg.sender);
    }

    function getOperatorInfo(address op_address) public view returns (bytes32 name) {
        Operator storage current_operator = operator[op_address];
        require(current_operator.registered == true, "Operator is not registered with this address. Please register.");
        return current_operator.name;
    }

    function AnnounceService(bytes memory _requirements, bytes32 _id,
                             bytes32 endpoint_service_catalog_db, bytes32 endpoint_topology_db,
                             bytes32 endpoint_nsd_id, bytes32 endpoint_ns_id) public returns(ServiceState) {
        Operator storage current_operator = operator[msg.sender];
        Service storage current_service = service[_id];
        require(current_operator.registered == true, "Operator is not registered. Can not bid. Please register.");
        require(current_service.id != _id, "Service ID for operator already exists");
        bytes32 endpoint_keccak = keccak256(abi.encodePacked(endpoint_service_catalog_db, endpoint_topology_db, endpoint_nsd_id, endpoint_ns_id));
        endpoints[endpoint_keccak] = Endpoint(endpoint_service_catalog_db, endpoint_topology_db, endpoint_nsd_id, endpoint_ns_id);
        service[_id] = Service(msg.sender, endpoint_keccak, _id, msg.sender, endpoint_keccak, _requirements, ServiceState.Open);
        emit ServiceAnnouncement(_requirements, _id);
        return ServiceState.Open;
    }

    function UpdateEndpoint(bool provider, bytes32 _id,
                            bytes32 endpoint_service_catalog_db, bytes32 endpoint_topology_db,
                            bytes32 endpoint_nsd_id, bytes32 endpoint_ns_id) public returns (bool) {
        Operator storage current_operator = operator[msg.sender];
        Service storage current_service = service[_id];
        bytes32 endpoint_keccak = keccak256(abi.encodePacked(endpoint_service_catalog_db, endpoint_topology_db, endpoint_nsd_id, endpoint_ns_id));
        require(current_operator.registered == true, "Operator is not registered. Can not look into. Please register.");
        require(current_service.state >= ServiceState.Open, "Service is closed or not exists");
        if(provider == true) {
                require(current_service.state >= ServiceState.Closed, "Service is still open or not exists");
                require(current_service.provider == msg.sender, "This domain is not a winner");
                endpoints[endpoint_keccak] = Endpoint(endpoint_service_catalog_db, endpoint_topology_db, endpoint_nsd_id, endpoint_ns_id);
                service[_id].endpoint_provider = endpoint_keccak;
                return true;
        }
        else {
                require(current_service.creator == msg.sender, "This domain is not a creator");
                endpoints[endpoint_keccak] = Endpoint(endpoint_service_catalog_db, endpoint_topology_db, endpoint_nsd_id, endpoint_ns_id);
                service[_id].endpoint_consumer = endpoint_keccak;
                return true;
        }
    }
        
    function GetServiceState(bytes32 _id) public view returns (ServiceState) {
        return service[_id].state;
    }

    function GetServiceInfo(bytes32 _id, bool provider, address call_address) public view returns (bytes32, bytes memory, bytes32, bytes32, bytes32, bytes32) {
        Operator storage current_operator = operator[call_address];
        Service storage current_service = service[_id];
        require(current_operator.registered == true, "Operator is not registered. Can not look into. Please register.");
        require(current_service.state >= ServiceState.Closed, "Service is still open or not exists");
        if(provider == true) {
            require(current_service.provider == call_address, "This domain is not a winner");
            Endpoint storage current_endpoint = endpoints[current_service.endpoint_consumer];
            return(current_service.id, current_service.req_info,
                   current_endpoint.service_catalog_db, current_endpoint.topology_db,
                   current_endpoint.nsd_id, current_endpoint.ns_id);
        } else {
            require(current_service.creator == call_address, "This domain is not a creator");
            Endpoint storage current_endpoint = endpoints[current_service.endpoint_provider];
            return(current_service.id, current_service.req_info,
                   current_endpoint.service_catalog_db, current_endpoint.topology_db,
                   current_endpoint.nsd_id, current_endpoint.ns_id);
        }
    }

    function GetEndpoint(bytes32 endpoint_id, address call_address) public view returns (bytes32, bytes32, bytes32, bytes32) {
        Operator storage current_operator = operator[call_address];
        Endpoint storage current_endpoint = endpoints[endpoint_id];
        require(current_operator.registered == true, "Operator is not registered. Can not look into. Please register.");
        return(current_endpoint.service_catalog_db, current_endpoint.topology_db,
               current_endpoint.nsd_id, current_endpoint.ns_id);
    }

    function PlaceBid(bytes32 _id, uint32 _price,
                      bytes32 endpoint_service_catalog_db, bytes32 endpoint_topology_db,
                      bytes32 endpoint_nsd_id, bytes32 endpoint_ns_id) public returns (uint256) {
        Operator storage current_operator = operator[msg.sender];
        Service storage current_service = service[_id];
        require(current_operator.registered == true, "Operator is not registered. Can not bid. Please register.");
        require(current_service.state == ServiceState.Open, "Service is closed or not exists");
        bytes32 endpoint_keccak = keccak256(abi.encodePacked(endpoint_service_catalog_db, endpoint_topology_db, endpoint_nsd_id, endpoint_ns_id));
        endpoints[endpoint_keccak] = Endpoint(endpoint_service_catalog_db, endpoint_topology_db, endpoint_nsd_id, endpoint_ns_id);
        uint256 max_bid_index = bids[_id].push(Bid(msg.sender, _price, endpoint_keccak));
        bidCount[_id] = max_bid_index;
        emit NewBid(_id, max_bid_index);
        return max_bid_index;
    }

    function GetBidCount(bytes32 _id, address _creator) public view returns (uint256) {
        Service storage current_service = service[_id];
        require(current_service.id == _id, "Service not exists");
        require(current_service.creator == _creator, "Only service creator can look into the information");
        return bidCount[_id];
    }

    function GetBid(bytes32 _id, uint256 bider_index, address _creator) public view returns (address, uint, uint256) {
        Service storage current_service = service[_id];
        Bid[] storage current_bid_pool = bids[_id];
        require(current_service.id == _id, "Service not exists");
        require(current_service.creator == _creator, "Only service creator can look into the information");
        require(bids[_id].length > 0, "No bids for requested Service");
        return (current_bid_pool[bider_index].bid_address, current_bid_pool[bider_index].price, bider_index);
    }

    function ChooseProvider(bytes32 _id, uint256 bider_index) public returns (bool) {
        Service storage current_service = service[_id];
        Bid[] storage current_bid_pool = bids[_id];
        require(current_service.id == _id, "Service not exists");
        require(current_service.creator == msg.sender, "Only service creator can close the announcement");
        require(current_service.state == ServiceState.Open, "Service announcement already closed");

        current_service.state = ServiceState.Closed;
        service[_id].provider = current_bid_pool[bider_index].bid_address;
        service[_id].endpoint_provider = current_bid_pool[bider_index].endpoint_provider;
        emit ServiceAnnouncementClosed(_id);
        return true;
    }

    function isWinner(bytes32 _id, address _winner) public view returns (bool) {
        Service storage current_service = service[_id];
        require(current_service.state == ServiceState.Closed, "Service winner not choosen. Service: DEPLOYED or OPEN");
        if(current_service.provider == _winner) {
            return true;
        } else {
            return false;
        }
    }

    function ServiceDeployed(bytes memory info, bytes32 _id) public returns (bool) {
        Service storage current_service = service[_id];
        require(current_service.id == _id, "Service not exists");
        require(current_service.provider == msg.sender, "Only service provider can deploy the service");
        require(current_service.state == ServiceState.Closed, "Service winner not choosen. Service: DEPLOYED or OPEN");
        current_service.state = ServiceState.Deployed;
        current_service.req_info = info;
        emit ServiceDeployedEvent(_id);
        return true;
    }
}
