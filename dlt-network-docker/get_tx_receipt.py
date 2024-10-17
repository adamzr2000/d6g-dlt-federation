import argparse
from web3 import Web3, WebsocketProvider
from web3.middleware import geth_poa_middleware
from pprint import pprint

def get_tx_info(eth_node_url, tx_hash):
    try:
        # Configure Web3
        web3 = Web3(WebsocketProvider(eth_node_url))
        web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        # Check if connected to the Ethereum node
        if web3.isConnected():
            # print(f"Successfully connected to Ethereum node {eth_node_url}")
            
            # Get the transaction receipt
            receipt = web3.eth.get_transaction_receipt(tx_hash)

            if receipt:
                print(f"Transaction Receipt for {tx_hash}:")
                pprint(dict(receipt))

            else:
                print(f"Transaction receipt not found for hash {tx_hash}")

        else:
            print(f"Failed to connect to the Ethereum node {eth_node_url}")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get transaction information from an Ethereum node.")
    parser.add_argument("--eth_node_url", required=True, help="The URL of the Ethereum node.")
    parser.add_argument("--tx_hash", required=True, help="The transaction hash to retrieve the receipt for.")
    args = parser.parse_args()

    get_tx_info(args.eth_node_url, args.tx_hash)
