# blockchain_interface.py

import json
import time
import logging
from enum import Enum
from web3 import Web3, WebsocketProvider, HTTPProvider
from web3.middleware import geth_poa_middleware


logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class FederationEvents(str, Enum):
    OPERATOR_REGISTERED = "OperatorRegistered"
    OPERATOR_REMOVED = "OperatorRemoved"
    SERVICE_ANNOUNCEMENT = "ServiceAnnouncement"
    NEW_BID = "NewBid"
    SERVICE_ANNOUNCEMENT_CLOSED = "ServiceAnnouncementClosed"
    SERVICE_DEPLOYED_EVENT = "ServiceDeployedEvent"

class BlockchainInterface:
    def __init__(self, eth_address, private_key, eth_node_url, abi_path, contract_address):
        if eth_node_url.startswith("ws://"):
            self.web3 = Web3(WebsocketProvider(eth_node_url))
        elif eth_node_url.startswith("http://"):
            self.web3 = Web3(HTTPProvider(eth_node_url))
        else:
            raise ValueError("eth_node_url must start with ws:// or http://")

        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        if not self.web3.isConnected():
            raise ConnectionError(f"Cannot connect to Ethereum node at {eth_node_url}")

        self.eth_address = eth_address
        self.private_key = private_key

        with open(abi_path, "r") as f:
            abi = json.load(f).get("abi")
        if not abi:
            raise ValueError("ABI not found in JSON")

        self.contract = self.web3.eth.contract(address=Web3.toChecksumAddress(contract_address), abi=abi)

        logger.info(f"Web3 initialized. Address: {self.eth_address}")
        logger.info(f"Connected to Ethereum node {eth_node_url} | Version: {self.web3.clientVersion}")

    def send_signed_transaction(self, build_transaction):
        nonce = self.web3.eth.getTransactionCount(self.eth_address, 'pending')
        build_transaction['nonce'] = nonce
        signed_txn = self.web3.eth.account.signTransaction(build_transaction, self.private_key)
        tx_hash = self.web3.eth.sendRawTransaction(signed_txn.rawTransaction)
        return tx_hash.hex()

    def get_transaction_receipt(self, tx_hash: str) -> dict:
        """
        Retrieves details of the transaction receipt for the specified hash, including:
        
        - Block info: Block hash, block number, and timestamp.
        - Gas usage: Gas used and cumulative gas.
        - Status: Transaction success (1) or failure (0).
        - Sender/Receiver: from_address and to_address.
        - Logs: Event logs generated during the transaction.
        - Gas price: Actual gas price paid.
        - Timestamp: The timestamp of the block in which the transaction was included.
        
        Args:
            tx_hash (str): The transaction hash to retrieve the receipt.

        Returns:
            dict: A dictionary containing transaction receipt details and block timestamp, or an error message.
        """
        try:
            # Get the transaction receipt
            receipt = self.web3.eth.get_transaction_receipt(tx_hash)

            if receipt:
                # Convert HexBytes to strings for JSON serialization
                receipt_dict = dict(receipt)
                receipt_dict['blockHash'] = receipt_dict['blockHash'].hex()
                receipt_dict['transactionHash'] = receipt_dict['transactionHash'].hex()
                receipt_dict['logsBloom'] = receipt_dict['logsBloom'].hex()
                receipt_dict['logs'] = [dict(log) for log in receipt_dict['logs']]

                # Rename fields to be more descriptive
                receipt_dict['from_address'] = receipt_dict.pop('from')
                receipt_dict['to_address'] = receipt_dict.pop('to')

                # Convert nested hex values in logs
                for log in receipt_dict['logs']:
                    log['blockHash'] = log['blockHash'].hex()
                    log['transactionHash'] = log['transactionHash'].hex()
                    log['topics'] = [topic.hex() for topic in log['topics']]

                # Retrieve the block number from the receipt
                block_number = receipt['blockNumber']

                # Fetch the block details using the block number
                block = self.web3.eth.get_block(block_number)

                # Add the block timestamp to the receipt dictionary
                receipt_dict['timestamp'] = block['timestamp']

                return receipt_dict

            else:
                raise Exception("Error: Transaction receipt not found")

        except Exception as e:
            raise Exception(f"An exception occurred: {str(e)}")

        
    def create_event_filter(self, event_name: FederationEvents, last_n_blocks: int = None):
        """
        Creates a filter to catch the specified event emitted by the smart self.contract.
        This function can be used to monitor events in real-time or from a certain number of past blocks.

        Args:
            self.contract: The self.contract instance to monitor events from.
            event_name (FederationEvents): The name of the smart self.contract event to create a filter for.
            last_n_blocks (int, optional): If provided, specifies the number of blocks to look back from the latest block.
                                        If not provided, it listens from the latest block onward.

        Returns:
            Filter: A filter for catching the specified event.
        """
        try:
            block = self.web3.eth.getBlock('latest')
            block_number = block['number']
            
            # If last_n_blocks is provided, look back, otherwise start from the latest block
            from_block = max(0, block_number - last_n_blocks) if last_n_blocks else block_number
            
            # Use the self.contract instance passed as an argument to access the events
            event_filter = getattr(self.contract.events, event_name.value).createFilter(fromBlock=self.web3.toHex(from_block))
            return event_filter
        except AttributeError:
            raise ValueError(f"Event '{event_name}' does not exist in the self.contract.")
        except Exception as e:
            raise Exception(f"An error occurred while creating the filter for event '{event_name}': {str(e)}")

        
    def register_domain(self, domain_name: str) -> str:
        try:
            tx_data = self.contract.functions.addOperator(self.web3.toBytes(text=domain_name)).buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            return tx_hash
        except Exception as e:
            logger.error(f"Failed to register domain: {str(e)}")
            raise Exception("Domain registration failed.")


    def unregister_domain(self) -> str:
        try:
            tx_data = self.contract.functions.removeOperator().buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            return tx_hash
        except Exception as e:
            logger.error(f"Failed to unregister domain: {str(e)}")
            raise Exception("Domain unregistration failed.")
                                    
    def announce_service(self, service_requirements: str,
                        endpoint_service_catalog_db: str, endpoint_topology_db: str,
                        endpoint_nsd_id: str, endpoint_ns_id: str):
        try:
            service_id = 'service' + str(int(time.time()))
            tx_data = self.contract.functions.AnnounceService(
                _requirements=self.web3.toBytes(text=service_requirements),
                _id=self.web3.toBytes(text=service_id),
                endpoint_service_catalog_db=self.web3.toBytes(text=endpoint_service_catalog_db),
                endpoint_topology_db=self.web3.toBytes(text=endpoint_topology_db),
                endpoint_nsd_id=self.web3.toBytes(text=endpoint_nsd_id),
                endpoint_ns_id=self.web3.toBytes(text=endpoint_ns_id)
            ).buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            return tx_hash, service_id
        except Exception as e:
            logger.error(f"Failed to announce service: {str(e)}")
            raise Exception("Service announcement failed.")

    def update_endpoint(self, service_id: str, domain: str, 
                    endpoint_service_catalog_db: str, endpoint_topology_db: str,
                    endpoint_nsd_id: str, endpoint_ns_id: str) -> str:
        try:
            provider_flag = (domain == "provider")
            tx_data = self.contract.functions.UpdateEndpoint(
                provider=provider_flag, 
                _id=self.web3.toBytes(text=service_id),
                endpoint_service_catalog_db=self.web3.toBytes(text=endpoint_service_catalog_db),
                endpoint_topology_db=self.web3.toBytes(text=endpoint_topology_db),
                endpoint_nsd_id=self.web3.toBytes(text=endpoint_nsd_id),
                endpoint_ns_id=self.web3.toBytes(text=endpoint_ns_id)
            ).buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            return tx_hash
        except Exception as e:
            logger.error(f"Failed to update endpoint: {str(e)}")
            raise Exception("Service update failed.")

    def get_bid_info(self, service_id: str, bid_index: int) -> tuple:
        try:
            bid_info = self.contract.functions.GetBid(
                _id=self.web3.toBytes(text=service_id),
                bider_index=bid_index,
                _creator=self.eth_address
            ).call()
            return bid_info
        except Exception as e:
            logger.error(f"Failed to retrieve bid info for service_id '{service_id}' and bid_index '{bid_index}': {str(e)}")
            raise Exception("Error occurred while retrieving bid information.")

    def choose_provider(self, service_id: str, bid_index: int) -> str:
        try:
            tx_data = self.contract.functions.ChooseProvider(
                _id=self.web3.toBytes(text=service_id),
                bider_index=bid_index
            ).buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            return tx_hash
        except Exception as e:
            logger.error(f"Failed to choose provider for service_id '{service_id}' and bid_index '{bid_index}': {str(e)}")
            raise Exception("Error occurred while choosing the provider.")

    def get_service_state(self, service_id: str) -> int:  
        try:
            service_state = self.contract.functions.GetServiceState(_id=self.web3.toBytes(text=service_id)).call()
            return service_state
        except Exception as e:
            logger.error(f"Failed to retrieve service state for service_id '{service_id}': {str(e)}")
            raise Exception(f"Error occurred while retrieving the service state for service_id '{service_id}'.")

    def get_service_info(self, service_id: str, domain: str) -> tuple:
        try:
            service_id_bytes = self.web3.toBytes(text=service_id)
            provider_flag = (domain == "provider")
            
            service_id, federated_host, endpoint_service_catalog_db, endpoint_topology_db, endpoint_nsd_id, endpoint_ns_id = self.contract.functions.GetServiceInfo(
                _id=service_id_bytes, provider=provider_flag, call_address=self.eth_address).call()

            return (
                federated_host.rstrip(b'\x00').decode('utf-8'),
                endpoint_service_catalog_db.rstrip(b'\x00').decode('utf-8'),
                endpoint_topology_db.rstrip(b'\x00').decode('utf-8'),
                endpoint_nsd_id.rstrip(b'\x00').decode('utf-8'),
                endpoint_ns_id.rstrip(b'\x00').decode('utf-8')
            )
        except Exception as e:
            logger.error(f"Failed to retrieve deployed info for service_id '{service_id}' and domain '{domain}': {str(e)}")
            raise Exception(f"Error occurred while retrieving deployed info for service_id '{service_id}' and domain '{domain}'.")

    def place_bid(self, service_id: str, service_price: int,
                endpoint_service_catalog_db: str, endpoint_topology_db: str,
                endpoint_nsd_id: str, endpoint_ns_id: str) -> str:
        try:
            tx_data = self.contract.functions.PlaceBid(
                _id=self.web3.toBytes(text=service_id),
                _price=service_price,
                endpoint_service_catalog_db=self.web3.toBytes(text=endpoint_service_catalog_db),
                endpoint_topology_db=self.web3.toBytes(text=endpoint_topology_db),
                endpoint_nsd_id=self.web3.toBytes(text=endpoint_nsd_id),
                endpoint_ns_id=self.web3.toBytes(text=endpoint_ns_id)
            ).buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            return tx_hash

        except Exception as e:
            logger.error(f"Failed to place bid for service_id {service_id}: {str(e)}")
            raise Exception(f"Error occurred while placing bid for service_id {service_id}.")

    def check_winner(self, service_id: str) -> bool:
        try:
            state = self.get_service_state(service_id)
            if state == 1:
                result = self.contract.functions.isWinner(
                    _id=self.web3.toBytes(text=service_id), 
                    _winner=self.eth_address
                ).call()
                return result
            else:
                return False
        except Exception as e:
            logger.error(f"Failed to check winner for service_id '{service_id}': {str(e)}")
            raise Exception(f"Error occurred while checking the winner for service_id '{service_id}'.")

    def service_deployed(self, service_id: str, federated_host: str) -> str:
        try:
            tx_data = self.contract.functions.ServiceDeployed(
                info=self.web3.toBytes(text=federated_host),
                _id=self.web3.toBytes(text=service_id)
            ).buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            return tx_hash
        except Exception as e:
            logger.error(f"Failed to confirm deployment for service_id {service_id}: {str(e)}")
            raise Exception(f"Failed to confirm deployment for service_id {service_id}.")

    def display_service_state(self, service_id: str):  
        current_service_state = self.get_service_state(service_id)
        if current_service_state == 0:
            logger.info("Service state: Open")
        elif current_service_state == 1:
            logger.info("Service state: Closed")
        elif current_service_state == 2:
            logger.info("Service state: Deployed")
        else:
            logger.error(f"Error: state for service '{service_id}' is '{current_service_state}'")