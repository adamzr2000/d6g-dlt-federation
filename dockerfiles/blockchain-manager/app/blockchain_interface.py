# blockchain_interface.py

import json
import time
import logging
import threading

from enum import Enum
from web3 import Web3, WebsocketProvider, HTTPProvider
from web3.middleware import geth_poa_middleware

logger = logging.getLogger(__name__)

class FederationEvents(str, Enum):
    OPERATOR_REGISTERED = "OperatorRegistered"
    OPERATOR_REMOVED = "OperatorRemoved"
    SERVICE_ANNOUNCEMENT = "ServiceAnnouncement"
    NEW_BID = "NewBid"
    SERVICE_ANNOUNCEMENT_CLOSED = "ServiceAnnouncementClosed"
    CONSUMER_ENDPOINT_UPDATED = "ConsumerEndpointUpdated"
    PROVIDER_ENDPOINT_UPDATED = "ProviderEndpointUpdated"
    SERVICE_DEPLOYED = "ServiceDeployed"
    SERVICE_CANCELLED = "ServiceCancelled"

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

        logger.info(f"Web3 initialized:")
        logger.info(f"  - Address: {self.eth_address}")        
        logger.info(f"  - Ethereum node URL: {eth_node_url}")
        logger.info(f"  - Version: {self.web3.clientVersion}")

        # Initialize local nonce and lock
        self._nonce_lock = threading.Lock()
        self._local_nonce = self.web3.eth.getTransactionCount(self.eth_address)


    def send_signed_transaction(self, build_transaction):
        with self._nonce_lock:
            build_transaction['nonce'] = self._local_nonce
            self._local_nonce += 1

        # Bump the gas price slightly to avoid underpriced errors
        # If not using EIP-1559, inject legacy gasPrice
        if 'maxFeePerGas' not in build_transaction and 'maxPriorityFeePerGas' not in build_transaction:
            base_gas_price = self.web3.eth.gas_price
            build_transaction['gasPrice'] = int(base_gas_price * 1.25)

        # Else (EIP-1559): Optional tweak to bump the maxFeePerGas slightly
        elif 'maxFeePerGas' in build_transaction:
            build_transaction['maxFeePerGas'] = int(build_transaction['maxFeePerGas'] * 1.25)
            
        # print(f"nonce = {build_transaction['nonce']}, maxFeePerGas = {build_transaction['maxFeePerGas']}")
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

        
    def register_domain(self, domain_name: str, wait: bool = False, timeout: int = 120) -> str:
        try:
            tx_data = self.contract.functions.addOperator(domain_name).buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            if wait:
                logger.debug(f"Waiting for transaction {tx_hash} to be mined...")
                receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status != 1:
                    raise Exception(
                        f"Transaction {tx_hash} was mined in block {receipt.blockNumber} but failed (status=0)."
                    )

                logger.debug(f"Transaction {tx_hash} successfully included in block {receipt.blockNumber}")

            return tx_hash

        except Exception as e:
            logger.error(f"Failed to register domain: {str(e)}")
            raise Exception(f"Failed to register domain: {str(e)}")


    def unregister_domain(self, wait: bool = False, timeout: int = 120) -> str:
        try:
            tx_data = self.contract.functions.removeOperator().buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            if wait:
                logger.debug(f"Waiting for transaction {tx_hash} to be mined...")
                receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status != 1:
                    raise Exception(
                        f"Transaction {tx_hash} was mined in block {receipt.blockNumber} but failed (status=0)."
                    )

                logger.debug(f"Transaction {tx_hash} successfully included in block {receipt.blockNumber}")

            return tx_hash

        except Exception as e:
            logger.error(f"Failed to unregister domain: {str(e)}")
            raise Exception(f"Failed to unregister domain: {str(e)}")
                                    
    def announce_service(self, description: str, availability: int, max_latency_ms: int,
                         max_jitter_ms: int, min_bandwidth_mbps: int, cpu_millicores: int, ram_mb: int):
        try:
            service_id = 'service' + str(int(time.time()))
            tx_data = self.contract.functions.announceService(
                self.web3.toBytes(text=service_id),
                description,
                availability,
                max_latency_ms,
                max_jitter_ms,
                min_bandwidth_mbps,
                cpu_millicores,
                ram_mb
            ).buildTransaction({'from': self.eth_address})
            tx_hash = self.send_signed_transaction(tx_data)
            return tx_hash, service_id
        except Exception as e:
            logger.error(f"Failed to announce service: {str(e)}")
            raise Exception(f"Failed to announce service: {str(e)}")

    def update_endpoint(self, service_id: str, is_provider: bool, deployment_manifest_ipfs_cid: str):
        try:
            tx_data = self.contract.functions.updateEndpoint(
                is_provider,
                self.web3.toBytes(text=service_id),
                deployment_manifest_ipfs_cid
            ).buildTransaction({'from': self.eth_address})
            return self.send_signed_transaction(tx_data)

        except Exception as e:
            logger.error(f"Failed to update endpoint: {str(e)}")
            raise Exception(f"Failed to update endpoint: {str(e)}")

    def place_bid(self, service_id: str, price_wei_per_hour: int, location: str):
        try:
            tx_data = self.contract.functions.placeBid(
                self.web3.toBytes(text=service_id),
                price_wei_per_hour,
                location
            ).buildTransaction({'from': self.eth_address})
            return self.send_signed_transaction(tx_data)

        except Exception as e:
            logger.error(f"Failed to place bid for service_id {service_id}: {str(e)}")
            raise Exception(f"Failed to place bid for service_id {service_id}: {str(e)}")

    def choose_provider(self, service_id: str, bid_index: int, expected_hours: int, payment_wei: int):
        try:
            tx_data = self.contract.functions.chooseProvider(
                self.web3.toBytes(text=service_id),
                bid_index,
                expected_hours
            ).buildTransaction({
                'from': self.eth_address,
                'value': payment_wei
            })
            return self.send_signed_transaction(tx_data)

        except Exception as e:
            logger.error(f"Failed to choose provider for service_id '{service_id}' and bid_index '{bid_index}': {str(e)}")
            raise Exception(f"Failed to choose provider for service_id '{service_id}' and bid_index '{bid_index}': {str(e)}")

    def service_deployed(self, service_id: str):
        try:
            tx_data = self.contract.functions.serviceDeployed(
                self.web3.toBytes(text=service_id)
            ).buildTransaction({'from': self.eth_address})
            return self.send_signed_transaction(tx_data)

        except Exception as e:
            logger.error(f"Failed to confirm deployment for service_id {service_id}: {str(e)}")
            raise Exception(f"Failed to confirm deployment for service_id {service_id}: {str(e)}")

    def cancel_service(self, service_id: str):
        try:
            tx_data = self.contract.functions.cancelService(
                self.web3.toBytes(text=service_id)
            ).buildTransaction({'from': self.eth_address})
            return self.send_signed_transaction(tx_data)
            
        except Exception as e:
            logger.error(f"Failed to cancel service_id {service_id}: {str(e)}")
            raise Exception(f"Failed to cancel service_id {service_id}: {str(e)}")

    def withdraw_payment(self, service_id: str):
        try:
            tx_data = self.contract.functions.withdrawPayment(
                self.web3.toBytes(text=service_id)
            ).buildTransaction({'from': self.eth_address})
            return self.send_signed_transaction(tx_data)
            
        except Exception as e:
            logger.error(f"Failed to withdraw payment for service_id {service_id}: {str(e)}")
            raise Exception(f"Failed to withdraw payment for service_id {service_id}: {str(e)}")

    def get_service_state(self, service_id: str) -> int:  
        try:
            return self.contract.functions.getServiceState(self.web3.toBytes(text=service_id)).call()
        except Exception as e:
            logger.error(f"Failed to retrieve service state for service_id '{service_id}': {str(e)}")
            raise Exception(f"Failed to retrieve service state for service_id '{service_id}': {str(e)}")

    def get_service_requirements(self, service_id: str):
        try:            
            return self.contract.functions.getServiceRequirements(self.web3.toBytes(text=service_id)).call()
        except Exception as e:
            logger.error(f"Failed to retrieve deployed info for service_id '{service_id}': {str(e)}")
            raise Exception(f"Failed to retrieve deployed info for service_id '{service_id}': {str(e)}")
        
    def is_winner(self, service_id: str) -> bool:
        try:
            return self.contract.functions.isWinner(self.web3.toBytes(text=service_id), self.eth_address).call()
        except Exception as e:
            logger.error(f"Failed to check winner for service_id '{service_id}': {str(e)}")
            raise Exception(f"Failed to check winner for service_id '{service_id}': {str(e)}")

    def is_consumer_endpoint_set(self, service_id: str) -> bool:
        try:
            return self.contract.functions.isEndpointSet(self.web3.toBytes(text=service_id), False).call()
        except Exception as e:
            logger.error("Failed to check consumer endpoint for '%s': %s", service_id, e)
            raise
    
    def is_provider_endpoint_set(self, service_id: str) -> bool:
        try:
            return self.contract.functions.isEndpointSet(self.web3.toBytes(text=service_id), True).call()
        except Exception as e:
            logger.error("Failed to check provider endpoint for '%s': %s", service_id, e)
            raise
        
    def get_bid_count(self, service_id) -> int:
        try:
            return self.contract.functions.getBidCount(self.web3.toBytes(text=service_id), self.eth_address).call()
        except Exception as e:
            logger.error(f"Failed to retrieve bid count for service_id '{service_id}': {str(e)}")
            raise Exception(f"Failed to retrieve bid count for service_id '{service_id}': {str(e)}")

    def get_bid_info(self, service_id: str, index: int):
        try:
            return self.contract.functions.getBidInfo(
                self.web3.toBytes(text=service_id),
                index,
                self.eth_address
            ).call()
        except Exception as e:
            logger.error(f"Failed to retrieve bid info for service_id '{service_id}' and bider index '{index}': {str(e)}")
            raise Exception(f"Failed to retrieve bid info for service_id '{service_id}' and bider index '{index}': {str(e)}")

    def get_service_info(self, service_id: str, is_provider: bool):
        try:            
            service_id, description, deployment_manifest_ipfs_cid = self.contract.functions.getServiceInfo(
                self.web3.toBytes(text=service_id),
                is_provider,
                self.eth_address
            ).call()

            return description, deployment_manifest_ipfs_cid
        except Exception as e:
            logger.error(f"Failed to retrieve deployed info for service_id '{service_id}': {str(e)}")
            raise Exception(f"Failed to retrieve deployed info for service_id '{service_id}': {str(e)}")
        
    def get_operator_info(self):
        try:            
            return self.contract.functions.getOperatorInfo(self.eth_address).call()
        except Exception as e:
            logger.error(f"Failed to retrieve operator info: {str(e)}")
            raise Exception(f"Failed to retrieve operator info: {str(e)}")

    def display_service_state(self, service_id: str):  
        state = self.get_service_state(service_id)
        states = ["Open", "Closed", "Deployed"]
        if 0 <= state < len(states):
            logger.info(f"Service state: {states[state]}")
        else:
            logger.error(f"Service state: {states[state]}")
