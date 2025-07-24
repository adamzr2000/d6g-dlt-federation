# DLT-based Service Federation — DESIRE6G Project

This repository contains the source code for the **DLT-based Federation** module, part of the **Service Management and Orchestration (SMO)** component developed within the scope of the [DESIRE6G](https://desire6g.eu/) project.

**Author:** Adam Zahir Rodriguez  

---

## 🚀 Deployment guide

### Build the images

To build the required Docker images, navigate to the [dockerfiles](./dockerfiles) directory:

```bash
git clone git@github.com:adamzr2000/d6g-dlt-federation.git
cd d6g-dlt-federation/dockerfiles
```

Run the `./build.sh` scripts for each submodule:

| Module                 | Description                                                                                                     | Status       |
|------------------------|-----------------------------------------------------------------------------------------------------------------|--------------|
| **blockchain-node**    | Ethereum node image using [Go-Ethereum (Geth)](https://geth.ethereum.org/docs) for private blockchain deployment ([details](./dockerfiles/blockchain-node/))                                                                            | ✅ Available |
| **blockchain-manager** | REST API built with [FastAPI](https://github.com/fastapi/fastapi) and [Web3.py](https://web3py.readthedocs.io/en/stable/) to interact with the `Federation Smart Contract` ([details](./dockerfiles/blockchain-manager/))               | ✅ Available |
| **truffle**            | Development environment based on [Truffle](https://archive.trufflesuite.com/docs/truffle/) for compiling and deploying the [Federation Smart Contract](./smart-contracts/contracts/Federation.sol). ([details](./dockerfiles/truffle/)) | ✅ Available |
| **eth-netstats**       | Lightweight Ethereum network monitoring dashboard ([details](./dockerfiles/eth-netstats/))                                                                                                                                              | ✅ Available |


### Deploy the blockchain network (distributed)

This setup creates a basic 3-node private Ethereum network distributed across separate SMO machines (illustrating `domain1`, `domain2`, and `domain3`).

### 🟩 `domain1` — bootstrap node

`domain1` must be deployed first and is responsible for:

- **Bootnode** — Acts as the entry point and discovery service, allowing other nodes to join and connect automatically.
- **Validator node** — Participates in the consensus protocol and maintains a synchronized copy of the distributed ledger.
- **Monitoring dashboard** — Runs Ethereum network monitoring dahsboard.

### 🟨 `domain2` and `domain3` — joining nodes

Each of these domains runs:

- A **validator node** that connects to the network through the bootnode hosted in `domain1`.

> ℹ️ Note: Before deploying make sure you update the 'IP_ADDR', 'BOOTNODE_IP', 'NETSTATS_IP' environment variables in the following files with the actual IP address of each respective SMO machine:
- [bootnode.env](./blockchain-network/geth-poa/config/bootnode.env)
- [domain1.env](./blockchain-network/geth-poa/config/domain1.env)
- [domain2.env](./blockchain-network/geth-poa/config/domain2.env)
- [domain3.env](./blockchain-network/geth-poa/config/domain3.env)

### Steps

1. Initialize the network on `domain1`:

```bash
./start_geth_net.sh --file domain1-geth-network.yml
```

📊 Network dashboard: [http://localhost:3000](http://localhost:3000)

![geth_dashboard](./utils/geth_net_dashboard.png)


2. Join `domain2` to the network:

```bash
./start_geth_net.sh --file domain2-geth-network.yml
```

2. Join `domain3` to the network:

```bash
./start_geth_net.sh --file domain3-geth-network.yml
```

> ℹ️ Note: To add or remove validator nodes, follow the steps outlined in the [blockchain-network](./blockchain-network/geth-poa) directory

### Deploy the blockchain network (local)

A local deployment option is also provided for development and debugging purposes using the [local-geth-network.yml](./blockchain-network/geth-poa/local-geth-network.yml) Docker Compose file on a single host.

To start the local Ethereum network:

```bash
./start_geth_net.sh --file local-geth-network.yml
```

---

### Deploy the Federation Smart Contract

To deploy the `Federation Smart Contract` on the blockchain network:

```bash
./deploy_smart_contract.sh --node-ip 127.0.0.1 --port 3334
```

> ℹ️ Note: The smart contract can be deployed from any participating node in the network

### Deploy the blockchain manager

```bash
# Domain1
./start_blockchain_manager.sh --config blockchain-network/geth-poa/domain1.env --domain-function consumer --port 8080

# Domain2
./start_blockchain_manager.sh --config blockchain-network/geth-poa/domain2.env --domain-function provider --port 8080

# Domain3
./start_blockchain_manager.sh --config blockchain-network/geth-poa/domain3.env --domain-function provider --port 8080
```

📚 FastAPI Docs: [http://localhost:8080/docs](http://localhost:8080/docs)

## API endpoints

### Web3 Info
Returns `web3_info` details; otherwise returns an error message.

```bash
FEDERATION_ENDPOINT="localhost:8080"
curl -X 'GET' "http://$FEDERATION_ENDPOINT/web3_info" | jq
```

---

### Transaction Receipt
Returns `tx-receipt` details for a specified `tx_hash`; otherwise returns an error message.

```bash
TX_HASH="0x123…"
curl -X GET "http://$FEDERATION_ENDPOINT/tx_receipt?tx_hash=$TX_HASH" | jq
```

---

### Register Domain
Returns the `tx_hash`; otherwise returns an error message.

```bash
curl -X POST "http://$FEDERATION_ENDPOINT/register_domain" \
-H 'Content-Type: application/json' \
-d '{
   "name": "<domain_name>"
}' | jq
```

---

### Unregister Domain
Returns the `tx_hash`; otherwise returns an error message.

```bash
curl -X DELETE "http://$FEDERATION_ENDPOINT/unregister_domain" | jq
```

---

### Create Service Announcement
Returns the `tx_hash` and `service_id` for federation; otherwise returns an error message.
```bash
curl -X POST "http://$FEDERATION_ENDPOINT/create_service_announcement" \
-H 'Content-Type: application/json' \
-d '{
   "service_type": "K8s App Deployment",
   "bandwidth_gbps": 0.1,
   "rtt_latency_ms": 20,
   "compute_cpus": 2,
   "compute_ram_gb": 4
}' | jq
```

---

### Check Service Announcements
Returns `announcements` details; otherwise, returns an error message.
```bash
curl -X GET "http://$FEDERATION_ENDPOINT/service_announcements" | jq
```

---

### Place Bid
Returns the `tx_hash`; otherwise returns an error message.
```bash
curl -X POST "http://$FEDERATION_ENDPOINT/place_bid" \
-H 'Content-Type: application/json' \
-d '{
   "service_id": "<id>", 
   "service_price": 5
}' | jq
```

---

### Check Bids
Returns `bids` details; otherwise returns an error message.
```bash
curl -X GET "http://$FEDERATION_ENDPOINT/bids?service_id=<id>" | jq
```

---

### Choose Provider
Returns the `tx_hash`; otherwise returns an error message.
```bash
curl -X POST "http://$FEDERATION_ENDPOINT/choose_provider" \
-H 'Content-Type: application/json' \
-d '{
   "bid_index": 0, 
   "service_id": "<id>"
}' | jq
``` 

---

### Send Endpoint Info
Returns the `tx_hash`; otherwise returns an error message.
```bash
curl -X POST "http://$FEDERATION_ENDPOINT/send_endpoint_info" \
-H 'Content-Type: application/json' \
-d '{
   "service_id": "<id>", 
   "service_catalog_db": "http://10.5.15.55:5000/catalog",
   "topology_db": "http://10.5.15.55:5000/topology",
   "nsd_id": "ros-app.yaml",
   "ns_id": "ros-service-consumer"
}' | jq
``` 

---

### Check if the calling provider is the winner
Returns the `is_winner`, which can be `yes`, or `no`; otherwise, returns an error message.
```bash
curl -X GET "http://$FEDERATION_ENDPOINT/is_winner?service_id=<id>" | jq
```

---

### Send Endpoint Info
Returns the `tx_hash`; otherwise returns an error message.
```bash
curl -X POST "http://$FEDERATION_ENDPOINT/send_endpoint_info" \
-H 'Content-Type: application/json' \
-d '{
   "service_id": "<id>", 
   "topology_db": "http://10.5.15.56:5000/topology",
   "ns_id": "ros-service-provider"
}' | jq
``` 

---

### Confirm Service Deployment
Returns the `tx_hash`; otherwise returns an error message.
```bash
curl -X POST "http://$FEDERATION_ENDPOINT/service_deployed" \
-H 'Content-Type: application/json' \
-d '{
   "service_id": "<id>",
   "federated_host": "10.0.0.10"
}' | jq
```

---

### Check Service State
Returns the `state` of the federated service, which can be `open`,`closed`, or `deployed`; otherwise, returns an error message.
```bash
curl -X GET "http://$FEDERATION_ENDPOINT/service_state?service_id=<id>" | jq
```

---

### Check Deployed Info
Returns the `federated_host` (IP address of the deployed service) along with either `endpoint_consumer` or `endpoint_provider` details; otherwise, returns an error message.
```bash
curl -X GET "http://$FEDERATION_ENDPOINT/service_info?service_id=<id>" | jq
```
