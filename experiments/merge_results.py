import pandas as pd
import os
import re

def merge_and_save_files(base_dir):
    consumer_dir = os.path.join(base_dir, 'consumer')
    provider_dir = os.path.join(base_dir, 'provider')
    output_dir = os.path.join(base_dir, 'merged')

    print(f"Consumer dir: {consumer_dir}")
    print(f"Provider dir: {provider_dir}")
    print(f"Output dir: {output_dir}")

    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    order = [
        'service_announced',
        'announce_received',
        'bid_offer_sent',
        'bid_offer_received',
        'winner_choosen',
        'winner_received',
        'deployment_start',
        'deployment_finished',
        'confirm_deployment_sent',
        'confirm_deployment_received',
        'establish_vxlan_connection_with_provider_start',
        'establish_vxlan_connection_with_provider_finished'
    ]

    # Pattern to match the files and extract the test number
    pattern = r"federation_events_(consumer|provider)_test_(\d+)\.csv"

    # Discover all consumer test files
    consumer_files = [f for f in os.listdir(consumer_dir) if re.search(pattern, f)]
    test_numbers = [re.search(pattern, f).group(2) for f in consumer_files]

    # print(f"Found consumer files: {consumer_files}")
    # print(f"Test numbers: {test_numbers}")

    # Process each test file
    for test_num in test_numbers:
        consumer_file = os.path.join(consumer_dir, f'federation_events_consumer_test_{test_num}.csv')
        provider_file = os.path.join(provider_dir, f'federation_events_provider_test_{test_num}.csv')

        print(f"Processing: {consumer_file} and {provider_file}")

        # Check if both files exist before proceeding
        if os.path.exists(consumer_file) and os.path.exists(provider_file):
            # Read the consumer and provider files
            consumer_df = pd.read_csv(consumer_file)
            provider_df = pd.read_csv(provider_file)

            # Merge the dataframes
            merged_df = pd.concat([consumer_df, provider_df])
            merged_df = merged_df.set_index('step').reindex(order).reset_index()

            # Save the merged dataframe
            output_file = os.path.join(output_dir, f'federation_events_merged_test_{test_num}.csv')
            merged_df.to_csv(output_file, index=False)

            print(f"Merged file saved to {output_file}")
        else:
            print(f"Files for test {test_num} do not exist in both directories.")

# Adjust this path to be your project's base directory
base_dir = './'

# Run the function
merge_and_save_files(base_dir)
