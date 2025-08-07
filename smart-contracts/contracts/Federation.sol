// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;


// Define the smart contract
contract Federation {

    // Possible states of a service
    enum ServiceState {Open, Closed, Deployed}

    // Structs
    struct Operator {
        string name;
        address payable operatorAddress;
        uint256 registrationTime;
        bool registered;
    }

    struct Endpoint {
        string serviceCatalogDb;
        string topologyDb;
        string nsdId;
        string nsId; 
    }

    struct ServiceRequirements {
        uint256 availability; // In percentage * 100 (e.g., 9990 = 99.90%)
        uint256 maxLatencyMs;
        uint256 maxJitterMs;
        uint256 minBandwidthMbps;      
        uint256 resourceCpuMillicores;
        uint256 resourceRamMB;
    }

    struct Service {
        bytes32 serviceId; // Example "service123" -> 0x7365727669636531323300000000000000000000000000000000000000000000
        string description; 
        ServiceRequirements requirements;
        ServiceState state;
        address payable creator;
        address payable provider;
        bytes32 endpointConsumer; 
        bytes32 endpointProvider; 
    }

    struct Bid {
        address payable bidAddress;
        uint priceWeiPerHour; // Cost in wei per hour of service
        string location;
    }
    
    // Mappings
    mapping(bytes32 => uint) private bidCount;
    mapping(bytes32 => Bid[]) private bids;
    mapping(bytes32 => Service) private service;
    mapping(address => Operator) private operator;
    mapping(bytes32 => Endpoint) private endpoints;
    mapping(bytes32 => uint256) private lockedPayments;
    mapping(bytes32 => uint256) private expectedServiceUtilizationHours;

    // Events
    event OperatorRegistered(address operator, string name);
    event OperatorRemoved(address operator);
    event ServiceAnnouncement(bytes32 serviceId, string description);
    event NewBid(bytes32 serviceId, uint256 biderIndex);
    event ServiceAnnouncementClosed(bytes32 serviceId);
    event ConsumerEndpointUpdated(bytes32 serviceId);
    event ProviderEndpointUpdated(bytes32 serviceId);    
    event ServiceDeployed(bytes32 serviceId);
    event ServiceCancelled(bytes32 serviceId);

    // Modifiers
    modifier onlyRegistered() {
        require(operator[msg.sender].registered, "Operator: not registered");
        _;
    }

    modifier serviceExists(bytes32 serviceId) {
        require(service[serviceId].serviceId == serviceId, "Service: does not exist");
        _;
    }

    modifier onlyServiceCreator(bytes32 serviceId) {
        require(service[serviceId].creator == msg.sender, "Service: caller is not creator");
        _;
    }

    function addOperator(string memory name) public {
        require(bytes(name).length > 0, "Name is not valid");
        require(!operator[msg.sender].registered, "Operator: already registered");
        
        operator[msg.sender] = Operator({
                name: name,
                operatorAddress: payable(msg.sender),
                registrationTime: block.timestamp,
                registered: true
        });
        emit OperatorRegistered(msg.sender, name);
    }

    function removeOperator() public onlyRegistered {
        delete operator[msg.sender];
        emit OperatorRemoved(msg.sender);
    }

    function getOperatorInfo(address callAddress) public view returns (
        string memory name,
        address opAddress,
        uint256 registrationTime,
        bool registered
    ) {
        Operator storage op = operator[callAddress];
        require(op.registered == true, "Operator: not registered");
        return (op.name, op.operatorAddress, op.registrationTime, op.registered);
    }


    function createServiceRequirements(
        uint256 availability,
        uint256 maxLatencyMs,
        uint256 maxJitterMs,
        uint256 minBandwidthMbps,
        uint256 resourceCpuMillicores,
        uint256 resourceRamMB
    ) internal pure returns (ServiceRequirements memory) {
        return ServiceRequirements({
            availability: availability,
            maxLatencyMs: maxLatencyMs,
            maxJitterMs: maxJitterMs,
            minBandwidthMbps: minBandwidthMbps,
            resourceCpuMillicores: resourceCpuMillicores,
            resourceRamMB: resourceRamMB
        });
    }

    function announceService(
        bytes32 serviceId,
        string memory description,
        uint256 availability,
        uint256 maxLatencyMs,
        uint256 maxJitterMs,
        uint256 minBandwidthMbps,
        uint256 resourceCpuMillicores,
        uint256 resourceRamMB
    ) public onlyRegistered {
        require(service[serviceId].serviceId != serviceId, "Service: ID already exists");

        ServiceRequirements memory reqs = createServiceRequirements(
            availability,
            maxLatencyMs,
            maxJitterMs,
            minBandwidthMbps,
            resourceCpuMillicores,
            resourceRamMB
        );

        Service storage newService = service[serviceId];

        newService.serviceId = serviceId;
        newService.description = description;
        newService.state = ServiceState.Open;
        newService.creator = payable(msg.sender);
        newService.provider = payable(msg.sender);
        newService.requirements = reqs;

        emit ServiceAnnouncement(serviceId, description);
    }

    function updateEndpoint(
        bool isProvider, 
        bytes32 serviceId,
        string memory endpointServiceCatalogDb, 
        string memory endpointTopologyDb,
        string memory endpointNsdId, 
        string memory endpointNsId
    ) public onlyRegistered serviceExists(serviceId) {
        Service storage currentService = service[serviceId];
       
        bytes32 endpointKeccak = keccak256(abi.encodePacked(endpointServiceCatalogDb, endpointTopologyDb, endpointNsdId, endpointNsId));
        endpoints[endpointKeccak] = Endpoint(endpointServiceCatalogDb, endpointTopologyDb, endpointNsdId, endpointNsId);

        if(isProvider) {
            require(currentService.state >= ServiceState.Closed, "Service: not closed");
            require(currentService.provider == msg.sender, "Service: caller is not provider");
            currentService.endpointProvider = endpointKeccak;
            emit ProviderEndpointUpdated(serviceId);
        }
        else {
            require(currentService.creator == msg.sender, "Service: caller is not creator");
            currentService.endpointConsumer = endpointKeccak;
            emit ConsumerEndpointUpdated(serviceId);
        }
    }
        
    function getServiceState(bytes32 serviceId) public view returns (ServiceState) {
        return service[serviceId].state;
    }

    function getServiceRequirements(bytes32 serviceId) public view serviceExists(serviceId) returns (
        uint256 availability,
        uint256 maxLatencyMs,
        uint256 maxJitterMs,
        uint256 minBandwidthMbps,
        uint256 resourceCpuMillicores,
        uint256 resourceRamMB
    ) {
        ServiceRequirements memory reqs = service[serviceId].requirements;
        return (
            reqs.availability,
            reqs.maxLatencyMs,
            reqs.maxJitterMs,
            reqs.minBandwidthMbps,
            reqs.resourceCpuMillicores,
            reqs.resourceRamMB
        );
    }

    function getServiceInfo(
        bytes32 serviceId, 
        bool isProvider, 
        address callAddress
    ) public view returns (bytes32, string memory, string memory, string memory, string memory, string memory) {
        Service storage currentService = service[serviceId];
        require(operator[callAddress].registered, "Operator: not registered");
        require(currentService.state >= ServiceState.Closed, "Service: not closed");

        Endpoint storage ep = isProvider
            ? endpoints[currentService.endpointConsumer]
            : endpoints[currentService.endpointProvider];
        
        require(bytes(ep.nsdId).length > 0, "Endpoint: not yet set");

        if(isProvider) {
            require(currentService.provider == callAddress, "Service: not provider");
        } else {
            require(currentService.creator == callAddress, "Service: not creator");
        }

        return (currentService.serviceId, currentService.description, ep.serviceCatalogDb, ep.topologyDb, ep.nsdId, ep.nsId);

    }

    function getServiceEndpoint(bytes32 endpointId, address callAddress) public view returns (string memory, string memory, string memory, string memory) {
        require(operator[callAddress].registered, "Operator: not registered");

        Endpoint storage ep = endpoints[endpointId];
        return (ep.serviceCatalogDb, ep.topologyDb, ep.nsdId, ep.nsId);
    }

    function placeBid(
        bytes32 serviceId, 
        uint32 priceWeiPerHour,
        string memory location
    ) public onlyRegistered serviceExists(serviceId) {
        Service storage currentService = service[serviceId];
        require(currentService.state == ServiceState.Open, "Service: not open");
        require(priceWeiPerHour > 0, "Bid: price must be greater than 0");

        // require(msg.sender != currentService.creator, "Bid: cannot bid on own service");

        bids[serviceId].push(Bid(payable(msg.sender), priceWeiPerHour, location));
        uint256 index = bids[serviceId].length;
        bidCount[serviceId] = index;

        emit NewBid(serviceId, index);
    }

    function getBidCount(bytes32 serviceId, address callAddress) public view serviceExists(serviceId) returns (uint256) {
        require(service[serviceId].creator == callAddress, "Service: caller not creator");
        return bidCount[serviceId];
    }

    function getBidInfo(bytes32 serviceId, uint256 index, address callAddress) public view serviceExists(serviceId) returns (address, uint, uint256, string memory) {
        require(service[serviceId].creator == callAddress, "Service: caller not creator");
        Bid[] storage bidPool = bids[serviceId];
        require(bidPool.length > 0, "Bid: no bids");
        require(index < bidPool.length, "Bid: index out of range");

        Bid storage b = bidPool[index];
        return (b.bidAddress, b.priceWeiPerHour, index, b.location);
    }

    function chooseProvider(bytes32 serviceId, uint256 biderIndex, uint256 expectedHours) payable public serviceExists(serviceId) onlyServiceCreator(serviceId) {
        Service storage currentService = service[serviceId];
        require(currentService.state == ServiceState.Open, "Service: not open");
        require(biderIndex < bids[serviceId].length, "Bid: index out of range");
    
        Bid storage winningBid = bids[serviceId][biderIndex];
        uint256 requiredAmount = winningBid.priceWeiPerHour * expectedHours;
        require(msg.value >= requiredAmount, "Insufficient payment");

        currentService.state = ServiceState.Closed;
        currentService.provider = bids[serviceId][biderIndex].bidAddress;
        lockedPayments[serviceId] = msg.value;
        expectedServiceUtilizationHours[serviceId] = expectedHours;

        emit ServiceAnnouncementClosed(serviceId);
    }


    function withdrawPayment(bytes32 serviceId) public serviceExists(serviceId) {
        Service storage currentService = service[serviceId];
        require(currentService.state == ServiceState.Deployed, "Service: not deployed");
        require(currentService.provider == msg.sender, "Only provider can withdraw");

        uint256 amount = lockedPayments[serviceId];
        require(amount > 0, "No funds to withdraw");

        lockedPayments[serviceId] = 0;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");
    }


    function isWinner(bytes32 serviceId, address callAddress) public view serviceExists(serviceId) returns (bool) {
        Service storage currentService = service[serviceId];
        require(currentService.state == ServiceState.Closed, "Service: not closed");
        
        return currentService.provider == callAddress;
    }

    function serviceDeployed(bytes32 serviceId) public serviceExists(serviceId) {
        Service storage currentService = service[serviceId];
        require(currentService.provider == msg.sender, "Service: not provider");
        require(currentService.state == ServiceState.Closed, "Service: not closed");
        
        currentService.state = ServiceState.Deployed;
        
        emit ServiceDeployed(serviceId);
    }

    function cancelService(bytes32 serviceId) public serviceExists(serviceId) onlyServiceCreator(serviceId) {
        Service storage currentService = service[serviceId];
        require(currentService.state != ServiceState.Deployed, "Service: already deployed");

        delete service[serviceId];
        delete bids[serviceId];
        delete bidCount[serviceId];

        emit ServiceCancelled(serviceId);
    }
}


