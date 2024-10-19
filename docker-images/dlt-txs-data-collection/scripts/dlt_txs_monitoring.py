# Import the necessary classes and functions from the web3 library for interacting with the blockchain network.
from web3 import Web3, HTTPProvider, WebsocketProvider
from web3.middleware import geth_poa_middleware
import logging
import time
import json
import pandas as pd
from eth_abi import decode_abi
from eth_utils import function_signature_to_4byte_selector, encode_hex
from dotenv import load_dotenv
import os
import argparse

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Parse command-line arguments for Ethereum node URL and contract address
parser = argparse.ArgumentParser(description='Monitor Ethereum blockchain transactions.')
parser.add_argument('--eth_node_url', type=str, required=True, help='URL of the Ethereum node (e.g., ws://localhost:8546)')
parser.add_argument('--contract_address', type=str, required=True, help='Smart contract address to monitor')

args = parser.parse_args()

# Debug: Log the provided command-line arguments
logger.debug(f"Received Ethereum node URL: {args.eth_node_url}")
logger.debug(f"Received contract address: {args.contract_address}")

# Configure Web3
eth_node_url = args.eth_node_url
try:
    web3 = Web3(WebsocketProvider(eth_node_url))
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    # Check if connected to the Ethereum node
    if web3.isConnected():
        # Attempt to get the Geth version to confirm a successful connection
        geth_version = web3.clientVersion
        logger.info(f"Successfully connected to Ethereum node {eth_node_url} - Version: {geth_version}")
    else:
        logger.error(f"Failed to connect to the Ethereum node {eth_node_url}")
        exit()
except Exception as e:
    logger.error(f"An error occurred while trying to connect to the Ethereum node: {e}")
    exit()

# Debug: Log connection status and account details
logger.debug(f"Ethereum accounts available: {web3.eth.accounts}")
eth_address = web3.eth.accounts[0] if web3.eth.accounts else None
if eth_address:
    logger.debug(f"Using Ethereum account: {eth_address}")
else:
    logger.warning("No Ethereum accounts available, ensure the node is configured correctly.")
    
# Function to decode contract interaction
def decode_input(input_data, abi):
    if input_data == '0x':
        return None, None  # No input data
    try:
        function_selector = input_data[:10]
        for item in abi:
            if item['type'] == 'function':
                function_signature = f"{item['name']}({','.join(i['type'] for i in item['inputs'])})"
                if encode_hex(function_signature_to_4byte_selector(function_signature)) == function_selector:
                    function_name = item['name']
                    input_types = [input['type'] for input in item['inputs']]
                    decoded_params = decode_abi(input_types, bytes.fromhex(input_data[10:]))
                    return function_name, decoded_params
        return None, None  # Function not found in ABI
    except Exception as e:
        logger.error(f"Error decoding input data: {e}")
        return None, None

# Load the ABI of the smart contract from a JSON file
abi_path = "./smart-contracts/build/contracts/"
with open(abi_path + "Federation.json") as c_json:
    contract_json = json.load(c_json)
contract_abi = contract_json["abi"]
contract_name = contract_json["contractName"]

# Load .env variables
load_dotenv()

# Contract address provided by the user as an argument
contract_address = Web3.toChecksumAddress(args.contract_address)

# Known contract addresses (can be expanded if there are multiple known contracts)
known_contracts = {
    contract_address: contract_name
}

# Function to fetch block data with transactions
def fetch_block_data(block_number):
    block = web3.eth.getBlock(block_number, full_transactions=True)
    if len(block.transactions) > 0:
        transactions_data = []
        for tx in block.transactions:
            receipt = web3.eth.getTransactionReceipt(tx.hash)
            if receipt.contractAddress:
                # Contract creation transaction
                contract_address = receipt.contractAddress
                contract_name = known_contracts.get(contract_address, None)
                function_name, function_params = None, None
            else:
                contract_address = None
                if tx.to in known_contracts:
                    function_name, function_params = decode_input(tx.input, contract_abi)
                    contract_name = known_contracts[tx.to]
                else:
                    function_name, function_params = None, None
                    contract_name = None
            
            tx_data = {
                'blockNumber': block.number,
                'timestamp': block.timestamp,
                'transactionHash': tx.hash.hex(),
                'from': tx['from'],
                'to': tx.to,
                'value': web3.fromWei(tx.value, 'ether'),
                'gas': tx.gas,
                'gasPrice': web3.fromWei(tx.gasPrice, 'gwei'),
                'nonce': tx.nonce,
                'status': receipt.status,
                'contractAddress': contract_address,
                'contractName': contract_name,
                'functionName': function_name
            }
            transactions_data.append(tx_data)
        return transactions_data
    else:
        return []

# Initialize the dataset
columns = [
    'blockNumber', 'timestamp', 'transactionHash', 'from', 'to', 'value', 'gas', 'gasPrice',
    'nonce', 'status', 'contractAddress', 'contractName', 'functionName'
]
data = []

# Function to save data to CSV in the "data" subdirectory
def save_to_csv(filename):
    df = pd.DataFrame(data, columns=columns)
    file_path = os.path.join("data", filename)
    df.to_csv(file_path, index=False, na_rep='None')

# Function to handle new block events
def handle_new_blocks(block_hash):
    block_number = web3.eth.getBlock(block_hash).number
    block_data = fetch_block_data(block_number)
    if block_data:
        data.extend(block_data)
        logger.info(f"Recorded data for block {block_number} with {len(block_data)} transactions")
        save_to_csv('blockchain_txs_data.csv')

# Create a new block filter
block_filter = web3.eth.filter('latest')

# Poll for new blocks and handle them
try:
    while True:
        for block_hash in block_filter.get_new_entries():
            handle_new_blocks(block_hash)

except KeyboardInterrupt:
    logger.info("Script terminated by user.")
    save_to_csv('blockchain_txs_data_final.csv')
    logger.info("Final data saved to 'blockchain_txs_data_final.csv'")
